"""Tests for episode + session DB layer in SQLiteMemoryDB."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from memory_core.storage.db import SQLiteMemoryDB
from memory_core.utils.episode import compute_event_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db(tmp_path) -> SQLiteMemoryDB:
    db = SQLiteMemoryDB(tmp_path / "memory.db")
    db.initialize()
    return db


def _episode_fields(
    *,
    session_id: str,
    agent_id: str = "claude-code",
    content: str = "Did a thing.",
    event_type: str = "action",
    namespace: str = "global",
) -> dict:
    return {
        "id": str(uuid4()),
        "session_id": session_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "severity": "info",
        "agent_id": agent_id,
        "namespace": namespace,
        "content": content,
    }


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_schema_creates_sessions_table(tmp_path) -> None:
    db = _db(tmp_path)
    row = db._connect().execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions';"
    ).fetchone()
    assert row is not None


def test_schema_creates_episodes_table(tmp_path) -> None:
    db = _db(tmp_path)
    row = db._connect().execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='episodes';"
    ).fetchone()
    assert row is not None


def test_schema_creates_indexes(tmp_path) -> None:
    db = _db(tmp_path)
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_episodes_%';"
        ).fetchall()
    index_names = {r["name"] for r in rows}
    assert "idx_episodes_session" in index_names
    assert "idx_episodes_timestamp" in index_names
    assert "idx_episodes_type" in index_names


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def test_get_or_create_session_creates_new(tmp_path) -> None:
    db = _db(tmp_path)
    session_id = "ses-test-001"
    record = db.get_or_create_session(session_id, creator="claude-code", namespace="global")
    assert record.session_id == session_id
    assert record.creator == "claude-code"
    assert record.finalized is False
    assert record.last_sequence == 0
    assert record.chain_head is None


def test_get_or_create_session_idempotent(tmp_path) -> None:
    db = _db(tmp_path)
    session_id = "ses-test-002"
    r1 = db.get_or_create_session(session_id, creator="claude-code", namespace="global")
    r2 = db.get_or_create_session(session_id, creator="claude-code", namespace="global")
    assert r1.session_id == r2.session_id
    # Second call returns existing — start_ts unchanged
    assert r1.start_ts == r2.start_ts


def test_get_session_returns_none_for_missing(tmp_path) -> None:
    db = _db(tmp_path)
    assert db.get_session("nonexistent") is None


def test_finalize_session(tmp_path) -> None:
    db = _db(tmp_path)
    session_id = "ses-test-003"
    db.get_or_create_session(session_id, creator="agent", namespace="global")
    db.finalize_session(session_id)
    record = db.get_session(session_id)
    assert record is not None
    assert record.finalized is True
    assert record.end_ts is not None


# ---------------------------------------------------------------------------
# Episode atomic append
# ---------------------------------------------------------------------------

def test_insert_episode_atomically_assigns_sequence(tmp_path) -> None:
    db = _db(tmp_path)
    session_id = "ses-seq-001"
    db.get_or_create_session(session_id, creator="agent", namespace="global")

    ep1 = db.insert_episode_atomic(_episode_fields(session_id=session_id, content="first"))
    ep2 = db.insert_episode_atomic(_episode_fields(session_id=session_id, content="second"))
    ep3 = db.insert_episode_atomic(_episode_fields(session_id=session_id, content="third"))

    assert ep1.sequence == 1
    assert ep2.sequence == 2
    assert ep3.sequence == 3


def test_insert_episode_computes_hashes(tmp_path) -> None:
    db = _db(tmp_path)
    session_id = "ses-hash-001"
    db.get_or_create_session(session_id, creator="agent", namespace="global")

    ep1 = db.insert_episode_atomic(_episode_fields(session_id=session_id, content="first"))
    ep2 = db.insert_episode_atomic(_episode_fields(session_id=session_id, content="second"))

    # First event has no previous_hash
    assert ep1.previous_hash is None
    assert len(ep1.event_hash) == 64

    # Second event's previous_hash == first event's hash
    assert ep2.previous_hash == ep1.event_hash
    assert ep2.event_hash != ep1.event_hash


def test_insert_episode_updates_session_chain_head(tmp_path) -> None:
    db = _db(tmp_path)
    session_id = "ses-chain-001"
    db.get_or_create_session(session_id, creator="agent", namespace="global")

    ep = db.insert_episode_atomic(_episode_fields(session_id=session_id))
    session = db.get_session(session_id)

    assert session is not None
    assert session.chain_head == ep.event_hash
    assert session.last_sequence == 1


def test_insert_episode_raises_for_missing_session(tmp_path) -> None:
    db = _db(tmp_path)
    with pytest.raises(ValueError, match="Session not found"):
        db.insert_episode_atomic(_episode_fields(session_id="does-not-exist"))


def test_episode_hashes_match_compute_event_hash(tmp_path) -> None:
    """Verify stored hashes match independent recomputation."""
    db = _db(tmp_path)
    session_id = "ses-verify-001"
    db.get_or_create_session(session_id, creator="agent", namespace="global")

    ep1 = db.insert_episode_atomic(_episode_fields(session_id=session_id, content="first"))
    ep2 = db.insert_episode_atomic(_episode_fields(session_id=session_id, content="second"))

    expected_h1 = compute_event_hash(
        {"id": ep1.id, "session_id": ep1.session_id, "sequence": ep1.sequence,
         "timestamp": ep1.timestamp, "event_type": ep1.event_type,
         "agent_id": ep1.agent_id, "content": ep1.content},
        None,
    )
    expected_h2 = compute_event_hash(
        {"id": ep2.id, "session_id": ep2.session_id, "sequence": ep2.sequence,
         "timestamp": ep2.timestamp, "event_type": ep2.event_type,
         "agent_id": ep2.agent_id, "content": ep2.content},
        ep1.event_hash,
    )

    assert ep1.event_hash == expected_h1
    assert ep2.event_hash == expected_h2


def test_unique_sequence_constraint_prevents_duplicates(tmp_path) -> None:
    """SQLite UNIQUE(session_id, sequence) prevents double-inserts of same sequence."""
    db = _db(tmp_path)
    session_id = "ses-dup-001"
    db.get_or_create_session(session_id, creator="agent", namespace="global")

    fields = _episode_fields(session_id=session_id)
    db.insert_episode_atomic(fields)

    # Manually try to insert same session_id + sequence=1 again (bypassing our API)
    with pytest.raises(Exception):  # sqlite3.IntegrityError
        with db.begin_immediate() as conn:
            conn.execute(
                """INSERT INTO episodes (id, session_id, sequence, timestamp, event_type,
                severity, agent_id, namespace, content, event_hash, schema_version)
                VALUES (?, ?, 1, ?, 'action', 'info', 'agent', 'global', 'dup', 'abc', 1)""",
                (str(uuid4()), session_id, datetime.now(UTC).isoformat()),
            )


# ---------------------------------------------------------------------------
# get_episodes queries
# ---------------------------------------------------------------------------

def _setup_episodes(db: SQLiteMemoryDB) -> tuple[str, str]:
    """Create two sessions with episodes for query tests."""
    sid1 = "ses-q-001"
    sid2 = "ses-q-002"
    db.get_or_create_session(sid1, creator="agent", namespace="global", project="proj-a")
    db.get_or_create_session(sid2, creator="agent", namespace="ns-b", project="proj-b")

    db.insert_episode_atomic(_episode_fields(session_id=sid1, content="a1", event_type="action", namespace="global"))
    db.insert_episode_atomic(_episode_fields(session_id=sid1, content="a2", event_type="decision", namespace="global"))
    db.insert_episode_atomic(_episode_fields(session_id=sid2, content="b1", event_type="observation", namespace="ns-b"))
    return sid1, sid2


def test_get_episodes_by_session_id(tmp_path) -> None:
    db = _db(tmp_path)
    sid1, sid2 = _setup_episodes(db)
    eps = db.get_episodes(session_id=sid1)
    assert len(eps) == 2
    assert all(e.session_id == sid1 for e in eps)


def test_get_episodes_by_event_type(tmp_path) -> None:
    db = _db(tmp_path)
    sid1, _ = _setup_episodes(db)
    eps = db.get_episodes(event_type="decision")
    assert len(eps) == 1
    assert eps[0].event_type == "decision"


def test_get_episodes_by_namespace(tmp_path) -> None:
    db = _db(tmp_path)
    _setup_episodes(db)
    eps = db.get_episodes(namespace="ns-b")
    assert len(eps) == 1
    assert eps[0].namespace == "ns-b"


def test_get_episodes_by_namespaces_list(tmp_path) -> None:
    db = _db(tmp_path)
    _setup_episodes(db)
    eps = db.get_episodes(namespaces=["global", "ns-b"])
    assert len(eps) == 3


def test_get_episodes_returns_chronological_order(tmp_path) -> None:
    db = _db(tmp_path)
    sid1, _ = _setup_episodes(db)
    eps = db.get_episodes(session_id=sid1)
    sequences = [e.sequence for e in eps]
    assert sequences == sorted(sequences)


def test_get_last_session_end_returns_none_when_empty(tmp_path) -> None:
    db = _db(tmp_path)
    result = db.get_last_session_end()
    assert result is None


def test_get_last_session_end_returns_correct_episode(tmp_path) -> None:
    db = _db(tmp_path)
    sid = "ses-end-001"
    db.get_or_create_session(sid, creator="agent", namespace="global")
    db.insert_episode_atomic(_episode_fields(session_id=sid, event_type="action", namespace="global"))
    db.insert_episode_atomic({
        **_episode_fields(session_id=sid, namespace="global"),
        "event_type": "session_end",
        "content": "Session done.",
    })

    ep = db.get_last_session_end(namespaces=["global"])
    assert ep is not None
    assert ep.event_type == "session_end"
    assert ep.content == "Session done."


# ---------------------------------------------------------------------------
# Multiple independent sessions (chain isolation)
# ---------------------------------------------------------------------------

def test_multiple_sessions_have_independent_chains(tmp_path) -> None:
    """Events in session A do not affect session B's chain."""
    db = _db(tmp_path)
    sid_a = "ses-a"
    sid_b = "ses-b"
    db.get_or_create_session(sid_a, creator="agent", namespace="global")
    db.get_or_create_session(sid_b, creator="agent", namespace="global")

    ep_a1 = db.insert_episode_atomic(_episode_fields(session_id=sid_a, content="a1"))
    ep_b1 = db.insert_episode_atomic(_episode_fields(session_id=sid_b, content="b1"))
    ep_a2 = db.insert_episode_atomic(_episode_fields(session_id=sid_a, content="a2"))

    # Both sessions start from sequence=1 independently
    assert ep_a1.sequence == 1
    assert ep_b1.sequence == 1
    assert ep_a2.sequence == 2

    # Session A's chain is independent
    assert ep_a1.previous_hash is None
    assert ep_a2.previous_hash == ep_a1.event_hash

    # Session B's first event also has no previous_hash
    assert ep_b1.previous_hash is None
