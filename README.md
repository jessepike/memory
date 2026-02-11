# Memory Layer

Local-first persistent memory service for agent workflows.

## Requirements

- Python 3.11+
- `pip` and `venv`

## Bootstrap

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Development Commands

Run tests:

```bash
python -m pytest -q
```

Run the MCP smoke checklist:

```bash
python scripts/mcp_smoke.py --json
```

Run the MCP server over stdio:

```bash
python -m memory_core.access.mcp_server
```

## Notes

- Runtime data is stored under `data/` (gitignored).
- Default runtime configuration lives in `config/memory_config.yaml`.
- If runtime is configured with `enforce_offline: true`, ensure embedding model artifacts are already provisioned locally.

## Connecting Clients

The memory server uses stdio transport — each client spawns its own process on demand.

**Claude Code** (already registered at user scope):
```bash
claude mcp add -s user memory -- uv run --directory ~/code/_shared/memory python -m memory_core.access.mcp_server
```

**Codex:**
```bash
codex mcp add memory -- uv run --directory ~/code/_shared/memory python -m memory_core.access.mcp_server
```

**Gemini:**
```bash
gemini mcp add -s user memory uv run --directory ~/code/_shared/memory python -m memory_core.access.mcp_server
```

Once registered, memory tools (`write_memory`, `search_memories`, `get_memory`, etc.) are available in every session. See `docs/usage.md` for tool-by-tool examples.

## Usage Guide

- See `docs/usage.md` for practical tool-by-tool usage examples and common workflows.
