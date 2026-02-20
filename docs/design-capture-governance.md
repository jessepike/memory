# Memory Capture & Governance Design

> **Project:** Memory Layer v1.1
> **Stage:** Design (pending review)
> **Created:** 2026-02-19
> **Status:** Draft — awaiting internal + external review

---

## 1. Problem Statement

The Memory Layer storage works. The capture layer doesn't exist. Agents don't write to memory reliably because it requires active intent — 5 routing decisions under time pressure at session end. The result: the system is built but underused.

Secondary problem: no audit trail. When agents make decisions based on memories, there's no record of what happened, when, or why. This blocks the path from personal tooling to enterprise-grade governance.

### What This Document Covers

1. **Cross-client memory capture** — how to get memories written reliably from Claude Code, Codex CLI, and Gemini CLI without adding noise
2. **Episodic event log** — append-only record of agent sessions as a governance foundation
3. **Governance trajectory** — what we build now to avoid closing off the enterprise path

### What This Document Does NOT Cover

- Changes to semantic memory (write_memory, search_memories) — those work
- Hybrid search (FTS5/BM25) — separate backlog item
- LLM-based memory consolidation (ADD/UPDATE/DELETE/NOOP) — future work

---

## 2. Research Summary

### 2.1 Hook Capabilities by Client

| Capability | Claude Code | Codex CLI | Gemini CLI |
|-----------|------------|-----------|------------|
| Lifecycle hooks | 8 events (Stop, SessionEnd, PreCompact, PostToolUse, etc.) | **None** (requested, not implemented) | 11 events (AfterModel, SessionEnd, BeforeTool, etc.) |
| MCP support | Yes (stdio, well-tested) | Yes (stdio + HTTP) | Yes (stdio, SSE, HTTP) |
| System prompt injection | CLAUDE.md | AGENTS.md | GEMINI.md |
| Hook → MCP tools | Yes (agent-type hooks only) | N/A | Yes (via shell/script) |
| Async hooks | Yes (command hooks only) | N/A | Yes |
| Built-in memory | Auto-memory (MEMORY.md) | None | save_memory (GEMINI.md) |
| Extensions/plugins | Plugins | None | Extensions (bundles hooks+MCP+instructions) |

**Key finding:** Hooks are per-client and non-portable. MCP is the only universal channel.

### 2.2 Community Approaches

| Pattern | Noise Level | Cross-Client | Latency Impact | Signal Quality |
|---------|------------|--------------|----------------|----------------|
| Inline hook capture (every tool use) | High | No | Moderate | Low (captures everything) |
| Stop hook with "block" (force continuation) | High | No | High (blocks response) | Moderate |
| Background worker (fire-and-forget) | Low | No | None | Moderate |
| Isolated agent (separate context window) | None | No | None on main session | Good |
| Post-session transcript extraction | None | Partial | None | Good |
| Instruction-driven (system prompt) | None | **Yes** | None | Variable (unreliable) |
| Git-commit-triggered | None | No | None | High (commits = milestones) |

**Key finding:** The lowest-noise, highest-signal approaches are post-session extraction and instruction-driven capture. The noisiest are inline hooks that interrupt the conversation.

### 2.3 Enterprise Governance Patterns

| Pattern | Complexity | What It Enables | Must Design In Now? |
|---------|-----------|-----------------|---------------------|
| Append-only event log | Low | Basic audit trail | **Yes** — mutations break auditability permanently |
| Hash chaining (event_hash + previous_hash) | Low (~15 lines SQL) | Tamper detection | **Yes** — unchained prefix can't be retrofitted |
| Agent identity (agent_id on every record) | Low | Multi-agent attribution | **Yes** — can't determine authorship retroactively |
| Schema versioning | Low | Forward compatibility | **Yes** — unversioned records can't be migrated reliably |
| Source references / provenance | Low | Traceability | **Yes** — link between memory and evidence |
| Cryptographic signing | Medium | Non-repudiation | No — can layer on hash chains later |
| Formal attestation | High | Compliance certification | No — requires hash chains first |
| Trust scoring | Medium | Multi-agent governance | No — needs usage data first |

**Key finding:** Four things must be designed in from event #1: append-only discipline, hash chaining, agent identity, and schema versioning. Everything else can be added incrementally.

Reference implementations: Langfuse (trace/observation/session model), PROV-AGENT/Flowcept (W3C PROV for MCP agents), SQLite hash chain pattern (15 lines of SQL for tamper-evident chaining).

