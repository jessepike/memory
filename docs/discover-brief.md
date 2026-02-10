---
type: "brief"
project: "Memory Layer"
version: "0.3"
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

Persistent memory service for the personal agent ecosystem — the "what we remember" layer alongside KB ("what we know") and Work OS/ADF ("what we're doing"). Clean-sheet build informed by prior ACK/Claude-Mem research and prototype work. Follows the proven KB architectural pattern (SQLite + Chroma + MCP server) adapted for contextual memory semantics.

Initially serves ADF development agents and Krypton. Architecturally, must support broader access over time (personal assistant, dashboards, non-dev workflows).

## Prior Art

- **ACK/Claude-Mem (sandbox/ai-dev)** — Prototype with working hooks-based capture (53 memories, 10 sessions). Validated SQLite + Chroma storage, PostToolUse/Stop hook capture pattern. Blocked at Phase 2 (curation). This project is a clean-sheet redesign informed by that work.
- **memory-layer-research.md** — Landscape scan of Mem0, Letta, LangGraph, OpenAI/Claude memory approaches.
- **KB entries** — Four-layer cognitive model, write-back patterns, ecosystem mapping, system boundary definitions.

## Scope

### In Scope

- SQLite storage for structured memory metadata
- Chroma vector store for semantic search
- MCP server as primary API surface
- Namespace-based scoping (project, global, private)
- Core MCP tools: write, search, update, archive
- Memory types: observation, preference, decision, progress, relationship
- Writer identification (who wrote it, what type of writer)
- Visibility controls (public, restricted, private)
- Multiple write paths: manual ("save to memory"), agent-driven (structured), hooks-based (automatic capture)
- Curation workflow (mechanism TBD — critical open question)
- Session summary capture (warm path write-back)

### Out of Scope

- LLM-based consolidation/deduplication (future — start simpler)
- Decay/pruning system (future — add when volume demands)
- Graph memory / relationship traversal (future — flat entries + vector search for MVP)
- REST API (future — MCP-only for MVP)
- Tier 1 → Tier 2 automatic promotion (future — manual bridge for MVP)
- Multi-user / multi-tenant support (single-user, local-first)
- UI/dashboard for memory browsing (future)

## Success Criteria

- [ ] MCP server runs and is connectable from Claude Code
- [ ] Agents can write memories with scope, type, and visibility metadata
- [ ] Agents can search memories by semantic query with scope filtering
- [ ] Project-scoped agents see only project + global memories (isolation)
- [ ] Cross-scope queries work for authorized consumers (e.g., Krypton)
- [ ] Manual entries can be added via MCP tool
- [ ] Memory entries persist across sessions
- [ ] Curation workflow exists — memories can be reviewed, promoted, or rejected
- [ ] KB boundary is maintained — memory stores contextual knowledge, not reference knowledge
- [ ] Architecture supports future multi-channel access without redesign

## Constraints

- Follow KB project's architectural patterns (SQLite + Chroma + MCP) for consistency
- Local-first — no external service dependencies
- Single-user — no auth/multi-tenant complexity
- Python (consistent with KB project)
- MCP server as primary interface
- Clean-sheet implementation — informed by ACK, not dependent on it

## Open Questions

> All 8 questions researched and resolved for MVP. Full analysis: `docs/adf/open-questions-research.md`

- [x] **Curation workflow** — Write-time consolidation (Mem0's ADD/UPDATE/DELETE/NOOP pattern). Review candidates surfaced via MCP tool. No TUI/CLI needed — MCP tools sufficient. ACK lesson: staging state required from day one, but curation as a separate phase was over-engineered.
- [x] **Single store vs partitioned** — Single store with namespace metadata. SQLite + Chroma (KB pattern). Scoping enforced at query time via metadata filtering. Physical partitioning adds complexity for zero benefit at personal scale.
- [x] **MCP tool surface** — ~8-10 tools in 4 categories: write (write_memory, update_memory), read (search_memories, get_memory, get_recent, get_session_context), manage (archive_memory, review_candidates), stats (get_stats). Modeled on KB's pattern.
- [x] **Memory entry format** — Atomic facts as primary format (one fact per entry, independently searchable). Session summaries as separate `progress` type for session-end write-back. ACK's 4-layer format (title/subtitle/facts/narrative) was over-coupled — atomic facts are more composable.
- [x] **Capture mechanism** — MCP tools (primary, agent-initiated). Session-end hook (secondary, post-MVP). ACK's PostToolUse hook captured too much noise. Explicit tool calls produce higher quality memories.
- [x] **Write-back paths** — Two paths for MVP: hot (explicit `write_memory` tool call) + warm (session-end extraction). Cold path (background consolidation, decay) deferred until volume demands.
- [x] **Cross-channel access architecture** — MCP-only for MVP. Core as Python library with clean API; MCP server is one interface, REST adapter is future second interface. Neither contains business logic.
- [x] **State-based vs retrieval-based** — Retrieval-first for MVP. All memories stored as atomic facts with vector embeddings. State profiles (entity-level summaries) added later as a layer on top when entity coherence is needed.

## Issue Log

| # | Issue | Source | Impact | Priority | Status | Resolution |
|---|-------|--------|--------|----------|--------|------------|
| - | - | - | - | - | - | - |

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-10 | Initial draft from research synthesis |
| 0.2 | 2026-02-10 | Corrected framing: ecosystem infra, not Krypton-specific. Added prior art, expanded open questions from KB + ACK research. |
| 0.3 | 2026-02-10 | All 8 open questions researched and resolved for MVP. Deep-dive across ACK prior art, 16 KB entries, and landscape research (Mem0, Letta, LangMem, ChatGPT, AWS AgentCore). |
