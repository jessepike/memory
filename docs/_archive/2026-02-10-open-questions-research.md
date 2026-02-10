# Open Questions — Research Synthesis

**Date:** 2026-02-10
**Purpose:** Resolve or narrow the 8 open questions from discover-brief v0.2
**Sources:** ACK prior art, KB (16 entries), landscape research, web research (Mem0, Letta, LangMem, ChatGPT, AWS AgentCore)

---

## 1. Curation Workflow

> How should memories be reviewed, promoted, rejected?

### What We Found

**ACK experience (the blocker):**
- Phase 2 was never implemented. 72 memories captured, zero curated.
- Designed: interactive TUI (`claude-mem review`), staging state, bulk ops, audit trail
- Root cause: built capture without curation path — memories went straight to "approved"
- Key lesson: **staging state is required from day one**

**Industry patterns:**

| System | Pattern | Human-in-loop? |
|--------|---------|----------------|
| Mem0 | LLM-as-judge at write-time (ADD/UPDATE/DELETE/NOOP) | No |
| Letta | Agent self-curates via memory tools during conversation | No |
| LangMem | Dual-path: hot (agent writes) + background ReflectionExecutor | Optional |
| ChatGPT | Opaque background classifiers; user can view/edit/delete | Post-hoc only |
| AWS AgentCore | Separate extraction + consolidation async stages | No |

**KB signal:**
- KB's own `curate` command (identify low-quality, duplicates, stale) is the closest existing analogy
- KB synthesis workflow (`9125b9a3`) uses layered promotion: individual → cluster → cross-topic

### Proposed Resolution

**Two-phase curation, automated-first:**

1. **Write-time consolidation** (Mem0 pattern): When a new memory arrives, compare against top-k similar existing entries. LLM decides: ADD new, UPDATE existing, DELETE contradicted, or NOOP (already exists). This prevents duplication and staleness at the source.

2. **Periodic review** (human-optional): MCP tool to surface candidates for review — low-confidence entries, high-similarity pairs, entries older than threshold with no access. Can be triggered manually or by a curation agent.

**Why not ACK's approach:**
- ACK designed curation as a separate phase (Phase 2) with full TUI — too much infrastructure for MVP
- Write-time consolidation handles 80% of the problem with zero human effort
- Human review becomes optional quality-checking, not a blocking gate

**MVP scope:** Write-time consolidation only. Surface review candidates via MCP tool. No TUI, no CLI — MCP tools are sufficient for agent-driven or human-triggered review.

**Status: Resolved for MVP**

---

## 2. Single Store vs Partitioned

> One memory store with scoping metadata, or separate stores per scope/domain?

### What We Found

**ACK:** Single store (`~/.claude-mem/`). Multi-scope designed but never implemented. All 72 memories mixed together — scoping was metadata-only (project column).

**Industry:**
- Mem0: Multi-store (vector + graph + KV + history) — but that's for SaaS scale
- LangGraph: Single store with namespace scoping (PostgreSQL + pgvector)
- ChatGPT: No vector DB at all — pre-computed layers injected directly

**KB signal (`5f24eeb7`):** At personal scale (sub-100M vectors), single-store with namespace metadata is sufficient. Multi-store only justified at SaaS scale.

**KB project reference:** Single SQLite + single Chroma instance. Works well with ~200+ entries.

### Proposed Resolution

**Single store with namespace metadata.**

- SQLite: one `memories` table with scope/visibility/writer columns
- Chroma: one collection with metadata filters for scoped queries
- Scoping enforced at query time via metadata filtering, not physical separation

**Rationale:**
- KB proves the pattern at our scale
- Physical partitioning adds operational complexity (multiple DBs, migration overhead) for zero benefit at personal scale
- Namespace metadata gives equivalent query isolation
- If scale ever demands it, partitioning can be added later without schema changes

**Status: Resolved**

---

## 3. MCP Tool Surface

> How many tools, what granularity?

### What We Found

