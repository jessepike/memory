---
project: "Memory Layer"
stage: "Develop"
updated: "2026-02-10"
---

# Status

## Current State

- **Phase:** Develop — In Progress
- **Focus:** MCP smoke flow validated end-to-end with real dependencies. Next: harden scope authorization behavior for non-privileged update/archive flows.

## Next Steps

- [x] Governance — Add required agent workflow policy (`AGENTS.md`) for backlog/tasks/status/commits
- [x] Governance — Create explicit backlog artifact (`docs/backlog.md`) and seed current work items
- [ ] Governance — Keep backlog/status updated every work slice and commit in regular cadence
- [x] Human sign-off — Design accepted, transition to Develop approved
- [x] Develop Step 1 — Scaffold project (`pyproject.toml`, package layout, config)
- [x] Develop Step 2 — Implement Pydantic models (`memory_core/models.py`)
- [x] Develop Step 3 — Implement SQLite schema + DB layer (`memory_core/storage/schema.sql`, `db.py`)
- [x] Develop Step 4 — Embedding provisioning + startup preflight checks
- [x] Develop Step 5 — Implement embeddings wrapper (`memory_core/utils/embeddings.py`)
- [x] Develop Step 6 — Implement Chroma wrapper (`memory_core/storage/vector_store.py`)
- [x] Develop Step 7 — Implement MemoryStorage orchestration (`memory_core/storage/api.py`)
- [x] Develop Step 8 — Reconciliation path (`reconcile_dual_store`) + drift metrics plumbing
- [x] Develop Step 9 — Failed lifecycle maintenance APIs (`list_failed_memories`, `retry_failed_memory`, `archive_failed_memory`)
- [x] Develop Step 10 — Consolidation utility hardening + edge-case tests
- [x] Develop Step 11 — MCP server tool definitions + dispatch integration
- [x] Develop Step 12 — MCP integration polish + end-to-end smoke checklist
- [ ] Develop Step 13 — Scope-authorization hardening for update/archive defense-in-depth

## Pending Decisions

- None

## Blockers

- None

## Design Stage Handoff

### What Was Produced

- **design.md v1.0** — Full technical specification: 3-layer architecture (MCP → core → dual store), 9 MCP tools, data model, write-time consolidation (0.92 threshold), 7 design decisions, Develop Handoff with build order and test strategy
- **7 design decisions** — Caller-provided namespace with client-profile policy enforcement, local embeddings (all-MiniLM-L6-v2), namespace-only scoping, conservative dedup, no chunking, staged commit, Chroma-first ordering
- **8 review issues resolved** — 5 from internal (brief deviations, cross-scope search, update flow, review_candidates), 3 from external (Chroma distance semantics, metadata API, dual-store ordering)

### Success Criteria Status

- 10 testable criteria from Brief, all addressable by design
- Each criterion mapped to specific implementation in Develop Handoff
- No deferred criteria

### Known Limitations

- 2 Brief deviations documented: visibility→namespace simplification (D3), consolidation simplified to ADD/SKIP only (D4)
- Kimi model timed out in both Discover and Design external reviews (2/3 models — sufficient coverage)

### Read Order for Develop Stage

1. `docs/intent.md` — North Star
2. `docs/discover-brief.md` — Full project contract
3. `docs/design.md` — Technical spec (start with Develop Handoff section)
4. `docs/status.md` — This file

## Discover Stage Handoff

### What Was Produced

- **intent.md v0.2** — North Star: persistent memory service for agent ecosystem
- **discover-brief.md v0.6** — Full project contract: scope, success criteria, constraints, resolved open questions
- **Research artifacts** — Landscape scan (Mem0, Letta, LangMem, ChatGPT, AWS), ACK prior art analysis, 8 open questions resolved

### What Was Archived

- `docs/_archive/2026-02-10-memory-layer-research.md` — Initial landscape research synthesis
- `docs/_archive/2026-02-10-memory-systems-deep-dive.md` — Deep-dive across 7 memory systems
- `docs/_archive/2026-02-10-open-questions-research.md` — Analysis resolving all 8 open questions

## Session Log

