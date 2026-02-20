# Memory Layer — System Overview

> Generated: 2026-02-19. Covers architecture, data flows, validation gaps, and backlog state.

## Diagrams

| File | Description |
|------|-------------|
| `docs/diagrams/01-system-architecture.png` | High-level 4-layer architecture — consumers → MCP → core → dual store |
| `docs/diagrams/02-write-flow.png` | Sequence diagram — full write/capture path with all dedup branches |
| `docs/diagrams/03-read-flow.png` | Data flow — scope resolution + search + recent paths |

---

## Architecture

The system is a 3-layer MCP server backed by a dual store (SQLite + Chroma).

```
Consumers (Claude Code, Krypton, ADF agents, manual user)
    │  MCP stdio transport
    ▼
MCP Server — access/mcp_server.py
    15 tools, Pydantic validation, _run_tool() dispatch wrapper, usage logging
    │  Python API
    ▼
MemoryStorage — storage/api.py
    All business logic: write/dedup, search, scope resolution, stats, reconciliation
    │                           │
    ▼                           ▼
SQLite WAL                  Chroma
data/memory.db              data/chroma/
metadata + lifecycle        vector embeddings + semantic search
source of truth             search-only, no authoritative state
```

**Supporting components:**
- `utils/embeddings.py` — all-MiniLM-L6-v2, local/offline only, 384-dim output
- `utils/consolidation.py` — SHA-256 idempotency key, canonical text normalization
- `config.py` — loads `memory_config.yaml`, including `client_profiles` for scope auth
- `access/usage_logger.py` — append-only JSONL log at `data/usage.jsonl`
- `access/usage_reporter.py` — metrics from usage log (tool counts, error rate, etc.)

---

## How Memories Get Captured

**There is no automatic capture.** Agents must explicitly call `write_memory`. No hooks, no session monitoring. The ADF session protocol (global CLAUDE.md) instructs agents to call `write_memory` at session end with cross-project learnings — that's the only governance, and it's not enforced.

### Write path (`write_memory`)

```
Agent calls: write_memory(content, namespace, writer_id, memory_type, confidence)
    │
    ▼
1. Build idempotency key: SHA-256(namespace + canonical(content))
    │
    ▼
2. INSERT into SQLite — status = staged
    ├── IdempotencyConflictError → exact duplicate detected
    │       return { action: skipped, similar_id: <existing> }
    │
    ▼ (no conflict)
3. embed_text(content) → EmbeddingService → float[384]  [local, never cloud]
    │
    ▼
4. Chroma: query_similar(embedding, limit=5, allowed_ids=committed in namespace)
    ├── top hit similarity ≥ 0.92 → semantic duplicate
    │       DELETE staged row from SQLite
    │       return { action: skipped, similar_id: <hit>, similarity: 0.94 }
    │
    ▼ (below threshold — new memory)
5. Chroma: upsert_memory(id, content, embedding, metadata)
6. SQLite: set_status(id, COMMITTED)
    return { action: added, id: <uuid> }

    ▼ (on any exception in steps 3-6)
    SQLite: set_status(id, FAILED)
    [survives for retry via retry_failed_memory tool]
```

**Dedup has two layers:**
1. **Deterministic** — exact match on SHA-256 of normalized content + namespace. Zero Chroma cost.
2. **Semantic** — cosine similarity ≥ 0.92 against committed entries in the same namespace. Catches near-duplicates.

---

## How Memories Are Retrieved

Every read path starts with **scope resolution**.

### Scope resolution (`_resolve_scope`)

```
caller_id → config.client_profiles.get(caller_id)
    │
    ├── Profile found → use profile.allowed_namespaces, can_cross_scope, can_access_private
    │
    └── No profile found → FALLBACK:
            allowed_namespaces = [caller_id, "global"]
            can_cross_scope = False
            ⚠ THIS IS THE CURRENT STATE — no profiles in production config

Intersect: requested_namespace(s) ∩ allowed_namespaces
    │
    ├── Empty intersection → ScopeForbidden → error returned to caller
    │
    └── Effective namespaces → passed to storage queries
```

### `search_memories` (semantic search)

```
1. _resolve_scope → effective namespaces
2. SQLite: get_committed_ids_by_namespaces(namespaces) → candidate ID set
3. EmbeddingService: embed_text(query) → float[384]
4. Chroma: query_similar(query_embedding, limit, allowed_ids=candidates)
5. Convert: similarity = max(0, min(1, 1.0 - cosine_distance))
6. Return: List[SearchResultItem] ranked by similarity desc
```

### `get_recent` (time-filtered)

```
1. _resolve_scope → effective namespaces
2. SQLite: list_memories(status=COMMITTED, namespaces, limit*3)
3. Filter: created_at >= now - timedelta(days=days)
4. Return: List[MemoryEntry] sorted by created_at desc, truncated to limit
```