Regulatory relevance: EU AI Act Article 12 (automatic recording of events for traceability), NIST AI RMF (governance functions require audit trails). Both mandate that high-risk AI systems maintain traceable decision records. Agentic coding assistants making architectural decisions are approaching this threshold.

---

## 3. Architecture

### 3.1 Design Principles

1. **Capture broadly, route later** — don't force routing decisions at capture time
2. **MCP-first** — every capability must work through MCP (the universal channel)
3. **No inline noise** — capture must not interrupt or slow down the conversation
4. **Append-only by default** — episodic events are immutable once written
5. **Schema from day one** — hash chains, agent_id, schema_version from the first event
6. **Separated concerns** — episodic log (what happened) is distinct from semantic memory (what we know)

### 3.2 System Layers

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Clients                         │
│  Claude Code  │  Codex CLI  │  Gemini CLI  │  Krypton   │
└──────┬────────┴──────┬──────┴──────┬───────┴─────┬──────┘
       │               │             │              │
       │  (hooks)      │ (instruct)  │  (hooks)     │
       │               │             │              │
┌──────▼───────────────▼─────────────▼──────────────▼─────┐
│                   MCP Server (memory-layer)              │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │  Semantic     │  │  Episodic     │  │  Usage         │ │
│  │  Memory       │  │  Event Log    │  │  Telemetry     │ │
│  │              │  │              │  │                │ │
│  │ write_memory │  │ write_episode│  │  (auto-logged  │ │
│  │ search       │  │ get_episodes │  │   per tool     │ │
│  │ get/update   │  │ get_session  │  │   call)        │ │
│  │ archive      │  │ end_session  │  │                │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────────┘ │
│         │                 │                              │
│  ┌──────▼───────┐  ┌──────▼───────┐                     │
│  │ SQLite + Chroma│  │  SQLite      │                     │
│  │ (existing)    │  │  (episodes   │                     │
│  │              │  │   table)     │                     │
│  └──────────────┘  └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

### 3.3 Capture Strategy by Client

#### Universal: Instruction-Driven Capture (All Clients)

System prompt instructions (CLAUDE.md / AGENTS.md / GEMINI.md) tell agents:

```
At session end, if you learned something that matters beyond this project:
- Call write_memory with one sentence. Namespace "global", type "observation".
- Don't announce it to the user. Just do it.
```

This is imperfect (agents forget under pressure) but it's zero-infrastructure, works everywhere, and produces zero noise when it fires.

**Reliability estimate:** 40-60% of sessions. Sufficient as a baseline, not as sole mechanism.

#### Claude Code: SessionEnd Transcript Post-Processing

```
Hook: SessionEnd (shell command)
Trigger: Every session end
Action: Python script reads transcript_path, extracts learnings
Output: Calls write_episode via MCP (or direct SQLite append)
Visibility: None — runs after session ends
```

Why SessionEnd over Stop:
- **Stop** fires at end of each turn, can block response, triggers loop-guard complexity
- **SessionEnd** fires once at session close, non-blocking, guaranteed cleanup phase
- SessionEnd can only run shell commands (no agent hooks), but a shell script can invoke a Python extractor that writes directly to SQLite — no MCP needed

Why not PreCompact:
- PreCompact **cannot call MCP tools** (shell only)
- PreCompact **cannot inject into the compaction prompt**
- It was the most promising hook on paper but research showed it's too limited

#### Gemini CLI: Extension with SessionEnd Hook

Same pattern — a Gemini extension that bundles:
- MCP memory server configuration
- SessionEnd hook → Python transcript extractor
- GEMINI.md instructions as belt-and-suspenders

#### Codex CLI: Instruction-Driven Only (For Now)

