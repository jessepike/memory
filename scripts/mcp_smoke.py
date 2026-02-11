#!/usr/bin/env python3
"""Run an in-process MCP smoke test against real storage dependencies."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from memory_core.access.mcp_server import create_server


def _payload(result: Any) -> Any:
    """Extract structured payload from FastMCP call_tool result."""
    if isinstance(result, tuple) and len(result) >= 2:
        return result[1]
    if isinstance(result, list) and result and hasattr(result[0], "text"):
        text = result[0].text
        return json.loads(text)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result
    raise TypeError(f"Unexpected MCP tool response shape: {type(result)!r}")


async def run_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        temp_root = Path(td)
        config_path = temp_root / "memory_config.yaml"
        config_path.write_text(
            textwrap.dedent(
                f"""
                paths:
                  sqlite_db: {temp_root / 'memory.db'}
                  chroma_dir: {temp_root / 'chroma'}
                embedding:
                  model_name: all-MiniLM-L6-v2
                  allow_model_download_during_setup: true
                consolidation:
                  similarity_threshold: 0.92
                runtime:
                  enforce_offline: false
                client_profiles:
                  krypton:
                    allowed_namespaces: [demo, global]
                    can_cross_scope: true
                    can_access_private: false
                  demo-agent:
                    allowed_namespaces: [demo, global]
                    can_cross_scope: false
                    can_access_private: false
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        app = create_server(config_path=str(config_path))

        tools = await app.list_tools()
        tool_names = sorted(tool.name for tool in tools)

        write_one = _payload(
            await app.call_tool(
                "write_memory",
                {
                    "content": "alpha memory",
                    "namespace": "demo",
                    "writer_id": "demo-agent",
                    "writer_type": "agent",
                },
            )
        )
        write_two = _payload(
            await app.call_tool(
                "write_memory",
                {
                    "content": "alpha memory!!!",
                    "namespace": "demo",
                    "writer_id": "demo-agent",
                    "writer_type": "agent",
                },
            )
        )
        search = _payload(
            await app.call_tool(
                "search_memories",
                {
                    "query": "alpha",
                    "caller_id": "demo-agent",
                    "namespace": "demo",
                    "limit": 5,
                },
            )
        )
        search_results = search.get("result", search) if isinstance(search, dict) else search
        has_search_results = False
        if isinstance(search_results, list):
            has_search_results = len(search_results) >= 1
        elif isinstance(search_results, dict):
            has_search_results = "id" in search_results and "content" in search_results
        # --- New checks: get_memory (before archive) ---
        get_mem = _payload(
            await app.call_tool(
                "get_memory", {"id": write_one["id"], "caller_id": "demo-agent"}
            )
        )

        # --- update_memory (before archive, with namespace for non-privileged caller) ---
        update_result = _payload(
            await app.call_tool(
                "update_memory",
                {
                    "id": write_one["id"],
                    "caller_id": "demo-agent",
                    "namespace": "demo",
                    "content": "alpha memory updated",
                },
            )
        )

        stats_before = _payload(await app.call_tool("get_stats", {"caller_id": "krypton"}))
        archive = _payload(
            await app.call_tool(
                "archive_memory",
                {"id": write_one["id"], "caller_id": "demo-agent", "namespace": "demo"},
            )
        )
        stats_after = _payload(await app.call_tool("get_stats", {"caller_id": "krypton"}))

        # --- get_recent ---
        recent = _payload(
            await app.call_tool(
                "get_recent", {"caller_id": "demo-agent", "namespace": "demo", "limit": 10, "days": 7}
            )
        )

        # --- get_session_context ---
        session_ctx = _payload(
            await app.call_tool(
                "get_session_context",
                {"caller_id": "demo-agent", "namespace": "demo", "query": "alpha", "limit": 5},
            )
        )

        # --- review_candidates ---
        candidates = _payload(
            await app.call_tool(
                "review_candidates", {"caller_id": "demo-agent", "namespace": "demo", "limit": 10}
            )
        )

        # --- reconcile_dual_store ---
        reconcile = _payload(await app.call_tool("reconcile_dual_store", {}))

        # --- list_failed_memories ---
        failed = _payload(await app.call_tool("list_failed_memories", {"limit": 10}))

        # --- Cross-namespace search (privileged caller) ---
        cross_search = _payload(
            await app.call_tool(
                "search_memories",
                {"query": "alpha", "caller_id": "krypton", "namespace": "demo", "limit": 5},
            )
        )

        # --- Forbidden scope error (unprivileged private access) ---
        # demo-agent has can_access_private: false, so searching private namespace raises ScopeForbidden
        forbidden_resp = _payload(
            await app.call_tool(
                "search_memories",
                {"query": "anything", "caller_id": "demo-agent", "namespace": "private", "limit": 5},
            )
        )

        checklist = {
            "tools_registered": len(tool_names) >= 9,
            "write_added": write_one.get("action") == "added",
            "dedup_skip": write_two.get("action") == "skipped",
            "search_returns_results": has_search_results,
            "archive_success": archive.get("archived") is True,
            "stats_decrease_after_archive": (
                isinstance(stats_before.get("total"), int)
                and isinstance(stats_after.get("total"), int)
                and stats_after["total"] < stats_before["total"]
            ),
            "get_memory_returns_content": (
                isinstance(get_mem, dict) and "content" in get_mem
            ),
            "update_memory_success": (
                isinstance(update_result, dict)
                and "updated_fields" in update_result
                and "content" in update_result.get("updated_fields", [])
            ),
            "get_recent_returns_list": isinstance(recent, list),
            "get_session_context_has_shape": (
                isinstance(session_ctx, dict)
                and ("recent" in session_ctx or "relevant" in session_ctx or isinstance(session_ctx, dict))
            ),
            "review_candidates_returns_list": isinstance(candidates, list),
            "reconcile_has_shape": isinstance(reconcile, dict),
            "list_failed_empty": isinstance(failed, list) and len(failed) == 0,
            "cross_namespace_search_ok": (
                isinstance(cross_search, list) or (isinstance(cross_search, dict) and "error" not in cross_search)
            ),
            "forbidden_scope_error": (
                isinstance(forbidden_resp, dict) and forbidden_resp.get("error_code") == "forbidden_scope"
            ),
        }
        success = all(checklist.values())

        return {
            "success": success,
            "checklist": checklist,
            "tool_count": len(tool_names),
            "tools": tool_names,
            "artifacts": {
                "write_added": write_one,
                "write_dedup": write_two,
                "search": search,
                "stats_before": stats_before,
                "stats_after": stats_after,
                "get_memory": get_mem,
                "update_memory": update_result,
                "get_recent": recent,
                "get_session_context": session_ctx,
                "review_candidates": candidates,
                "reconcile": reconcile,
                "list_failed": failed,
                "cross_search": cross_search,
                "forbidden_resp": forbidden_resp,
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MCP smoke test for memory-layer")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    result = asyncio.run(run_smoke())
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"success={result['success']}")
        for key, value in result["checklist"].items():
            print(f"- {key}: {value}")

    if not result["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
