"""Append-only JSONL usage logger for MCP tool calls."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path


class UsageLogger:
    """Logs MCP tool invocations to a JSONL file. Fail-safe: never raises."""

    def __init__(self, log_path: str | Path) -> None:
        self._path = Path(log_path)

    def log(
        self,
        tool: str,
        caller_id: str = "unknown",
        namespace: str | None = None,
        duration_ms: float = 0.0,
        status: str = "success",
        error: str | None = None,
    ) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": datetime.now(UTC).isoformat(),
                "tool": tool,
                "caller_id": caller_id,
                "namespace": namespace,
                "duration_ms": round(duration_ms, 2),
                "status": status,
                "error": error,
            }
            with self._path.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # Never break a tool call for logging