No hooks available. Rely on:
- AGENTS.md instructions to call `write_memory` before ending
- MCP server configured in `.codex/config.toml`
- `notify` config to trigger external post-processing on `agent-turn-complete` (limited — can't inject context back)

Watch for hooks support (GitHub issue #2109, 411+ thumbs-up).

---

## 4. Episodic Event Log

### 4.1 Why SQLite, Not JSONL

The original proposal in `capture-problem.md` suggested `data/episodes/YYYY-MM-DD.jsonl`. After research, SQLite is the better choice:

| Factor | JSONL Files | SQLite Table |
|--------|------------|--------------|
| Already in stack | — | Yes (WAL mode, used for semantic memory) |
| ACID guarantees | No | Yes |
| Indexing | External sidecar needed | Built-in B-tree indexes |
| Query capability | grep/jq only | Full SQL |
| Hash chaining | Application-level | Trigger-based (15 lines SQL) |
| Scale ceiling | ~50K entries (single file) | 1M+ entries |
| Concurrent reads during writes | No | Yes (WAL mode) |
| Human-readable | Yes (plain text) | No |

Trade-off: we lose human-readability of JSONL. Mitigated by providing a `get_episodes` MCP tool and optional JSONL export.

### 4.2 Schema

```sql
CREATE TABLE episodes (
    -- Identity
    id TEXT PRIMARY KEY,                -- UUID4
    session_id TEXT NOT NULL,           -- Groups events into sessions
    sequence INTEGER NOT NULL,          -- Monotonic within session

    -- Temporal
    timestamp TEXT NOT NULL,            -- ISO 8601 with timezone

    -- Classification
    event_type TEXT NOT NULL,           -- See event type taxonomy
    severity TEXT DEFAULT 'info',       -- info | warning | error | critical

    -- Attribution (governance-critical)
    agent_id TEXT NOT NULL,             -- Which agent/caller wrote this
    client TEXT,                        -- claude-code | codex | gemini | krypton
    project TEXT,                       -- Project context
    namespace TEXT NOT NULL,            -- Scope for access control

    -- Content
    content TEXT NOT NULL,              -- What happened (one sentence preferred)
    metadata TEXT,                      -- JSON blob for structured data

    -- Provenance (governance-critical)
    source_ref TEXT,                    -- File path, commit SHA, transcript ref

    -- Integrity (governance-critical)
    event_hash TEXT NOT NULL,           -- SHA-256 of (previous_hash + content fields)
    previous_hash TEXT,                 -- Hash of prior event (NULL for first event)

    -- Versioning (governance-critical)
    schema_version INTEGER DEFAULT 1,

    -- Constraints
    UNIQUE(session_id, sequence)
);

-- Indexes for common query patterns
CREATE INDEX idx_episodes_session ON episodes(session_id, sequence);
CREATE INDEX idx_episodes_timestamp ON episodes(timestamp DESC);
CREATE INDEX idx_episodes_project ON episodes(project, timestamp DESC);
CREATE INDEX idx_episodes_type ON episodes(event_type);
CREATE INDEX idx_episodes_agent ON episodes(agent_id);
```

### 4.3 Hash Chaining

Every event includes a cryptographic hash linking it to its predecessor:

```python
import hashlib, json

def compute_event_hash(event: dict, previous_hash: str | None) -> str:
    """Tamper-evident hash chain. If any event is modified or deleted,
    all subsequent hashes become invalid."""
    payload = json.dumps({
        "previous_hash": previous_hash,
        "id": event["id"],
        "session_id": event["session_id"],
        "sequence": event["sequence"],
        "timestamp": event["timestamp"],
        "event_type": event["event_type"],
        "agent_id": event["agent_id"],
        "content": event["content"],
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
```

This is the "15 lines of SQL" pattern from the research. Cost: one SHA-256 per event (~1 microsecond). Value: any modification to any event breaks all subsequent hashes — immediately detectable by a simple chain-walk verification.

**What this enables later (not now):**
- Cryptographic signing (agent private keys sign event_hash)
- Merkle tree roots for periodic attestation
- Third-party audit verification

### 4.4 Event Type Taxonomy

| Event Type | Description | Example |
|------------|-------------|---------|
| `session_start` | Session begins | "Started working on memory-layer FIX-01" |
| `session_end` | Session closes | "Completed FIX-01 and FIX-02, all tests pass" |
| `decision` | Explicit choice by agent | "Chose SQLite over JSONL for episodic storage" |
| `observation` | Something noticed/learned | "PreCompact hooks cannot call MCP tools" |
| `action` | Concrete step taken | "Added client_profiles to memory_config.yaml" |
| `error` | Something went wrong | "Stdio test failing — stale tool count assertion" |
| `milestone` | Significant checkpoint | "51 tests pass, 15 smoke, 7 stdio — all green" |
| `reflection` | Meta-cognitive assessment | "Instruction-driven capture is unreliable as sole mechanism" |

### 4.5 MCP Tools

Three new tools exposed through the existing MCP server:

#### `write_episode`

```json
{
  "content": "Added client_profiles to production config — root cause of scope narrowing",
  "event_type": "action",
  "session_id": "ses-20260219-1600",
  "project": "memory-layer",
  "agent_id": "claude-code",
  "source_ref": "commit:e997266"
}
```

Minimal required fields: `content`, `event_type`, `agent_id`. Everything else defaults:
- `session_id` → auto-generated from date + sequence if not provided
- `project` → inferred from namespace or left null
- `sequence` → auto-incremented within session
- `timestamp` → now
- `event_hash` + `previous_hash` → computed automatically
- `namespace` → caller's default namespace

#### `get_episodes`

Query episodes by session, project, time range, or event type:

```json
{
  "session_id": "ses-20260219-1600",
  "event_type": "decision",
  "project": "memory-layer",
  "since": "2026-02-19T00:00:00Z",
  "limit": 50
}
```

Returns episodes in chronological order with hash chain intact.

#### `end_session`

Explicitly close a session. Writes a `session_end` event and optionally triggers summarization:

```json
{
  "session_id": "ses-20260219-1600",
  "summary": "Fixed FIX-01/02. Researched capture hooks. Started design doc.",
  "agent_id": "claude-code"
}
```

### 4.6 Relationship to Existing Systems

```
┌─────────────────────────────────────────────────────────┐
│                  Episodic Event Log                       │
│            (append-only, hash-chained)                    │
│                                                          │
│  "What happened" — immutable source of truth             │
└────────────────────────┬─────────────────────────────────┘
                         │
              extraction pipeline
              (batch, session-end)
                         │
┌────────────────────────▼─────────────────────────────────┐
│                Semantic Memory                            │
│           (mutable, deduplicated)                         │
│                                                          │
│  "What we know" — current state projection               │
└──────────────────────────────────────────────────────────┘
```

This is the **event sourcing** pattern. Episodes are the log of events. Semantic memories are projections that can be rebuilt from the log. The key invariant: **episodes are never modified or deleted.** Semantic memories can be updated, consolidated, or archived.

The usage log (`data/usage.jsonl`) becomes a third leg:

| Log | Purpose | Mutability | Governance Role |
|-----|---------|-----------|-----------------|
| Episodic events | What happened, what was decided | Append-only, hash-chained | Audit trail, decision traceability |
| Semantic memories | What we currently believe to be true | Mutable (update, archive) | Knowledge management |
| Usage telemetry | Who called what tool, when | Append-only | Operations monitoring, access auditing |

---

## 5. Governance Trajectory

### 5.1 What We Build Now (v1.1)

| Capability | Cost | Governance Value |
|-----------|------|-----------------|
| Append-only episodes table | Low | Foundation — can't retrofit |
| Hash chaining (event_hash + previous_hash) | Low (~15 lines) | Tamper detection — can't retrofit |
| Agent identity on every record | Zero (already have writer_id/caller_id) | Multi-agent attribution |
| Schema versioning | Zero (one field) | Forward compatibility |
| source_ref field | Low | Provenance chain — link memory to evidence |
| Chain verification tool | Low | Audit capability |

### 5.2 What We Add Later (v1.2+)

| Capability | Prerequisites | Governance Value |
|-----------|--------------|-----------------|
| Trust scoring per agent | Usage data + episode history | Multi-agent governance |
| LLM-based extraction pipeline | Episodic log + extraction prompts | Automated memory curation |
| Periodic chain attestation | Hash chains | Compliance checkpoints |
| Cross-reference: memory → episode | source_ref field | "Why do we believe this?" |
| Usage log → SQLite migration | Current JSONL exists | Unified queryable audit surface |
| Formal decision records | Episode schema | Traceable architectural decisions |

### 5.3 Enterprise Path

The progression from personal to enterprise:

```
v1.0 (current)     → Semantic memory only, no audit trail
v1.1 (this design) → + Episodic log (hash-chained, append-only)
                     + Cross-client capture (instruction + hooks)
                     + source_ref (provenance links)
v1.2               → + Trust scoring per agent/source
                     + LLM extraction pipeline (episode → memory)
                     + Chain verification + attestation reports
v2.0               → + Cryptographic signing (agent keys)
                     + Multi-party verification
                     + Compliance framework alignment (SOC2, AI Act Art. 12)
                     + Role-based access control
```

Each step builds on the previous. Nothing in v1.1 closes off any v2.0 capability. The critical investment is the schema — hash chains, agent_id, schema_version, append-only discipline.

---

## 6. Design Decisions

### D1: SQLite over JSONL for episode storage

**Chosen:** SQLite episodes table in the existing database.

**Rationale:** Already have SQLite WAL in the stack. Provides ACID, indexing, SQL queries, concurrent reads, and scales to 1M+ entries. JSONL adds a second storage system with no indexing and a ~50K scale ceiling.

**Trade-off:** Lose human-readability. Mitigated by MCP tools (`get_episodes`) and optional JSONL export.

### D2: Hash chaining from event #1

**Chosen:** Every event includes `event_hash` (SHA-256 of content + previous_hash) and `previous_hash`.

**Rationale:** Research showed this cannot be retrofitted — an unchained prefix permanently weakens auditability. Cost is ~1 microsecond per event. Value is tamper detection and foundation for future cryptographic signing.

**Trade-off:** Slightly more complex write path. Mitigated by computing hash in the write_episode tool — callers never see it.

### D3: Post-session extraction over inline capture

**Chosen:** Capture happens at session end (SessionEnd hook + transcript extraction), not inline during the conversation.

**Rationale:** Inline capture (PostToolUse hooks, Stop hook with "block") is the primary noise source in community implementations. Post-session extraction adds zero latency and zero visible interruption.

**Trade-off:** Episodes aren't available until session ends. Mitigated by instruction-driven `write_episode` calls during session for high-signal events.

### D4: Instruction-driven capture as universal baseline

**Chosen:** All three clients (Claude, Codex, Gemini) get system prompt instructions to call `write_memory` / `write_episode` at session end.

**Rationale:** Only mechanism that works across all clients. Zero infrastructure. Zero noise when it fires.

**Trade-off:** Unreliable (estimated 40-60% compliance). Mitigated by hooks where available (Claude, Gemini) as enhancement layer.

### D5: Separate episode and semantic stores

**Chosen:** Episodes table is distinct from memories table. Episodes are append-only and immutable. Semantic memories remain mutable.

**Rationale:** Event sourcing pattern — the log is the source of truth, current state is a projection. Mixing mutable and immutable data in one store creates governance ambiguity.

### D6: Scope episodes through existing namespace system

**Chosen:** Episodes use the same namespace + client_profiles authorization as semantic memories.

**Rationale:** Reuse existing access control. An agent that can read `memory-layer` namespace memories can also read `memory-layer` namespace episodes.

---

## 7. Open Questions for Review

### Q1: Should the usage log migrate to SQLite?

Currently `data/usage.jsonl` (append-only JSONL). With episodes in SQLite, we'd have two append-only systems in different formats. Consolidating to SQLite gives a unified query surface but adds migration work. **Recommendation:** Migrate in v1.2, not v1.1.

### Q2: What triggers the transcript extraction?

The SessionEnd hook fires a Python script. That script needs to:
1. Read the transcript file
2. Extract high-signal events (decisions, errors, learnings)
3. Write episodes to SQLite

Should extraction use (a) heuristic keyword matching (fast, cheap, misses novel patterns), (b) LLM-based extraction (better quality, costs API calls), or (c) structured section parsing (if transcript has consistent format)?

**Recommendation:** Start with (c) — parse transcript structure (tool calls, final messages) without LLM. Graduate to (b) in v1.2 when we have data on what patterns matter.

### Q3: Episode retention and archival

Episodes are append-only forever? Or should there be a compaction/archival policy for old episodes? Governance argues for forever (or legally required retention period). Practicality argues for archival after N months.

**Recommendation:** Keep all episodes in SQLite. Add optional compressed JSONL export for cold archival after 90 days. Never delete — only archive.

### Q4: Should write_episode require authentication?

Current semantic memory tools use `caller_id` from the MCP call with client_profiles authorization. Episodes should use the same model. But should episodes have stricter write controls (e.g., only the agent that created a session can write to it)?

**Recommendation:** Same model as semantic memory for v1.1. Session-scoped write locks in v1.2.

### Q5: How do we measure capture reliability?

Instruction-driven capture is estimated at 40-60% compliance. How do we measure actual compliance to know if hooks are needed? **Recommendation:** Compare session count (from SessionEnd hook logs) vs episode count. The gap is the miss rate.

---

## 8. Implementation Plan

### Phase 1: Episodic Log Foundation

1. Add `episodes` table to SQLite schema (schema.sql, db.py)
2. Implement hash chaining (compute_event_hash utility)
3. Add EpisodicEvent Pydantic model
4. Implement episode storage API (write, query, verify chain)
5. Add MCP tools: `write_episode`, `get_episodes`, `end_session`
6. Tests: schema, hash chaining, episode CRUD, MCP integration

### Phase 2: Cross-Client Capture

7. Update CLAUDE.md session protocol with `write_episode` instructions
8. Create Claude Code SessionEnd hook (shell → Python extractor)
9. Create Gemini CLI extension (SessionEnd hook + MCP config)
10. Update AGENTS.md (Codex) with `write_episode` instructions
11. Create transcript extraction script (structured parsing)

### Phase 3: Governance Utilities

12. Add `verify_chain` MCP tool (walk hash chain, report integrity)
13. Add `source_ref` field to `write_memory` (backlog item — connects semantic to episodic)
14. Update `get_usage_report` to include episode stats
15. Documentation: usage guide for episodic tools

### Phase 4: Measurement & Iteration

16. Deploy, run for 2 weeks
17. Measure capture rate (sessions vs episodes)
18. Assess signal quality of extracted episodes
19. Decide on LLM-based extraction (v1.2) based on data

---

## 9. Success Criteria

| # | Criterion | Measurement |
|---|-----------|-------------|
| 1 | Episodes table exists with hash chaining | Schema deployed, chain verification passes |
| 2 | write_episode / get_episodes / end_session MCP tools work | Smoke test + stdio test pass |
| 3 | Claude Code SessionEnd hook captures episodes | Run 5 sessions, check episode count > 0 |
| 4 | System prompt instructions work for all 3 clients | Test with Claude, Codex, Gemini — each writes at least 1 episode |
| 5 | Hash chain integrity holds across 100+ events | verify_chain returns clean for full chain |
| 6 | No user-visible noise during normal operation | Hooks run silently, no screen output |
| 7 | Episodes are queryable by session, project, time range | get_episodes returns correct filtered results |
| 8 | Existing semantic memory functionality unchanged | All 51 existing tests still pass |

---

## 10. Sources

### Hook Capabilities
- Claude Code Hooks Reference — events, execution model, async support, decision control
- Gemini CLI Hooks Reference — 11 lifecycle events, extension system
- Codex CLI — no hooks; issue #2109 (411+ thumbs-up requesting them)

### Community Memory Capture
- **claude-mem** (thedotmack) — 5 lifecycle hooks, background Bun worker, 8ms PostToolUse latency
- **claude-code-auto-memory** (severity1) — isolated agent processing, zero main-session noise
- **Claude Diary** (Lance Martin/Anthropic) — manual /diary + /reflect, highest signal-to-noise
- **ContextStream** — cloud-backed auto-capture, 5 hooks
- **AgentKits Memory** — background workers, progressive disclosure, 5+ clients via MCP
- **mcp-memory-service** (doobidoo) — 13+ client support, hybrid BM25+vector, REST+MCP

### Enterprise Governance
- **Langfuse** — trace/observation/session model, OpenTelemetry-native
- **PROV-AGENT/Flowcept** — W3C PROV extension for MCP-based agent workflows
- **SQLite hash chain pattern** — 15 lines of SQL for tamper-evident chaining
- **EU AI Act Article 12** — automatic recording requirements for traceability
- **NIST AI RMF** — governance functions requiring audit trails

### Episodic Memory Architecture
- **Zep** — temporal knowledge graph, bi-temporal model, streaming extraction pipeline
- **LangMem SDK** — Episode model (observation/thoughts/action/result), hot-path + background
- **Letta/MemGPT** — recall memory as episode log, date-range queries
- **SEEM framework** — Episodic Event Frames with semantic roles and provenance
- **REMem** — hybrid memory graph with temporal qualifiers
- **CrewAI** — unified memory with temporal decay + importance scoring
- **Event sourcing pattern** — episodes as immutable log, semantic memory as projection

Full research documents:
- `docs/research-episodic-memory.md` — episodic patterns, schemas, extraction pipelines
- `docs/research-synthesis.md` — production memory system research (6 inbox documents)
- `docs/capture-problem.md` — capture enforcement gap analysis
- `docs/architecture-review.md` — design quality and optimization assessment
