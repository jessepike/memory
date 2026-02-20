"""Tests for EpisodeStorage API layer."""

from __future__ import annotations

import pytest

from memory_core.models import (
    EndSessionRequest,
    GetEpisodesRequest,
    WriteEpisodeRequest,
)
from memory_core.storage.db import SQLiteMemoryDB
from memory_core.storage.episode_storage import EpisodeStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path):
    d = SQLiteMemoryDB(tmp_path / "memory.db")
    d.initialize()
    return d


@pytest.fixture()
def store(db):
    return EpisodeStorage(db)


# ---------------------------------------------------------------------------
# write_episode
# ---------------------------------------------------------------------------

def test_write_episode_returns_response(store) -> None:
    req = WriteEpisodeRequest(content="Did a thing.", event_type="action", agent_id="claude-code")
    resp = store.write_episode(req)
    assert resp.episode_id
    assert resp.session_id
    assert resp.sequence == 1
    assert len(resp.event_hash) == 64


def test_write_episode_auto_creates_session(store, db) -> None:
    req = WriteEpisodeRequest(content="First event.", event_type="action", agent_id="claude-code")
    resp = store.write_episode(req)
    session = db.get_session(resp.session_id)
    assert session is not None
    assert session.creator == "claude-code"


def test_write_episode_uses_provided_session_id(store, db) -> None:
    sid = "ses-provided-001"
    # Pre-create the session
    db.get_or_create_session(sid, creator="agent", namespace="global")
    req = WriteEpisodeRequest(
        content="Event in existing session.",
        event_type="observation",
        agent_id="claude-code",
        session_id=sid,
    )
    resp = store.write_episode(req)
    assert resp.session_id == sid


def test_write_episode_auto_creates_session_from_id(store, db) -> None:
    """If session_id given but session doesn't exist, it is auto-created."""
    sid = "ses-auto-new-001"
    req = WriteEpisodeRequest(
        content="Event with new session.",
        event_type="action",
        agent_id="agent",
        session_id=sid,
    )
    resp = store.write_episode(req)
    assert resp.session_id == sid
    assert db.get_session(sid) is not None


def test_write_episode_increments_sequence(store) -> None:
    req = WriteEpisodeRequest(content="First.", event_type="action", agent_id="agent", session_id="ses-inc-001")
    r1 = store.write_episode(req)
    req2 = WriteEpisodeRequest(content="Second.", event_type="action", agent_id="agent", session_id="ses-inc-001")
    r2 = store.write_episode(req2)
    assert r1.sequence == 1
    assert r2.sequence == 2


def test_write_episode_dict_input(store) -> None:
    resp = store.write_episode({
        "content": "Dict input.",
        "event_type": "observation",
        "agent_id": "agent",
    })
    assert resp.episode_id


def test_write_episode_with_metadata(store, db) -> None:
    req = WriteEpisodeRequest(
        content="Event with metadata.",
        event_type="decision",
        agent_id="agent",
        metadata={"key": "value", "count": 42},
    )
    resp = store.write_episode(req)
    episodes = db.get_episodes(session_id=resp.session_id)
    assert episodes[0].metadata == {"key": "value", "count": 42}


def test_write_episode_with_source_ref(store, db) -> None:
    req = WriteEpisodeRequest(
        content="From commit.",
        event_type="milestone",
        agent_id="agent",
        source_ref="commit:abc1234",
    )
    resp = store.write_episode(req)
    episodes = db.get_episodes(session_id=resp.session_id)
    assert episodes[0].source_ref == "commit:abc1234"


# ---------------------------------------------------------------------------
# get_episodes
# ---------------------------------------------------------------------------

def _write_n_episodes(store, n: int, session_id: str, namespace: str = "global") -> None:
    for i in range(n):
        store.write_episode(WriteEpisodeRequest(
            content=f"event {i}",
            event_type="action",
            agent_id="agent",
            session_id=session_id,
            namespace=namespace,
        ))


