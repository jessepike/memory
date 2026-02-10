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

## Usage Guide

- See `docs/usage.md` for practical tool-by-tool usage examples and common workflows.
