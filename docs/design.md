---
type: "design"
project: "Memory Layer"
version: "0.3"
status: "external-review-complete"
created: "2026-02-10"
updated: "2026-02-10"
brief_ref: "./discover-brief.md"
intent_ref: "./intent.md"
---

# Design: Memory Layer

## Summary

Technical specification for the Memory Layer — a persistent, queryable memory service for the personal agent ecosystem. Transforms the validated Brief (v0.6) into an implementable architecture following the Knowledge Base project's proven patterns (SQLite + Chroma + MCP), adapted for contextual memory semantics with local-only embeddings.

**Classification:** App / personal / mvp / standalone

### Brief Deviations

Design simplifies two Brief items based on Intake decisions:

1. **Visibility controls dropped** (D3) — Brief lists "Visibility controls (public, restricted, private)" in scope and "visibility metadata" in success criterion #2. Design replaces visibility with namespace-only scoping (project/global/private). In a single-user system, namespace provides equivalent isolation. Success criterion #2 is satisfied: agents write memories with scope (namespace), type (memory_type), and writer metadata.

2. **Consolidation simplified** (D4) — Brief specifies ADD/UPDATE/SKIP with contradiction detection for write-time consolidation. Design implements ADD/SKIP only (0.92+ threshold). UPDATE and contradiction detection move to Backlog as part of LLM-based consolidation (post-MVP). Rationale: rule-based UPDATE requires merge logic that's error-prone without LLM judgment. Conservative SKIP-only dedup is safer for MVP.

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

**Search resolution:**

| Caller passes | Searches | Use case |
|---------------|----------|----------|
| `namespace="memory-layer"` | memory-layer + global | Project agent — sees own scope + global |
| `namespace="private"` | private only | Explicit private query |
| *namespace omitted* | All namespaces except private | Cross-scope consumer (e.g., Krypton) |

All searches exclude `status = "archived"`.

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

**Update flow (dual-store, Chroma-first ordering):**
1. Validate entry exists in SQLite (status = "committed")
2. If `content` changed: generate new embedding → `collection.upsert(ids=[id], embeddings=[emb], documents=[content], metadatas=[meta])` → update SQLite fields + `updated_at`
3. If only metadata changed: `collection.update(ids=[id], metadatas=[meta])` → update SQLite fields + `updated_at`
4. No staged status for updates — entry remains "committed" throughout
5. **Ordering rationale:** Chroma operation first. If Chroma fails, SQLite is unchanged (consistent). If SQLite fails after Chroma succeeds, next update corrects the drift.

### Read Tools

**`search_memories`** — Semantic search with namespace filtering.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| query | string | yes | | Search query |
| namespace | string | no | | If set, searches this namespace + global. If omitted, searches all except private (cross-scope). |
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

**Archive flow (Chroma-first ordering):** `collection.delete(ids=[id])` → update SQLite status = "archived". If Chroma delete fails, entry remains searchable (safe fallback). Returns: `{ id, archived: true }`

**`review_candidates`** — Surface memories needing human review.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| namespace | string | no | | Filter by namespace |
| limit | int | no | 20 | Max results |

Returns entries where confidence < 0.7 OR has high-similarity pair (>= 0.85 with another committed entry).

**Implementation:** On-demand computation at query time. Low-confidence entries: SQLite query (fast). High-similarity pairs: for each committed entry in scope, query Chroma for nearest neighbor — if similarity >= 0.85, include as candidate. O(n) Chroma queries; acceptable at MVP scale (hundreds of entries). No pre-computed similarity storage needed.

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

**Important:** Chroma returns cosine **distance** (lower = more similar), not similarity. Convert: `similarity = 1 - distance`. All thresholds below are expressed as similarity values.