def test_get_episodes_by_session_id(store) -> None:
    _write_n_episodes(store, 3, "ses-get-001")
    _write_n_episodes(store, 2, "ses-get-002")

    req = GetEpisodesRequest(session_id="ses-get-001")
    eps = store.get_episodes(req)
    assert len(eps) == 3
    assert all(e.session_id == "ses-get-001" for e in eps)


def test_get_episodes_namespace_filter(store) -> None:
    _write_n_episodes(store, 2, "ses-ns-001", namespace="ns-a")
    _write_n_episodes(store, 2, "ses-ns-002", namespace="ns-b")

    # allowed_namespaces restricts to ns-a only
    req = GetEpisodesRequest()
    eps = store.get_episodes(req, allowed_namespaces=["ns-a"])
    assert len(eps) == 2
    assert all(e.namespace == "ns-a" for e in eps)


def test_get_episodes_event_type_filter(store) -> None:
    sid = "ses-type-001"
    store.write_episode(WriteEpisodeRequest(content="act", event_type="action", agent_id="a", session_id=sid))
    store.write_episode(WriteEpisodeRequest(content="obs", event_type="observation", agent_id="a", session_id=sid))
    store.write_episode(WriteEpisodeRequest(content="dec", event_type="decision", agent_id="a", session_id=sid))

    req = GetEpisodesRequest(session_id=sid, event_type="observation")
    eps = store.get_episodes(req)
    assert len(eps) == 1
    assert eps[0].event_type == "observation"


def test_get_episodes_limit(store) -> None:
    _write_n_episodes(store, 10, "ses-lim-001")
    req = GetEpisodesRequest(session_id="ses-lim-001", limit=5)
    eps = store.get_episodes(req)
    assert len(eps) == 5


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------

def test_end_session_writes_session_end_episode(store, db) -> None:
    sid = "ses-end-001"
    db.get_or_create_session(sid, creator="agent", namespace="global")
    req = EndSessionRequest(
        session_id=sid,
        agent_id="claude-code",
        summary="Work is done.",
    )
    resp = store.end_session(req)

    assert resp.session_id == sid
    assert resp.episode_id
    assert len(resp.event_hash) == 64

    episodes = db.get_episodes(session_id=sid, event_type="session_end")
    assert len(episodes) == 1
    assert episodes[0].content == "Work is done."
    assert episodes[0].event_type == "session_end"


def test_end_session_marks_session_finalized(store, db) -> None:
    sid = "ses-fin-001"
    db.get_or_create_session(sid, creator="agent", namespace="global")
    req = EndSessionRequest(session_id=sid, agent_id="agent", summary="Done.")
    store.end_session(req)

    session = db.get_session(sid)
    assert session is not None
    assert session.finalized is True


def test_end_session_stores_handoff_metadata(store, db) -> None:
    sid = "ses-meta-001"
    db.get_or_create_session(sid, creator="agent", namespace="global")
    req = EndSessionRequest(
        session_id=sid,
        agent_id="claude-code",
        summary="Session complete.",
        work_done=["Task A", "Task B"],
        next_steps=["Task C"],
        open_questions=["Q1"],
        commits=["abc1234 feat: add thing"],
        key_files_changed=["src/main.py"],
    )
    store.end_session(req)

    episodes = db.get_episodes(session_id=sid, event_type="session_end")
    meta = episodes[0].metadata
    assert meta is not None
    assert meta["work_done"] == ["Task A", "Task B"]
    assert meta["next_steps"] == ["Task C"]
    assert meta["open_questions"] == ["Q1"]
    assert meta["commits"] == ["abc1234 feat: add thing"]
    assert meta["key_files_changed"] == ["src/main.py"]
    assert meta["handoff"] is True


def test_end_session_auto_creates_session_if_missing(store, db) -> None:
    """end_session creates the session row if it doesn't exist yet."""
    sid = "ses-autocreate-001"
    req = EndSessionRequest(session_id=sid, agent_id="agent", summary="Done.")
    store.end_session(req)
    assert db.get_session(sid) is not None


# ---------------------------------------------------------------------------
# get_last_handoff
# ---------------------------------------------------------------------------

def test_get_last_handoff_returns_none_when_empty(store) -> None:
    result = store.get_last_handoff(namespaces=["global"])
    assert result is None