| Date | Summary |
|------|---------|
| 2026-02-10 | Project initialized. Drafted v0.1 artifacts from research synthesis. Explored KB (20+ relevant entries) and ACK prior art (sandbox/ai-dev). Corrected framing: ecosystem infra, not Krypton-specific. Updated intent and brief to v0.2. Identified 8 open questions needing research before review. |
| 2026-02-10 | Deep-dive research complete across 6 open questions. Researched Mem0, Letta/MemGPT, LangGraph/LangMem, ChatGPT, Claude Memory, AWS AgentCore, MemAct. Findings written to docs/adf/memory-systems-deep-dive.md. Key findings: Mem0 uses LLM-as-judge ADD/UPDATE/DELETE/NOOP curation; Letta uses agent-initiated self-editing tools; LangMem supports both hot-path and background extraction; ChatGPT uses no vector DB (4-layer pre-computed injection); hybrid stores dominate production; atomic facts win for retrieval, narrative for session logs. |
| 2026-02-10 | All 8 open questions researched and resolved for MVP. Synthesized ACK prior art (72 memories, hooks capture, Phase 2 blocker), 16 KB entries, and landscape research into `docs/adf/open-questions-research.md`. Updated brief to v0.3. Ready for internal review. |
| 2026-02-10 | Phase 1 internal review complete (2 cycles). Fixed 2 Critical (session-end capture contradiction, write-time consolidation mechanism undefined), 2 High (untestable success criteria, undefined Tier jargon), 1 Low (issue log format). Brief v0.5. Ready for external review. |
| 2026-02-10 | Phase 2 external review complete. Gemini + GPT reviewed (Kimi timed out). 6 issues raised, 2 accepted: embedding locality constraint added, caller identity gap flagged for Design. 4 rejected as Design-stage concerns. Brief v0.6. Ready for Discover-to-Design transition. |
| 2026-02-10 | Discover stage complete. Archived research artifacts. Transitioned to Design stage. |
| 2026-02-10 | Design Intake & Clarification complete. Resolved 7 decisions: caller-provided namespace with client-profile policy enforcement, local embeddings (all-MiniLM-L6-v2), namespace-only scoping (dropped visibility), 0.92 dedup threshold, memory_core package naming, private=excluded-by-default, no-merge consolidation. Analyzed KB project architecture for pattern alignment. Drafted design.md v0.1 with full technical spec: architecture, 9 MCP tools, data model, write-time consolidation, decision log. Ready for Review Loop. |
| 2026-02-10 | Design Review Loop complete. Phase 1 internal (2 cycles): 5 High resolved (brief deviations, cross-scope search, update flow, review_candidates, consolidation). Phase 2 external (Gemini + GPT): 3 High accepted (Chroma distance semantics, metadata update API, dual-store ordering), 4 rejected. design.md v0.3. |
| 2026-02-10 | Design Finalization complete. Develop Handoff section written (summary, key decisions, capabilities, success criteria mapping, build order, edge cases, test strategy). Exit criteria verified. design.md v1.0. Pending human sign-off. |
| 2026-02-10 | Human sign-off received. Transitioned from Design to Develop. Develop kickoff set to build-order steps 1-3 (scaffold, models, SQLite layer). |
| 2026-02-10 | Develop foundation implemented. Completed Step 1 scaffold, Step 2 Pydantic model layer, and Step 3 SQLite schema + DB API (WAL init, idempotency-conflict handling, lifecycle updates, committed-only stats). Added validation and DB tests; all passing. |
| 2026-02-10 | Develop Step 4/5 implemented. Added YAML config loader + typed config dump, and embedding service with setup/runtime modes, offline runtime preflight, explicit provisioning policy checks, and single/batch embedding APIs. Added config and embeddings unit tests (mocked sentence-transformers). |
| 2026-02-10 | Develop Step 6-9 implemented. Added Chroma wrapper, canonicalization/hash utilities, and `MemoryStorage` orchestration for write/search/get/update/archive/review/stats plus reconciliation and failed-memory maintenance APIs. Added orchestration and consolidation tests; all passing. |
| 2026-02-10 | Develop Step 10/11 implemented. Hardened consolidation normalization/hash helpers with edge-case tests. Added MCP server entrypoint with tool dispatch wiring for write/read/manage/stats and maintenance APIs backed by `MemoryStorage`. |
| 2026-02-10 | Added required operational governance artifacts. Created `AGENTS.md` and `docs/backlog.md`, and updated `CLAUDE.md` to require backlog-first task execution, status updates, and regular commits for every tested slice. |
| 2026-02-10 | Completed DEV-12 MCP integration polish: added scope-error serialization handling in MCP tool wrappers, fixed stats drift type mismatch, added MCP access regression tests, and added `scripts/mcp_smoke.py` (real dependency smoke checklist). Smoke and test suite passing. |
