"""Tests for UsageLogger."""

import json
from pathlib import Path

from memory_core.access.usage_logger import UsageLogger


def test_log_writes_valid_jsonl(tmp_path: Path) -> None:
    log_path = tmp_path / "usage.jsonl"
    logger = UsageLogger(log_path)
    logger.log("write_memory", "claude-code", "global", 12.4, "success")
    logger.log("search_memories", "krypton", "private", 5.1, "success")

    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        entry = json.loads(line)
        assert "ts" in entry
        assert "tool" in entry
        assert "caller_id" in entry
        assert "namespace" in entry
        assert "duration_ms" in entry
        assert "status" in entry
        assert "error" in entry


def test_log_all_fields_present(tmp_path: Path) -> None:
    log_path = tmp_path / "usage.jsonl"
    logger = UsageLogger(log_path)
    logger.log("get_memory", "test-agent", "ns1", 3.14, "error", "not found")

    entry = json.loads(log_path.read_text().strip())
    assert entry["tool"] == "get_memory"
    assert entry["caller_id"] == "test-agent"
    assert entry["namespace"] == "ns1"
    assert entry["duration_ms"] == 3.14
    assert entry["status"] == "error"
    assert entry["error"] == "not found"


def test_failsafe_bad_path(tmp_path: Path) -> None:
    logger = UsageLogger("/nonexistent/deeply/nested/nope/usage.jsonl")
    # Should not raise
    logger.log("health", "test", None, 1.0, "success")


def test_creates_parent_dirs(tmp_path: Path) -> None:
    log_path = tmp_path / "sub" / "dir" / "usage.jsonl"
    logger = UsageLogger(log_path)
    logger.log("health", "test", None, 0.5, "success")
    assert log_path.exists()
    entry = json.loads(log_path.read_text().strip())
    assert entry["tool"] == "health"
