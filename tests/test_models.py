"""Validation tests for core Pydantic models."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from memory_core.models import (
    MemoryConfig,
    MemoryEntry,
    MemoryStatus,
    SearchMemoriesRequest,
    StatsResponse,
    WriteMemoryRequest,
    WriteMemoryResponse,
)


def test_write_memory_request_defaults() -> None:
    request = WriteMemoryRequest(content="Remember this")

    assert request.memory_type.value == "observation"
    assert request.namespace == "global"
    assert request.writer_type.value == "agent"
    assert request.confidence == 1.0


def test_write_memory_request_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        WriteMemoryRequest(content="x", confidence=1.1)


def test_memory_entry_default_status_is_staged() -> None:
    entry = MemoryEntry(content="x", idempotency_key="ns:hash")

    assert entry.status == MemoryStatus.STAGED


def test_search_request_limit_constraints() -> None:
    with pytest.raises(ValidationError):
        SearchMemoriesRequest(query="hello", limit=0)


def test_write_memory_response_similarity_bounds() -> None:
    with pytest.raises(ValidationError):
        WriteMemoryResponse(id=uuid4(), action="skipped", similarity=1.5)


def test_memory_config_defaults() -> None:
    config = MemoryConfig()

    assert config.paths.sqlite_db == "data/memory.db"
    assert config.embedding.model_name == "all-MiniLM-L6-v2"


def test_stats_response_accepts_nullable_reconcile_timestamp() -> None:
    stats = StatsResponse(
        total=0,
        by_type={},
        by_namespace={},
        recent_7d=0,
        recent_30d=0,
        drift={
            "sqlite_committed_missing_chroma": 0,
            "sqlite_archived_present_chroma": 0,
            "chroma_orphans": 0,
            "last_reconcile_at": None,
        },
    )
    assert stats.drift is not None
