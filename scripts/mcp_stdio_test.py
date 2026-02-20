#!/usr/bin/env python3
"""Live stdio transport test — spawns the MCP server as a subprocess and
communicates via JSON-RPC over stdin/stdout."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any


def _jsonrpc_request(id: int, method: str, params: dict[str, Any] | None = None) -> bytes:
    """Build a JSON-RPC 2.0 request line (newline-terminated)."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg).encode() + b"\n"


def _read_response(proc: subprocess.Popen) -> dict[str, Any]:
    """Read one JSON-RPC response line from the subprocess stdout."""
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("Server closed stdout unexpectedly")
    return json.loads(line)


def _call_tool(proc: subprocess.Popen, req_id: int, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Send a tools/call request and return the parsed response."""
    assert proc.stdin is not None
    proc.stdin.write(
        _jsonrpc_request(req_id, "tools/call", {"name": name, "arguments": arguments})
    )
    proc.stdin.flush()
    return _read_response(proc)


def run_stdio_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        temp_root = Path(td)
        config_path = temp_root / "memory_config.yaml"
        config_path.write_text(
            textwrap.dedent(
                f"""\
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
            ),
            encoding="utf-8",
        )

        # Launch the MCP server as a subprocess
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"from memory_core.access.mcp_server import create_server; "
                f"create_server(config_path={str(config_path)!r}).run(transport='stdio')",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        checklist: dict[str, bool] = {}
        artifacts: dict[str, Any] = {}
        req_id = 0

        try:
            assert proc.stdin is not None

            # 1. Initialize
            req_id += 1
            proc.stdin.write(
                _jsonrpc_request(req_id, "initialize", {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "stdio-test", "version": "0.1.0"},
                })
            )
            proc.stdin.flush()
            init_resp = _read_response(proc)
            checklist["server_starts"] = "result" in init_resp
            artifacts["initialize"] = init_resp

            # Send initialized notification (no id, no response expected)
            proc.stdin.write(json.dumps({
                "jsonrpc": "2.0", "method": "notifications/initialized"
            }).encode() + b"\n")
            proc.stdin.flush()

            # 2. List tools
            req_id += 1
            proc.stdin.write(_jsonrpc_request(req_id, "tools/list"))
            proc.stdin.flush()
            tools_resp = _read_response(proc)
            tool_names = sorted(t["name"] for t in tools_resp.get("result", {}).get("tools", []))
            checklist["tools_list_returns_19"] = len(tool_names) == 19
            artifacts["tools"] = tool_names

            # 3. Write a memory
            req_id += 1
            write_resp = _call_tool(proc, req_id, "write_memory", {
                "content": "stdio test memory",
                "namespace": "demo",
                "writer_id": "demo-agent",
                "writer_type": "agent",
            })
            write_payload = _extract_tool_payload(write_resp)
            checklist["write_succeeds"] = write_payload.get("action") == "added"
            artifacts["write"] = write_payload

            # 4. Search
            req_id += 1
            search_resp = _call_tool(proc, req_id, "search_memories", {
                "query": "stdio test",
                "caller_id": "demo-agent",
                "namespace": "demo",
                "limit": 5,
            })
            search_payload = _extract_tool_payload(search_resp)
            if isinstance(search_payload, list):
                checklist["search_returns_result"] = len(search_payload) >= 1
            elif isinstance(search_payload, dict) and "id" in search_payload:
                checklist["search_returns_result"] = True
            else:
                checklist["search_returns_result"] = False
            artifacts["search"] = search_payload

            # 5. Archive
            req_id += 1
            archive_resp = _call_tool(proc, req_id, "archive_memory", {
                "id": write_payload["id"],
                "caller_id": "demo-agent",
                "namespace": "demo",
            })
            archive_payload = _extract_tool_payload(archive_resp)
            checklist["archive_succeeds"] = archive_payload.get("archived") is True
            artifacts["archive"] = archive_payload

            # 6. Responses are well-formed JSON-RPC
            checklist["responses_well_formed"] = all(
                r.get("jsonrpc") == "2.0" and "id" in r
                for r in [init_resp, tools_resp, write_resp, search_resp, archive_resp]
            )

        finally:
            # Clean shutdown
            proc.stdin.close()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            checklist["clean_shutdown"] = proc.returncode in (0, None, -13)  # 0 or SIGPIPE
            stderr_output = proc.stderr.read().decode() if proc.stderr else ""
            artifacts["stderr"] = stderr_output

        success = all(checklist.values())
        return {
            "success": success,
            "checklist": checklist,
            "tool_count": len(tool_names) if "tools" in artifacts else 0,
            "tools": artifacts.get("tools", []),
            "artifacts": artifacts,
        }


def _extract_tool_payload(resp: dict[str, Any]) -> Any:
    """Extract the parsed JSON payload from a tools/call JSON-RPC response."""
    content = resp.get("result", {}).get("content", [])
    if content and isinstance(content, list):
        text = content[0].get("text", "{}")
        return json.loads(text)
    return resp.get("result", {})


def main() -> None:
    parser = argparse.ArgumentParser(description="Live stdio transport test for memory-layer MCP")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    result = run_stdio_test()
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
