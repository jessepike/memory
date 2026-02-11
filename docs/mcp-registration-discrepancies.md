---
type: discrepancy-report
project: Memory Layer
created: 2026-02-10
scope: MCP registration + capabilities registry
target-agent: adf-server developer
---

# MCP Registration & Registry Discrepancies

## Issue 1: Memory Layer MCP server not registered in Claude Code

**Severity:** High — server is built but unusable

**Problem:** The memory-layer MCP server was built and its launcher config was added to the capabilities registry (`capabilities/tools/memory-layer/capability.yaml`), but it was never registered in the user's Claude Code settings (`~/.claude/settings.json`). The `/mcp` panel showed no `memory` server.

**Resolution:** Added `mcpServers.memory` entry to `~/.claude/settings.json` with:
- Command: `~/code/_shared/memory/.venv/bin/python -m memory_core.access.mcp_server`
- Env: `PYTHONPATH=~/code/_shared/memory/src`

**Status:** Fixed (2026-02-10)

---

## Issue 2: `get_capability_detail` ADF MCP tool fails for all typed capabilities

**Severity:** High — affects entire capabilities registry lookup

**Problem:** The ADF server's `get_capability_detail` tool constructs the filesystem path as:

```
{REGISTRY_ROOT}/capabilities/{capability_id}/capability.yaml
```

But the actual directory structure organizes capabilities by type:

```
{REGISTRY_ROOT}/capabilities/{type}/{capability_id}/capability.yaml
```

For example, `memory-layer` lives at `capabilities/tools/memory-layer/capability.yaml`, but the tool looks for `capabilities/memory-layer/capability.yaml`.

**Location:** `/Users/jessepike/code/_shared/adf/adf-server/src/tools/capabilities.ts` (lines ~84-102)

**Impact:** `get_capability_detail` returns "not found" for every capability in the registry, since all capabilities are organized under type subdirectories (`agents/`, `plugins/`, `skills/`, `tools/`).

**Fix needed:** The path construction must include the type directory. Options:
1. Accept a `type` parameter alongside `capability_id`
2. Search across all type subdirectories for the matching ID
3. Use `inventory.json` to resolve `name → type → path`

**Status:** Open — needs fix in adf-server

---

## Issue 3: `inventory.json` missing `id` field

**Severity:** Low — cosmetic but affects programmatic lookup

**Problem:** Entries in `inventory.json` use `name` as the identifier but have no explicit `id` field. The `capability.yaml` files have `install_id` but this isn't mirrored in the JSON index. If any tool expects an `id` key, lookups fail silently.

**Status:** Open — consider adding `id` field to inventory entries for consistency
