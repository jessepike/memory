# Memory Layer — Architecture Review

> Generated: 2026-02-19. Covers design quality, optimization opportunities, and alignment with agent memory systems (CLAUDE.md, AGENTS.md, auto-memory).

---

## What's Well-Designed

**The 3-layer separation is correct.** MCP as pure dispatch, MemoryStorage as the business logic home, storage adapters as replaceable internals. Adding a new interface (REST, CLI) later would be straightforward.

**Dual store for the right reasons.** SQLite holds lifecycle state (staged/committed/failed/archived), metadata, and is the source of truth. Chroma holds only what it's good at — vector search. The reconciliation tool exists to repair divergence. This is appropriate.

**Staged commit pattern is solid.** Write to SQLite first (status=staged), embed, dedup check, then commit both stores. Failures leave a recoverable `failed` row — meaningfully better than write-to-both patterns with no recovery path.

**Two-layer dedup is smart.** Deterministic (SHA-256) catches zero-cost exact duplicates before touching Chroma. Semantic (0.92 cosine) catches near-duplicates. Most writes short-circuit at the SHA-256 check — no embedding compute needed.

**Local-first embeddings is the right call.** `all-MiniLM-L6-v2` is fast, good enough for this use case, no cloud dependency, no API cost per write. For a high-write system this matters a lot.

---

## What's Architecturally Weak

**The scope system is inverted.** The write path has no authorization — any caller can write to any namespace. The read path enforces scope via `_resolve_scope`. This asymmetry is a design gap: the namespace taxonomy is only enforced on queries, not at ingestion. Garbage or mislabeled writes can pollute namespaces silently.

**Client profiles are load-bearing config with no validation at startup.** The server starts and runs fine with no profiles defined. The consequence (silent scope narrowing on every read) is only observable at query time, with no warning logged. A startup check — "no client_profiles configured, all callers will use fallback scope" — would surface this immediately.

**The fallback scope behavior is wrong for the common case.** The fallback (`allowed_namespaces = [caller_id, "global"]`) assumes `caller_id` is used as the namespace. But the routing guide says to default to `global`, and the global CLAUDE.md instructs `caller_id: "claude-code"`. A caller writing to `namespace="global"` with `caller_id="claude-code"` can read it back. But a caller writing to `namespace="memory-layer"` (reasonable for project-scoped memories) with `caller_id="claude-code"` cannot. The fallback design creates a non-obvious trap.

**`review_candidates` is O(n) Chroma queries.** For every committed entry, it queries Chroma for similar entries. At 500 memories this is slow. At 5,000 it's unusable. There's no pre-computation, no approximation, no index on similarity pairs. This needs rethinking before scale.

**`get_recent` over-fetches and time-filters in Python.** It fetches `limit * 3` rows from SQLite then applies the date cutoff in Python. The date cutoff should be pushed into the SQL query as a `WHERE created_at >= ?` clause.

**No embedding cache.** The same content embedded multiple times (e.g., repeated `get_session_context` calls with the same query) re-computes from scratch. A simple LRU cache keyed on content hash would eliminate most redundant compute.

**UPDATE path for consolidation was never implemented.** The brief specified ADD/UPDATE/SKIP. Design simplified to ADD/SKIP-only, reasoning that UPDATE without LLM judgment is error-prone. That's defensible, but it means the system accumulates stale memories with no way to evolve them except full archive + rewrite. As the memory store grows, this becomes a real problem.

---

## Optimization Opportunities

| Issue | Impact | Fix |
|-------|--------|-----|
| `get_recent` fetches 3x, filters in Python | Wasteful at scale | Push `WHERE created_at >= ?` into SQL |
| `review_candidates` O(n) Chroma queries | Unusable at scale | Pre-compute pair scores on write, or approximate with clustering |
| No embedding cache | Redundant compute on repeated queries | LRU cache keyed on SHA-256 of content |
| No startup validation of client_profiles | Silent misconfiguration | Warn on init if `client_profiles` is empty |
| No write-path namespace guard | Polluted namespaces | `_authorize_namespace_write()` mirroring read-path logic |
| SQLite ID pre-fetch before Chroma query | N+1 pattern at scale | Use Chroma native metadata filter on `namespace` directly |

The last one is subtle but meaningful: `search_memories` currently asks SQLite "give me all committed IDs in these namespaces" then passes that entire ID list to Chroma as an `allowed_ids` filter. At 10,000 memories, that's a large ID set being serialized across the Chroma API. Chroma supports metadata filtering natively — filtering by `namespace in [...]` in the Chroma `where` clause would be more efficient and wouldn't require the SQLite pre-fetch.

---

## Alignment with CLAUDE.md / AGENTS.md / Auto-Memory

### The four memory systems and what they're for

