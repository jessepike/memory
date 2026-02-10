"""SQLite storage-layer tests."""

from uuid import uuid4

import pytest

from memory_core.models import MemoryEntry, MemoryStatus
from memory_core.storage.db import IdempotencyConflictError, SQLiteMemoryDB


def _make_entry(
    *,
    content: str = "memory",
    namespace: str = "global",
    status: MemoryStatus = MemoryStatus.STAGED,
    idempotency_key: str = "global:hash",
) -> MemoryEntry:
    return MemoryEntry(
        id=uuid4(),
        content=content,
        namespace=namespace,
        idempotency_key=idempotency_key,
        status=status,
    )


def test_initialize_creates_schema(tmp_path) -> None:
    db = SQLiteMemoryDB(tmp_path / "memory.db")
    db.initialize()

    row = db._connect().execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memories';"
    ).fetchone()
    assert row is not None


def test_insert_and_get_memory(tmp_path) -> None:
    db = SQLiteMemoryDB(tmp_path / "memory.db")
    db.initialize()
    entry = _make_entry(idempotency_key="global:a")

    db.insert_staged(entry)
    loaded = db.get_memory(entry.id)

    assert loaded is not None
    assert loaded.id == entry.id
    assert loaded.status == MemoryStatus.STAGED


def test_insert_staged_raises_on_active_idempotency_conflict(tmp_path) -> None:
    db = SQLiteMemoryDB(tmp_path / "memory.db")
    db.initialize()
    entry_one = _make_entry(idempotency_key="global:same")
    entry_two = _make_entry(idempotency_key="global:same")

    db.insert_staged(entry_one)
    with pytest.raises(IdempotencyConflictError) as exc_info:
        db.insert_staged(entry_two)

    assert exc_info.value.existing_id == entry_one.id


def test_list_memories_filters_by_status(tmp_path) -> None:
    db = SQLiteMemoryDB(tmp_path / "memory.db")
    db.initialize()
    staged = _make_entry(idempotency_key="global:staged", status=MemoryStatus.STAGED)
    committed = _make_entry(idempotency_key="global:committed", status=MemoryStatus.COMMITTED)
    db.insert_staged(staged)
    db.insert_staged(committed)

    results = db.list_memories(statuses=[MemoryStatus.COMMITTED])

    assert len(results) == 1
    assert results[0].id == committed.id


def test_stats_committed_excludes_non_committed_rows(tmp_path) -> None:
    db = SQLiteMemoryDB(tmp_path / "memory.db")
    db.initialize()
    committed = _make_entry(idempotency_key="global:c", status=MemoryStatus.COMMITTED)
    failed = _make_entry(idempotency_key="global:f", status=MemoryStatus.FAILED)
    db.insert_staged(committed)
    db.insert_staged(failed)

    stats = db.stats_committed()

    assert stats.total == 1
    assert stats.by_namespace["global"] == 1