### `get_session_context` (combined)

Calls both `get_recent` and `search_memories` (if query provided) and merges into:
```json
{ "recent": [...MemoryEntry], "relevant": [...SearchResultItem] }
```

---

## Storage Model

**SQLite `memories` table** — 11 columns:

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| content | TEXT | The memory text |
| namespace | TEXT | Scope: project name, "global", or "private" |
| memory_type | TEXT | observation, preference, decision, progress, relationship |
| status | TEXT | staged → committed \| failed \| archived |
| idempotency_key | TEXT | SHA-256 of namespace+canonical content. Unique across staged/committed. |
| writer_id | TEXT | Who wrote it (e.g. "claude-code") |
| writer_type | TEXT | agent or user |
| source_project | TEXT | Optional project context |
| confidence | REAL | 0.0–1.0 |
| created_at / updated_at | DATETIME | UTC timestamps |

**Chroma collection** — one entry per committed memory:
- Embedding: float[384] (all-MiniLM-L6-v2)
- Stored metadata: memory_type, namespace, writer_type, writer_id, confidence, created_at
- IDs kept in sync with SQLite via `reconcile_dual_store`

**Lifecycle states:**
```
staged → committed   (normal write)
staged → failed      (embedding or Chroma error)
committed → archived (explicit archive_memory call)
failed → committed   (retry_failed_memory)
failed → archived    (archive_failed_memory)
```

---

## 15 MCP Tools

| Category | Tool | Description |
|----------|------|-------------|
| Write | `write_memory` | Write with dedup |
| Read | `search_memories` | Semantic search, scope-filtered |
| Read | `get_memory` | Fetch by ID |
| Read | `get_recent` | Time-windowed recent entries |
| Read | `get_session_context` | Combined recent + relevant |
| Manage | `update_memory` | Update content or metadata |
| Manage | `archive_memory` | Soft-delete a committed entry |
| Manage | `review_candidates` | Surface low-confidence or high-similarity pairs |
| Stats | `get_stats` | Counts by type/namespace + drift metrics |
| Maintenance | `reconcile_dual_store` | Repair SQLite/Chroma divergence |
| Maintenance | `list_failed_memories` | Inspect failed entries |
| Maintenance | `retry_failed_memory` | Re-attempt vector write for failed entry |
| Maintenance | `archive_failed_memory` | Discard unrecoverable failed entry |
| Observability | `get_usage_report` | Metrics from usage.jsonl |
| Observability | `health` | Liveness check |

---

## Validation Gaps (2026-02-19)

### Critical — in backlog

| ID | Issue |
|----|-------|
| FIX-01 | `memory_config.yaml` has no `client_profiles` section. All callers fall back to `allowed_namespaces=[caller_id, "global"]`. Any memory written to a project namespace (e.g. `memory-layer`) is silently unreachable unless caller_id matches the namespace. **Root cause of system not working as intended.** |
| FIX-02 | `scripts/mcp_stdio_test.py` line 121 checks `len(tool_names) == 14` but server exposes 15 tools. Stdio transport test always fails — no regression coverage for the live transport path. |

### Medium — not backlogged

- `write_memory` has no namespace authorization. Any caller can write to any namespace including `private`. Read paths enforce scope; write path does not.

### Low — informational

- `status.md` says "14 MCP tools" in the Develop and Deliver handoff sections (written before `get_usage_report` was added in POST-04). Current state header is correct at 15.
- `_find_semantic_duplicate` queries Chroma for top-5 hits but returns only the first non-self hit. The other 4 are discarded. Functionally correct for dedup; no impact on `review_candidates` (which runs its own queries).

---

## What Was Explicitly Deferred (by design)

| Feature | Decision |
|---------|---------|
| Session-end auto-capture hook | Post-MVP. Agents call `write_memory` explicitly per ADF discipline. |
| LLM-based curation (ADD/UPDATE/DELETE/NOOP) | Post-MVP. MVP uses vector similarity + rules (ADD/SKIP only). |
| Background consolidation / merge | Post-MVP. Write-time dedup only. |
| Decay / pruning | Future — add when volume demands. |
| REST API | Future — MCP only for MVP. |
| Graph memory / relationship traversal | Future — flat entries + vector search for MVP. |
| Multi-user / multi-tenant | Out of scope — single-user, local-first by design. |
| UI / dashboard | Future. |
| Codex / Gemini CLI registration | Blocked — Codex not installed, Gemini needs API key. Tracked in capabilities-registry CR-10. |
| ADF session protocol in CLAUDE.md | Tracked in ADF B86. |
| Weekly review cadence | Tracked in Krypton B17. |
