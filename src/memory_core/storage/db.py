"""SQLite persistence layer for memory metadata and lifecycle state."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from memory_core.models import EpisodicEvent, MemoryEntry, MemoryStatus, SessionRecord, memory_entry_from_db_row
from memory_core.utils.episode import compute_event_hash


class MemoryNotFoundError(Exception):
    """Raised when a memory row cannot be found."""


class IdempotencyConflictError(Exception):
    """Raised when staged insert collides with an active idempotency key."""

    def __init__(self, existing_id: UUID | None) -> None:
        self.existing_id = existing_id
        super().__init__("Active idempotency key already exists")


@dataclass(frozen=True)
class MemoryStats:
    """Committed-memory stats summary."""

    total: int
    by_type: dict[str, int]
    by_namespace: dict[str, int]
    recent_7d: int
    recent_30d: int


class SQLiteMemoryDB:
    """SQLite access layer used by MemoryStorage."""

    def __init__(self, db_path: str | Path, schema_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path)
        default_schema = Path(__file__).with_name("schema.sql")
        self.schema_path = Path(schema_path) if schema_path is not None else default_schema

    def initialize(self) -> None:
        """Create DB file, apply pragmas, and load schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        schema_sql = self.schema_path.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema_sql)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA temp_store=MEMORY;")
            # Migration: add source_ref to memories if not present (v1.1 Phase 3)
            existing = {row[1] for row in conn.execute("PRAGMA table_info(memories);")}
            if "source_ref" not in existing:
                conn.execute("ALTER TABLE memories ADD COLUMN source_ref TEXT;")

    @contextmanager
    def begin_immediate(self) -> Iterator[sqlite3.Connection]:
        """Open a write transaction for deterministic staged reservations."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def insert_staged(self, entry: MemoryEntry) -> None:
        """Insert a staged row, raising on active idempotency collisions."""
        payload = entry.model_dump(mode="json")
        sql = """
        INSERT INTO memories (
            id, content, memory_type, namespace, writer_id, writer_type,
            source_project, source_ref, idempotency_key, confidence, status, created_at, updated_at
        ) VALUES (
            :id, :content, :memory_type, :namespace, :writer_id, :writer_type,
            :source_project, :source_ref, :idempotency_key, :confidence, :status, :created_at, :updated_at
        );
        """
        try:
            with self.begin_immediate() as conn:
                conn.execute(sql, payload)
        except sqlite3.IntegrityError as exc:
            if "idx_memories_idempotency_active" in str(exc) or "idempotency_key" in str(exc):
                existing_id = self.get_active_id_by_idempotency_key(entry.idempotency_key)
                raise IdempotencyConflictError(existing_id) from exc
            raise

    def get_active_id_by_idempotency_key(self, idempotency_key: str) -> UUID | None:
        """Return active row ID for an idempotency key."""
        sql = """
        SELECT id
        FROM memories
        WHERE idempotency_key = ?
          AND status IN (?, ?)
        LIMIT 1;
        """
        with self._connect() as conn:
            row = conn.execute(
                sql, (idempotency_key, MemoryStatus.STAGED.value, MemoryStatus.COMMITTED.value)
            ).fetchone()
        return UUID(row["id"]) if row else None

    def get_memory(self, memory_id: UUID | str) -> MemoryEntry | None:
        """Fetch one memory by ID."""
        sql = "SELECT * FROM memories WHERE id = ? LIMIT 1;"
        with self._connect() as conn:
            row = conn.execute(sql, (str(memory_id),)).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def list_memories(
        self,
        *,
        statuses: list[MemoryStatus] | None = None,
        namespaces: list[str] | None = None,
        memory_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """List memories with optional lifecycle and scope filters."""
        clauses: list[str] = []
        params: list[Any] = []

        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(status.value for status in statuses)

        if namespaces:
            placeholders = ", ".join("?" for _ in namespaces)
            clauses.append(f"namespace IN ({placeholders})")
            params.extend(namespaces)

        if memory_type is not None:
            clauses.append("memory_type = ?")
            params.append(memory_type)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
        SELECT * FROM memories
        {where}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?;
        """
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def update_memory(self, memory_id: UUID | str, **updates: Any) -> MemoryEntry:
        """Update mutable memory fields and return the fresh row."""
        allowed = {
            "content",
            "memory_type",
            "namespace",
            "writer_id",
            "writer_type",
            "source_project",
            "confidence",
            "status",
            "idempotency_key",
        }
        invalid = set(updates).difference(allowed)
        if invalid:
            raise ValueError(f"Unsupported update fields: {sorted(invalid)}")
        if not updates:
            existing = self.get_memory(memory_id)
            if existing is None:
                raise MemoryNotFoundError(f"Memory not found: {memory_id}")
            return existing

        updates["updated_at"] = datetime.now(UTC).isoformat()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [str(memory_id)]
        sql = f"UPDATE memories SET {assignments} WHERE id = ?;"

        with self.begin_immediate() as conn:
            result = conn.execute(sql, params)
            if result.rowcount == 0:
                raise MemoryNotFoundError(f"Memory not found: {memory_id}")

        updated = self.get_memory(memory_id)
        if updated is None:
            raise MemoryNotFoundError(f"Memory not found: {memory_id}")
        return updated

    def set_status(self, memory_id: UUID | str, status: MemoryStatus) -> MemoryEntry:
        """Transition a row status."""
        return self.update_memory(memory_id, status=status.value)

    def archive_memory(self, memory_id: UUID | str) -> MemoryEntry:
        """Soft-delete a committed row by marking it archived."""
        return self.set_status(memory_id, MemoryStatus.ARCHIVED)

    def delete_memory(self, memory_id: UUID | str) -> bool:
        """Hard-delete a row. Intended for internal maintenance only."""
        sql = "DELETE FROM memories WHERE id = ?;"
        with self.begin_immediate() as conn:
            result = conn.execute(sql, (str(memory_id),))
        return result.rowcount > 0

    def get_committed_ids_by_namespaces(self, namespaces: list[str]) -> list[UUID]:
        """Return committed IDs filtered by namespaces."""
        if not namespaces:
            return []
        placeholders = ", ".join("?" for _ in namespaces)
        sql = f"""
        SELECT id FROM memories
        WHERE status = ?
          AND namespace IN ({placeholders});
        """
        params = [MemoryStatus.COMMITTED.value, *namespaces]
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [UUID(row["id"]) for row in rows]

    def list_failed_memories(self, *, limit: int = 100, older_than_days: int | None = None) -> list[MemoryEntry]:
        """List failed rows for operator remediation."""
        clauses = ["status = ?"]
        params: list[Any] = [MemoryStatus.FAILED.value]
        if older_than_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
            clauses.append("updated_at <= ?")
            params.append(cutoff.isoformat())
        where = " AND ".join(clauses)
        sql = f"""
        SELECT * FROM memories
        WHERE {where}
        ORDER BY updated_at ASC
        LIMIT ?;
        """
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def list_ids_by_statuses(self, statuses: list[MemoryStatus]) -> list[UUID]:
        """Return IDs matching one or more statuses."""
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        sql = f"SELECT id FROM memories WHERE status IN ({placeholders});"
        with self._connect() as conn:
            rows = conn.execute(sql, [status.value for status in statuses]).fetchall()
        return [UUID(row["id"]) for row in rows]

    def stats_committed(self, namespaces: list[str] | None = None) -> MemoryStats:
        """Compute committed-only stats for normal read surfaces."""
        where_parts = ["status = ?"]
        params: list[Any] = [MemoryStatus.COMMITTED.value]
        if namespaces:
            placeholders = ", ".join("?" for _ in namespaces)
            where_parts.append(f"namespace IN ({placeholders})")
            params.extend(namespaces)
        where_clause = " AND ".join(where_parts)

        total_sql = f"SELECT COUNT(*) AS total FROM memories WHERE {where_clause};"
        by_type_sql = f"""
        SELECT memory_type, COUNT(*) AS count
        FROM memories
        WHERE {where_clause}
        GROUP BY memory_type;
        """
        by_namespace_sql = f"""
        SELECT namespace, COUNT(*) AS count
        FROM memories
        WHERE {where_clause}
        GROUP BY namespace;
        """
        recent_7d_sql = f"""
        SELECT COUNT(*) AS count
        FROM memories
        WHERE {where_clause} AND created_at >= ?;
        """
        recent_30d_sql = f"""
        SELECT COUNT(*) AS count
        FROM memories
        WHERE {where_clause} AND created_at >= ?;
        """

        now = datetime.now(UTC)
        recent_7d_cutoff = (now - timedelta(days=7)).isoformat()
        recent_30d_cutoff = (now - timedelta(days=30)).isoformat()

        with self._connect() as conn:
            total = int(conn.execute(total_sql, params).fetchone()["total"])
            by_type_rows = conn.execute(by_type_sql, params).fetchall()
            by_namespace_rows = conn.execute(by_namespace_sql, params).fetchall()
            recent_7d = int(conn.execute(recent_7d_sql, [*params, recent_7d_cutoff]).fetchone()["count"])
            recent_30d = int(
                conn.execute(recent_30d_sql, [*params, recent_30d_cutoff]).fetchone()["count"]
            )

        by_type = {row["memory_type"]: int(row["count"]) for row in by_type_rows}
        by_namespace = {row["namespace"]: int(row["count"]) for row in by_namespace_rows}
        return MemoryStats(
            total=total,
            by_type=by_type,
            by_namespace=by_namespace,
            recent_7d=recent_7d,
            recent_30d=recent_30d,
        )

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        data = dict(row)
        return memory_entry_from_db_row(data)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    # ------------------------------------------------------------------
    # Episode / session methods
    # ------------------------------------------------------------------

    def get_or_create_session(self, session_id: str, creator: str, namespace: str, **kwargs: Any) -> SessionRecord:
        """Return existing session or insert a new one.

        Extra kwargs (client, project, metadata) are passed on insert only.
        """
        existing = self.get_session(session_id)
        if existing is not None:
            return existing
        now = datetime.now(UTC).isoformat()
        record = SessionRecord(
            session_id=session_id,
            start_ts=now,
            creator=creator,
            namespace=namespace,
            client=kwargs.get("client"),
            project=kwargs.get("project"),
            metadata=kwargs.get("metadata"),
        )
        sql = """
        INSERT INTO sessions (
            session_id, start_ts, creator, namespace, client, project,
            finalized, last_sequence, chain_head, metadata, schema_version
        ) VALUES (
            :session_id, :start_ts, :creator, :namespace, :client, :project,
            0, 0, NULL, :metadata_json, 1
        );
        """
        metadata_json = json.dumps(record.metadata) if record.metadata else None
        try:
            with self.begin_immediate() as conn:
                conn.execute(sql, {
                    "session_id": record.session_id,
                    "start_ts": record.start_ts,
                    "creator": record.creator,
                    "namespace": record.namespace,
                    "client": record.client,
                    "project": record.project,
                    "metadata_json": metadata_json,
                })
        except sqlite3.IntegrityError:
            # Another thread/process inserted the session between our read and write.
            existing = self.get_session(record.session_id)
            if existing is not None:
                return existing
            raise
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        """Fetch one session by ID."""
        sql = "SELECT * FROM sessions WHERE session_id = ? LIMIT 1;"
        with self._connect() as conn:
            row = conn.execute(sql, (session_id,)).fetchone()
        return self._row_to_session(row) if row else None

    def insert_episode_atomic(self, episode_fields: dict[str, Any]) -> EpisodicEvent:
        """Atomically append an episode and update the session chain.

        Within a single BEGIN IMMEDIATE transaction:
        1. Read session.last_sequence and session.chain_head
        2. Compute new sequence and event_hash
        3. INSERT episode
        4. UPDATE sessions chain head and sequence counter

        Args:
            episode_fields: Dict with id, session_id, timestamp, event_type,
                severity, agent_id, client, project, namespace, content,
                metadata, source_ref, schema_version. sequence and
                event_hash/previous_hash are computed here.

        Returns:
            Fully populated EpisodicEvent with computed hash fields.
        """
        metadata_json = (
            json.dumps(episode_fields.get("metadata")) if episode_fields.get("metadata") else None
        )

        with self.begin_immediate() as conn:
            # Read current chain state
            sess_row = conn.execute(
                "SELECT last_sequence, chain_head FROM sessions WHERE session_id = ?;",
                (episode_fields["session_id"],),
            ).fetchone()
            if sess_row is None:
                raise ValueError(f"Session not found: {episode_fields['session_id']}")

            prev_hash: str | None = sess_row["chain_head"]
            new_sequence = sess_row["last_sequence"] + 1

            # Build event dict for hashing
            event_for_hash = {
                "id": episode_fields["id"],
                "session_id": episode_fields["session_id"],
                "sequence": new_sequence,
                "timestamp": episode_fields["timestamp"],
                "event_type": episode_fields["event_type"],
                "agent_id": episode_fields["agent_id"],
                "content": episode_fields["content"],
            }
            event_hash = compute_event_hash(event_for_hash, prev_hash)

            # INSERT episode
            conn.execute(
                """
                INSERT INTO episodes (
                    id, session_id, sequence, timestamp, event_type, severity,
                    agent_id, client, project, namespace, content, metadata,
                    source_ref, event_hash, previous_hash, schema_version
                ) VALUES (
                    :id, :session_id, :sequence, :timestamp, :event_type, :severity,
                    :agent_id, :client, :project, :namespace, :content, :metadata,
                    :source_ref, :event_hash, :previous_hash, :schema_version
                );
                """,
                {
                    "id": episode_fields["id"],
                    "session_id": episode_fields["session_id"],
                    "sequence": new_sequence,
                    "timestamp": episode_fields["timestamp"],
                    "event_type": episode_fields["event_type"],
                    "severity": episode_fields.get("severity", "info"),
                    "agent_id": episode_fields["agent_id"],
                    "client": episode_fields.get("client"),
                    "project": episode_fields.get("project"),
                    "namespace": episode_fields.get("namespace", "global"),
                    "content": episode_fields["content"],
                    "metadata": metadata_json,
                    "source_ref": episode_fields.get("source_ref"),
                    "event_hash": event_hash,
                    "previous_hash": prev_hash,
                    "schema_version": episode_fields.get("schema_version", 1),
                },
            )

            # UPDATE sessions chain head and counter
            conn.execute(
                "UPDATE sessions SET last_sequence = ?, chain_head = ? WHERE session_id = ?;",
                (new_sequence, event_hash, episode_fields["session_id"]),
            )

        return EpisodicEvent(
            id=episode_fields["id"],
            session_id=episode_fields["session_id"],
            sequence=new_sequence,
            timestamp=episode_fields["timestamp"],
            event_type=episode_fields["event_type"],
            severity=episode_fields.get("severity", "info"),
            agent_id=episode_fields["agent_id"],
            client=episode_fields.get("client"),
            project=episode_fields.get("project"),
            namespace=episode_fields.get("namespace", "global"),
            content=episode_fields["content"],
            metadata=episode_fields.get("metadata"),
            source_ref=episode_fields.get("source_ref"),
            event_hash=event_hash,
            previous_hash=prev_hash,
            schema_version=episode_fields.get("schema_version", 1),
        )

    def finalize_session(self, session_id: str) -> None:
        """Mark a session as finalized (ended)."""
        now = datetime.now(UTC).isoformat()
        with self.begin_immediate() as conn:
            conn.execute(
                "UPDATE sessions SET finalized = 1, end_ts = ? WHERE session_id = ?;",
                (now, session_id),
            )

    def get_episodes(
        self,
        *,
        session_id: str | None = None,
        project: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        namespace: str | None = None,
        namespaces: list[str] | None = None,
        limit: int = 50,
    ) -> list[EpisodicEvent]:
        """Query episodes with optional filters, chronological order."""
        clauses: list[str] = []
        params: list[Any] = []

        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if project is not None:
            clauses.append("project = ?")
            params.append(project)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(since)
        if namespace is not None:
            clauses.append("namespace = ?")
            params.append(namespace)
        elif namespaces:
            placeholders = ", ".join("?" for _ in namespaces)
            clauses.append(f"namespace IN ({placeholders})")
            params.extend(namespaces)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
        SELECT * FROM episodes
        {where}
        ORDER BY timestamp ASC, sequence ASC
        LIMIT ?;
        """
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_episode(row) for row in rows]

    def get_last_session_end(self, *, namespaces: list[str] | None = None) -> EpisodicEvent | None:
        """Return the most recent session_end episode for a namespace set."""
        clauses = ["event_type = 'session_end'"]
        params: list[Any] = []
        if namespaces:
            placeholders = ", ".join("?" for _ in namespaces)
            clauses.append(f"namespace IN ({placeholders})")
            params.extend(namespaces)
        where = " AND ".join(clauses)
        sql = f"""
        SELECT * FROM episodes
        WHERE {where}
        ORDER BY timestamp DESC
        LIMIT 1;
        """
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._row_to_episode(row) if row else None

    def get_episode_stats(self) -> dict[str, Any]:
        """Return aggregate session/episode counts for usage reporting."""
        sql_sessions = "SELECT COUNT(*) AS total, SUM(finalized) AS finalized FROM sessions;"
        sql_episodes = "SELECT COUNT(*) AS total FROM episodes;"
        sql_session_ends = "SELECT COUNT(*) AS total FROM episodes WHERE event_type = 'session_end';"
        sql_last_ts = "SELECT MAX(start_ts) AS last_ts FROM sessions;"

        with self._connect() as conn:
            sess_row = conn.execute(sql_sessions).fetchone()
            ep_row = conn.execute(sql_episodes).fetchone()
            se_row = conn.execute(sql_session_ends).fetchone()
            last_row = conn.execute(sql_last_ts).fetchone()

        return {
            "total_sessions": int(sess_row["total"] or 0),
            "finalized_sessions": int(sess_row["finalized"] or 0),
            "total_episodes": int(ep_row["total"] or 0),
            "session_end_count": int(se_row["total"] or 0),
            "last_session_ts": last_row["last_ts"] if last_row else None,
        }

    def _row_to_session(self, row: sqlite3.Row) -> SessionRecord:
        data = dict(row)
        # Deserialize JSON metadata field
        if data.get("metadata") and isinstance(data["metadata"], str):
            data["metadata"] = json.loads(data["metadata"])
        # SQLite stores finalized as int
        data["finalized"] = bool(data.get("finalized", 0))
        return SessionRecord.model_validate(data)

    def _row_to_episode(self, row: sqlite3.Row) -> EpisodicEvent:
        data = dict(row)
        if data.get("metadata") and isinstance(data["metadata"], str):
            data["metadata"] = json.loads(data["metadata"])
        return EpisodicEvent.model_validate(data)
