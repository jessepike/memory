---
type: "brief"
project: "Memory Layer"
version: "0.1"
status: "draft"
review_cycle: 0
created: "2026-02-10"
updated: "2026-02-10"
intent_ref: "./intent.md"
---

# Brief: Memory Layer

## Classification

- **Type:** App
- **Scale:** personal
- **Scope:** mvp
- **Complexity:** standalone

## Summary

A persistent memory service for the Krypton agent ecosystem — Tier 2 in the 3-layer architecture. Follows the proven KB pattern (SQLite + Chroma + MCP server) adapted for contextual memory semantics. Any agent can write memories; any authorized agent can query them. Scoping and visibility controls determine access.

## Scope

### In Scope

- SQLite storage for structured memory metadata
- Chroma vector store for semantic search
- MCP server as primary API surface
- Namespace-based scoping (project, global, private)
- Core MCP tools: add, search, update, archive
- Memory types: observation, preference, decision, progress, relationship
- Writer identification (who wrote it, what type of writer)
- Visibility controls (public, restricted, private)
- Manual "save to memory" entry path

### Out of Scope

- Automated extraction from conversations (future — start with structured passthrough)
- LLM-based consolidation/deduplication (future — start with manual curation)
- Decay/pruning system (future — add when volume demands)
- Graph memory / relationship traversal (future — flat entries + vector search for MVP)
- REST API (future — MCP-only for MVP)
- Tier 1 → Tier 2 automatic promotion (future — manual bridge for MVP)
- Multi-user / multi-tenant support (single-user, local-first)

## Success Criteria

- [ ] MCP server runs and is connectable from Claude Code
- [ ] Agents can write memories with scope, type, and visibility metadata
- [ ] Agents can search memories by semantic query with scope filtering
- [ ] Project-scoped agents only see project + global memories (not other projects, not private)
- [ ] Krypton can query across all non-private scopes
- [ ] Manual entries can be added via MCP tool
- [ ] Memory entries persist across sessions
- [ ] KB boundary is maintained — memory stores contextual knowledge, not reference knowledge

## Constraints

- Follow KB project's architectural patterns (SQLite + Chroma + MCP) for consistency
- Local-first — no external service dependencies
- Single-user — no auth/multi-tenant complexity
- Python (consistent with KB project)
- MCP server as primary interface

## Open Questions

- [ ] Exact MCP tool surface — how many tools, what granularity? (Mirror KB's 16-tool pattern or start smaller?)
- [ ] Memory entry size/format — short facts vs. longer summaries vs. both?
- [ ] Consolidation strategy for MVP — purely manual, or basic dedup on write?
- [ ] How does Krypton's cross-scope query work in practice? Filter syntax?
- [ ] Should writer_type and writer_id be enforced or advisory?

## Issue Log

| # | Issue | Source | Impact | Priority | Status | Resolution |
|---|-------|--------|--------|----------|--------|------------|
| - | - | - | - | - | - | - |

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-10 | Initial draft from research synthesis |
