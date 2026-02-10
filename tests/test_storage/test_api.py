"""MemoryStorage orchestration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from memory_core.models import ClientProfile, MemoryConfig, MemoryStatus, UpdateMemoryRequest
from memory_core.storage.api import MemoryStorage, ScopeForbidden
from memory_core.storage.db import SQLiteMemoryDB


@dataclass
class _FakeEmbeddings:
    preflight_calls: int = 0

    def preflight(self) -> None:
        self.preflight_calls += 1

    def embed_text(self, text: str) -> list[float]:
        score = float(len(text.strip()) or 1)
        return [score, 0.5]


@dataclass
class _FakeVectorStore:
    rows: dict[str, dict] = field(default_factory=dict)

    def initialize(self) -> None:
        return

    def upsert_memory(self, *, memory_id, content, embedding, metadata) -> None:
        self.rows[str(memory_id)] = {
            "id": memory_id,
            "content": content,
            "embedding": embedding,
            "metadata": metadata,
        }

    def update_metadata(self, *, memory_id, metadata) -> None:
        row = self.rows[str(memory_id)]
        row["metadata"] = metadata

    def delete_memory(self, memory_id) -> None:
        self.rows.pop(str(memory_id), None)

    def has_id(self, memory_id) -> bool:
        return str(memory_id) in self.rows

    def list_all_ids(self) -> list[UUID]:
        return [UUID(key) for key in self.rows]

    def query_similar(self, *, query_embedding, limit=10, where=None, allowed_ids=None):
        allowed = {str(value) for value in allowed_ids} if allowed_ids is not None else None
        out = []
        for key, row in self.rows.items():
            if allowed is not None and key not in allowed:
                continue
            if where and row["metadata"].get("memory_type") != where.get("memory_type"):
                continue
            distance = abs(float(query_embedding[0]) - float(row["embedding"][0])) / 100.0
            out.append(
                {
                    "id": UUID(key),
                    "content": row["content"],
                    "metadata": row["metadata"],
                    "distance": distance,
                }
            )
        out.sort(key=lambda item: item["distance"])
        return out[:limit]


def _storage(tmp_path) -> MemoryStorage:
    config = MemoryConfig.model_validate(
        {
            "paths": {
                "sqlite_db": str(tmp_path / "memory.db"),
                "chroma_dir": str(tmp_path / "chroma"),
            },
            "client_profiles": {
                "krypton": {
                    "allowed_namespaces": ["alpha", "beta", "global"],
                    "can_cross_scope": True,
                    "can_access_private": False,
                },
                "alpha-agent": {
                    "allowed_namespaces": ["alpha", "global"],
                    "can_cross_scope": False,
                    "can_access_private": False,
                },
            },
        }
    )
    db = SQLiteMemoryDB(config.paths.sqlite_db)
    vector = _FakeVectorStore()
    embeddings = _FakeEmbeddings()
    storage = MemoryStorage(config, db=db, vector_store=vector, embeddings=embeddings)
    storage.initialize()
    return storage


def test_write_and_search_memory(tmp_path) -> None:
    storage = _storage(tmp_path)

    write = storage.write_memory(
        {"content": "Remember project alpha goals", "namespace": "alpha", "writer_id": "alpha-agent"}
    )
    assert write.action.value == "added"

    results = storage.search_memories(query="alpha goals", caller_id="alpha-agent", namespace="alpha")
    assert len(results) == 1
    assert results[0].namespace == "alpha"


def test_deterministic_dedup_skips_duplicate_content(tmp_path) -> None:
    storage = _storage(tmp_path)

    first = storage.write_memory({"content": "Same fact", "namespace": "alpha"})
    second = storage.write_memory({"content": " same   fact!!! ", "namespace": "alpha"})

    assert first.action.value == "added"
    assert second.action.value == "skipped"
    assert second.similar_id == first.id


def test_non_privileged_cross_scope_is_forbidden(tmp_path) -> None:
    storage = _storage(tmp_path)
    storage.write_memory({"content": "Alpha item", "namespace": "alpha"})

    with pytest.raises(ScopeForbidden):
        storage.search_memories(query="Alpha", caller_id="alpha-agent")


def test_update_content_rewrites_vector_and_sqlite(tmp_path) -> None:
    storage = _storage(tmp_path)
    write = storage.write_memory({"content": "Old content", "namespace": "alpha"})

    result = storage.update_memory(
        UpdateMemoryRequest(id=write.id, content="New content", confidence=0.8, namespace="alpha"),
        caller_id="alpha-agent",
    )
    refreshed = storage.get_memory(write.id, caller_id="alpha-agent")

    assert "content" in result["updated_fields"]
    assert refreshed.content == "New content"
    assert refreshed.confidence == 0.8


def test_archive_memory_removes_vector_and_marks_archived(tmp_path) -> None:
    storage = _storage(tmp_path)
    write = storage.write_memory({"content": "Archive me", "namespace": "alpha"})

    response = storage.archive_memory(write.id, caller_id="alpha-agent", namespace="alpha")
    row = storage.db.get_memory(write.id)
    assert response["archived"] is True
    assert row is not None and row.status is MemoryStatus.ARCHIVED


def test_non_privileged_update_requires_matching_namespace(tmp_path) -> None:
    storage = _storage(tmp_path)
    write = storage.write_memory({"content": "Needs namespace guard", "namespace": "alpha"})

    with pytest.raises(ScopeForbidden):
        storage.update_memory(
            UpdateMemoryRequest(id=write.id, content="x"),
            caller_id="alpha-agent",
        )
    with pytest.raises(ScopeForbidden):
        storage.update_memory(
            UpdateMemoryRequest(id=write.id, content="x", namespace="beta"),
            caller_id="alpha-agent",
        )


def test_non_privileged_archive_requires_matching_namespace(tmp_path) -> None:
    storage = _storage(tmp_path)
    write = storage.write_memory({"content": "Needs archive namespace guard", "namespace": "alpha"})

    with pytest.raises(ScopeForbidden):
        storage.archive_memory(write.id, caller_id="alpha-agent")
    with pytest.raises(ScopeForbidden):
        storage.archive_memory(write.id, caller_id="alpha-agent", namespace="beta")


def test_reconcile_repairs_missing_committed_vector(tmp_path) -> None:
    storage = _storage(tmp_path)
    write = storage.write_memory({"content": "Needs reconcile", "namespace": "alpha"})

    storage.vector_store.delete_memory(write.id)
    metrics = storage.reconcile_dual_store()

    assert metrics["sqlite_committed_missing_chroma"] == 1
    assert storage.vector_store.has_id(write.id)
