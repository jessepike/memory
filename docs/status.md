---
project: "Memory Layer"
stage: "Discover"
updated: "2026-02-10"
---

# Status

## Current State

- **Phase:** Research complete, ready for review
- **Focus:** Internal review (Ralph Loop) of brief v0.3

## Next Steps

- [x] Deep-dive research: curation workflow patterns, single vs partitioned store, capture mechanisms, state-based vs retrieval-based
- [x] Resolve enough open questions for solid brief
- [ ] Internal review (Ralph Loop) of discover-brief v0.3
- [ ] Address review feedback
- [ ] External review
- [ ] Finalize and transition to Design

## Pending Decisions

- None — all 8 open questions resolved for MVP (see `docs/adf/open-questions-research.md`)

## Blockers

- None

## Session Log

| Date | Summary |
|------|---------|
| 2026-02-10 | Project initialized. Drafted v0.1 artifacts from research synthesis. Explored KB (20+ relevant entries) and ACK prior art (sandbox/ai-dev). Corrected framing: ecosystem infra, not Krypton-specific. Updated intent and brief to v0.2. Identified 8 open questions needing research before review. |
| 2026-02-10 | Deep-dive research complete across 6 open questions. Researched Mem0, Letta/MemGPT, LangGraph/LangMem, ChatGPT, Claude Memory, AWS AgentCore, MemAct. Findings written to docs/adf/memory-systems-deep-dive.md. Key findings: Mem0 uses LLM-as-judge ADD/UPDATE/DELETE/NOOP curation; Letta uses agent-initiated self-editing tools; LangMem supports both hot-path and background extraction; ChatGPT uses no vector DB (4-layer pre-computed injection); hybrid stores dominate production; atomic facts win for retrieval, narrative for session logs. |
| 2026-02-10 | All 8 open questions researched and resolved for MVP. Synthesized ACK prior art (72 memories, hooks capture, Phase 2 blocker), 16 KB entries, and landscape research into `docs/adf/open-questions-research.md`. Updated brief to v0.3. Ready for internal review. |
