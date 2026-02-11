"""Unit tests for UsageReporter."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from memory_core.access.usage_reporter import UsageReporter


def _write_entries(path: Path, entries: list[dict]) -> None:
    with path.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _make_entry(
    tool: str = "search_memories",
    caller_id: str = "agent-a",
    namespace: str | None = "demo",
    status: str = "success",
    duration_ms: float = 10.0,
    hours_ago: float = 0,
) -> dict:
    ts = datetime.now(UTC) - timedelta(hours=hours_ago)
    return {
        "ts": ts.isoformat(),
        "tool": tool,
        "caller_id": caller_id,
        "namespace": namespace,
        "duration_ms": duration_ms,
        "status": status,
        "error": None,
    }


def test_basic_counts(tmp_path: Path) -> None:
    log = tmp_path / "usage.jsonl"
    _write_entries(log, [
        _make_entry(tool="write_memory", duration_ms=5),
        _make_entry(tool="search_memories", duration_ms=15),
        _make_entry(tool="search_memories", duration_ms=10),
    ])

    report = UsageReporter(log).report(days=7)
    assert report["total_calls"] == 3
    assert report["by_tool"]["write_memory"] == 1
    assert report["by_tool"]["search_memories"] == 2
    assert report["search_to_write_ratio"] == 2.0
    assert report["error_rate"] == 0.0
    assert report["avg_duration_ms"] == 10.0
    assert report["empty_period"] is False


def test_date_filtering(tmp_path: Path) -> None:
    log = tmp_path / "usage.jsonl"
    _write_entries(log, [
        _make_entry(hours_ago=1),       # within 1 day
        _make_entry(hours_ago=48),      # outside 1 day
    ])

    report = UsageReporter(log).report(days=1)
    assert report["total_calls"] == 1


def test_namespace_filtering(tmp_path: Path) -> None:
    log = tmp_path / "usage.jsonl"
    _write_entries(log, [
        _make_entry(namespace="demo"),
        _make_entry(namespace="global"),
        _make_entry(namespace="demo"),
    ])

    report = UsageReporter(log).report(namespace="demo")
    assert report["total_calls"] == 2
    assert report["namespace_filter"] == "demo"


def test_error_rate(tmp_path: Path) -> None:
    log = tmp_path / "usage.jsonl"
    _write_entries(log, [
        _make_entry(status="success"),
        _make_entry(status="success"),
        _make_entry(status="error"),
        _make_entry(status="error"),
    ])

    report = UsageReporter(log).report()
    assert report["error_rate"] == 0.5
    assert report["by_status"] == {"success": 2, "error": 2}


def test_by_caller(tmp_path: Path) -> None:
    log = tmp_path / "usage.jsonl"
    _write_entries(log, [
        _make_entry(caller_id="claude-code"),
        _make_entry(caller_id="krypton"),
        _make_entry(caller_id="claude-code"),
    ])

    report = UsageReporter(log).report()
    assert report["by_caller"] == {"claude-code": 2, "krypton": 1}


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    report = UsageReporter(tmp_path / "nonexistent.jsonl").report()
    assert report["total_calls"] == 0
    assert report["empty_period"] is True


def test_corrupt_lines_skipped(tmp_path: Path) -> None:
    log = tmp_path / "usage.jsonl"
    log.write_text(
        json.dumps(_make_entry()) + "\n"
        + "not valid json\n"
        + json.dumps(_make_entry()) + "\n"
    )

    report = UsageReporter(log).report()
    assert report["total_calls"] == 2


def test_no_writes_ratio_is_none(tmp_path: Path) -> None:
    log = tmp_path / "usage.jsonl"
    _write_entries(log, [_make_entry(tool="search_memories")])

    report = UsageReporter(log).report()
    assert report["search_to_write_ratio"] is None


def test_empty_period_with_all_old_entries(tmp_path: Path) -> None:
    log = tmp_path / "usage.jsonl"
    _write_entries(log, [_make_entry(hours_ago=500)])

    report = UsageReporter(log).report(days=1)
    assert report["total_calls"] == 0
    assert report["empty_period"] is True
