"""Tests for episode utilities: compute_event_hash and generate_session_id."""

import re

import pytest

from memory_core.utils.episode import compute_event_hash, generate_session_id


# ---------------------------------------------------------------------------
# compute_event_hash
# ---------------------------------------------------------------------------

def _make_event(
    *,
    id: str = "e1",
    session_id: str = "ses-01",
    sequence: int = 1,
    timestamp: str = "2026-02-19T16:00:00+00:00",
    event_type: str = "action",
    agent_id: str = "claude-code",
    content: str = "Did a thing.",
) -> dict:
    return {
        "id": id,
        "session_id": session_id,
        "sequence": sequence,
        "timestamp": timestamp,
        "event_type": event_type,
        "agent_id": agent_id,
        "content": content,
    }


def test_hash_is_64_hex_chars() -> None:
    event = _make_event()
    h = compute_event_hash(event, None)
    assert len(h) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", h)


def test_hash_deterministic() -> None:
    event = _make_event()
    h1 = compute_event_hash(event, None)
    h2 = compute_event_hash(event, None)
    assert h1 == h2


def test_hash_changes_with_previous_hash() -> None:
    event = _make_event()
    h_first = compute_event_hash(event, None)
    h_second = compute_event_hash(event, h_first)
    assert h_first != h_second


def test_hash_changes_when_content_changes() -> None:
    event_a = _make_event(content="Did thing A.")
    event_b = _make_event(content="Did thing B.")
    assert compute_event_hash(event_a, None) != compute_event_hash(event_b, None)


def test_hash_changes_when_sequence_changes() -> None:
    e1 = _make_event(sequence=1)
    e2 = _make_event(sequence=2)
    assert compute_event_hash(e1, None) != compute_event_hash(e2, None)


def test_hash_chain_links_correctly() -> None:
    """Simulates a 3-event chain; each hash depends on the previous."""
    e1 = _make_event(id="e1", sequence=1)
    e2 = _make_event(id="e2", sequence=2)
    e3 = _make_event(id="e3", sequence=3)

    h1 = compute_event_hash(e1, None)
    h2 = compute_event_hash(e2, h1)
    h3 = compute_event_hash(e3, h2)

    # Changing e2 breaks h2 and therefore h3
    e2_modified = {**e2, "content": "TAMPERED"}
    h2_bad = compute_event_hash(e2_modified, h1)
    h3_bad = compute_event_hash(e3, h2_bad)

    assert h2 != h2_bad
    assert h3 != h3_bad


# ---------------------------------------------------------------------------
# generate_session_id
# ---------------------------------------------------------------------------

def test_session_id_format() -> None:
    sid = generate_session_id()
    assert sid.startswith("ses-")
    # ses-YYYYMMDD-HHMMSS-8hex
    assert re.fullmatch(r"ses-\d{8}-\d{6}-[0-9a-f]{8}", sid)


def test_session_ids_are_unique() -> None:
    ids = {generate_session_id() for _ in range(50)}
    assert len(ids) == 50
