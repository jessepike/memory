"""MCP integration tests for write_episode, get_episodes, end_session tools,
and the enhanced get_session_context with last_handoff."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from memory_core.access.mcp_server import create_server
from memory_core.models import MemoryConfig
from memory_core.storage.api import MemoryStorage
from memory_core.storage.db import SQLiteMemoryDB
from memory_core.storage.vector_store import ChromaVectorStore
from memory_core.utils.embeddings import EmbeddingService


# ---------------------------------------------------------------------------
# Fixtures: in-memory storage with mocked embeddings/vector store
# ---------------------------------------------------------------------------

@pytest.fixture()
def storage(tmp_path):
    config = MemoryConfig()
    config.paths.sqlite_db = str(tmp_path / "memory.db")
    config.paths.chroma_dir = str(tmp_path / "chroma")
    config.paths.usage_log = str(tmp_path / "usage.jsonl")

    db = SQLiteMemoryDB(config.paths.sqlite_db)
    db.initialize()

    mock_vs = MagicMock(spec=ChromaVectorStore)
    mock_vs.query_similar.return_value = []
    mock_vs.list_all_ids.return_value = []

    mock_emb = MagicMock(spec=EmbeddingService)
    mock_emb.embed_text.return_value = [0.1] * 384

    return MemoryStorage(config, db=db, vector_store=mock_vs, embeddings=mock_emb)


@pytest.fixture()
def app(storage):
    return create_server(storage)


def _payload(result):
    """Extract value from FastMCP call_tool response.

    FastMCP serializes list return values as one TextContent per element.
    A non-list return value (or a JSON-encoded list) is a single TextContent.
    """
    if isinstance(result, list) and result and hasattr(result[0], "text"):
        if len(result) > 1:
            # Multiple TextContent items = FastMCP expanded a list
            return [json.loads(item.text) for item in result]
        decoded = json.loads(result[0].text)
        return decoded
    return result


def _payload_list(result):
    """_payload variant for tools that always return a list.

    When a tool returns a 1-element list, FastMCP produces a single
    TextContent (indistinguishable from a scalar). Wrap it in a list.
    """
    raw = _payload(result)
    if isinstance(raw, list):
        return raw
    return [raw]


def _call(app, tool_name: str, args: dict):
    async def run():
        return _payload(await app.call_tool(tool_name, args))
    return asyncio.run(run())


def _call_list(app, tool_name: str, args: dict):
    async def run():
        return _payload_list(await app.call_tool(tool_name, args))
    return asyncio.run(run())


# ---------------------------------------------------------------------------
# write_episode
# ---------------------------------------------------------------------------

def test_write_episode_tool_returns_response(app) -> None:
    result = _call(app, "write_episode", {
        "content": "Added sessions table.",
        "event_type": "action",
        "agent_id": "claude-code",
        "namespace": "global",
    })
    assert "episode_id" in result
    assert "session_id" in result
    assert result["sequence"] == 1
    assert len(result["event_hash"]) == 64


def test_write_episode_tool_sequential_events(app) -> None:
    """Multiple writes to the same session produce sequential events."""
    sid = "ses-mcp-seq-001"
    r1 = _call(app, "write_episode", {
        "content": "First.", "event_type": "action",
        "agent_id": "agent", "session_id": sid, "namespace": "global",
    })
    r2 = _call(app, "write_episode", {
        "content": "Second.", "event_type": "decision",
        "agent_id": "agent", "session_id": sid, "namespace": "global",
    })
    assert r1["sequence"] == 1
    assert r2["sequence"] == 2
    assert r1["session_id"] == r2["session_id"] == sid


def test_write_episode_tool_auto_generates_session_id(app) -> None:
    result = _call(app, "write_episode", {
        "content": "No session_id provided.",
        "event_type": "observation",
        "agent_id": "agent",
    })
    assert result["session_id"].startswith("ses-")


def test_write_episode_tool_passes_metadata(app, storage) -> None:
    """metadata parameter is wired through MCP tool to episode row."""
    sid = "ses-mcp-meta-write-001"
    result = _call(app, "write_episode", {
        "content": "Event with metadata.",
        "event_type": "decision",
        "agent_id": "agent",
        "session_id": sid,
        "namespace": "global",
        "metadata": {"key": "value", "score": 42},
    })
    episodes = storage.db.get_episodes(session_id=sid)
    assert episodes[0].metadata == {"key": "value", "score": 42}


# ---------------------------------------------------------------------------
# get_episodes
# ---------------------------------------------------------------------------

def test_get_episodes_tool_returns_list(app) -> None:
    sid = "ses-mcp-get-001"
    _call(app, "write_episode", {"content": "e1", "event_type": "action", "agent_id": "agent", "session_id": sid, "namespace": "global"})
    _call(app, "write_episode", {"content": "e2", "event_type": "observation", "agent_id": "agent", "session_id": sid, "namespace": "global"})

    result = _call_list(app, "get_episodes", {"caller_id": "agent", "session_id": sid, "namespace": "global"})
    assert isinstance(result, list)
    assert len(result) == 2


def test_get_episodes_tool_filters_by_event_type(app) -> None:
    sid = "ses-mcp-filter-001"
    _call(app, "write_episode", {"content": "act", "event_type": "action", "agent_id": "agent", "session_id": sid, "namespace": "global"})
    _call(app, "write_episode", {"content": "obs", "event_type": "observation", "agent_id": "agent", "session_id": sid, "namespace": "global"})

    result = _call_list(app, "get_episodes", {"caller_id": "agent", "session_id": sid, "event_type": "action", "namespace": "global"})
    assert len(result) == 1
    assert result[0]["event_type"] == "action"


def test_get_episodes_tool_returns_empty_for_unknown_session(app) -> None:
    result = _call_list(app, "get_episodes", {"caller_id": "agent", "session_id": "nonexistent"})
    assert result == []


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------

def test_end_session_tool_returns_response(app, storage) -> None:
    sid = "ses-mcp-end-001"
    storage.db.get_or_create_session(sid, creator="agent", namespace="global")

    result = _call(app, "end_session", {
        "session_id": sid,
        "agent_id": "claude-code",
        "summary": "Phase 1 complete.",
        "namespace": "global",
        "work_done": ["Added schema", "Added models"],
        "next_steps": ["Wire MCP tools"],
    })
    assert result["session_id"] == sid
    assert "episode_id" in result
    assert len(result["event_hash"]) == 64


def test_end_session_tool_marks_session_finalized(app, storage) -> None:
    sid = "ses-mcp-fin-001"
    storage.db.get_or_create_session(sid, creator="agent", namespace="global")

    _call(app, "end_session", {
        "session_id": sid, "agent_id": "agent", "summary": "Done.", "namespace": "global",
    })

    session = storage.db.get_session(sid)
    assert session is not None
    assert session.finalized is True


def test_end_session_tool_stores_handoff_metadata(app, storage) -> None:
    sid = "ses-mcp-meta-001"
    storage.db.get_or_create_session(sid, creator="agent", namespace="global")

    _call(app, "end_session", {
        "session_id": sid,
        "agent_id": "agent",
        "summary": "Done.",
        "namespace": "global",
        "work_done": ["step A"],
        "next_steps": ["step B"],
    })

    episodes = storage.db.get_episodes(session_id=sid, event_type="session_end")
    assert len(episodes) == 1
    meta = episodes[0].metadata
    assert meta["work_done"] == ["step A"]
    assert meta["next_steps"] == ["step B"]


# ---------------------------------------------------------------------------
# get_session_context — last_handoff field
# ---------------------------------------------------------------------------

def test_get_session_context_includes_last_handoff_key(app) -> None:
    """get_session_context always includes last_handoff (even if None)."""
    result = _call(app, "get_session_context", {"caller_id": "agent", "namespace": "global"})
    assert "last_handoff" in result


def test_get_session_context_last_handoff_none_when_no_sessions(app) -> None:
    ctx = _call(app, "get_session_context", {"caller_id": "fresh-agent", "namespace": "global"})
    assert ctx["last_handoff"] is None


def test_get_session_context_returns_last_handoff_after_end_session(app, storage) -> None:
    sid = "ses-mcp-ctx-001"
    storage.db.get_or_create_session(sid, creator="agent", namespace="global")
    _call(app, "end_session", {
        "session_id": sid,
        "agent_id": "claude-code",
        "summary": "Session summary for briefing.",
        "namespace": "global",
        "next_steps": ["Do Phase 2"],
    })

    ctx = _call(app, "get_session_context", {"caller_id": "agent", "namespace": "global"})
    handoff = ctx.get("last_handoff")
    assert handoff is not None
    assert handoff["summary"] == "Session summary for briefing."
    assert handoff["next_steps"] == ["Do Phase 2"]


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def test_episode_tools_are_registered(app) -> None:
    """write_episode, get_episodes, end_session are registered as MCP tools."""
    tool_names = {t.name for t in app._tool_manager._tools.values()}
    assert "write_episode" in tool_names
    assert "get_episodes" in tool_names
    assert "end_session" in tool_names


def test_total_tool_count_increased(app) -> None:
    """Tool count should be 18 (15 existing + 3 new episode tools)."""
    tool_count = len(app._tool_manager._tools)
    assert tool_count == 18
