"""Episodic log utilities: hash chaining and session-id generation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4


def compute_event_hash(event: dict, previous_hash: str | None) -> str:
    """Compute tamper-evident SHA-256 hash for an episodic event.

    Hashes a deterministic subset of immutable fields plus the previous_hash
    (chain link). If any event is modified or deleted, all subsequent hashes
    within that session become invalid.

    Args:
        event: Dict with keys: id, session_id, sequence, timestamp,
               event_type, agent_id, content.
        previous_hash: event_hash of the prior episode in the session,
                       or None for the first event.

    Returns:
        Hex-encoded SHA-256 digest string.
    """
    payload = json.dumps(
        {
            "previous_hash": previous_hash,
            "id": event["id"],
            "session_id": event["session_id"],
            "sequence": event["sequence"],
            "timestamp": event["timestamp"],
            "event_type": event["event_type"],
            "agent_id": event["agent_id"],
            "content": event["content"],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def generate_session_id() -> str:
    """Generate a unique, human-readable session ID.

    Format: ses-YYYYMMDD-HHMMSS-<8 random hex chars>
    Example: ses-20260219-160042-a3f2b7c1
    """
    now = datetime.now(UTC)
    ts = now.strftime("%Y%m%d-%H%M%S")
    uid = uuid4().hex[:8]
    return f"ses-{ts}-{uid}"
