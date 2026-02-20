#!/usr/bin/env python3
"""SessionEnd hook — transcript extractor for Claude Code.

Reads the session transcript and writes episodes to the episodic log.
This is the safety net layer: fires if the user closes without running /handoff.

Input (stdin): JSON with transcript_path and session metadata from Claude Code hook.
Output: Writes episode(s) to EpisodeStorage. Always produces at least one episode.

Usage (called by Claude Code SessionEnd hook):
    python3 /path/to/extract_episodes.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# Memory project root (absolute path — this script runs outside the project venv)
_MEMORY_PROJECT = Path(__file__).resolve().parent.parent
_SRC_DIR = _MEMORY_PROJECT / "src"


def _load_episode_storage():
    """Import EpisodeStorage from the memory project."""
    if str(_SRC_DIR) not in sys.path:
        sys.path.insert(0, str(_SRC_DIR))
    from memory_core.config import load_config  # noqa: PLC0415
    from memory_core.storage.db import SQLiteMemoryDB  # noqa: PLC0415
    from memory_core.storage.episode_storage import EpisodeStorage  # noqa: PLC0415

    config = load_config(_MEMORY_PROJECT / "config" / "memory_config.yaml")
    db = SQLiteMemoryDB(config.paths.sqlite_db)
    db.initialize()
    return EpisodeStorage(db)


def _read_hook_input() -> dict[str, Any]:
    """Read Claude Code hook JSON payload from stdin."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def _parse_transcript(transcript_path: str) -> dict[str, Any]:
    """Parse Claude Code transcript JSONL.

    Returns:
        {
            "session_id": str | None,
            "cwd": str | None,
            "had_handoff_tool": bool,  # True if end_session was called via /handoff
            "last_assistant_text": str | None,
            "tool_names": list[str],
        }
    """
    result: dict[str, Any] = {
        "session_id": None,
        "cwd": None,
        "had_handoff_tool": False,
        "last_assistant_text": None,
        "tool_names": [],
    }

    try:
        path = Path(transcript_path)
        if not path.exists():
            return result

        with path.open("rb") as f:
            raw = f.read()

        last_text: str | None = None
        tool_names: list[str] = []

        for line in raw.split(b"\n"):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue

            # Extract session metadata from first entry with sessionId
            if result["session_id"] is None and "sessionId" in entry:
                result["session_id"] = entry.get("sessionId")
            if result["cwd"] is None and "cwd" in entry:
                result["cwd"] = entry.get("cwd")

            msg = entry.get("message", {})
            if not isinstance(msg, dict):
                continue

            role = msg.get("role")
            content = msg.get("content", [])

            if role == "assistant" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        text = block.get("text", "").strip()
                        if text:
                            last_text = text
                    elif btype == "tool_use":
                        name = block.get("name", "")
                        tool_names.append(name)
                        # Detect /handoff having called end_session
                        if name == "mcp__memory__end_session" or name == "end_session":
                            result["had_handoff_tool"] = True

        result["last_assistant_text"] = last_text
        result["tool_names"] = tool_names

    except Exception as e:
        result["parse_error"] = str(e)

    return result


def _extract_summary(last_text: str | None, cwd: str | None) -> str:
    """Extract a brief summary from the last assistant text."""
    if not last_text:
        project = Path(cwd).name if cwd else "unknown"
        return f"Session ended in {project} (no summary extracted)"

    # Take first meaningful line (skip empty, markdown headers)
    lines = [ln.strip() for ln in last_text.split("\n") if ln.strip()]
    for line in lines:
        # Skip pure markdown structure
        if line.startswith("#") or line.startswith("---") or line.startswith("```"):
            continue
        if len(line) > 10:
            return line[:200]

    return last_text[:200]


def main() -> int:
    """Main entry point. Returns exit code (0 = success, 1 = error)."""
    hook_input = _read_hook_input()
    transcript_path = hook_input.get("transcript_path") or hook_input.get("transcriptPath")

    now_iso = datetime.now(UTC).isoformat()

    # Parse transcript
    parsed: dict[str, Any] = {}
    if transcript_path:
        parsed = _parse_transcript(transcript_path)
    else:
        parsed = {
            "session_id": None,
            "cwd": None,
            "had_handoff_tool": False,
            "last_assistant_text": None,
            "tool_names": [],
            "parse_error": "no transcript_path in hook input",
        }

    cwd = parsed.get("cwd") or os.environ.get("PWD", "")
    project = Path(cwd).name if cwd else None

    # Generate a session_id for this hook invocation
    date_str = datetime.now(UTC).strftime("%Y%m%d")
    hook_session_id = f"hook-{date_str}-{project or 'unknown'}"

    # Build episode metadata
    metadata: dict[str, Any] = {
        "source": "sessionend_hook",
        "hook_session_id": hook_input.get("session_id") or hook_input.get("sessionId"),
        "cwd": cwd,
    }

    if parsed.get("had_handoff_tool"):
        # /handoff was already called — write a lightweight marker only
        content = f"SessionEnd hook: /handoff was called earlier this session (project: {project})"
        metadata["extraction_result"] = "handoff_already_called"
        metadata["tool_count"] = len(parsed.get("tool_names", []))
    elif parsed.get("parse_error") and not parsed.get("last_assistant_text"):
        content = f"SessionEnd hook: transcript extraction failed (project: {project})"
        metadata["extraction_result"] = "parse_error"
        metadata["error"] = parsed.get("parse_error")
    elif parsed.get("last_assistant_text"):
        summary = _extract_summary(parsed["last_assistant_text"], cwd)
        content = f"Session ended: {summary}"
        metadata["extraction_result"] = "text_extracted"
        metadata["tool_count"] = len(parsed.get("tool_names", []))
        # Include last assistant text for richer context
        metadata["last_assistant_text"] = parsed["last_assistant_text"][:500]
    else:
        content = f"SessionEnd hook fired (project: {project}, no transcript content)"
        metadata["extraction_result"] = "no_content"

    # Write episode to storage
    try:
        storage = _load_episode_storage()
        storage.write_episode({
            "content": content,
            "event_type": "session_end",
            "agent_id": "claude-code:sessionend-hook",
            "session_id": hook_session_id,
            "project": project,
            "namespace": "global",
            "severity": "info",
            "client": "claude-code",
            "source_ref": f"transcript:{transcript_path}" if transcript_path else None,
            "metadata": metadata,
        })
        return 0
    except Exception as e:
        # Fail silently — never surface errors to the user
        _ = e
        return 1


if __name__ == "__main__":
    sys.exit(main())