**ACK:** Only generic `chroma-mcp` (2 tools: query, get). Designed but never built: 5 custom tools (query_memories, get_memory, list_scopes, get_context, suggest_promotion_candidates).

**KB project:** 16 tools across 4 categories:
- Query: search, get_item, get_items, get_learnings, get_ideas, get_to_read, get_recent, get_backlog
- Write: send_to_kb
- Manage: update_item, archive_item, mark_complete, set_focus_topics
- Stats: get_stats, get_focus_topics, get_unprocessed

**KB signal (`f5bb8402`):** MCP server design reference — separate read/write/manage/stats tools.

### Proposed Resolution

**Start with ~8-10 tools in 4 categories, modeled on KB but adapted for memory semantics:**

| Category | Tool | Purpose |
|----------|------|---------|
| Write | `write_memory` | Add a memory entry (with write-time consolidation) |
| Write | `update_memory` | Edit an existing memory |
| Read | `search_memories` | Semantic search with scope/type/visibility filters |
| Read | `get_memory` | Get a single memory by ID |
| Read | `get_recent` | Recent memories (optionally scoped) |
| Read | `get_session_context` | Memories relevant to current project/session |
| Manage | `archive_memory` | Soft-delete / archive |
| Manage | `review_candidates` | Surface entries needing review |
| Stats | `get_stats` | Counts, scope breakdown, health metrics |

**Design principles:**
- `write_memory` does consolidation internally — callers don't manage ADD/UPDATE/DELETE
- `search_memories` is the primary read path — semantic search with metadata filters
- `get_session_context` is the "context loading" tool — what ADF agents call on session start
- No bulk operations for MVP — add when needed

**Status: Resolved**

---

## 4. Memory Entry Format

> Short facts vs longer summaries vs both?

### What We Found

**ACK's 4-layer format:**
1. Title (3-8 words)
2. Subtitle (max 24 words)
3. Facts (3-7 atomic statements, 50-150 chars each)
4. Narrative (512-1024 tokens)

**Industry:**
- Mem0: Atomic facts only — short, self-contained, composable
- ChatGPT: Short timestamped single-sentence entries
- Letta: Structured blocks (persona/human sections) for core; free-text for archival
- LangMem: Two formats — **profiles** (JSON state docs) and **collections** (individual narrow docs)

**KB signal (`f5969951`):** LangMem's profile/collection distinction maps to state-vs-retrieval. Atomic facts dominate for retrieval quality and composability.

### Proposed Resolution

**Atomic facts as primary format, with structured metadata:**

```
Memory Entry:
  id: uuid
  content: string          # The memory itself — one fact, one observation, one preference
  memory_type: enum        # observation | preference | decision | progress | relationship
  scope: string            # project:{id} | global | private
  writer_type: enum        # agent | human | system
  writer_id: string        # who wrote it
  visibility: enum         # public | restricted | private
  confidence: float        # 0-1, set by writer or consolidation
  source_session: string   # session that produced this memory (nullable)
  tags: string[]           # free-form tags for filtering
  created_at: timestamp
  updated_at: timestamp
  accessed_at: timestamp   # for decay/relevance tracking
```

**Why atomic facts over ACK's 4-layer:**
- ACK's format is rich but coupled — title/subtitle/facts/narrative creates redundancy
- Atomic facts are independently searchable, composable, and easier to consolidate
- Session summaries are a separate write-back path (see Q6), not embedded in every entry

**Session summaries as a separate type:**
- `memory_type: progress` with longer content for session-end write-back
- These serve a different purpose (continuity) than atomic facts (retrieval)

**Status: Resolved**

---

## 5. Capture Mechanism

> Hooks-based (ACK pattern) vs agent-initiated vs hybrid?

### What We Found

**ACK:** Three hooks (PostToolUse, UserPromptSubmit, Stop) using streaming SDK sessions. Captured 72 memories across 10 sessions. Async, non-blocking. Used spawned subprocesses for writes.

