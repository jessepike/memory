# Memory Layer — Research Synthesis

> Generated: 2026-02-19. Based on 6 inbox research documents covering production agentic memory architectures (2026).
> Source docs: docs/inbox/ — NotebookLM-generated research set covering JIT verification, hybrid search, 4-tier memory models, OpenClaw/file-first architectures.

---

## Where We're Well-Aligned

**Local-first philosophy** — Multiple docs validate our choice. SQLite + local embeddings + no cloud dependency is called "surprising elegance" and the preferred pattern for single-user systems.

**SQLite + vector dual store** — The research endorses this exact pattern. We're ahead of the "sqlite-vec" approach mentioned in the docs (we use a separate Chroma process, which is more capable for similarity search).

**Atomic facts as the memory unit** — Consistent with what the docs call "semantic memory." One atomic fact per entry, independently searchable. We got this right.

**Staged commit + idempotency** — The research recommends "idempotent tool calls" as a production best practice. We implemented deterministic SHA-256 dedup + staged commit.

**Procedural memory exists in the ecosystem** — CLAUDE.md, AGENTS.md, memory-routing.md are our procedural memory. OpenClaw calls it SOUL.md. Same concept, different filename.

---

## The 4-Tier Model — We Only Built One Tier

The consistent framework across all documents is a 4-tier cognitive hierarchy. We only explicitly built one of these tiers.

| Tier | What it is | Implementation approach | Our status |
|------|-----------|------------------------|------------|
| **Short-term / Working** | In-session context, partial plans, intermediate tool results | Redis checkpointers / in-memory K-V | context window + status.md — not Memory Layer |
| **Episodic** | Chronological record of "what happened and when" — narrative, temporal | Timestamped logs: `YYYY-MM-DD.md` or JSONL | **Not implemented** |
| **Semantic** | Persistent atomic facts, preferences, learnings, entity state | Vector search + SQLite | ✅ Our Memory Layer |
| **Procedural** | Behavioral rules, skills, operational protocols — the agent's "soul" | SOUL.md / AGENTS.md / CLAUDE.md | exists in ecosystem, outside Memory Layer |

The semantic tier is what we built — and built well. The episodic tier is entirely absent.

---

## Key Gaps Identified

### Gap 1: Semantic-Only Search (Missing BM25 / Keyword Layer)

Every document recommends **hybrid search: 70% vector + 30% BM25 keyword**, not semantic-only.

The reason matters: pure vector search fails on exact technical identifiers — function names, error codes, version strings, UUIDs. An agent writing "the `_resolve_scope` function has a bug" to memory, then searching for "resolve_scope" — vector search may or may not surface it. BM25 will find it instantly.

SQLite already has FTS5 built in. Adding BM25 to `search_memories` is low-cost, high-value.

Two fusion approaches used in production:
- **Weighted Score Fusion** — 70% vector score + 30% BM25 score (OpenClaw pattern)
- **Reciprocal Rank Fusion (RRF)** — score-agnostic, rank-based; better when the two search engines use incompatible score scales

### Gap 2: No Citation / Source Provenance on Write

GitHub Copilot's **Just-in-Time (JIT) Verification** model:
1. When a memory is written, store a **citation** — pointer to the source (file path, session date, line number, URL)
2. At retrieval time, check whether the citation source still matches
3. If the source changed and contradicts the memory → discard or regenerate it
4. Result: "self-healing" memory that stays synchronized with reality

Our memories float free of any source reference. This matters because:
- A memory "API uses v2 format" written in February may be factually wrong by June
- We have no mechanism to detect staleness without active human curation
- JIT verification is cheaper than curation — verify at read time, not write time

Implementation path: add optional `source_ref` field to `write_memory` (file path, session date, URL). Store in SQLite. No behavior change at write time, but enables JIT validation at retrieval and gives `review_candidates` a useful signal.

### Gap 3: The UPDATE Problem — ADD/SKIP Accumulates Contradictions

Multiple docs use a concrete example:
- "User prefers business class" (Monday)
- "User needs economy class, budget cut" (Tuesday)

A naive vector store keeps both. `search_memories("flight preferences")` returns conflicting results. The agent is confused.

Our ADD/SKIP-only approach means these two memories coexist. `review_candidates` flags them as `high_similarity` pairs but doesn't resolve them. This is documented as "deferred to LLM-based consolidation (post-MVP)" — but the research is clear this is a critical correctness problem, not a nice-to-have.

The **Mem0 pattern** solves it:
- At write time, an LLM evaluates the incoming memory against similar existing entries
- Decision: ADD (genuinely new) / UPDATE (supersedes existing) / DELETE (old is now false) / NOOP (exact duplicate)
- Updates preserve **changelog/version history** — not just overwriting, but capturing "previously X, now Y because of Z"
- This preserves the *why* of the change, not just the current state

