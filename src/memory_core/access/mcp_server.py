"""MCP server entrypoint and tool dispatch wiring."""

from __future__ import annotations

import time
from dataclasses import asdict, is_dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from memory_core.access.usage_logger import UsageLogger
from memory_core.access.usage_reporter import UsageReporter
from memory_core.storage.api import MemoryStorage, ScopeForbidden


def _serialize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, UUID):
        return str(value)
    return value


def create_server(storage: MemoryStorage | None = None, *, config_path: str = "config/memory_config.yaml") -> Any:
    """Create and register MCP tools."""
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - dependency-specific
        raise RuntimeError(
            "MCP dependency is unavailable. Install package 'mcp>=1.0.0' to run the server."
        ) from exc

    memory_storage = storage or MemoryStorage.from_config_path(config_path)
    memory_storage.initialize()

    usage_logger = UsageLogger(memory_storage.config.paths.usage_log)
    usage_reporter = UsageReporter(memory_storage.config.paths.usage_log)

    app = FastMCP("memory-layer")

    def _run_tool(func, *args, _tool_name: str = "unknown", _caller_id: str = "unknown", _namespace: str | None = None, **kwargs):  # type: ignore[no-untyped-def]
        start = time.monotonic()
        try:
            result = _serialize(func(*args, **kwargs))
            usage_logger.log(_tool_name, _caller_id, _namespace, (time.monotonic() - start) * 1000, "success")
            return result
        except ScopeForbidden as exc:
            usage_logger.log(_tool_name, _caller_id, _namespace, (time.monotonic() - start) * 1000, "error", str(exc))
            return _serialize(exc.error)

    @app.tool()
    def write_memory(
        content: str,
        memory_type: str = "observation",
        namespace: str = "global",
        writer_id: str = "unknown",
        writer_type: str = "agent",
        source_project: str | None = None,
        confidence: float = 1.0,
    ) -> Any:
        return _run_tool(
            memory_storage.write_memory,
            {
                "content": content,
                "memory_type": memory_type,
                "namespace": namespace,
                "writer_id": writer_id,
                "writer_type": writer_type,
                "source_project": source_project,
                "confidence": confidence,
            },
            _tool_name="write_memory",
            _caller_id=writer_id,
            _namespace=namespace,
        )

    @app.tool()
    def search_memories(
        query: str,
        caller_id: str = "unknown",
        namespace: str | None = None,
        memory_type: str | None = None,
        limit: int = 10,
    ) -> Any:
        return _run_tool(
            memory_storage.search_memories,
            query=query,
            caller_id=caller_id,
            namespace=namespace,
            memory_type=memory_type,
            limit=limit,
            _tool_name="search_memories",
            _caller_id=caller_id,
            _namespace=namespace,
        )

    @app.tool()
    def get_memory(id: str, caller_id: str = "unknown") -> Any:
        return _run_tool(memory_storage.get_memory, id, caller_id=caller_id, _tool_name="get_memory", _caller_id=caller_id)

    @app.tool()
    def get_recent(
        caller_id: str = "unknown",
        namespace: str | None = None,
        memory_type: str | None = None,
        limit: int = 20,
        days: int = 7,
    ) -> Any:
        return _run_tool(
            memory_storage.get_recent,
            caller_id=caller_id,
            namespace=namespace,
            memory_type=memory_type,
            limit=limit,
            days=days,
            _tool_name="get_recent",
            _caller_id=caller_id,
            _namespace=namespace,
        )

    @app.tool()
    def get_session_context(
        caller_id: str = "unknown",
        namespace: str | None = None,
        query: str | None = None,
        limit: int = 10,
    ) -> Any:
        return _run_tool(
            memory_storage.get_session_context,
            caller_id=caller_id,
            namespace=namespace,
            query=query,
            limit=limit,
            _tool_name="get_session_context",
            _caller_id=caller_id,
            _namespace=namespace,
        )

    @app.tool()
    def update_memory(
        id: str,
        caller_id: str = "unknown",
        content: str | None = None,
        memory_type: str | None = None,
        namespace: str | None = None,
        writer_id: str | None = None,
        writer_type: str | None = None,
        source_project: str | None = None,
        confidence: float | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "id": id,
            "content": content,
            "memory_type": memory_type,
            "namespace": namespace,
            "writer_id": writer_id,
            "writer_type": writer_type,
            "source_project": source_project,
            "confidence": confidence,
        }
        filtered = {key: value for key, value in payload.items() if value is not None or key == "id"}
        return _run_tool(memory_storage.update_memory, filtered, caller_id=caller_id, _tool_name="update_memory", _caller_id=caller_id, _namespace=namespace)

    @app.tool()
    def archive_memory(id: str, caller_id: str = "unknown", namespace: str | None = None) -> Any:
        return _run_tool(memory_storage.archive_memory, id, caller_id=caller_id, namespace=namespace, _tool_name="archive_memory", _caller_id=caller_id, _namespace=namespace)

    @app.tool()
    def review_candidates(
        caller_id: str = "unknown",
        namespace: str | None = None,
        limit: int = 20,
    ) -> Any:
        return _run_tool(memory_storage.review_candidates, caller_id=caller_id, namespace=namespace, limit=limit, _tool_name="review_candidates", _caller_id=caller_id, _namespace=namespace)

    @app.tool()
    def get_stats(caller_id: str = "unknown", namespace: str | None = None) -> Any:
        return _run_tool(memory_storage.get_stats, caller_id=caller_id, namespace=namespace, _tool_name="get_stats", _caller_id=caller_id, _namespace=namespace)

    @app.tool()
    def reconcile_dual_store() -> Any:
        return _run_tool(memory_storage.reconcile_dual_store, _tool_name="reconcile_dual_store")

    @app.tool()
    def list_failed_memories(limit: int = 100, older_than_days: int | None = None) -> Any:
        return _run_tool(memory_storage.list_failed_memories, limit=limit, older_than_days=older_than_days, _tool_name="list_failed_memories")

    @app.tool()
    def retry_failed_memory(id: str) -> Any:
        return _run_tool(memory_storage.retry_failed_memory, id, _tool_name="retry_failed_memory")

    @app.tool()
    def archive_failed_memory(id: str) -> Any:
        return _run_tool(memory_storage.archive_failed_memory, id, _tool_name="archive_failed_memory")

    @app.tool()
    def get_usage_report(
        days: int = 7,
        namespace: str | None = None,
        caller_id: str = "unknown",
    ) -> Any:
        start = time.monotonic()
        result = usage_reporter.report(days=days, namespace=namespace)
        usage_logger.log("get_usage_report", caller_id, namespace, (time.monotonic() - start) * 1000, "success")
        return result

    @app.tool()
    def health() -> dict[str, str]:
        start = time.monotonic()
        result = {"status": "ok"}
        usage_logger.log("health", "unknown", None, (time.monotonic() - start) * 1000, "success")
        return result

    return app


def main() -> None:
    """Run MCP server over stdio."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
