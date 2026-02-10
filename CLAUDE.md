# Memory Layer

## Intent

See `docs/intent.md`

## Classification

- **Type:** App
- **Scale:** personal
- **Scope:** mvp
- **Complexity:** standalone

## Current Stage

Develop

## Context Map

| File | Load When | Purpose |
|------|-----------|---------|
| AGENTS.md | Always | Required operating rules (tasks, backlog, status, commits) |
| docs/intent.md | Always | North Star |
| docs/status.md | Always | Session state — review at start, update at end |
| docs/backlog.md | Always | Active task queue and execution order |
| docs/discover-brief.md | Design | Primary input — fully consumed |
| docs/design.md | Design (after created) | Working design spec |

## Architecture Reference

- Ecosystem infrastructure — not tied to any single project or agent
- Follows KB project patterns: SQLite + Chroma + MCP server
- KB project location: `~/code/_shared/knowledge-base/`
- Prior research (ACK): `~/code/sandbox/ai-dev/ack/`
- Python, local-first, single-user

## Stack

- Language: Python
- Storage: SQLite + Chroma
- API: MCP server (stdio)
- Framework: TBD (Design stage)

## Commands

- Setup: `TBD`
- Dev: `TBD`
- Test: `TBD`

## Workflow Requirements

- Always execute work from `docs/backlog.md` in priority order.
- Update backlog task status continuously (`todo`, `in_progress`, `blocked`, `done`).
- Update `docs/status.md` at every meaningful milestone.
- Make regular small commits for tested slices, not one final commit.
