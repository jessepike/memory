---
type: "design"
project: "Memory Layer"
version: "0.1"
status: "draft"
created: "2026-02-10"
updated: "2026-02-10"
brief_ref: "./discover-brief.md"
intent_ref: "./intent.md"
---

# Design: Memory Layer

## Summary

Technical specification for the Memory Layer — a persistent, queryable memory service for the personal agent ecosystem. Transforms the validated Brief (v0.6) into an implementable architecture following the Knowledge Base project's proven patterns (SQLite + Chroma + MCP), adapted for contextual memory semantics with local-only embeddings.

**Classification:** App / personal / mvp / standalone

## Architecture

### System Structure

```
┌─────────────────────────────────────────────────────┐
│                    Consumers                         │
│  ADF Agents  │  Krypton  │  Manual (user via MCP)   │
└──────────────┬──────────────────────────────────────┘
               │ MCP (stdio)
┌──────────────▼──────────────────────────────────────┐
│              MCP Server (access layer)               │
│  - Tool definitions + dispatch                       │
│  - Input validation (Pydantic)                       │
│  - No business logic                                 │
└──────────────┬──────────────────────────────────────┘
               │ Python API
┌──────────────▼──────────────────────────────────────┐
│              MemoryStorage (core library)             │
│  - Write with consolidation                          │
│  - Search with namespace filtering                   │
│  - Archive, review, stats                            │
│  - Embedding generation (local)                      │
└──────┬───────────────────────────┬──────────────────┘
       │                           │
┌──────▼──────────┐  ┌────────────▼─────────────────┐
│  SQLite (WAL)    │  │  Chroma (PersistentClient)   │
│  - Entry metadata│  │  - Vector embeddings          │
│  - Status tracking│ │  - Semantic search             │
│  - Schema.sql    │  │  - Metadata filtering          │
└─────────────────┘  └────────────────────────────────┘
```

### Package Layout

```
memory/
├── memory_core/
│   ├── __init__.py
│   ├── config.py              # YAML + env config
│   ├── models.py              # Pydantic data models
│   ├── access/
│   │   └── mcp_server.py      # MCP server (stdio)
│   ├── storage/
│   │   ├── api.py             # MemoryStorage class
│   │   ├── db.py              # SQLite operations
│   │   ├── vector_store.py    # Chroma wrapper
│   │   └── schema.sql         # DDL
│   └── utils/
│       ├── embeddings.py      # sentence-transformers wrapper
│       └── consolidation.py   # Write-time dedup
├── config/
│   └── memory_config.yaml
├── data/                      # Runtime (gitignored)
│   ├── memory.db
│   └── chroma/
├── tests/
│   ├── test_storage/
│   ├── test_access/
│   ├── test_utils/
│   └── conftest.py
├── pyproject.toml
└── README.md
```

### Key Architectural Decisions