```
1. Generate embedding for new content (sentence-transformers)
2. Search Chroma for top-5 similar entries in target namespace + global
   - Filter: status = 'committed', same namespace OR 'global'
   - Convert Chroma distances to similarities: similarity = 1 - distance
3. Check top result similarity:
   - >= 0.92 (distance <= 0.08): SKIP — return { action: "skipped", similar_id, similarity }
   - < 0.92 (distance > 0.08): ADD — proceed with staged commit
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
| 1 | Visibility dropped but Brief success criterion #2 and In Scope reference it — no acknowledgment | Ralph-Design | High | Resolved | Added Brief Deviations section explaining D3 simplification and how success criterion is still satisfied via namespace |
| 2 | Cross-scope search impossible — namespace omitted returns global only, Krypton can't search all namespaces | Ralph-Design | High | Resolved | Changed default: namespace omitted now searches all except private. Added search resolution table. |
| 3 | Consolidation simplified (ADD/SKIP only) vs Brief's ADD/UPDATE/SKIP + contradiction detection — no explanation | Ralph-Design | High | Resolved | Added to Brief Deviations section with rationale for D4 simplification |
| 4 | `update_memory` dual-store flow unspecified — developer wouldn't know how to handle SQLite+Chroma update | Ralph-Design | High | Resolved | Added update flow specification: content change triggers re-embed+upsert, metadata-only updates skip embedding |
| 5 | `review_candidates` similarity data not captured — consolidation doesn't persist 0.85-0.92 similarity info | Ralph-Design | High | Resolved | Specified on-demand computation at query time — O(n) Chroma queries, acceptable at MVP scale |
| 6 | Phase 1 internal review complete — 2 cycles, 0 Critical / 5 High / 0 Low found and resolved | Ralph-Design | — | Complete | All issues addressed. Ready for Phase 2. |
| 7 | Chroma returns cosine distance, not similarity — thresholds would be inverted causing incorrect dedup/review decisions | External-GPT | High | Resolved | Added distance↔similarity conversion note. Expressed thresholds in both forms. |
| 8 | Chroma metadata update operation unspecified — developer wouldn't know exact API call for metadata-only updates | External-Gemini | High | Resolved | Added explicit `collection.update(ids, metadatas)` and `collection.upsert()` calls to update flow |
| 9 | Update/archive dual-store ordering unspecified — Chroma failure after SQLite change creates divergence | External-GPT | High | Resolved | Specified Chroma-first ordering for both update and archive flows with failure rationale |
| 10 | Phase 2 external review complete — 3 High accepted, 4 rejected (namespace ambiguity, timestamps, upsert verification, race condition) | External | — | Complete | Design v0.3 ready for finalization |

## Develop Handoff

> Populated after review. Summarizes design decisions, capabilities, and implementation guidance for the Develop stage.

*Section will be completed during Finalization phase.*

## Review Log

### Phase 1: Internal Review

**Date:** 2026-02-10
**Mechanism:** Manual Ralph Loop (2 cycles)
**Cycle 1 Issues Found:** 0 Critical, 5 High, 0 Low
**Actions Taken:**
- Brief Deviations section added — documented D3 (visibility→namespace) and D4 (consolidation simplification) with rationale
- Cross-scope search fixed — namespace omitted now searches all except private, enabling Krypton access
- Update flow specified — dual-store update behavior for content vs metadata changes
- review_candidates implementation clarified — on-demand O(n) computation at query time

**Cycle 2 Issues Found:** 0 Critical, 0 High, 0 Low
**Actions Taken:** None required — all prior fixes verified, no new issues found.

**Outcome:** Internal review complete after 2 cycles. Design v0.2 ready for Phase 2 (external review).

### Phase 2: External Review

**Date:** 2026-02-10
**Mechanism:** External model review (Gemini 2.5 Flash Lite, GPT-5 Mini)
**Models Responding:** 2/3 (Kimi K2.5 timed out)
**Issues Raised:** 7 total (3 accepted, 4 rejected)
**Actions Taken:**
- **Accepted (3 issues):**
  - Chroma distance vs similarity semantics (High, GPT) — Added conversion note and dual-form thresholds
  - Chroma metadata update operation unspecified (High, Gemini) — Added explicit API calls to update flow
  - Update/archive dual-store ordering (High, GPT) — Specified Chroma-first ordering with failure rationale
- **Rejected (4 issues):**
  - Namespace omitted behavior ambiguous (Medium, Gemini) — By design; search resolution table is explicit
  - ISO 8601 timestamps vs native types (Medium, Gemini) — Standard SQLite approach, not a design gap
  - Chroma upsert/delete verification steps (High, GPT) — Over-engineering for MVP; KB uses same patterns
  - Concurrent write race condition (Medium, GPT) — Single-user MVP, stdio is sequential per connection

**Outcome:** External review complete. Design v0.3 ready for finalization.

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-10 | Initial draft from Intake & Clarification decisions. Full technical spec. |
| 0.2 | 2026-02-10 | Internal review cycle 1: 5 High issues found and resolved. Added Brief Deviations section, fixed cross-scope search, specified update flow, clarified review_candidates implementation. |
| 0.3 | 2026-02-10 | External review (Phase 2): 2/3 models responded. 3 High issues accepted (Chroma distance semantics, metadata update API, dual-store ordering). 4 rejected. Ready for finalization. |
