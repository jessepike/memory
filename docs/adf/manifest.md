---
type: "manifest"
project: "Memory Layer"
stage: "deliver"
created: "2026-02-11"
---

# Deployment Manifest

## Deployment Target

Local agent ecosystem on developer laptop. MCP server accessed via stdio transport — each client spawns its own process on demand. No long-running daemon.

## Runtime Dependencies

| Dependency | Purpose | Already Present |
|-----------|---------|-----------------|
| Python 3.12+ | Runtime | Yes (pyenv) |
| Virtual environment | Isolated packages | Yes (`.venv/`) |
| `pip install -e ".[dev]"` | Package + deps | Yes (editable install) |
| SQLite (WAL mode) | Structured storage | Yes (stdlib) |
| Chroma | Vector store | Yes (pip dep) |
| sentence-transformers | Local embeddings | Yes (pip dep) |
| `all-MiniLM-L6-v2` | Embedding model | Downloaded on first run |

## Storage Locations

| Store | Path | Shared Across Clients |
|-------|------|-----------------------|
| SQLite DB | `data/memory.db` (relative to project) | Yes — WAL mode for concurrency |
| Chroma data | `chroma_data/` (relative to project) | Yes — persistent local |
| Config | `config/default.yaml` | Yes |

## Client Configurations Required

Each client needs an MCP server entry pointing to the same server:

| Client | Config Method | Scope |
|--------|--------------|-------|
| Claude Code | `claude mcp add` | project or user |
| Codex | `codex mcp add` | global |
| Gemini | `gemini mcp add` | user |

All use the same launcher from `capability.yaml`:
- **Command:** `${HOME}/code/_shared/memory/.venv/bin/python`
- **Args:** `-m memory_core.access.mcp_server`
- **Env:** `PYTHONPATH=${HOME}/code/_shared/memory/src`

## Hosting / Infrastructure

None. Local-only, no cloud services, no ports, no DNS.

## CI/CD

None for MVP. Manual install per client.

## Secrets / Credentials

None. No API keys, no auth tokens. Local-first, single-user.