| System | What lives there | Auto-loaded? | Scope |
|--------|-----------------|--------------|-------|
| `CLAUDE.md` / `AGENTS.md` | Project conventions, commands, architecture rules, agent protocols | Yes — injected every session | Project (or global for `~/.claude/`) |
| Auto-memory (`MEMORY.md`) | Session-discovered patterns; Claude Code injects these | Yes — injected into system prompt | Project, Claude Code only |
| Memory Layer MCP | Cross-project learnings, reusable insights, ecosystem facts | No — must be queried explicitly | All agents, all projects |
| `status.md` / `backlog.md` | Operational state — what's done, what's next | Manual (read at session start per protocol) | Project |

### Where alignment works well

The conceptual layering is right. CLAUDE.md is *constitutional* — it defines how the agent behaves, not what it knows. Memory Layer is *experiential* — what was learned through doing. These are genuinely different things and shouldn't conflict if the routing rule is followed.

The `memory-routing.md` heuristic ("does it matter beyond this project and client?") is a good practical test. The comparison table against the Knowledge Base draws a real line between atomic facts (Memory) and structured knowledge (KB).

### Where alignment breaks down

**No technical enforcement of the routing rule.** An agent could write "always use pnpm in this project" to `namespace="global"` in the Memory Layer. It would sit there alongside cross-project learnings, polluting search results for all callers. Nothing stops this.

**Auto-memory and Memory Layer can duplicate each other.** Auto-memory (`MEMORY.md`) is populated passively by Claude Code from session observations. Memory Layer is populated explicitly by agent tool calls. The same fact can exist in both with no dedup mechanism between them. The routing guide says "don't duplicate into auto-memory what belongs in Memory MCP" — but there's no enforcement and no detection.

**Memory Layer content is invisible unless queried.** CLAUDE.md loads every session automatically. Memory Layer requires an explicit `get_session_context` call. If agents don't follow the session start protocol, the Memory Layer is effectively dead — the knowledge exists but never gets used. The system works only if agents are disciplined about the session protocol.

**No promotion path from Memory → CLAUDE.md.** When something in the Memory Layer becomes important enough to be always-loaded (i.e., it crosses the threshold from "useful context" to "always-applicable rule"), there's no workflow to promote it. The reverse (CLAUDE.md → Memory Layer migration) also has no tooling.

**Namespace and caller_id conventions aren't enforced anywhere.** The routing guide suggests `project-<name>` for project-scoped memories and `global` as default. But any agent can use any string for namespace. Without the client_profiles fix, the namespace taxonomy is nearly meaningless — the scope resolution fallback makes it irrelevant anyway.

### What would actually solve the alignment problem

1. **Fix client_profiles first** — the Memory Layer can't work correctly without it. Once scope is working, namespace discipline starts to matter.

2. **Session-start context injection** — agents need to call `get_session_context` as a hard habit, not a soft protocol. The ADF session protocol in CLAUDE.md says `MUST` — but there's no hook, no reminder, no enforcement. A session-start hook that automatically calls `get_session_context` and prepends results to context would close this gap without requiring discipline.

3. **Dedup across systems** — the fact that the same insight can live in auto-memory, Memory Layer MCP, and a CLAUDE.md comment simultaneously is a real problem at scale. At minimum, when writing to Memory Layer, check if content already exists in local CLAUDE.md or MEMORY.md first.

4. **Promotion workflow** — a `promote_to_claude_md(memory_id)` operation that takes a Memory Layer entry and appends it to the appropriate project/global CLAUDE.md with proper formatting. Makes the "graduate a memory to a rule" pattern explicit.

5. **Staleness detection** — memories have no expiry or freshness signal. A preference written 6 months ago may be stale. The `review_candidates` tool surfaces low-confidence and high-similarity entries, but not old ones. Age + lack of access should factor into review signal.

---

## Improvements Worth Considering

### Near-term — closes known gaps

- Fix client_profiles + stdio test (backlog FIX-01, FIX-02)
- Add startup warning when client_profiles is empty
- Push `get_recent` date filter into SQL
- Add namespace authorization to write path

### Medium-term — improves utility

- Session-start hook that auto-calls `get_session_context`
- LRU embedding cache
- Chroma metadata filter on namespace (skip SQLite ID pre-fetch)
- Age-based signal in `review_candidates` (not just confidence + similarity)

### Longer-term — addresses architecture gaps

- **LLM-based UPDATE consolidation** (the Mem0 pattern) — biggest functional gap; SKIP-only means stale memories accumulate with no evolution path
- **`review_candidates` pre-computation** — can't stay O(n) Chroma queries as the store grows; pre-compute pair scores at write time or use approximate clustering
- **Memory → CLAUDE.md promotion workflow** — explicit path to graduate a memory to an always-loaded rule
- **Staleness/decay mechanism** — when volume demands it, surface and prune memories that haven't been accessed and haven't been validated recently
