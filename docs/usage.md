---
project: "Memory Layer"
type: "usage-guide"
updated: "2026-02-20"
---

# Memory Layer Usage Guide

This guide explains how to use the Memory Layer MCP tools in practice.

## Quick Start

1. Start the MCP server:

```bash
python -m memory_core.access.mcp_server
```

2. Use MCP tool calls from your client (for example Claude Code connected to this server).

3. Use these caller IDs consistently:
- Project-scoped agent: `caller_id` / `writer_id` tied to a project profile
- Cross-scope consumer: `caller_id` with `can_cross_scope=true`

## Scoping Rules You Should Expect

- `namespace="project-x"` reads/writes project scope.
- `namespace` omitted on reads is only allowed for callers with cross-scope permission.
- Non-privileged ID-based update/archive requires explicit matching `namespace`.
- Private namespace requires explicit request and permission.

When scope is denied, tools return:

```json
{
  "error_code": "forbidden_scope",
  "id": "optional-memory-id",
  "namespace": "requested-or-row-namespace",
  "caller_id": "your-caller-id"
}
```

## Core Tool Examples

### 1. Write Memory

```json
{
  "tool": "write_memory",
  "arguments": {
    "content": "User prefers concise status updates.",
    "memory_type": "preference",
    "namespace": "memory-layer",
    "writer_id": "memory-layer-agent",
    "writer_type": "agent",
    "source_ref": "commit:abc1234",
    "confidence": 0.95
  }
}
```

Typical response:

```json
{
  "id": "uuid",
  "action": "added",
  "similar_id": null,
  "similarity": null
}
```

If deduplicated:

```json
{
  "id": "uuid",
  "action": "skipped",
  "similar_id": "existing-uuid",
  "similarity": 0.93
}
```

### 2. Search Memories

```json
{
  "tool": "search_memories",
  "arguments": {
    "query": "status updates preference",
    "caller_id": "memory-layer-agent",
    "namespace": "memory-layer",
    "limit": 5
  }
}
```

Response shape can be one result object or a result list depending on MCP response wrapping; handle both.

### 3. Get One Memory

```json
{
  "tool": "get_memory",
  "arguments": {
    "id": "uuid",
    "caller_id": "memory-layer-agent"
  }
}
```

### 4. Get Recent

```json
{
  "tool": "get_recent",
  "arguments": {
    "caller_id": "memory-layer-agent",
    "namespace": "memory-layer",
    "days": 7,
    "limit": 20
  }
}
```

### 5. Get Session Context

```json
{
  "tool": "get_session_context",
  "arguments": {
    "caller_id": "memory-layer-agent",
    "namespace": "memory-layer",
    "query": "current implementation risks",
    "limit": 10
  }
}
```

### 6. Update Memory (Non-Privileged Path)

For non-privileged callers, `namespace` is required and must match the row namespace.

```json
{
  "tool": "update_memory",
  "arguments": {
    "id": "uuid",
    "caller_id": "memory-layer-agent",
    "namespace": "memory-layer",
    "confidence": 0.9
  }
}
```

### 7. Archive Memory (Non-Privileged Path)

```json
{
  "tool": "archive_memory",
  "arguments": {
    "id": "uuid",
    "caller_id": "memory-layer-agent",
    "namespace": "memory-layer"
  }
}
```

### 8. Review Candidates

```json
{
  "tool": "review_candidates",
  "arguments": {
    "caller_id": "memory-layer-agent",
    "namespace": "memory-layer",
    "limit": 20
  }
}
```

### 9. Get Stats

```json
{
  "tool": "get_stats",
  "arguments": {
    "caller_id": "krypton"
  }
}
```

Includes drift counters:
- `sqlite_committed_missing_chroma`
- `sqlite_archived_present_chroma`
- `chroma_orphans`
- `last_reconcile_at`

## Maintenance and Health Tools

These are useful for operations and debugging:

- `reconcile_dual_store`
- `list_failed_memories`
- `retry_failed_memory`
- `archive_failed_memory`
- `health`

## Recommended Workflow

1. `write_memory` during session when an atomic fact matters across sessions.
2. `get_session_context` at session start.
3. `search_memories` for targeted recall.
4. `review_candidates` periodically.
5. `get_stats` and `reconcile_dual_store` during maintenance windows.

## Verification Commands

Run integration smoke check:

```bash
python scripts/mcp_smoke.py --json
```

Run full tests:

```bash
python -m pytest -q
```

## Capabilities Registry Install (Codex / Claude Code / Gemini)

If you use the central capabilities registry entry (`memory-layer`), install via:

```bash
# Codex
cd ~/code/_shared/capabilities-registry
./scripts/install-mcp-codex.sh memory-layer --apply

# Claude Code (project scope)
./scripts/install-mcp-claude.sh memory-layer --scope project --apply

# Gemini (user scope)
./scripts/install-mcp-gemini.sh memory-layer --scope user --apply
```

Dry-run variants (without `--apply`) print exact commands before execution.

---

## Episodic Event Log (v1.1+)

The episodic log records agent sessions as an append-only, hash-chained audit trail. Use it for session handoffs and governance.

### write_episode — Record an event

```json
{
  "tool": "write_episode",
  "arguments": {
    "content": "Added client_profiles to production config.",
    "event_type": "action",
    "agent_id": "claude-code",
    "session_id": "ses-20260220-001",
    "project": "memory-layer",
    "namespace": "global",
    "source_ref": "commit:e997266"
  }
}
```

`session_id` is auto-generated if omitted. The session is auto-created if it doesn't exist.
`source_ref` links the episode to evidence (commit SHA, file path, PR URL, etc.).

### end_session — Close a session with a handoff

```json
{
  "tool": "end_session",
  "arguments": {
    "session_id": "ses-20260220-001",
    "agent_id": "claude-code",
    "summary": "Phase 3 implemented: verify_chain, source_ref, episode stats.",
    "namespace": "global",
    "work_done": ["Added verify_chain MCP tool", "Added source_ref to write_memory"],
    "next_steps": ["Run mcp_stdio_test.py to verify tool count"],
    "commits": ["abc1234"]
  }
}
```

### get_episodes — Query the event log

```json
{
  "tool": "get_episodes",
  "arguments": {
    "caller_id": "claude-code",
    "project": "memory-layer",
    "event_type": "action",
    "limit": 20
  }
}
```

Filter by `session_id`, `project`, `event_type`, `since` (ISO timestamp), or `namespace`.

### verify_chain — Audit hash chain integrity

```json
{
  "tool": "verify_chain",
  "arguments": {
    "session_id": "ses-20260220-001",
    "caller_id": "claude-code"
  }
}
```

Response:

```json
{
  "session_id": "ses-20260220-001",
  "event_count": 5,
  "valid": true,
  "first_broken_sequence": null,
  "error": null
}
```

`valid: false` means the chain was tampered with. `first_broken_sequence` identifies the earliest broken link.

### get_session_context — Session start briefing

```json
{
  "tool": "get_session_context",
  "arguments": {
    "caller_id": "claude-code",
    "namespace": "global"
  }
}
```

Returns recent memories plus `last_handoff` (the most recent `end_session` payload for this namespace). Use at session start to brief the agent on prior context.

### get_usage_report — Tool + episode stats

```json
{
  "tool": "get_usage_report",
  "arguments": {
    "caller_id": "claude-code",
    "days": 7
  }
}
```

Response includes an `episodes` key with DB-level aggregate stats:

```json
{
  "period_days": 7,
  "total_calls": 42,
  "by_tool": { "write_memory": 10, "search_memories": 20 },
  ...
  "episodes": {
    "total_sessions": 5,
    "finalized_sessions": 4,
    "total_episodes": 38,
    "session_end_count": 4,
    "last_session_ts": "2026-02-20T04:00:00Z"
  }
}
```