- **Core library pattern** — All business logic in `MemoryStorage`. MCP server is a thin dispatch layer. This enables future REST adapter without duplicating logic (Brief success criterion #10).
- **Local embeddings** — Diverges from KB (which uses OpenAI cloud). Uses sentence-transformers `all-MiniLM-L6-v2` for offline operation. No external API dependencies.
- **Staged commit** — Follows KB's pattern: SQLite write (staged) → embed → Chroma write → SQLite update (committed). Idempotent vector writes make rollback unnecessary.

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | KB consistency |
| Package mgr | uv | KB consistency |
| Structured store | SQLite (WAL mode) | KB pattern, local-first |
| Vector store | ChromaDB >= 0.4.0 | KB pattern, local persistence |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | 384 dims, ~80MB, local-only, Chroma-compatible |
| Data models | Pydantic v2 | KB pattern, validation |
| MCP | mcp >= 1.0.0 | Protocol library |
| Testing | pytest, pytest-asyncio, pytest-cov | KB pattern |
| Linting | ruff | KB pattern |
| Type checking | mypy | KB pattern |

## Data Model

### Memory Entry (SQLite: `memories` table)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PK, UUID4 | Unique identifier |
| `content` | TEXT | NOT NULL | The atomic fact / memory text |
| `memory_type` | TEXT | NOT NULL | observation, preference, decision, progress, relationship |
| `namespace` | TEXT | NOT NULL, DEFAULT 'global' | Scoping: project name, "global", or "private" |
| `writer_id` | TEXT | NOT NULL | Who wrote it (e.g., "adf-agent", "krypton", "user") |
| `writer_type` | TEXT | NOT NULL | agent, user, system |
| `source_project` | TEXT | | Originating project (context, may differ from namespace) |
| `confidence` | REAL | DEFAULT 1.0 | 0.0-1.0, low values surface in review_candidates |
| `status` | TEXT | NOT NULL, DEFAULT 'staged' | staged, committed, failed, archived |
| `created_at` | TEXT | NOT NULL | ISO 8601 timestamp |
| `updated_at` | TEXT | NOT NULL | ISO 8601 timestamp |

**Indexes:**
- `idx_memories_namespace` on (namespace, status)
- `idx_memories_type` on (memory_type)
- `idx_memories_created` on (created_at DESC)
- `idx_memories_status` on (status)

### Chroma Collection: `memories`

| Field | Value |
|-------|-------|
| Collection name | `memories` |
| Distance metric | cosine |
| Embedding model | all-MiniLM-L6-v2 (384 dims) |
| ID | Memory UUID (same as SQLite) |
| Document | `content` text |
| Metadata | `memory_type`, `namespace`, `writer_type`, `confidence`, `created_at` |

**Note:** No chunking needed. Memory entries are atomic facts — single sentences or short paragraphs. Each entry = one embedding. This is simpler than KB (which chunks long documents).

### Namespace Scoping Rules

| Namespace | Stored as | Default search behavior | Explicit query |
|-----------|-----------|------------------------|----------------|
| Project | Project name (e.g., "memory-layer") | Included when caller's namespace matches | `namespace="memory-layer"` |
| Global | `"global"` | Always included in search | `namespace="global"` |
| Private | `"private"` | Excluded from search unless explicitly requested | `namespace="private"` |

**Search resolution:** When a caller searches with `namespace="memory-layer"`:
1. Search entries where namespace = "memory-layer" OR namespace = "global"
2. Exclude namespace = "private" (unless caller explicitly passes `namespace="private"`)
3. Exclude status = "archived"

When namespace is omitted, search global only (+ exclude private, archived).

### Status State Machine

```
staged → committed    (normal write path)
staged → failed       (embedding or Chroma failure)
committed → archived  (soft delete via archive_memory)
```

## Interface: MCP Tools

### Overview

9 tools across 4 categories. All tools accept JSON parameters and return JSON responses.

### Write Tools

**`write_memory`** — Create a new memory with write-time consolidation.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| content | string | yes | | The memory text (atomic fact) |
| memory_type | string | no | "observation" | observation, preference, decision, progress, relationship |
| namespace | string | no | "global" | Project name, "global", or "private" |
| writer_id | string | no | "unknown" | Caller identifier |
| writer_type | string | no | "agent" | agent, user, system |
| source_project | string | no | | Originating project context |
| confidence | float | no | 1.0 | 0.0-1.0 |

Returns: `{ id, action: "added" | "skipped", similar_id?, similarity? }`

Consolidation runs before write — see Write-Time Consolidation section.

**`update_memory`** — Update an existing memory entry.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| id | string | yes | Memory UUID |
| content | string | no | Updated text (triggers re-embedding) |
| memory_type | string | no | Updated type |
| namespace | string | no | Updated namespace |
| confidence | float | no | Updated confidence |

Returns: `{ id, updated_fields: [...] }`

### Read Tools

**`search_memories`** — Semantic search with namespace filtering.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| query | string | yes | | Search query |
| namespace | string | no | | If set, searches this namespace + global. If omitted, global only. |
| memory_type | string | no | | Filter by type |
| limit | int | no | 10 | Max results |

Returns: `[{ id, content, memory_type, namespace, similarity, writer_id, created_at }]`

**`get_memory`** — Get a single memory by ID.

Returns: Full memory entry (all fields).

**`get_recent`** — Get recent memories.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| namespace | string | no | | Filter by namespace |
| memory_type | string | no | | Filter by type |
| limit | int | no | 20 | Max results |
| days | int | no | 7 | Lookback window |

Returns: `[{ id, content, memory_type, namespace, writer_id, created_at }]`

**`get_session_context`** — Contextual retrieval for session start.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| namespace | string | yes | | Project namespace |
| query | string | no | | Optional focus query |
| limit | int | no | 10 | Max per section |

Returns: `{ recent: [...], relevant: [...] }` — recent entries for namespace + semantic matches if query provided.

### Manage Tools

**`archive_memory`** — Soft-delete a memory.

| Param | Type | Required |
|-------|------|----------|
| id | string | yes |

Sets status = "archived", removes embedding from Chroma. Returns: `{ id, archived: true }`

**`review_candidates`** — Surface memories needing human review.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| namespace | string | no | | Filter by namespace |
| limit | int | no | 20 | Max results |

Returns entries where confidence < 0.7 OR has high-similarity pair (>= 0.85 with another committed entry).

Returns: `[{ id, content, reason: "low_confidence" | "high_similarity", confidence?, similar_entries?: [{ id, content, similarity }] }]`

### Stats Tools

**`get_stats`** — Memory statistics.

| Param | Type | Required |
|-------|------|----------|
| namespace | string | no |

Returns: `{ total, by_type: {}, by_namespace: {}, recent_7d, recent_30d }`

## Write-Time Consolidation

Runs on every `write_memory` call to prevent duplicate accumulation.

### Algorithm

```
1. Generate embedding for new content
2. Search Chroma for top-5 similar entries in target namespace + global
   - Filter: status = 'committed', same namespace OR 'global'
3. Check top result similarity:
   - >= 0.92: SKIP — return { action: "skipped", similar_id, similarity }
   - < 0.92: ADD — proceed with staged commit
4. No UPDATE or MERGE for MVP
```

### Design Rationale

- **0.92 threshold** — Conservative. Only suppresses near-identical entries. Reduces false-positive merges.
- **Top-5 search** — Small k keeps consolidation fast. Only top-1 similarity matters for SKIP decision, but returning top-5 provides context for `review_candidates`.
- **No MERGE** — MVP avoids the complexity of deciding which version to keep or how to merge. LLM-based consolidation (post-MVP) will handle UPDATE/DELETE.
- **Namespace-scoped** — Dedup checks within the same namespace + global. A project-scoped fact can coexist with a similar global fact.

## Security

- **Single-user, no auth** — No authentication or authorization layer
- **Namespace isolation** — Enforced at query time via metadata filtering, not access control
- **Private namespace** — Excluded from default search; requires explicit request
- **No secrets** — Memory entries should not contain credentials or API keys (user responsibility, not system enforcement)
- **Local-only** — No external network calls. Embeddings computed locally. No data leaves the machine.

## Capabilities

### Runtime Dependencies
- Python 3.11+, uv, SQLite3 (system), sentence-transformers, chromadb, mcp, pydantic

### Development Dependencies
- pytest, pytest-asyncio, pytest-cov, ruff, mypy

### MCP Configuration
- Transport: stdio
- Entry point: `python -m memory_core.access.mcp_server`
- Config: `config/memory_config.yaml` (data paths, thresholds)

### Integration Points
- ADF agents: call MCP tools at session-end per ADF discipline
- Krypton: cross-namespace search consumer
- Future: REST adapter wrapping `MemoryStorage` (no code in MCP layer)

## Decision Log

| # | Decision | Options Considered | Rationale |
|---|----------|--------------------|-----------|
| D1 | Caller-provided namespace | Caller param vs cwd-derived vs MCP metadata | Simplest. No magic. Matches KB pattern (callers specify context). cwd-derived is fragile in MCP stdio. |
| D2 | Local embeddings (all-MiniLM-L6-v2) | all-MiniLM-L6-v2 vs Chroma default vs nomic-embed-text | 384 dims, ~80MB, fast, well-tested. Satisfies local-only constraint. Good quality-to-size ratio. |
| D3 | Namespace-only scoping | Namespace only vs namespace + visibility vs merged scope field | Single-user — visibility adds complexity for zero benefit. Namespace (project/global/private) covers all MVP needs. |
| D4 | Conservative dedup (0.92+) | 0.92 skip-only vs 0.85 with merge vs configurable | Conservative avoids false merges. Can tighten later. No merge logic reduces MVP complexity. |
| D5 | No chunking | No chunking vs token-based chunks | Memories are atomic facts (short). One entry = one embedding. Unlike KB docs, no need to chunk. |
| D6 | Staged commit pattern | KB-style staged commit vs direct write vs WAL-only | Proven in KB. Handles SQLite+Chroma consistency without 2PC. Idempotent Chroma writes. |
| D7 | Private = excluded from default search | Excluded by default vs hidden flag vs separate store | Clean namespace semantics. Private memories only surface on explicit request. No extra schema needed. |

## Backlog

Post-MVP items from Brief (Out of Scope) + Design decisions:

- LLM-based consolidation — ADD/UPDATE/DELETE/NOOP per Mem0 pattern (replaces rule-based)
- Decay/pruning — time-based or access-frequency-based memory expiration
- Hook-based capture — PostToolUse/Stop hooks for automatic memory extraction
- Graph memory — relationship traversal beyond flat entries + vector search
- REST API adapter — second interface wrapping `MemoryStorage`
- Memory-to-KB promotion — automated bridge (MVP: user decides manually)
- State profiles — entity-level summaries layered on top of atomic facts
- UI/dashboard — memory browsing and curation interface
- Configurable dedup threshold — move 0.92 to config file
- Multi-user support — auth, tenancy, access control

## Open Questions

None remaining. All questions resolved during Intake & Clarification.

Caller identity (the one question carried from Discover) resolved as D1: caller-provided namespace parameter.

## Issue Log

| # | Issue | Source | Severity | Status | Resolution |
|---|-------|--------|----------|--------|------------|
| — | No issues found yet | — | — | — | Pending review |

## Develop Handoff

> Populated after review. Summarizes design decisions, capabilities, and implementation guidance for the Develop stage.

*Section will be completed during Finalization phase.*

## Review Log

> Populated during review phases.

*Section will be completed during Review Loop.*

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-10 | Initial draft from Intake & Clarification decisions. Full technical spec. |
