---
project: "Memory Layer"
updated: "2026-02-10"
---

# Backlog

## In Progress

| id | priority | status | owner | description | done_when |
|----|----------|--------|-------|-------------|-----------|
| - | - | - | - | No active backlog items. | Add next prioritized work item before implementation resumes |

## Todo

| id | priority | status | owner | description | done_when |
|----|----------|--------|-------|-------------|-----------|
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
