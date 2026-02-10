"""Tests for MCP tool wiring and scope-error serialization."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from memory_core.access.mcp_server import create_server
from memory_core.models import ForbiddenScopeError
from memory_core.storage.api import ScopeForbidden


@dataclass
class _FakeStorage:
    initialized: bool = False

    def initialize(self) -> None:
        self.initialized = True

    def write_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": "123", "action": "added", "payload": payload}

    def search_memories(self, **_kwargs: Any) -> list[dict[str, Any]]:
        raise ScopeForbidden(ForbiddenScopeError(caller_id="demo-agent", namespace=None))

    def get_memory(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": "123"}

    def get_recent(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def get_session_context(self, **_kwargs: Any) -> dict[str, Any]:
        return {"recent": [], "relevant": []}

    def update_memory(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": "123", "updated_fields": []}

    def archive_memory(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": "123", "archived": True}

    def review_candidates(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def get_stats(self, **_kwargs: Any) -> dict[str, Any]:
        return {"total": 0, "by_type": {}, "by_namespace": {}, "recent_7d": 0, "recent_30d": 0}

    def reconcile_dual_store(self) -> dict[str, Any]:
        return {}

    def list_failed_memories(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def retry_failed_memory(self, _id: str) -> dict[str, Any]:
        return {"id": _id, "status": "committed"}

    def archive_failed_memory(self, _id: str) -> dict[str, Any]:
        return {"id": _id, "status": "archived"}


def _payload(result: Any) -> Any:
    if isinstance(result, tuple) and len(result) >= 2:
        return result[1]
    if isinstance(result, list) and result and hasattr(result[0], "text"):
        return json.loads(result[0].text)
    return result


def test_mcp_tool_serializes_scope_errors() -> None:
    async def run() -> None:
        storage = _FakeStorage()
        app = create_server(storage=storage)
        assert storage.initialized is True

        result = _payload(await app.call_tool("search_memories", {"query": "x", "caller_id": "demo-agent"}))
        assert isinstance(result, dict)
        assert result["error_code"] == "forbidden_scope"
        assert result["caller_id"] == "demo-agent"

    asyncio.run(run())
