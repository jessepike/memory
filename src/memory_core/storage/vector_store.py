"""Chroma vector store wrapper utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID


class VectorStoreUnavailableError(RuntimeError):
    """Raised when Chroma cannot be imported or initialized."""


class ChromaVectorStore:
    """Thin wrapper for Chroma collection operations."""

    def __init__(
        self,
        persist_dir: str | Path,
        *,
        collection_name: str = "memories",
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self._client: Any | None = None
        self._collection: Any | None = None

    def initialize(self) -> None:
        """Initialize persistent client and collection."""
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        chromadb = _import_chromadb()
        try:
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:  # pragma: no cover - dependency-specific
            raise VectorStoreUnavailableError("Failed to initialize Chroma vector store") from exc

    def upsert_memory(
        self,
        *,
        memory_id: UUID | str,
        content: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> None:
        """Insert or update vector/document/metadata for a memory."""
        collection = self._require_collection()
        collection.upsert(
            ids=[str(memory_id)],
            documents=[content],
            embeddings=[embedding],
            metadatas=[metadata],
        )

    def update_metadata(self, *, memory_id: UUID | str, metadata: dict[str, Any]) -> None:
        """Update metadata fields only (no re-embedding)."""
        collection = self._require_collection()
        collection.update(ids=[str(memory_id)], metadatas=[metadata])

    def delete_memory(self, memory_id: UUID | str) -> None:
        """Delete a memory from vector index."""
        collection = self._require_collection()
        collection.delete(ids=[str(memory_id)])

    def has_id(self, memory_id: UUID | str) -> bool:
        """Check whether a vector exists for the ID."""
        collection = self._require_collection()
        result = collection.get(ids=[str(memory_id)], include=[])
        return bool(result.get("ids"))

    def list_all_ids(self) -> list[UUID]:
        """Return all known Chroma IDs."""
        collection = self._require_collection()
        result = collection.get(include=[])
        ids = result.get("ids", [])
        return [UUID(memory_id) for memory_id in ids]

    def query_similar(
        self,
        *,
        query_embedding: list[float],
        limit: int = 10,
        where: dict[str, Any] | None = None,
        allowed_ids: list[UUID | str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query nearest vectors. Returns id/document/metadata/distance."""
        collection = self._require_collection()
        query_args: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": limit,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_args["where"] = where
        allowed_id_set = {str(memory_id) for memory_id in allowed_ids} if allowed_ids is not None else None
        raw = collection.query(**query_args)

        ids = raw.get("ids", [[]])[0]
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        rows: list[dict[str, Any]] = []
        for idx, memory_id in enumerate(ids):
            if allowed_id_set is not None and memory_id not in allowed_id_set:
                continue
            rows.append(
                {
                    "id": UUID(memory_id),
                    "content": documents[idx] if idx < len(documents) else "",
                    "metadata": metadatas[idx] if idx < len(metadatas) else {},
                    "distance": float(distances[idx]) if idx < len(distances) else 1.0,
                }
            )
        return rows

    def _require_collection(self) -> Any:
        if self._collection is None:
            raise VectorStoreUnavailableError("Vector store not initialized")
        return self._collection


def _import_chromadb() -> Any:
    try:
        import chromadb  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - import path is environment-specific
        raise VectorStoreUnavailableError("chromadb is required but not installed") from exc
    return chromadb
