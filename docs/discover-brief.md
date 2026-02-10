---
type: "brief"
project: "Memory Layer"
version: "0.5"
status: "internal-review-complete"
review_cycle: 2
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
- Multiple write paths: manual ("save to memory"), agent-driven (structured)
- Write-time consolidation to prevent accumulation — on each write, compare against top-k similar existing entries using vector similarity and rule-based logic (exact match, high-similarity dedup, contradiction detection). Decide: ADD new, UPDATE existing, SKIP duplicate. LLM-based consolidation deferred to post-MVP.
- Session-end memory promotion as a documented workflow pattern (agent calls `write_memory` at session end as part of ADF discipline), not a system-level hook. The hook-based capture path is post-MVP.

### Out of Scope

- LLM-based consolidation/deduplication (future — MVP uses vector similarity + rules)
- Decay/pruning system (future — add when volume demands)
- Graph memory / relationship traversal (future — flat entries + vector search for MVP)
- REST API (future — MCP-only for MVP)
- Automatic memory-to-KB promotion (future — manual bridge for MVP; user decides when a memory graduates to KB)
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
- [ ] Write-time consolidation prevents duplicate entries — writing the same fact twice does not create two entries
- [ ] `review_candidates` tool returns entries that are low-confidence or high-similarity pairs
- [ ] Core business logic lives in a Python library layer, not in the MCP server handler — MCP server delegates to core

## Constraints

- Follow KB project's architectural patterns (SQLite + Chroma + MCP) for consistency
- Local-first — no external service dependencies
- Single-user — no auth/multi-tenant complexity
- Python (consistent with KB project)
- MCP server as primary interface
- Clean-sheet implementation — informed by ACK, not dependent on it
- Non-duplicative — memory only stores what status.md, tasks.md, CLAUDE.md, and auto-memory don't already hold. The check is: "does this matter beyond this project and session?"
- Integrated capture — session-end memory promotion is a documented workflow pattern within existing ADF session-end discipline (agents call `write_memory` explicitly), not a system-level hook

## Open Questions

> All 8 questions researched and resolved for MVP. Full analysis: `docs/adf/open-questions-research.md`

- [x] **Curation workflow** — Write-time consolidation using vector similarity + rules for MVP (not LLM-based). Review candidates surfaced via MCP tool. No TUI/CLI needed — MCP tools sufficient. ACK lesson: staging state required from day one, but curation as a separate phase was over-engineered. LLM-based ADD/UPDATE/DELETE/NOOP (Mem0 pattern) deferred to post-MVP.
- [x] **Single store vs partitioned** — Single store with namespace metadata. SQLite + Chroma (KB pattern). Scoping enforced at query time via metadata filtering. Physical partitioning adds complexity for zero benefit at personal scale.
- [x] **MCP tool surface** — ~8-10 tools in 4 categories: write (write_memory, update_memory), read (search_memories, get_memory, get_recent, get_session_context), manage (archive_memory, review_candidates), stats (get_stats). Modeled on KB's pattern.
- [x] **Memory entry format** — Atomic facts as primary format (one fact per entry, independently searchable). Session summaries as separate `progress` type for session-end write-back. ACK's 4-layer format (title/subtitle/facts/narrative) was over-coupled — atomic facts are more composable.
- [x] **Capture mechanism** — MCP tools (primary, agent-initiated). Session-end hook (secondary, post-MVP). ACK's PostToolUse hook captured too much noise. Explicit tool calls produce higher quality memories.
- [x] **Write-back paths** — Hot path for MVP: explicit `write_memory` tool call (includes session-end calls as part of ADF discipline). Warm path (system-level session-end hook extraction) and cold path (background consolidation, decay) deferred until volume demands.
- [x] **Cross-channel access architecture** — MCP-only for MVP. Core as Python library with clean API; MCP server is one interface, REST adapter is future second interface. Neither contains business logic.
- [x] **State-based vs retrieval-based** — Retrieval-first for MVP. All memories stored as atomic facts with vector embeddings. State profiles (entity-level summaries) added later as a layer on top when entity coherence is needed.

