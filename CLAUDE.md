# Memory Layer

## Intent

See `docs/intent.md`

## Classification

- **Type:** App
- **Scale:** personal
- **Scope:** mvp
- **Complexity:** standalone

## Current Stage

Deliver

## Context Map

| File | Load When | Purpose |
|------|-----------|---------|
| AGENTS.md | Always | Required operating rules (tasks, backlog, status, commits) |
| docs/intent.md | Always | North Star |
| docs/status.md | Always | Session state — review at start, update at end |
| docs/backlog.md | Always | Active task queue and execution order |
| docs/discover-brief.md | Deliver | Success criteria reference |
| docs/design.md | Deliver (validation) | Architecture reference |
| docs/usage.md | Deliver | Tool-by-tool usage examples |
| docs/memory-routing.md | Always | Memory routing heuristic — when to use MCP vs local memory vs KB |

## Architecture Reference

- Ecosystem infrastructure — not tied to any single project or agent
- Follows KB project patterns: SQLite + Chroma + MCP server
- KB project location: `~/code/_shared/knowledge-base/`
- Prior research (ACK): `~/code/sandbox/ai-dev/ack/`
- Python, local-first, single-user

## Stack

- Language: Python
- Storage: SQLite + Chroma
- API: MCP server (stdio, FastMCP)
- Embeddings: sentence-transformers (all-MiniLM-L6-v2)

## Commands

- Setup: `pip install -e ".[dev]"`
- Test: `python -m pytest tests/ -q`
- Smoke: `python scripts/mcp_smoke.py --json`
- Stdio test: `python scripts/mcp_stdio_test.py --json`
- Server: `python -m memory_core.access.mcp_server`

## Workflow Requirements

- Always execute work from `docs/backlog.md` in priority order.
- Update backlog task status continuously (`todo`, `in_progress`, `blocked`, `done`).
- Update `docs/status.md` at every meaningful milestone.
- Make regular small commits for tested slices, not one final commit.
