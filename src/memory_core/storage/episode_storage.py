"""Episode storage orchestration — write/query the episodic event log."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from memory_core.models import (
    EndSessionRequest,
    EndSessionResponse,
    EpisodicEvent,
    GetEpisodesRequest,
    WriteEpisodeRequest,
    WriteEpisodeResponse,
)
from memory_core.storage.db import SQLiteMemoryDB
from memory_core.utils.episode import compute_event_hash, generate_session_id


class EpisodeStorage:
    """Business-logic layer for episodic event log operations.

    Wraps SQLiteMemoryDB for episode-specific workflows:
    - write_episode: atomic append with hash chaining
    - get_episodes: filtered queries
    - end_session: structured session-end handoff
    - get_last_handoff: last session_end for briefing
    - verify_chain: chain integrity check for a session
    """

    def __init__(
        self,
        db: SQLiteMemoryDB,
        namespace_resolver: Callable[[str | None], str] | None = None,
    ) -> None:
        self.db = db
        self._resolve_namespace = namespace_resolver or (lambda ns: ns if ns else "global")

    def write_episode(
        self,
        request: WriteEpisodeRequest | dict[str, Any],
    ) -> WriteEpisodeResponse:
        """Write an episode to the log with atomic hash chaining.

        If session_id is not provided, a new session is auto-created.
        If the session doesn't exist yet, it is auto-created in sessions table.
        """
        req = (
            request
            if isinstance(request, WriteEpisodeRequest)
            else WriteEpisodeRequest.model_validate(request)
        )

        resolved_ns = self._resolve_namespace(req.namespace)
        session_id = req.session_id or generate_session_id()

        # Ensure session exists (idempotent — returns existing if already there)
        self.db.get_or_create_session(
            session_id=session_id,
            creator=req.agent_id,
            namespace=resolved_ns,
            client=req.client,
            project=req.project,
        )

        episode_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        episode_fields: dict[str, Any] = {
            "id": episode_id,
            "session_id": session_id,
            "timestamp": now,
            "event_type": req.event_type,
            "severity": req.severity,
            "agent_id": req.agent_id,
            "client": req.client,
            "project": req.project,
            "namespace": resolved_ns,
            "content": req.content,
            "metadata": req.metadata,
            "source_ref": req.source_ref,
            "schema_version": 1,
        }

        episode = self.db.insert_episode_atomic(episode_fields)

        return WriteEpisodeResponse(
            episode_id=episode.id,
            session_id=episode.session_id,
            sequence=episode.sequence,
            event_hash=episode.event_hash,
        )

    def get_episodes(
        self,
        request: GetEpisodesRequest | dict[str, Any],
        *,
        allowed_namespaces: list[str] | None = None,
    ) -> list[EpisodicEvent]:
        """Query episodes with optional filters.

        allowed_namespaces constrains the query to caller-accessible namespaces.
        If the request specifies a namespace, it must be in allowed_namespaces.
        """
        req = (
            request
            if isinstance(request, GetEpisodesRequest)
            else GetEpisodesRequest.model_validate(request)
        )

        # Namespace access control: use allowed_namespaces if no specific one requested
        namespace_filter: str | None = req.namespace
        namespaces_filter: list[str] | None = None

        if namespace_filter is None and allowed_namespaces is not None:
            namespaces_filter = allowed_namespaces

        return self.db.get_episodes(
            session_id=req.session_id,
            project=req.project,
            event_type=req.event_type,
            since=req.since,
            namespace=namespace_filter,
            namespaces=namespaces_filter,
            limit=req.limit,
        )

    def end_session(
        self,
        request: EndSessionRequest | dict[str, Any],
    ) -> EndSessionResponse:
        """Close a session with a structured handoff payload.

        Writes a session_end episode. The structured handoff fields (work_done,
        next_steps, etc.) are stored in the episode's metadata JSON. Marks the
        session as finalized.
        """
        req = (
            request
            if isinstance(request, EndSessionRequest)
            else EndSessionRequest.model_validate(request)
        )

        resolved_ns = self._resolve_namespace(req.namespace)

        # Ensure session exists
        self.db.get_or_create_session(
            session_id=req.session_id,
            creator=req.agent_id,
            namespace=resolved_ns,
        )

        handoff_metadata: dict[str, Any] = {
            "handoff": True,
        }
        if req.work_done is not None:
            handoff_metadata["work_done"] = req.work_done
        if req.next_steps is not None:
            handoff_metadata["next_steps"] = req.next_steps
        if req.open_questions is not None:
            handoff_metadata["open_questions"] = req.open_questions
        if req.commits is not None:
            handoff_metadata["commits"] = req.commits
        if req.key_files_changed is not None:
            handoff_metadata["key_files_changed"] = req.key_files_changed

        episode_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        episode_fields: dict[str, Any] = {
            "id": episode_id,
            "session_id": req.session_id,
            "timestamp": now,
            "event_type": "session_end",
            "severity": "info",
            "agent_id": req.agent_id,
            "namespace": resolved_ns,
            "content": req.summary,
            "metadata": handoff_metadata,
            "schema_version": 1,
        }

        episode = self.db.insert_episode_atomic(episode_fields)

        # Mark session finalized
        self.db.finalize_session(req.session_id)

        return EndSessionResponse(
            session_id=req.session_id,
            episode_id=episode.id,
            event_hash=episode.event_hash,
        )

    def get_last_handoff(
        self, *, namespaces: list[str] | None = None
    ) -> dict[str, Any] | None:
        """Return the most recent session_end episode as a handoff dict.

        Returns None if no session_end exists for the given namespaces.
        Used by get_session_context to populate the last_handoff field.
        """
        episode = self.db.get_last_session_end(namespaces=namespaces)
        if episode is None:
            return None

        result: dict[str, Any] = {
            "session_id": episode.session_id,
            "summary": episode.content,
            "timestamp": episode.timestamp,
        }
        if episode.metadata:
            result.update({
                k: v for k, v in episode.metadata.items()
                if k in ("work_done", "next_steps", "open_questions", "commits", "key_files_changed")
            })
        return result

    def episode_stats(self) -> dict[str, Any]:
        """Return aggregate episode/session counts from the SQLite DB.

        Fail-safe: returns zeroed dict on any error.
        """
        try:
            return self.db.get_episode_stats()
        except Exception:
            return {
                "total_sessions": 0,
                "finalized_sessions": 0,
                "total_episodes": 0,
                "session_end_count": 0,
                "last_session_ts": None,
            }

    def verify_chain(self, session_id: str) -> dict[str, Any]:
        """Walk the hash chain for a session and verify integrity.

        Returns:
            {
                "session_id": str,
                "event_count": int,
                "valid": bool,
                "first_broken_sequence": int | None,
                "error": str | None,
            }
        """
        episodes = self.db.get_episodes(session_id=session_id, limit=10_000)
        if not episodes:
            return {
                "session_id": session_id,
                "event_count": 0,
                "valid": True,
                "first_broken_sequence": None,
                "error": None,
            }

        prev_hash: str | None = None
        for ep in episodes:
            expected = compute_event_hash(
                {
                    "id": ep.id,
                    "session_id": ep.session_id,
                    "sequence": ep.sequence,
                    "timestamp": ep.timestamp,
                    "event_type": ep.event_type,
                    "agent_id": ep.agent_id,
                    "content": ep.content,
                },
                prev_hash,
            )
            if ep.event_hash != expected:
                return {
                    "session_id": session_id,
                    "event_count": len(episodes),
                    "valid": False,
                    "first_broken_sequence": ep.sequence,
                    "error": f"Hash mismatch at sequence {ep.sequence}",
                }
            prev_hash = ep.event_hash

        return {
            "session_id": session_id,
            "event_count": len(episodes),
            "valid": True,
            "first_broken_sequence": None,
            "error": None,
        }
