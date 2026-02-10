---
project: "Memory Layer"
type: "usage-guide"
updated: "2026-02-10"
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
