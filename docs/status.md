---
project: "Memory Layer"
stage: "Deliver"
updated: "2026-02-19"
---

# Status

## Current State

- **Phase:** Design review complete. Ready for implementation.
- **Focus:** Implement Phase 1 (episodic log foundation) from `docs/design-capture-governance.md`.

## Next Steps

- [x] **FIX-01 (P0):** Add `client_profiles` to `config/memory_config.yaml` — profiles for claude-code, krypton, adf.
- [x] **FIX-02 (P0):** Fix `scripts/mcp_stdio_test.py` line 121 — tool count assertion (14→15).
- [x] **Research:** Hook capabilities for Claude Code, Codex CLI, Gemini CLI. PreCompact can't call MCP tools. SessionEnd is best capture point. Codex has no hooks at all.
- [x] **Design review:** `docs/design-capture-governance.md` — internal + external (Gemini, GPT). 11 issues resolved.
- [ ] **Implement v1.1:** Episodic log (SQLite, hash-chained), write_episode/get_episodes/end_session MCP tools, SessionEnd hooks, system prompt updates.
- [ ] **Hybrid search (FTS5/BM25):** Add SQLite FTS5 keyword search alongside Chroma vector search in `search_memories`. 70/30 fusion. Low-cost, high-value for technical content. See `docs/research-synthesis.md`.
- [ ] **Citation tracking:** Add optional `source_ref` field to `write_memory`. No behavior change now; unlocks JIT verification and staleness detection later.

- [x] POST-01: Define memory routing heuristic (MCP vs auto-memory)
- [x] POST-02: Add usage logging to MCP server (observability foundation)
- [x] POST-03: ADF session protocol → moved to ADF B86
- [x] POST-04: Add usage report tool (monitoring)
- [x] POST-05: Register in Codex/Gemini → moved to capabilities-registry CR-10
- [x] POST-06: Weekly review cadence → moved to Krypton B17
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
- [x] Develop Step 13 — Scope-authorization hardening for update/archive defense-in-depth
- [x] Develop Step 14 — MCP-level integration tests for tool surface + error contracts
- [x] Develop Step 15 — Packaging/dev setup command docs + bootstrap verification
- [x] Develop Step 16 — Final docs consistency alignment (design/brief/status/backlog)
- [x] Develop Step 17 — Practical usage guide (`docs/usage.md`) with tool-by-tool examples
- [x] Develop Step 18 — Capabilities registry registration + cross-client installer verification

## Pending Decisions

- None

## Blockers

- None

## Deliver Stage Handoff

### What Was Delivered

- **MCP server live** in Claude Code at user scope (stdio transport, `uv run` launcher)
- **14 MCP tools** accessible from every Claude Code session
- **Scope bug fixed** during Tier 2 validation — no-namespace queries now correctly search caller's allowed namespaces
- **Access documentation** added to README (per-client registration commands)
- **Codex/Gemini registration** deferred — CLI environment prerequisites (not memory-layer issues)

### Success Criteria Mapping

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | MCP server runs and is connectable from Claude Code | Met | `claude mcp get memory` shows connected, `health` returns `status: ok` |
| 2 | Agents can write memories with scope, type, and visibility metadata | Met | Tier 2: `write_memory` returns `action: added` with namespace + type |
| 3 | Agents can search memories by semantic query with scope filtering | Met | Tier 2: `search_memories` returns results filtered by namespace |
| 4 | Project-scoped agents see only project + global memories (isolation) | Met | Tier 2: cross-namespace search returns empty; outsider can't see other namespace |
| 5 | Cross-scope queries work for policy-allowed trusted consumers | Met | Test config: krypton profile with `can_cross_scope: true` works; Krypton session tested live |
| 6 | Manual entries can be added via MCP tool | Met | Tier 2: `write_memory` with explicit content succeeds |
| 7 | Memory entries persist across sessions | Met | Stdio transport spawns fresh process; SQLite data persists on disk |
| 8 | Write-time consolidation prevents duplicate entries | Met | Tier 2: second `write_memory` with same content returns `action: skipped` |
| 9 | `review_candidates` returns low-confidence or high-similarity pairs | Met | Tier 2: tool returns list (implementation tested in unit + smoke) |
| 10 | Core business logic in Python library, not MCP handler | Met | Architecture: `storage/api.py` (MemoryStorage) contains all logic; `access/mcp_server.py` is pure dispatch |

