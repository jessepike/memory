"""High-level MemoryStorage orchestration API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from memory_core.config import load_config
from memory_core.models import (
    ClientProfile,
    EndSessionRequest,
    EndSessionResponse,
    EpisodicEvent,
    ForbiddenScopeError,
    GetEpisodesRequest,
    MemoryConfig,
    MemoryEntry,
    MemoryStatus,
    NamespaceRegistry,
    SearchResultItem,
    StatsResponse,
    UpdateMemoryRequest,
    WriteEpisodeRequest,
    WriteEpisodeResponse,
    WriteMemoryRequest,
    WriteMemoryResponse,
)
from memory_core.storage.db import IdempotencyConflictError, SQLiteMemoryDB
from memory_core.storage.episode_storage import EpisodeStorage
from memory_core.storage.vector_store import ChromaVectorStore
from memory_core.utils.consolidation import build_idempotency_key
from memory_core.utils.embeddings import EmbeddingMode, EmbeddingService


class ScopeForbidden(Exception):
    """Raised when caller requests out-of-scope memory access."""

    def __init__(self, error: ForbiddenScopeError) -> None:
        self.error = error
        super().__init__(error.model_dump_json())


@dataclass(frozen=True)
class ReviewCandidate:
    """Candidate requiring human review."""

    id: UUID
    content: str
    reason: str
    confidence: float | None = None
    similar_entries: list[dict[str, Any]] | None = None


class MemoryStorage:
    """Business-logic orchestrator for memory write/read/manage flows."""

    def __init__(
        self,
        config: MemoryConfig,
        *,
        db: SQLiteMemoryDB | None = None,
        vector_store: ChromaVectorStore | None = None,
        embeddings: EmbeddingService | None = None,
        episode_storage: EpisodeStorage | None = None,
    ) -> None:
        self.config = config
        self.db = db or SQLiteMemoryDB(config.paths.sqlite_db)
        self.vector_store = vector_store or ChromaVectorStore(config.paths.chroma_dir)
        self.embeddings = embeddings or EmbeddingService(config, mode=EmbeddingMode.RUNTIME)
        self._namespace_registry = config.namespaces
        self.episode_storage = episode_storage or EpisodeStorage(
            self.db, namespace_resolver=self._resolve_namespace,
        )
        self.last_reconcile_at: str | None = None

    @classmethod
    def from_config_path(cls, path: str = "config/memory_config.yaml") -> "MemoryStorage":
        """Create storage from YAML config path."""
        return cls(load_config(path))

    def initialize(self) -> None:
        """Initialize all backing systems and run embedding preflight."""
        self.db.initialize()
        self.vector_store.initialize()
        self.embeddings.preflight()

    def _resolve_namespace(self, raw: str | None) -> str:
        """Resolve a namespace alias to its canonical name via the registry."""
        if self._namespace_registry is not None:
            return self._namespace_registry.resolve(raw)
        if raw is None or raw.strip() == "":
            return "_unscoped"
        return raw

    def write_memory(self, request: WriteMemoryRequest | dict[str, Any]) -> WriteMemoryResponse:
        """Write memory with deterministic + semantic dedup."""
        req = request if isinstance(request, WriteMemoryRequest) else WriteMemoryRequest.model_validate(request)
        resolved_ns = self._resolve_namespace(req.namespace)
        if resolved_ns != req.namespace:
            req = req.model_copy(update={"namespace": resolved_ns})
        idempotency_key = build_idempotency_key(req.namespace, req.content)
        now = datetime.now(UTC)
        entry = MemoryEntry(
            content=req.content,
            memory_type=req.memory_type,
            namespace=req.namespace,
            writer_id=req.writer_id,
            writer_type=req.writer_type,
            source_project=req.source_project,
            confidence=req.confidence,
            idempotency_key=idempotency_key,
            status=MemoryStatus.STAGED,
            created_at=now,
            updated_at=now,
        )

        try:
            self.db.insert_staged(entry)
        except IdempotencyConflictError as exc:
            return WriteMemoryResponse(
                id=exc.existing_id or entry.id,
                action="skipped",
                similar_id=exc.existing_id,
            )

        try:
            embedding = self.embeddings.embed_text(entry.content)
            top_hit = self._find_semantic_duplicate(
                embedding=embedding,
                namespace=entry.namespace,
                new_id=entry.id,
            )
            if top_hit is not None and top_hit["similarity"] >= self.config.consolidation.similarity_threshold:
                self.db.delete_memory(entry.id)
                return WriteMemoryResponse(
                    id=entry.id,
                    action="skipped",
                    similar_id=top_hit["id"],
                    similarity=top_hit["similarity"],
                )

            self.vector_store.upsert_memory(
                memory_id=entry.id,
                content=entry.content,
                embedding=embedding,
                metadata=self._vector_metadata(entry),
            )
            self.db.set_status(entry.id, MemoryStatus.COMMITTED)
            return WriteMemoryResponse(id=entry.id, action="added")
        except Exception:
            self.db.set_status(entry.id, MemoryStatus.FAILED)
            raise

    def search_memories(
        self,
        *,
        query: str,
        caller_id: str = "unknown",
        namespace: str | None = None,
        memory_type: str | None = None,
        limit: int = 10,
    ) -> list[SearchResultItem]:
        """Semantic search over committed entries in allowed namespaces."""
        namespaces = self._resolve_scope(caller_id=caller_id, requested_namespace=namespace)
        allowed_ids = self.db.get_committed_ids_by_namespaces(namespaces)
        if not allowed_ids:
            return []

        where = {"memory_type": memory_type} if memory_type is not None else None
        query_embedding = self.embeddings.embed_text(query)
        rows = self.vector_store.query_similar(
            query_embedding=query_embedding,
            limit=limit,
            where=where,
            allowed_ids=allowed_ids,
        )

        results: list[SearchResultItem] = []
        for row in rows:
            metadata = row["metadata"] or {}
            results.append(
                SearchResultItem(
                    id=row["id"],
                    content=row["content"],
                    memory_type=metadata.get("memory_type", "observation"),
                    namespace=metadata.get("namespace", "global"),
                    similarity=max(0.0, min(1.0, 1.0 - row["distance"])),
                    writer_id=metadata.get("writer_id", "unknown"),
                    created_at=metadata.get("created_at", datetime.now(UTC).isoformat()),
                )
            )
        return results

    def get_memory(self, memory_id: UUID | str, *, caller_id: str = "unknown") -> MemoryEntry:
        """Fetch a single memory entry if caller is authorized."""
        row = self.db.get_memory(memory_id)
        if row is None:
            raise KeyError(f"Memory not found: {memory_id}")
        self._authorize_row_access(caller_id=caller_id, row=row)
        return row

    def get_recent(
        self,
        *,
        caller_id: str = "unknown",
        namespace: str | None = None,
        memory_type: str | None = None,
        limit: int = 20,
        days: int = 7,
    ) -> list[MemoryEntry]:
        """Return committed recent memories in allowed scope."""
        namespaces = self._resolve_scope(caller_id=caller_id, requested_namespace=namespace)
        rows = self.db.list_memories(
            statuses=[MemoryStatus.COMMITTED],
            namespaces=namespaces,
            memory_type=memory_type,
            limit=max(limit * 3, limit),
        )
        cutoff = datetime.now(UTC) - timedelta(days=days)
        filtered = [row for row in rows if row.created_at >= cutoff]
        return filtered[:limit]

    def get_session_context(
        self,
        *,
        caller_id: str = "unknown",
        namespace: str | None = None,
        query: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Return `{last_handoff, recent, relevant}` session context payload."""
        recent = self.get_recent(caller_id=caller_id, namespace=namespace, limit=limit)
        relevant: list[SearchResultItem] = []
        if query:
            relevant = self.search_memories(
                query=query,
                caller_id=caller_id,
                namespace=namespace,
                limit=limit,
            )
        namespaces = self._resolve_scope(caller_id=caller_id, requested_namespace=namespace)
        last_handoff = self.episode_storage.get_last_handoff(namespaces=namespaces)
        return {"last_handoff": last_handoff, "recent": recent, "relevant": relevant}

    def write_episode(
        self,
        request: WriteEpisodeRequest | dict[str, Any],
    ) -> WriteEpisodeResponse:
        """Write an episode to the episodic log."""
        return self.episode_storage.write_episode(request)

    def get_episodes(
        self,
        request: GetEpisodesRequest | dict[str, Any],
        *,
        caller_id: str = "unknown",
        namespace: str | None = None,
    ) -> list[EpisodicEvent]:
        """Query episodes with namespace-based access control."""
        allowed_namespaces = self._resolve_scope(caller_id=caller_id, requested_namespace=namespace)
        return self.episode_storage.get_episodes(request, allowed_namespaces=allowed_namespaces)

    def end_session(
        self,
        request: EndSessionRequest | dict[str, Any],
    ) -> EndSessionResponse:
        """Close a session with a structured handoff payload."""
        return self.episode_storage.end_session(request)

    def verify_chain(self, session_id: str) -> dict[str, Any]:
        """Walk the hash chain for a session and report integrity."""
        return self.episode_storage.verify_chain(session_id)

    def update_memory(
        self,
        request: UpdateMemoryRequest | dict[str, Any],
        *,
        caller_id: str = "unknown",
    ) -> dict[str, Any]:
        """Update memory content and/or metadata with Chroma-first ordering."""
        req = request if isinstance(request, UpdateMemoryRequest) else UpdateMemoryRequest.model_validate(request)
        row = self.get_memory(req.id, caller_id=caller_id)
        self._enforce_id_tool_namespace_guard(
            caller_id=caller_id,
            row_namespace=row.namespace,
            requested_namespace=req.namespace,
            memory_id=row.id,
        )

        updates = req.model_dump(exclude_none=True)
        updates.pop("id", None)
        if not updates:
            return {"id": row.id, "updated_fields": []}

        changed_fields = sorted(updates.keys())
        new_content = updates.get("content")
        if new_content is not None:
            content = str(new_content)
            embedding = self.embeddings.embed_text(content)
            metadata = self._vector_metadata(row, override=updates)
            self.vector_store.upsert_memory(
                memory_id=row.id,
                content=content,
                embedding=embedding,
                metadata=metadata,
            )
        else:
            metadata = self._vector_metadata(row, override=updates)
            self.vector_store.update_metadata(memory_id=row.id, metadata=metadata)

        self.db.update_memory(row.id, **updates)
        return {"id": row.id, "updated_fields": changed_fields}

    def archive_memory(
        self,
        memory_id: UUID | str,
        *,
        caller_id: str = "unknown",
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Archive a committed memory with Chroma-first mutation order."""
        row = self.get_memory(memory_id, caller_id=caller_id)
        self._enforce_id_tool_namespace_guard(
            caller_id=caller_id,
            row_namespace=row.namespace,
            requested_namespace=namespace,
            memory_id=row.id,
        )
        if row.status is not MemoryStatus.COMMITTED:
            raise ValueError(f"Only committed rows can be archived (got: {row.status.value})")
        self.vector_store.delete_memory(row.id)
        self.db.archive_memory(row.id)
        return {"id": row.id, "archived": True}

    def review_candidates(
        self,
        *,
        caller_id: str = "unknown",
        namespace: str | None = None,
        limit: int = 20,
    ) -> list[ReviewCandidate]:
        """Return low-confidence and high-similarity review candidates."""
        namespaces = self._resolve_scope(caller_id=caller_id, requested_namespace=namespace)
        committed = self.db.list_memories(
            statuses=[MemoryStatus.COMMITTED],
            namespaces=namespaces,
            limit=5_000,
        )
        candidates: list[ReviewCandidate] = []
        seen: set[UUID] = set()
        for row in committed:
            if row.confidence < 0.7 and row.id not in seen:
                seen.add(row.id)
                candidates.append(
                    ReviewCandidate(
                        id=row.id,
                        content=row.content,
                        reason="low_confidence",
                        confidence=row.confidence,
                    )
                )

        for row in committed:
            if len(candidates) >= limit:
                break
            if row.id in seen:
                continue
            embedding = self.embeddings.embed_text(row.content)
            hits = self.vector_store.query_similar(
                query_embedding=embedding,
                limit=3,
                allowed_ids=[item.id for item in committed if item.id != row.id],
            )
            similar_entries: list[dict[str, Any]] = []
            for hit in hits:
                similarity = max(0.0, min(1.0, 1.0 - hit["distance"]))
                if similarity >= 0.85:
                    similar_entries.append(
                        {
                            "id": hit["id"],
                            "content": hit["content"],
                            "similarity": similarity,
                        }
                    )
            if similar_entries:
                seen.add(row.id)
                candidates.append(
                    ReviewCandidate(
                        id=row.id,
                        content=row.content,
                        reason="high_similarity",
                        similar_entries=similar_entries,
                    )
                )
        return candidates[:limit]

    def get_stats(self, *, caller_id: str = "unknown", namespace: str | None = None) -> StatsResponse:
        """Return committed-only stats with drift counters."""
        namespaces = self._resolve_scope(caller_id=caller_id, requested_namespace=namespace)
        stats = self.db.stats_committed(namespaces=namespaces)
        drift = self._drift_counts()
        return StatsResponse(
            total=stats.total,
            by_type=stats.by_type,
            by_namespace=stats.by_namespace,
            recent_7d=stats.recent_7d,
            recent_30d=stats.recent_30d,
            drift=drift,
        )

    def list_failed_memories(self, *, limit: int = 100, older_than_days: int | None = None) -> list[MemoryEntry]:
        """Maintenance API for failed row inspection."""
        return self.db.list_failed_memories(limit=limit, older_than_days=older_than_days)

    def retry_failed_memory(self, memory_id: UUID | str) -> dict[str, Any]:
        """Retry vector write for a failed row and transition to committed."""
        row = self.db.get_memory(memory_id)
        if row is None:
            raise KeyError(f"Memory not found: {memory_id}")
        if row.status is not MemoryStatus.FAILED:
            raise ValueError(f"Only failed rows can be retried (got: {row.status.value})")

        embedding = self.embeddings.embed_text(row.content)
        self.vector_store.upsert_memory(
            memory_id=row.id,
            content=row.content,
            embedding=embedding,
            metadata=self._vector_metadata(row),
        )
        self.db.set_status(row.id, MemoryStatus.COMMITTED)
        return {"id": row.id, "status": "committed"}

    def archive_failed_memory(self, memory_id: UUID | str) -> dict[str, Any]:
        """Archive an unrecoverable failed row."""
        row = self.db.get_memory(memory_id)
        if row is None:
            raise KeyError(f"Memory not found: {memory_id}")
        if row.status is not MemoryStatus.FAILED:
            raise ValueError(f"Only failed rows can be archived (got: {row.status.value})")
        self.db.set_status(row.id, MemoryStatus.ARCHIVED)
        return {"id": row.id, "status": "archived"}

    def reconcile_dual_store(self) -> dict[str, Any]:
        """Repair SQLite/Chroma divergence based on SQLite as source of truth."""
        committed_rows = self.db.list_memories(statuses=[MemoryStatus.COMMITTED], limit=100_000)
        archived_rows = self.db.list_memories(statuses=[MemoryStatus.ARCHIVED], limit=100_000)
        all_sqlite_ids = set(
            self.db.list_ids_by_statuses(
                [MemoryStatus.STAGED, MemoryStatus.COMMITTED, MemoryStatus.FAILED, MemoryStatus.ARCHIVED]
            )
        )
        chroma_ids = set(self.vector_store.list_all_ids())

        repaired_committed_missing = 0
        repaired_archived_present = 0
        removed_orphans = 0

        for row in committed_rows:
            if row.id not in chroma_ids:
                embedding = self.embeddings.embed_text(row.content)
                self.vector_store.upsert_memory(
                    memory_id=row.id,
                    content=row.content,
                    embedding=embedding,
                    metadata=self._vector_metadata(row),
                )
                repaired_committed_missing += 1

        for row in archived_rows:
            if row.id in chroma_ids:
                self.vector_store.delete_memory(row.id)
                repaired_archived_present += 1

        orphan_ids = chroma_ids.difference(all_sqlite_ids)
        for orphan_id in orphan_ids:
            self.vector_store.delete_memory(orphan_id)
            removed_orphans += 1

        self.last_reconcile_at = datetime.now(UTC).isoformat()
        return {
            "sqlite_committed_missing_chroma": repaired_committed_missing,
            "sqlite_archived_present_chroma": repaired_archived_present,
            "chroma_orphans": removed_orphans,
            "last_reconcile_at": self.last_reconcile_at,
        }

    def _find_semantic_duplicate(
        self,
        *,
        embedding: list[float],
        namespace: str,
        new_id: UUID,
    ) -> dict[str, Any] | None:
        dedup_namespaces = [namespace]
        if namespace != "private" and namespace != "global":
            dedup_namespaces.append("global")
        if namespace == "global":
            dedup_namespaces = ["global"]

        candidate_ids = self.db.get_committed_ids_by_namespaces(dedup_namespaces)
        if not candidate_ids:
            return None
        hits = self.vector_store.query_similar(
            query_embedding=embedding,
            limit=5,
            allowed_ids=candidate_ids,
        )
        for hit in hits:
            if hit["id"] == new_id:
                continue
            similarity = max(0.0, min(1.0, 1.0 - float(hit["distance"])))
            return {"id": hit["id"], "similarity": similarity}
        return None

    def _vector_metadata(self, entry: MemoryEntry, override: dict[str, Any] | None = None) -> dict[str, Any]:
        values = {
            "memory_type": entry.memory_type.value,
            "namespace": entry.namespace,
            "writer_type": entry.writer_type.value,
            "writer_id": entry.writer_id,
            "confidence": entry.confidence,
            "created_at": entry.created_at.isoformat(),
        }
        if override:
            for key, value in override.items():
                if key == "memory_type" and value is not None:
                    values[key] = value.value if hasattr(value, "value") else str(value)
                elif key == "writer_type" and value is not None:
                    values[key] = value.value if hasattr(value, "value") else str(value)
                elif key in values and value is not None:
                    values[key] = value
        return values

    def _resolve_scope(self, *, caller_id: str, requested_namespace: str | None) -> list[str]:
        profile = self._get_client_profile(caller_id)
        allowed = set(profile.allowed_namespaces)
        allowed.add("global")
        if profile.can_access_private:
            allowed.add("private")

        if requested_namespace is not None:
            requested = requested_namespace.lower() if requested_namespace in {"global", "private"} else requested_namespace
            if requested == "private":
                if not profile.can_access_private:
                    raise self._forbidden(caller_id=caller_id, namespace="private")
                namespaces = {"private"}
            else:
                namespaces = {requested, "global"}
        else:
            namespaces = set(allowed)
            if not profile.can_access_private:
                namespaces.discard("private")

        effective = sorted(namespaces.intersection(allowed))
        if not effective:
            raise self._forbidden(caller_id=caller_id, namespace=requested_namespace)
        return effective

    def _authorize_row_access(self, *, caller_id: str, row: MemoryEntry) -> None:
        profile = self._get_client_profile(caller_id)
        if row.namespace == "private" and not profile.can_access_private:
            raise self._forbidden(caller_id=caller_id, namespace=row.namespace, memory_id=row.id)
        if row.namespace not in set(profile.allowed_namespaces).union({"global"}):
            raise self._forbidden(caller_id=caller_id, namespace=row.namespace, memory_id=row.id)

    def _get_client_profile(self, caller_id: str) -> ClientProfile:
        profile = self.config.client_profiles.get(caller_id)
        if profile is not None:
            return profile
        return ClientProfile(allowed_namespaces=[caller_id, "global"], can_cross_scope=False)

    def _forbidden(
        self,
        *,
        caller_id: str,
        namespace: str | None,
        memory_id: UUID | None = None,
    ) -> ScopeForbidden:
        return ScopeForbidden(
            ForbiddenScopeError(
                id=memory_id,
                namespace=namespace,
                caller_id=caller_id,
            )
        )

    def _enforce_id_tool_namespace_guard(
        self,
        *,
        caller_id: str,
        row_namespace: str,
        requested_namespace: str | None,
        memory_id: UUID,
    ) -> None:
        """Require namespace-match on ID tools for non-privileged callers."""
        profile = self._get_client_profile(caller_id)
        if profile.can_cross_scope:
            return
        if requested_namespace is None:
            raise self._forbidden(caller_id=caller_id, namespace=row_namespace, memory_id=memory_id)
        if requested_namespace != row_namespace:
            raise self._forbidden(caller_id=caller_id, namespace=requested_namespace, memory_id=memory_id)

    def _drift_counts(self) -> dict[str, Any]:
        committed_ids = set(self.db.list_ids_by_statuses([MemoryStatus.COMMITTED]))
        archived_ids = set(self.db.list_ids_by_statuses([MemoryStatus.ARCHIVED]))
        chroma_ids = set(self.vector_store.list_all_ids())
        return {
            "sqlite_committed_missing_chroma": len(committed_ids.difference(chroma_ids)),
            "sqlite_archived_present_chroma": len(archived_ids.intersection(chroma_ids)),
            "chroma_orphans": len(chroma_ids.difference(committed_ids.union(archived_ids))),
            "last_reconcile_at": self.last_reconcile_at,
        }
