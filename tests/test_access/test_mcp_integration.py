"""MCP-level integration tests for tool surface and error contracts."""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from memory_core.access.mcp_server import create_server


class _FakeSentenceTransformer:
    def __init__(self, *_args, **_kwargs) -> None:
        return

    def encode(self, payload, normalize_embeddings: bool = True):
        assert normalize_embeddings is True
        if isinstance(payload, list):
            return [[0.1, 0.2, 0.3] for _ in payload]
        return [0.1, 0.2, 0.3]


def _extract_payload(result: Any) -> Any:
    if isinstance(result, tuple) and len(result) >= 2:
        return result[1]
    if isinstance(result, list) and result and hasattr(result[0], "text"):
        decoded = json.loads(result[0].text)
        if isinstance(decoded, list):
            return decoded
        if isinstance(decoded, dict) and "result" in decoded:
            return decoded["result"]
        return decoded
    return result


def _has_nonempty_results(payload: Any) -> bool:
    if isinstance(payload, list):
        return len(payload) > 0
    if isinstance(payload, dict):
        return "id" in payload or (isinstance(payload.get("result"), list) and len(payload["result"]) > 0)
    return False


def _write_test_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "memory_config.yaml"
    config_path.write_text(
        textwrap.dedent(
            f"""
            paths:
              sqlite_db: {tmp_path / 'memory.db'}
              chroma_dir: {tmp_path / 'chroma'}
            embedding:
              model_name: all-MiniLM-L6-v2
              allow_model_download_during_setup: true
            consolidation:
              similarity_threshold: 0.92
            runtime:
              enforce_offline: false
            client_profiles:
              demo-agent:
                allowed_namespaces: [demo, global]
                can_cross_scope: false
                can_access_private: false
              krypton:
                allowed_namespaces: [demo, global]
                can_cross_scope: true
                can_access_private: false
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return config_path


def test_mcp_core_tool_flow(monkeypatch, tmp_path: Path) -> None:
    async def run() -> None:
        monkeypatch.setitem(
            sys.modules,
            "sentence_transformers",
            SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer),
        )

        app = create_server(config_path=str(_write_test_config(tmp_path)))
        tools = await app.list_tools()
        tool_names = {tool.name for tool in tools}

        expected = {
            "write_memory",
            "search_memories",
            "get_memory",
            "get_recent",
            "get_session_context",
            "update_memory",
            "archive_memory",
            "review_candidates",
            "get_stats",
        }
        assert expected.issubset(tool_names)

        write = _extract_payload(
            await app.call_tool(
                "write_memory",
                {"content": "alpha memory", "namespace": "demo", "writer_id": "demo-agent"},
            )
        )
        memory_id = write["id"]
        assert write["action"] == "added"

        found = _extract_payload(
            await app.call_tool(
                "search_memories",
                {"query": "alpha", "caller_id": "demo-agent", "namespace": "demo"},
            )
        )
        assert _has_nonempty_results(found)

        got = _extract_payload(await app.call_tool("get_memory", {"id": memory_id, "caller_id": "demo-agent"}))
        assert got["id"] == memory_id

        recent = _extract_payload(await app.call_tool("get_recent", {"caller_id": "demo-agent", "namespace": "demo"}))
        assert _has_nonempty_results(recent)

        context = _extract_payload(
            await app.call_tool(
                "get_session_context",
                {"caller_id": "demo-agent", "namespace": "demo", "query": "alpha"},
            )
        )
        assert "recent" in context and "relevant" in context

        updated = _extract_payload(
            await app.call_tool(
                "update_memory",
                {"id": memory_id, "caller_id": "demo-agent", "namespace": "demo", "confidence": 0.8},
            )
        )
        assert updated["id"] == memory_id
        assert "confidence" in updated["updated_fields"]

        review = _extract_payload(
            await app.call_tool("review_candidates", {"caller_id": "demo-agent", "namespace": "demo"})
        )
        assert isinstance(review, list)

        stats_before = _extract_payload(await app.call_tool("get_stats", {"caller_id": "krypton"}))
        assert stats_before["total"] >= 1

        archived = _extract_payload(
            await app.call_tool(
                "archive_memory",
                {"id": memory_id, "caller_id": "demo-agent", "namespace": "demo"},
            )
        )
        assert archived["archived"] is True

        stats_after = _extract_payload(await app.call_tool("get_stats", {"caller_id": "krypton"}))
        assert stats_after["total"] < stats_before["total"]

    asyncio.run(run())


def test_mcp_scope_error_contracts(monkeypatch, tmp_path: Path) -> None:
    async def run() -> None:
        monkeypatch.setitem(
            sys.modules,
            "sentence_transformers",
            SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer),
        )

        app = create_server(config_path=str(_write_test_config(tmp_path)))
        write = _extract_payload(
            await app.call_tool(
                "write_memory",
                {"content": "guarded memory", "namespace": "demo", "writer_id": "demo-agent"},
            )
        )
        memory_id = write["id"]

        cross_scope = _extract_payload(await app.call_tool("search_memories", {"query": "guarded", "caller_id": "demo-agent"}))
        assert cross_scope["error_code"] == "forbidden_scope"
        assert cross_scope["caller_id"] == "demo-agent"

        update_missing_namespace = _extract_payload(
            await app.call_tool(
                "update_memory",
                {"id": memory_id, "caller_id": "demo-agent", "confidence": 0.9},
            )
        )
        assert update_missing_namespace["error_code"] == "forbidden_scope"
        assert update_missing_namespace["id"] == memory_id

        archive_mismatch = _extract_payload(
            await app.call_tool(
                "archive_memory",
                {"id": memory_id, "caller_id": "demo-agent", "namespace": "other"},
            )
        )
        assert archive_mismatch["error_code"] == "forbidden_scope"
        assert archive_mismatch["id"] == memory_id

    asyncio.run(run())