### Validation Summary

- **Tier 1 (Automated):** 36/36 pytest, 15/15 smoke, 7/7 stdio — all pass
- **Tier 2 (Live Client):** 13/13 scenarios pass from Claude Code
- **Tier 3 (Manual):** Krypton cross-session test surfaced scope bug → fixed and verified
- **Bug found and fixed:** `_resolve_scope` was overly restrictive for no-namespace queries

### Known Limitations

- Codex CLI not installed — registration deferred
- Gemini CLI requires `GEMINI_API_KEY` — registration deferred
- No automatic session-end capture (by design — post-MVP)
- No background consolidation (write-time dedup only)
- Single-user, local-only (by design for MVP)

### Archived Artifacts

- `docs/adf/manifest.md` → delivery manifest
- `docs/adf/capabilities.md` → delivery capabilities
- `docs/adf/plan.md` → delivery plan
- `docs/adf/tasks.md` → delivery tasks

## Develop Stage Handoff

### What Was Produced

- **14 MCP tools** — write_memory, search_memories, get_memory, get_recent, get_session_context, update_memory, archive_memory, review_candidates, get_stats, reconcile_dual_store, list_failed_memories, retry_failed_memory, archive_failed_memory, health
- **3-layer architecture** — MCP server (`access/mcp_server.py`) → MemoryStorage orchestration (`storage/api.py`) → dual store (SQLite `storage/db.py` + Chroma `storage/vector_store.py`)
- **Supporting layers** — Pydantic models (`models.py`), embedding service (`utils/embeddings.py`), YAML config loader (`config.py`), canonicalization/hash utilities (`utils/consolidation.py`)
- **36 unit/integration tests** — models, DB, config, embeddings, orchestration, consolidation, MCP integration, error contracts
- **2 smoke/transport scripts** — `scripts/mcp_smoke.py` (15 in-process checks), `scripts/mcp_stdio_test.py` (7 stdio JSON-RPC checks)
- **Documentation** — `docs/usage.md` (tool-by-tool examples), README (bootstrap/dev commands), capabilities registry entry

### What Was Archived

- No Develop-stage planning artifacts to archive (research artifacts already archived during Discover)

### Success Criteria Status

- All 10 testable criteria from Brief are addressable by implementation
- Scope authorization, dedup, reconciliation, failed-memory lifecycle all implemented and tested
- MCP server registered in capabilities registry and discoverable via `query_capabilities`

### Known Limitations

- Cross-client MCP distribution not automated (manual `.mcp.json` config per client) — separate project
- No background consolidation (write-time dedup only, no merge/summarize)
- No session-end auto-capture hook (future enhancement)
- Single-user, local-only (by design for MVP)

### Read Order for Deliver Stage

