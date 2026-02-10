"""MCP server entrypoint and tool dispatch wiring."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel

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
    app = FastMCP("memory-layer")

    def _run_tool(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            return _serialize(func(*args, **kwargs))
        except ScopeForbidden as exc:
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
        )

    @app.tool()
    def get_memory(id: str, caller_id: str = "unknown") -> Any:
        return _run_tool(memory_storage.get_memory, id, caller_id=caller_id)

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
        return _run_tool(memory_storage.update_memory, filtered, caller_id=caller_id)

    @app.tool()
    def archive_memory(id: str, caller_id: str = "unknown", namespace: str | None = None) -> Any:
        return _run_tool(memory_storage.archive_memory, id, caller_id=caller_id, namespace=namespace)

    @app.tool()
    def review_candidates(
        caller_id: str = "unknown",
        namespace: str | None = None,
        limit: int = 20,
    ) -> Any:
        return _run_tool(memory_storage.review_candidates, caller_id=caller_id, namespace=namespace, limit=limit)

    @app.tool()
    def get_stats(caller_id: str = "unknown", namespace: str | None = None) -> Any:
        return _run_tool(memory_storage.get_stats, caller_id=caller_id, namespace=namespace)

    @app.tool()
    def reconcile_dual_store() -> Any:
        return _run_tool(memory_storage.reconcile_dual_store)

    @app.tool()
    def list_failed_memories(limit: int = 100, older_than_days: int | None = None) -> Any:
        return _run_tool(memory_storage.list_failed_memories, limit=limit, older_than_days=older_than_days)

    @app.tool()
    def retry_failed_memory(id: str) -> Any:
        return _run_tool(memory_storage.retry_failed_memory, id)

    @app.tool()
    def archive_failed_memory(id: str) -> Any:
        return _run_tool(memory_storage.archive_failed_memory, id)

    @app.tool()
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def main() -> None:
    """Run MCP server over stdio."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