def test_get_last_handoff_returns_latest_session_end(store, db) -> None:
    sid = "ses-handoff-001"
    db.get_or_create_session(sid, creator="agent", namespace="global")
    req = EndSessionRequest(
        session_id=sid,
        agent_id="claude-code",
        summary="Phase 1 complete.",
        next_steps=["Start Phase 2"],
        namespace="global",
    )
    store.end_session(req)

    handoff = store.get_last_handoff(namespaces=["global"])
    assert handoff is not None
    assert handoff["summary"] == "Phase 1 complete."
    assert handoff["next_steps"] == ["Start Phase 2"]
    assert handoff["session_id"] == sid


def test_get_last_handoff_respects_namespace(store, db) -> None:
    """Handoffs are namespace-scoped; wrong namespace returns None."""
    sid = "ses-ns-handoff-001"
    db.get_or_create_session(sid, creator="agent", namespace="ns-x")
    req = EndSessionRequest(
        session_id=sid,
        agent_id="agent",
        summary="Done in ns-x.",
        namespace="ns-x",
    )
    store.end_session(req)

    # Correct namespace → found
    handoff = store.get_last_handoff(namespaces=["ns-x"])
    assert handoff is not None

    # Wrong namespace → None
    handoff_other = store.get_last_handoff(namespaces=["ns-y"])
    assert handoff_other is None


# ---------------------------------------------------------------------------
# verify_chain
# ---------------------------------------------------------------------------

def test_verify_chain_empty_session(store, db) -> None:
    sid = "ses-verify-empty"
    db.get_or_create_session(sid, creator="agent", namespace="global")
    result = store.verify_chain(sid)
    assert result["valid"] is True
    assert result["event_count"] == 0


def test_verify_chain_valid(store) -> None:
    sid = "ses-verify-valid"
    _write_n_episodes(store, 5, sid)
    result = store.verify_chain(sid)
    assert result["valid"] is True
    assert result["event_count"] == 5
    assert result["first_broken_sequence"] is None


def test_verify_chain_detects_tampering(store, db) -> None:
    """Directly modifying episode content breaks the chain."""
    sid = "ses-verify-tamper"
    _write_n_episodes(store, 3, sid)

    # Tamper with the second episode's content directly in SQLite
    with db.begin_immediate() as conn:
        conn.execute(
            "UPDATE episodes SET content = 'TAMPERED' WHERE session_id = ? AND sequence = 2;",
            (sid,),
        )

    result = store.verify_chain(sid)
    assert result["valid"] is False
    assert result["first_broken_sequence"] == 2


def test_verify_chain_scale_100_events_5_sessions(store) -> None:
    """Success Criterion 3: verify_chain valid across 100+ events in 5+ sessions."""
    session_ids = [f"ses-scale-{i:03d}" for i in range(6)]
    events_per_session = 20  # 6 × 20 = 120 events total

    for sid in session_ids:
        _write_n_episodes(store, events_per_session, sid)

    for sid in session_ids:
        result = store.verify_chain(sid)
        assert result["valid"] is True, f"Chain invalid for {sid}: {result['error']}"
        assert result["event_count"] == events_per_session


# ---------------------------------------------------------------------------
# Concurrent writes (Success Criterion 5)
# ---------------------------------------------------------------------------

def test_atomic_sequence_concurrent_writes(store) -> None:
    """Success Criterion 5: concurrent writes produce monotonic, gapless sequences per session."""
    import threading

    sid = "ses-concurrent-001"
    n_threads = 10
    results: list = []
    errors: list = []

    def write_one(i: int) -> None:
        try:
            resp = store.write_episode(WriteEpisodeRequest(
                content=f"concurrent event {i}",
                event_type="action",
                agent_id="agent",
                session_id=sid,
                namespace="global",
            ))
            results.append(resp.sequence)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write_one, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent writes produced errors: {errors}"
    assert len(results) == n_threads

    # Sequences must be exactly {1, 2, ..., n_threads} — no gaps, no duplicates
    assert sorted(results) == list(range(1, n_threads + 1))