## Issue Log

| # | Issue | Source | Severity | Status | Resolution |
|---|-------|--------|----------|--------|------------|
| 1 | Session-end capture listed In Scope but deferred to post-MVP in Open Questions Q5 — direct contradiction | Ralph-Internal | Critical | Resolved | Clarified: session-end is a workflow pattern (agent calls write_memory), not a system hook. Hook-based capture is post-MVP. |
| 2 | Write-time consolidation mechanism undefined — In Scope says ADD/UPDATE/DELETE/NOOP (LLM-based, per Mem0) but Out of Scope says "LLM-based consolidation (future)" | Ralph-Internal | Critical | Resolved | Clarified: MVP uses vector similarity + rule-based consolidation. LLM-based consolidation deferred. |
| 3 | Success criteria #8 ("curation workflow exists"), #9 ("KB boundary maintained"), #10 ("architecture supports future access") are not objectively testable | Ralph-Internal | High | Resolved | Replaced with testable criteria: dedup prevention, review_candidates tool output, core library separation. |
| 4 | "Tier 1 / Tier 2" in Out of Scope undefined — no context for what these tiers mean | Ralph-Internal | High | Resolved | Replaced with "Automatic memory-to-KB promotion" — clear without jargon. |
| 5 | Issue Log column headers don't match Brief Spec format (had Impact/Priority, spec uses Severity) | Ralph-Internal | Low | Resolved | Aligned columns with spec. |
| 6 | Phase 1 internal review complete — 2 cycles, 2 Critical / 2 High / 1 Low found and resolved | Ralph-Internal | - | Complete | All issues addressed. Ready for Phase 2. |

## Review Log

### Phase 1: Internal Review

**Date:** 2026-02-10
**Mechanism:** Ralph Loop (2 cycles)
**Cycle 1 Issues Found:** 2 Critical, 2 High, 1 Low
**Actions Taken:**
- **Auto-fixed (5 issues):**
  - Session-end capture contradiction (Critical) — Aligned In Scope, Constraints, and Open Questions: session-end is workflow pattern, not system hook
  - Write-time consolidation undefined (Critical) — Clarified as vector similarity + rules for MVP, LLM-based deferred
  - Three untestable success criteria (High) — Replaced with objectively verifiable criteria
  - Undefined Tier 1/Tier 2 jargon (High) — Replaced with clear "memory-to-KB promotion" language
  - Issue Log column mismatch (Low) — Aligned with spec format

**Cycle 2 Issues Found:** 0 Critical, 0 High, 0 Low
**Actions Taken:** None required — all prior fixes verified, no new issues found.

**Outcome:** Internal review complete after 2 cycles. Brief is ready for Phase 2 (external review).

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-10 | Initial draft from research synthesis |
| 0.2 | 2026-02-10 | Corrected framing: ecosystem infra, not Krypton-specific. Added prior art, expanded open questions from KB + ACK research. |
| 0.3 | 2026-02-10 | All 8 open questions researched and resolved for MVP. Deep-dive across ACK prior art, 16 KB entries, and landscape research (Mem0, Letta, LangMem, ChatGPT, AWS AgentCore). |
| 0.3.1 | 2026-02-10 | Added integrated capture constraint: session-end memory check folded into existing ADF discipline, not separate. Added non-duplication constraint. |
| 0.4 | 2026-02-10 | Internal review cycle 1: Resolved session-end capture contradiction, clarified write-time consolidation as rule-based for MVP, replaced untestable success criteria, removed Tier 1/Tier 2 jargon, aligned Issue Log format with spec. |
| 0.5 | 2026-02-10 | Internal review cycle 2: Zero issues found. Phase 1 complete. Status set to internal-review-complete. |