Without this, the semantic store degrades in quality as contradictions accumulate over time.

### Gap 4: No Episodic Layer

The `memory/YYYY-MM-DD.md` pattern described across all docs is **episodic memory** — chronological append-only log of what happened in sessions. Not facts. Events.

OpenClaw's file hierarchy:
```
memory/2026-02-10.md   ← session events, raw narrative (episodic)
memory/2026-02-11.md
MEMORY.md              ← curated semantic facts extracted from episodes
SOUL.md                ← procedural rules (behavioral)
```

The "Search then Get" pattern leverages episodic files with citations:
1. Search returns a 700-char snippet + citation (`path: memory/2026-02-10.md, startLine: 142`)
2. Get fetches only the relevant lines — keeps context lean

**Episodic vs semantic — different purposes:**

| Episodic (daily files) | Semantic (our Memory Layer) |
|------------------------|----------------------------|
| "On Feb 10, built SQLite schema, hit idempotency bug, fixed via partial unique index" | "SQLite idempotency: use partial unique index on status IN (staged, committed)" |
| Narrative, contextual, temporal | Atomic, deduped, searchable |
| Append-only, never curated | Curated on write via dedup |
| Good source for JIT citations | Good for semantic retrieval |
| Human-readable audit trail | Structured queryable data |

The episodic layer is the **raw input** that feeds semantic memory — session narrative gets distilled into atomic facts. This is what the docs call "fact extraction from the episodic stream."

---

## Improvement Priorities

### Near-term: High value, feasible

**1. Hybrid search — add FTS5 / BM25 to `search_memories`**
- SQLite FTS5 is already available (no new dependencies)
- Add FTS5 virtual table on `content` column to schema
- `search_memories` runs both vector and keyword in parallel, merges with 70/30 weighting
- Retrieval significantly more accurate for technical content

**2. Citation tracking on write — add `source_ref` to `write_memory`**
- Optional field: file path, session date, URL, or any source identifier
- Stored in SQLite alongside existing metadata
- No behavior change at write time
- Unlocks JIT verification later; improves `review_candidates` signal
- Enables "this memory came from session X, which is now stale"

### Medium-term: High value, more complex

**3. LLM-based UPDATE consolidation (Mem0 pattern)**
- Replace ADD/SKIP with ADD/UPDATE/SKIP/DELETE
- At write time: LLM evaluates incoming memory against top-k similar existing entries
- On UPDATE: write v2 entry with `previous_value` and `reason` fields — don't just overwrite
- This is the single biggest functional gap; the store degrades without it

**4. Episodic tier**
- `data/episodes/YYYY-MM-DD.jsonl` — append-only session event log
- Lightweight: session ID, timestamp, event type, content, source_project
- Benefits: narrative record of what happened, citation sources for JIT verification, raw material for fact extraction, human-readable audit trail
- Does not replace semantic tier — complements it

### Later: For scale and accuracy

**5. JIT verification at retrieval time**
- At `search_memories`: check `source_ref` if present against current state of source
- Flag memories whose source has changed as `needs_verification`
- Graceful degradation: still return the memory but with a staleness signal

**6. Re-ranking**
- After hybrid search returns top-k, second pass using LLM to evaluate relevance against the specific query
- Adds latency; worth it when accuracy matters more than speed
- Relevant once the store is large enough that top-k quality matters

---

## What's Not Relevant to Our Use Case

**Redis / hot-path in-memory store** — Relevant for enterprise multi-tenant. Single-user, local-first. SQLite WAL is fast enough.

**Context compaction / Head-Tail preservation** — The agent framework's problem (LangGraph, etc.), not our memory layer's problem. Out of scope.

**Docker sandboxing / Sovereignty Trap security** — We're local-first by design; security is at the OS level. Single-user trusted model.

**Cloud embedding providers** (Voyage4.large, OpenAI TextEmbedding-3-small) — We intentionally chose local. `all-MiniLM-L6-v2` is sufficient for personal scale. Cloud embeddings are for production enterprise multi-tenant.

**Heartbeat / proactive agents** — The "always-on agent checking every 30 minutes" pattern is interesting but out of scope for our MCP-based architecture.

---

## On the Flat Markdown Daily File

The daily `YYYY-MM-DD.md` file is episodic memory. It has a clear role — but as a **separate tier**, not a replacement for what we built.

Our semantic Memory Layer (atomic facts, deduped, vector-indexed) is the right architecture for "what we know." The daily file is the right architecture for "what happened." Trying to make one system do both would compromise both.

The practical path: if we add an episodic tier, implement it as `data/episodes/YYYY-MM-DD.jsonl` (machine-readable for indexing, but trivially convertible to markdown for human review). Session-end writes go here first as raw events; significant learnings get promoted to the semantic Memory Layer via `write_memory`.
