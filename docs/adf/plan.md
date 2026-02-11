---
type: "plan"
project: "Memory Layer"
stage: "deliver"
created: "2026-02-11"
---

# Delivery Plan

## Overview

Deploy the Memory Layer MCP server to the local agent ecosystem. The server is a Python stdio MCP server — each client spawns its own process on demand. Delivery means: register with each client, validate connectivity, confirm persistence and multi-client coexistence.

**Deployment target:** Local laptop, 3 clients (Claude Code, Codex, Gemini)

**Delivery type:** Workflow — install/activate in target environments

## Deployment Approach

### Phase A: Pre-flight

1. Ensure `.venv` is current and editable install works
2. Provision embedding model (first-run download if needed)
3. Run full test suite + smoke checks as baseline

### Phase B: Client Registration

For each client (Claude Code, Codex, Gemini):

1. Run the registry installer script with `--apply`
2. Verify the MCP server appears in client's tool list
3. Test a basic `health` tool call from the client

Order: Claude Code first (primary client, most tooling), then Codex, then Gemini.

### Phase C: Validation

3-tier testing per capabilities.md (see Testing Strategy below).

### Phase D: Closeout

Success criteria verification, access docs, archive, seal.

## Testing Strategy

### Tier 1: Automated (agent-driven)

| Test | Tool | Pass Criteria |
|------|------|---------------|
| Unit + integration suite | `pytest tests/ -q` | 36/36 pass |
| In-process smoke | `scripts/mcp_smoke.py` | 15/15 checks pass |
| Stdio transport | `scripts/mcp_stdio_test.py` | 7/7 checks pass |

**Must pass before Tier 2.**

### Tier 2: Live Client Testing (agent-driven)

From Claude Code (primary client):

| Scenario | Tool | Pass Criteria |
|----------|------|---------------|
| Health check | `health` | Returns `status: ok` |
| Write a memory | `write_memory` | Returns memory ID, no error |
| Search for it | `search_memories` | Finds the written memory |
| Get by ID | `get_memory` | Returns correct content |
| Update it | `update_memory` | Succeeds, content changed |
| Dedup test | `write_memory` (same content) | Returns `action: SKIP` |
| Review candidates | `review_candidates` | Returns list (may be empty) |
| Stats | `get_stats` | Returns counts reflecting writes |
| Archive | `archive_memory` | Succeeds |
| Session context | `get_session_context` | Returns session-scoped results |
| Cross-namespace isolation | `search_memories` with different namespace | Does not return other namespace's memories |
| Persistence | Disconnect + reconnect, `get_memory` | Memory still exists |

From Codex and Gemini: health check + write + search (connectivity confirmation).

### Tier 3: Manual (human-driven)

| Scenario | How | Pass Criteria |
|----------|-----|---------------|
| End-to-end flow | Human writes memory via Claude Code, searches from another client | Memory visible cross-client |
| Data survives restart | Human restarts laptop/terminal, queries memory | Data persists |
| Namespace isolation | Human verifies project-scoped query doesn't leak | Isolation holds |

## Rollback Plan

Since this is a local stdio MCP server with no infrastructure:

- **Unregister:** `claude mcp remove memory-layer`, `codex mcp remove memory-layer`, `gemini mcp remove memory-layer`
- **Data safe:** SQLite + Chroma data in `data/` directory is untouched by unregistration
- **No side effects:** Stdio transport means no ports, no daemons, no lingering processes

Rollback is instant and non-destructive.

## Risk Areas

| Risk | Mitigation |
|------|------------|
| Embedding model not downloaded → first `write_memory` fails | Pre-flight provisions model before client registration |
| Concurrent writes from multiple clients corrupt SQLite | WAL mode handles this; validate with multi-client Tier 2 test |
| Client CLI `mcp add` syntax changes | Registry installer scripts abstract this; test each client |
| Chroma version mismatch across installs | Single `.venv`, all clients use same Python |

## Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Register at user scope (not project) for Claude Code | Memory is ecosystem-wide, not project-specific |
| 2 | Claude Code first, then Codex, then Gemini | Primary client first; validates before expanding |
| 3 | Skip MCP Inspector for Tier 2 | Live client testing is more representative; Inspector is optional backup |
