---
project: "Memory Layer"
updated: "2026-02-10"
---

# Backlog

## In Progress

| id | priority | status | owner | description | done_when |
|----|----------|--------|-------|-------------|-----------|
| DEV-14 | P1 | in_progress | agent | Add MCP-level integration tests for 9-tool surface and error contracts | Integration suite verifies tool payloads, scope errors, and lifecycle flows |

## Todo

| id | priority | status | owner | description | done_when |
|----|----------|--------|-------|-------------|-----------|
| DEV-15 | P2 | todo | agent | Add packaging/dev setup commands to README and verify clean bootstrap path | Fresh checkout setup is documented and reproducible |
| DEV-16 | P2 | todo | agent | Review and align docs with implemented behavior and outstanding gaps | design/brief/status/backlog consistency verified and updated |

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
