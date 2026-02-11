"""Read usage JSONL and compute actionable metrics. Fail-safe: never raises."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


class UsageReporter:
    """Reads JSONL usage log and computes aggregate metrics."""

    def __init__(self, log_path: str | Path) -> None:
        self._path = Path(log_path)

    def report(self, days: int = 7, namespace: str | None = None) -> dict:
        """Return usage metrics for the given period and optional namespace filter."""
        try:
            return self._compute(days, namespace)
        except Exception:
            return self._empty_report(days, namespace)

    def _compute(self, days: int, namespace: str | None) -> dict:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        entries = self._read_entries(cutoff, namespace)

        if not entries:
            return self._empty_report(days, namespace, empty_period=True)

        by_tool: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_namespace: dict[str, int] = {}
        by_caller: dict[str, int] = {}
        total_duration = 0.0

        for e in entries:
            tool = e.get("tool", "unknown")
            by_tool[tool] = by_tool.get(tool, 0) + 1

            status = e.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1

            ns = e.get("namespace") or "none"
            by_namespace[ns] = by_namespace.get(ns, 0) + 1

            caller = e.get("caller_id") or "unknown"
            by_caller[caller] = by_caller.get(caller, 0) + 1

            total_duration += e.get("duration_ms", 0.0)

        total = len(entries)
        errors = by_status.get("error", 0)
        writes = by_tool.get("write_memory", 0)
        searches = by_tool.get("search_memories", 0)

        return {
            "period_days": days,
            "namespace_filter": namespace,
            "total_calls": total,
            "by_tool": by_tool,
            "by_status": by_status,
            "by_namespace": by_namespace,
            "by_caller": by_caller,
            "search_to_write_ratio": round(searches / writes, 2) if writes > 0 else None,
            "error_rate": round(errors / total, 3) if total > 0 else 0.0,
            "avg_duration_ms": round(total_duration / total, 1) if total > 0 else 0.0,
            "empty_period": False,
        }

    def _read_entries(self, cutoff: datetime, namespace: str | None) -> list[dict]:
        if not self._path.exists():
            return []

        entries = []
        for line in self._path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_str = entry.get("ts")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue

            if namespace is not None and entry.get("namespace") != namespace:
                continue

            entries.append(entry)
        return entries

    def _empty_report(self, days: int, namespace: str | None, *, empty_period: bool = False) -> dict:
        return {
            "period_days": days,
            "namespace_filter": namespace,
            "total_calls": 0,
            "by_tool": {},
            "by_status": {},
            "by_namespace": {},
            "by_caller": {},
            "search_to_write_ratio": None,
            "error_rate": 0.0,
            "avg_duration_ms": 0.0,
            "empty_period": empty_period or True,
        }
