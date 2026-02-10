# Memory Layer

## Intent

See `docs/intent.md`

## Classification

- **Type:** App
- **Scale:** personal
- **Scope:** mvp
- **Complexity:** standalone

## Current Stage

Discover

## Context Map

| File | Load When | Purpose |
|------|-----------|---------|
| docs/intent.md | Always | North Star |
| docs/status.md | Always | Session state — review at start, update at end |
| docs/discover-brief.md | Discover, Design | Project contract |
| memory-layer-research.md | Reference | Research synthesis informing design |

## Architecture Reference

- Follows KB project patterns: SQLite + Chroma + MCP server
- KB project location: `~/code/_shared/knowledge-base/`
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
