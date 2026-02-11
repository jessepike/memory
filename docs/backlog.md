---
project: "Memory Layer"
updated: "2026-02-10"
---

# Backlog

## In Progress

| id | priority | status | owner | description | done_when |
|----|----------|--------|-------|-------------|-----------|
| DEL-01 | P1 | done | agent | Phase 1 Intake & Readiness Check — verify Develop outputs | All checks pass, delivery scope understood |
| DEL-02 | P1 | done | agent | Phase 2 Delivery Capability Assessment — manifest.md + capabilities.md | Artifacts created with registry summary |
| DEL-03 | P1 | done | agent | Phase 3 Delivery Planning — plan.md + tasks.md | Plan with 3-tier testing, rollback, 11 atomic tasks |
| DEL-04 | P1 | done | agent | Phase 4 Review & Approval (simplified) | Self-review passed, human approved |
| DEL-05 | P1 | done | agent | Phases 5+6 Infrastructure + Deployment | Claude Code connected; scope bug fixed; Codex/Gemini deferred |
| DEL-06 | P1 | done | agent | Phase 7 Validation (Tier 1+2+3) | All tiers pass; 10/10 success criteria met |
| DEL-07 | P1 | done | agent | Phase 8 Milestone Closeout | Success criteria mapped, access docs, seal |

## Todo

| id | priority | status | owner | description | done_when |
|----|----------|--------|-------|-------------|-----------|
| POST-01 | P1 | todo | — | Define routing heuristic between Memory Layer MCP and Claude Code auto-memory | Documented convention or enforcement mechanism that prevents duplication between the two systems |
| POST-02 | P1 | todo | — | Add usage logging to MCP server | Every tool call logs caller_id, tool name, namespace, timestamp to append-only store. Foundation for all observability. |
| POST-03 | P1 | todo | — | Add memory check/write to ADF session protocol | Global CLAUDE.md updated: session start = check memory for context; session end = write key decisions/learnings. Agents use memory by convention. |
| POST-04 | P2 | todo | — | Add usage report tool (`get_usage_report`) | MCP tool or script that reports: memories written/searched this period, search-to-write ratio, active namespaces, dedup rate, empty searches (gap signal) |
| POST-05 | P2 | todo | — | Register memory MCP in Codex and Gemini | Codex CLI installed + registered; Gemini API key configured + registered |
| POST-06 | P3 | todo | — | Weekly review cadence: `get_stats` + `review_candidates` | Run manually for first month to build intuition on usage patterns before automating |
## Done

| id | priority | status | owner | description | done_when |
|----|----------|--------|-------|-------------|-----------|
| DEV-01 | P1 | done | agent | Scaffold project layout and tooling baseline | `src/`, `tests/`, `config/`, `pyproject.toml` created and tests run |
| DEV-02 | P1 | done | agent | Implement model layer | Pydantic models for core entities and tool payloads implemented with tests |
| DEV-03 | P1 | done | agent | Implement SQLite schema and DB API | DDL + lifecycle/idempotency/stats DB functions implemented with tests |
| DEV-04 | P1 | done | agent | Add embedding provisioning and preflight | Setup/runtime embedding behavior implemented and tested |
| DEV-05 | P1 | done | agent | Implement Chroma wrapper and orchestration core | Vector store + MemoryStorage write/read/manage/stats/reconcile APIs implemented |
| DEV-06 | P1 | done | agent | Wire MCP tool dispatch | MCP server entrypoint and tool wiring implemented |
| DEV-12 | P1 | done | agent | MCP integration polish and end-to-end smoke testing | `scripts/mcp_smoke.py` passes against real dependencies; MCP error serialization and regression tests added |
| DEV-13 | P1 | done | agent | Harden scope authorization rules for update/archive defense-in-depth namespace checks | Non-privileged update/archive now require matching namespace; covered by regression tests and passing smoke |
| DEV-14 | P1 | done | agent | Add MCP-level integration tests for 9-tool surface and error contracts | Added MCP integration flow + error-contract tests for tool coverage and forbidden-scope cases; full suite and smoke pass |
| DEV-15 | P2 | done | agent | Add packaging/dev setup commands to README and verify clean bootstrap path | README now contains concrete bootstrap/dev commands; verified in fresh venv with editable install, full tests, and smoke pass |
| DEV-16 | P2 | done | agent | Review and align docs with implemented behavior and outstanding gaps | Aligned design/brief wording to implementation reality (tool surface + caller identity resolution) and synchronized status/backlog state |
| DEV-17 | P2 | done | agent | Add practical usage documentation for operators and agents | Added `docs/usage.md` with tool-by-tool examples, scope/error contracts, workflows, and verification commands; linked from README |
| DEV-18 | P1 | done | agent | Register memory MCP server in central capabilities registry and verify cross-client installability | Added `memory-layer` tool capability in capabilities registry, regenerated inventory, verified discovery via `query_capabilities`, and validated Codex/Claude/Gemini installer dry-runs |