**Industry patterns:**
- Agent-initiated (Letta): Agent explicitly calls memory tools. Best context, but consumes reasoning bandwidth.
- Event-driven (Mem0, ChatGPT): External process extracts automatically. Consistent but may capture noise.
- Hybrid (LangMem, most production): Combine explicit writes + background extraction.

**KB signal:**
- `7f4b8e28`: Claude Code has 9 hook events available (PreToolUse, PostToolUse, Stop, etc.)
- `fbaaa6f9`: Claude Code auto-memory already exists as basic capture mechanism
- `1b556a4e`: Auto-memory is raw experience layer; Memory Layer would be structured persistence

**Key insight from ACK:** The hooks worked technically but produced unreviewed memories. The capture mechanism isn't the problem — curation is. With write-time consolidation (Q1), hooks become safe to use.

### Proposed Resolution

**Hybrid: MCP tools (primary) + session-end hook (secondary)**

1. **MCP tools** (agent-initiated): Any agent can call `write_memory` during conversation. This is the primary path for high-confidence, structured writes. ADF agents write progress/decisions. Manual "save to memory" goes here.

2. **Session-end hook** (event-driven): A Stop hook extracts key memories from the session. Runs write-time consolidation. Lower confidence than explicit writes.

**Why not PostToolUse hooks (ACK pattern):**
- Captures too much noise (every tool use → potential memory)
- Requires SDK session overhead (separate LLM call per tool use)
- Write-time consolidation handles dedup, but volume still creates unnecessary processing
- Session-end extraction with full context produces better quality memories

**MVP scope:** MCP tools only. Session-end hook added once the core system is stable.

**Status: Resolved for MVP**

---

## 6. Write-Back Paths

> Which paths for MVP? Hot, warm, cold?

### What We Found

**ACK:** All three paths designed (hot/warm/cold). Hot (PostToolUse) and warm (Stop) implemented. Cold (manual) designed but not built.

**Industry:**
- Real-time synchronous (Letta, Mem0): Memory written during conversation
- Session-end batch (LangMem, AWS): Process entire conversation after close
- Periodic (AWS, Letta sleep-time): For long conversations
- Async background (AWS, Mem0 async): Queued, non-blocking

**KB signal (`62ab1a1f`):** Three-tier pattern is standard. Hot = mid-conversation tool calls. Warm = session-end extraction. Cold = background consolidation.

### Proposed Resolution

**Two paths for MVP:**

1. **Hot path** — Explicit `write_memory` MCP tool call during conversation. Agent or human decides something is worth remembering, calls the tool. Immediate persistence. Highest confidence.

2. **Warm path** — Session-end summary extraction. A hook or agent call at session end processes the conversation for key memories. Batch write with consolidation. Medium confidence.

**Deferred:**
- Cold path (background consolidation, decay, re-ranking) — add when volume demands
- Periodic extraction — not needed for session-bounded conversations

**Status: Resolved**

---

## 7. Cross-Channel Access Architecture

> How does a non-MCP consumer access memories?

### What We Found

**Current ecosystem:** MCP is the universal API for agent tooling. KB uses MCP exclusively. All Claude Code integrations use MCP.

**Future consumers identified in intent:**
- Personal assistant (non-dev)
- Dashboards
- Non-dev workflows

**Industry:** Mem0 exposes REST + Python SDK. LangGraph uses Python SDK. Most systems have a programmatic API alongside any agent-specific interface.

### Proposed Resolution

**MCP-only for MVP. REST adapter as future extension point.**

- The MCP server already speaks a protocol that any MCP client can consume
- For non-MCP consumers (dashboards, scripts), a thin REST wrapper over the same core library
- Architecture: `core library` → `MCP server` (MVP) and `core library` → `REST server` (future)

**Design principle:** Build the core as a Python library with clean API. MCP server is one interface. REST is another. Neither contains business logic.

**Status: Resolved (architectural principle established, implementation deferred)**

---

## 8. State-Based vs Retrieval-Based

> Pure vector retrieval, or hybrid with entity/belief state tracking?

