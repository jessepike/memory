---
project: "Memory Layer"
stage: "Design"
updated: "2026-02-10"
---

# Status

## Current State

- **Phase:** Design — Complete (pending human sign-off)
- **Focus:** design.md v1.0 finalized, Develop Handoff complete

## Next Steps

- [x] Intake & Clarification — 7 decisions resolved (caller ID, embeddings, scope model, dedup, package naming, private namespace, consolidation approach)
- [x] Technical Design — design.md v0.1 drafted (architecture, 9 MCP tools, data model, consolidation algorithm, decision log)
- [x] Review Loop — Phase 1 internal (2 cycles, 5 High resolved) + Phase 2 external (Gemini + GPT, 3 High resolved)
- [x] Finalization — Develop Handoff complete, exit criteria verified
- [ ] Human sign-off → transition to Develop

## Pending Decisions

- None

## Blockers

- None

## Design Stage Handoff

### What Was Produced

- **design.md v1.0** — Full technical specification: 3-layer architecture (MCP → core → dual store), 9 MCP tools, data model, write-time consolidation (0.92 threshold), 7 design decisions, Develop Handoff with build order and test strategy
- **7 design decisions** — Caller-provided namespace, local embeddings (all-MiniLM-L6-v2), namespace-only scoping, conservative dedup, no chunking, staged commit, Chroma-first ordering
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
| 2026-02-10 | Design Intake & Clarification complete. Resolved 7 decisions: caller-provided namespace, local embeddings (all-MiniLM-L6-v2), namespace-only scoping (dropped visibility), 0.92 dedup threshold, memory_core package naming, private=excluded-by-default, no-merge consolidation. Analyzed KB project architecture for pattern alignment. Drafted design.md v0.1 with full technical spec: architecture, 9 MCP tools, data model, write-time consolidation, decision log. Ready for Review Loop. |
| 2026-02-10 | Design Review Loop complete. Phase 1 internal (2 cycles): 5 High resolved (brief deviations, cross-scope search, update flow, review_candidates, consolidation). Phase 2 external (Gemini + GPT): 3 High accepted (Chroma distance semantics, metadata update API, dual-store ordering), 4 rejected. design.md v0.3. |
| 2026-02-10 | Design Finalization complete. Develop Handoff section written (summary, key decisions, capabilities, success criteria mapping, build order, edge cases, test strategy). Exit criteria verified. design.md v1.0. Pending human sign-off. |
