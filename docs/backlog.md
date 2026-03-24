---
project: "Memory Layer"
updated: "2026-02-24"
---

# Backlog

## In Progress

| id | priority | status | owner | description | why | done_when |
|----|----------|--------|-------|-------------|-----|-----------|
| V1-P4 | P2 | in_progress | agent | Phase 4: Daily checks + iteration | Without measurement data, we can't know whether memory capture is actually working or improving | SessionStart hook surfaces daily capture stats. Run `measure_capture.py --days 7` weekly. Decide v1.2 direction after ~10 sessions of data. |

## Todo

| id | priority | status | owner | description | why | done_when |
|----|----------|--------|-------|-------------|-----|-----------|
| V2-01 | P2 | todo | agent | Krypton GM: search-before-write for pattern-tracking observations | GM agent writes daily incremental observations (e.g., "smoke test deferred day N") as new entries instead of updating existing ones. This created 15+ near-duplicate memories before manual cleanup. GM should search for existing pattern memories and update them rather than creating new entries each day. | GM agent searches before writing pattern-tracking observations; daily increments update existing memory instead of creating new entries. Verified by running 3+ daily cycles with zero duplicate clusters. |

## Done

| id | priority | status | owner | description | done_when | outcome |
|----|----------|--------|-------|-------------|-----------|---------|
| POST-01 | P1 | done | agent | Define routing heuristic between Memory Layer MCP and Claude Code auto-memory | Documented convention or enforcement mechanism that prevents duplication between the two systems | Yes — routing heuristic documented at docs/memory-routing.md |
| DEV-01 | P1 | done | agent | Scaffold project layout and tooling baseline | `src/`, `tests/`, `config/`, `pyproject.toml` created and tests run | Yes — project scaffold created and tests run |
| DEV-02 | P1 | done | agent | Implement model layer | Pydantic models for core entities and tool payloads implemented with tests | Yes — Pydantic models implemented with tests |
| DEV-03 | P1 | done | agent | Implement SQLite schema and DB API | DDL + lifecycle/idempotency/stats DB functions implemented with tests | Yes — SQLite DDL + lifecycle/idempotency/stats functions implemented |
| DEV-04 | P1 | done | agent | Add embedding provisioning and preflight | Setup/runtime embedding behavior implemented and tested | Yes — embedding provisioning implemented and tested |
| DEV-05 | P1 | done | agent | Implement Chroma wrapper and orchestration core | Vector store + MemoryStorage write/read/manage/stats/reconcile APIs implemented | Yes — Chroma wrapper + MemoryStorage APIs implemented |
| DEV-06 | P1 | done | agent | Wire MCP tool dispatch | MCP server entrypoint and tool wiring implemented | Yes — MCP server entrypoint and tool wiring implemented |
| DEV-12 | P1 | done | agent | MCP integration polish and end-to-end smoke testing | `scripts/mcp_smoke.py` passes against real dependencies; MCP error serialization and regression tests added | Yes — smoke tests pass against real dependencies |
| DEV-13 | P1 | done | agent | Harden scope authorization rules for update/archive defense-in-depth namespace checks | Non-privileged update/archive now require matching namespace; covered by regression tests and passing smoke | Yes — namespace checks added with regression coverage |
| DEV-14 | P1 | done | agent | Add MCP-level integration tests for 9-tool surface and error contracts | Added MCP integration flow + error-contract tests for tool coverage and forbidden-scope cases; full suite and smoke pass | Yes — MCP integration tests for 9-tool surface and error contracts |
| DEV-15 | P2 | done | agent | Add packaging/dev setup commands to README and verify clean bootstrap path | README now contains concrete bootstrap/dev commands; verified in fresh venv with editable install, full tests, and smoke pass | Yes — bootstrap/dev commands in README, verified in fresh venv |
| DEV-16 | P2 | done | agent | Review and align docs with implemented behavior and outstanding gaps | Aligned design/brief wording to implementation reality (tool surface + caller identity resolution) and synchronized status/backlog state | Yes — docs aligned to implementation reality |
| DEV-17 | P2 | done | agent | Add practical usage documentation for operators and agents | Added `docs/usage.md` with tool-by-tool examples, scope/error contracts, workflows, and verification commands; linked from README | Yes — docs/usage.md with tool-by-tool examples and workflows |
| DEV-18 | P1 | done | agent | Register memory MCP server in central capabilities registry and verify cross-client installability | Added `memory-layer` tool capability in capabilities registry, regenerated inventory, verified discovery via `query_capabilities`, and validated Codex/Claude/Gemini installer dry-runs | Yes — memory-layer registered in capabilities registry, cross-client installability verified |
| DEL-01 | P1 | done | agent | Phase 1 Intake & Readiness Check — verify Develop outputs | All checks pass, delivery scope understood | Yes — readiness confirmed, delivery scope locked |
| DEL-02 | P1 | done | agent | Phase 2 Delivery Capability Assessment — manifest.md + capabilities.md | Artifacts created with registry summary | Yes — manifest.md and capabilities.md produced |
| DEL-03 | P1 | done | agent | Phase 3 Delivery Planning — plan.md + tasks.md | Plan with 3-tier testing, rollback, 11 atomic tasks | Yes — plan with 3-tier testing and 11 atomic tasks delivered |
| DEL-04 | P1 | done | agent | Phase 4 Review & Approval (simplified) | Self-review passed, human approved | Yes — self-review passed, human approval received |
| DEL-05 | P1 | done | agent | Phases 5+6 Infrastructure + Deployment | Claude Code connected; scope bug fixed; Codex/Gemini deferred | Yes — Claude Code connected; Codex/Gemini deferred as planned |
| DEL-06 | P1 | done | agent | Phase 7 Validation (Tier 1+2+3) | All tiers pass; 10/10 success criteria met | Yes — all tiers pass, 10/10 success criteria met |
| DEL-07 | P1 | done | agent | Phase 8 Milestone Closeout | Success criteria mapped, access docs, seal | Yes — sealed with access docs and success criteria mapped |
| FIX-01 | P0 | done | agent | Add `client_profiles` to production config — root cause of scope narrowing | `memory_config.yaml` has profiles for claude-code, krypton, adf; callers can retrieve memories from their project namespaces | Yes — config now has client profiles for claude-code, krypton, adf |
| FIX-02 | P0 | done | agent | Fix stdio transport test stale tool count (14→15) | `scripts/mcp_stdio_test.py` passes with `success=true` | Yes — stdio transport test passes with success=true |
| POST-02 | P1 | done | agent | Add usage logging to MCP server | Every tool call logs caller_id, tool name, namespace, timestamp to append-only store. Foundation for all observability. | Yes — every tool call now logs caller_id, tool name, namespace, timestamp |
| POST-03 | P1 | moved | — | Codify multi-system session protocol in ADF spec + global CLAUDE.md → **moved to ADF B86** | Touches ADF repo, not memory-layer. Tracked at `~/code/_shared/adf/BACKLOG.md#B86`. | Moved — tracked at ADF B86 |
| POST-04 | P2 | done | agent | Add usage report tool (`get_usage_report`) | MCP tool or script that reports: memories written/searched this period, search-to-write ratio, active namespaces, dedup rate, empty searches (gap signal) | Yes — get_usage_report provides search/write ratio and gap signals |
| POST-05 | P2 | moved | — | Register memory MCP in Codex and Gemini → **moved to capabilities-registry CR-10** | Codex CLI installed + registered; Gemini API key configured + registered | Moved — tracked at capabilities-registry CR-10 |
| POST-06 | P3 | moved | — | Weekly review cadence → **moved to Krypton B17** | `/focus` should surface weekly memory review reminder | Moved — tracked at Krypton B17 |
| V1-P1 | P0 | done | agent | Phase 1: Episodic log foundation | 119 tests pass, 18 MCP tools, validator PASS | Yes — 119 tests pass, 18 MCP tools, validator PASS |
| V1-P2 | P1 | done | agent | Phase 2: Session lifecycle + Claude Code capture | /handoff skill, CLAUDE.md briefing protocol, SessionEnd hook, transcript extractor, Codex AGENTS.md update | Yes — /handoff skill, SessionEnd hook, transcript extractor all delivered |
| V1-P3 | P2 | done | agent | Phase 3: Governance utilities | verify_chain MCP tool, source_ref on write_memory, episode stats in get_usage_report, docs update | Yes — verify_chain, source_ref, episode stats all delivered |