### What We Found

**Industry — every mature system is hybrid:**
- Letta: core memory (state, always in context) + archival (retrieval, searchable)
- ChatGPT: flat belief state (explicit facts, injected every prompt) — no retrieval step
- Mem0: Retrieval-first but converges toward state via consolidation (UPDATE/DELETE)
- LangMem: profiles (state docs, regenerated on update) + collections (retrieval)

**KB signal (`f5969951`):**
- Retrieval-based: Vector search, fast, accumulates stale data
- State-based: Entity-level belief docs with revision history, robust but requires explicit entity extraction
- Hybrid is the emerging consensus

**Key insight:** The distinction maps to two use cases:
- "What do we know about X right now?" → State (current beliefs)
- "What happened related to Y?" → Retrieval (semantic search)

### Proposed Resolution

**Retrieval-first for MVP. Add state profiles when entity coherence is needed.**

- All memories are stored as atomic facts with vector embeddings → searchable
- `search_memories` is the primary read path
- `get_session_context` composes relevant memories for a given scope

**State profiles (future):**
- Entity-level summary docs (e.g., "current understanding of project X")
- Regenerated periodically from underlying atomic facts
- Injected into agent context on session start
- This is essentially what `get_session_context` produces dynamically

**Why not state-first:**
- State requires entity extraction infrastructure (which entities? what schema?)
- Retrieval with good metadata filtering covers 90% of use cases
- State profiles can be built on top of retrieval without schema changes

**Status: Resolved for MVP**

---

## Summary: Resolution Status

| # | Question | Status | MVP Direction |
|---|----------|--------|---------------|
| 1 | Curation workflow | **Resolved** | Write-time consolidation (ADD/UPDATE/DELETE/NOOP). Review candidates via MCP tool. |
| 2 | Single vs partitioned | **Resolved** | Single store, namespace metadata, query-time filtering. |
| 3 | MCP tool surface | **Resolved** | ~8-10 tools in 4 categories (write/read/manage/stats). |
| 4 | Memory entry format | **Resolved** | Atomic facts primary. Session summaries as separate type. |
| 5 | Capture mechanism | **Resolved** | MCP tools (primary) + session-end hook (secondary, post-MVP). |
| 6 | Write-back paths | **Resolved** | Hot (explicit tool call) + warm (session-end extraction). |
| 7 | Cross-channel access | **Resolved** | MCP-only MVP. Core library pattern enables future REST. |
| 8 | State vs retrieval | **Resolved** | Retrieval-first. State profiles as future layer on top. |

---

## Sources

### Prior Art
- ACK project (`~/code/sandbox/ai-dev/ack/`) — 72 captured memories, hooks-based capture, Phase 2 curation blocker

### KB Entries (by ID)
- `3cef36c4` — Four-Layer Cognitive Model
- `f5969951` — State-Based vs Retrieval-Based Memory
- `62ab1a1f` — Write-Back Patterns: Hot/Warm/Cold
- `4fc0887d` — KB vs Memory vs Intelligence Boundary
- `5f24eeb7` — Mem0 vs Zep vs Letta Comparison
- `0128a728` — Context Graphs / Decision Traces
- `f5bb8402` — MCP Server Design KB
- `9125b9a3` — KB Synthesis Workflow (curation analogy)
- `7f4b8e28` — Claude Code Hooks Reference
- `fbaaa6f9` — Claude Code Auto-Memory Reference
- `1b556a4e` — ADF + Auto-Memory Integration

### Landscape Research
- `docs/adf/memory-layer-research.md` — Mem0, Letta, LangGraph, ChatGPT architectures
- `docs/adf/memory-systems-deep-dive.md` — Deep-dive on curation, capture, format, write-back patterns

### External
- Mem0 docs and architecture (2025-2026)
- Letta/MemGPT documentation (2025-2026)
- LangMem/LangGraph memory docs (2026)
- AWS AgentCore memory documentation (2026)
- SIGARCH multi-agent memory paper (Jan 2026)