1. `docs/intent.md` — North Star
2. `docs/discover-brief.md` — Success criteria reference
3. `docs/design.md` — Architecture reference
4. `src/memory_core/` — Implementation
5. `docs/status.md` — This file

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
| 2026-02-10 | Completed DEV-13 scope hardening: non-privileged callers now must provide matching namespace for ID-based `update_memory` and `archive_memory`. Added regression tests for missing/mismatched namespace guards. Full test suite and smoke checklist passing. |
| 2026-02-10 | Completed DEV-14 MCP integration tests: added end-to-end tool flow coverage and explicit forbidden-scope/namespace mismatch contract checks at the MCP layer. Updated test payload parsing for FastMCP response shape variants. Full test suite and smoke checklist passing. |
| 2026-02-10 | Completed DEV-15 packaging/bootstrap verification: updated README with concrete setup/dev/test/smoke/server commands, then validated in fresh `/tmp` venv using editable install (`pip install -e .[dev]`), full pytest pass, and smoke success (`tool_count=14`, `success=true`). |
| 2026-02-10 | Completed DEV-16 documentation alignment: reconciled design wording with implemented MCP surface (core + maintenance tools), updated discover brief to mark caller-identity enforcement resolved via Design D1, and synchronized backlog/status completion state. |
| 2026-02-10 | Completed DEV-17 usage documentation: added `docs/usage.md` covering quick start, scoping behavior, forbidden-scope contract, tool-by-tool request examples, maintenance flows, and verification commands; linked from README. |
| 2026-02-11 | Completed DEV-18 registry integration: registered `memory-layer` as a tool capability in `/Users/jessepike/code/_shared/capabilities-registry`, regenerated `inventory.json`/`INVENTORY.md`, verified ADF `query_capabilities` discovery, and confirmed installer command generation for Codex, Claude Code, and Gemini. |
| 2026-02-11 | Added `scripts/mcp_stdio_test.py` (live stdio JSON-RPC transport test, 7 checks) and expanded `scripts/mcp_smoke.py` with 9 new workflow checks (get_memory, update_memory, get_recent, get_session_context, review_candidates, reconcile, failed memories, cross-namespace, forbidden scope). All 36 unit tests + both scripts passing. |
| 2026-02-11 | Deliver stage complete. Phases 1-3: planning artifacts (manifest, capabilities, plan, tasks). Phase 4: simplified internal review + human approval. Phases 5+6 collapsed: Claude Code already registered at user scope; Codex/Gemini deferred (CLI env issues). Phase 7: Tier 1 (36/36 + smoke + stdio), Tier 2 (13/13 live scenarios), Tier 3 (Krypton cross-session test surfaced scope bug — fixed). Phase 8: success criteria mapped (10/10 met), access docs added, milestone sealed. |
| 2026-02-11 | Post-MVP planning. Added 6 backlog items for v1.1 Observability & Adoption (usage logging, ADF session protocol integration, usage report tool, client registration, weekly review). Pushed 3 learnings to KB (Deliver phase collapsing, Tier 2 catch rate, scope design). Identified unresolved MCP-vs-auto-memory routing concern → POST-01 + KB idea. Fastest next step: POST-03 (update global CLAUDE.md session protocol to drive adoption). |
| 2026-02-11 | POST-01 complete. Created `docs/memory-routing.md` — cross-client routing heuristic covering Claude Code, Codex CLI, and Gemini CLI. Defines core rule ("does it matter beyond this project and client?"), decision table (10 scenarios), litmus tests, per-client guidance with system comparison tables, Memory-vs-KB boundary, prescriptive session protocol (MUST not SHOULD), and Krypton delegation option. Researched Codex/Gemini memory capabilities (Codex: AGENTS.md hierarchy + session transcripts, Gemini: GEMINI.md + `/memory add`). Added B84 to ADF backlog (cross-client memory integration spec) and B85 (retire stale B18/B19). Linked from CLAUDE.md context map. |
| 2026-02-11 | POST-02 complete. Added usage logging to MCP server. New `UsageLogger` class writes append-only JSONL to `data/usage.jsonl`. Every `_run_tool()` call logs tool name, caller_id, namespace, duration_ms, status, and error. Fail-safe (never breaks tool calls). Added `usage_log` to `PathsConfig` and `memory_config.yaml`. 41 tests pass + 15 smoke checks. |
| 2026-02-11 | POST-04 complete. Added `get_usage_report` MCP tool. New `UsageReporter` class reads JSONL log and computes metrics: call counts by tool/status/namespace/caller, search-to-write ratio, error rate, avg duration. Fail-safe (returns empty report on missing/corrupt file). 10 unit tests + 1 integration test. 51 tests pass, 15 tool smoke (tool_count=15). |
| 2026-02-19 | Validation session. Missing client_profiles identified as root cause. FIX-01/02 backlogged. 4 docs + 3 diagrams created. Capture problem documented. |
| 2026-02-19 | FIX-01/02 resolved. Hook research (3 clients). Design doc written. 5 KB entries. KB cross-checked. |
| 2026-02-20 | Design review complete. 11 issues resolved (1 Critical, 3 High, 7 Medium). 6 rejected. |
