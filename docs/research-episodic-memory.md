---
type: "research"
project: "Memory Layer"
topic: "Episodic Memory Patterns in Production Agentic Systems"
created: "2026-02-19"
status: "complete"
---

# Episodic Memory Patterns in Production Agentic Systems

Research synthesis covering how production agentic systems implement episodic memory, session logs, and event journals -- the "what happened" layer, distinct from semantic memory (facts).

## 1. Episodic Memory in Agent Frameworks

### LangGraph / LangMem SDK

LangGraph separates memory into three types: **semantic** (facts/knowledge), **episodic** (past experiences), and **procedural** (behavioral rules).

Episodic memory in LangMem is implemented as **few-shot examples distilled from raw interactions**. Each episode captures a full reasoning chain:

```python
class Episode(BaseModel):
    observation: str  # Context and setup -- "what was the situation"
    thoughts: str     # Internal reasoning process
    action: str       # What was done and how
    result: str       # Outcome and retrospective
```

Key design choice: episodes are not raw transcripts. They are **structured retrospectives** written from the agent's perspective, using hindsight. The extraction instruction defines what to capture:

> "Extract examples of successful explanations... the full chain of reasoning that led to success."

Storage uses LangGraph's `BaseStore` with hierarchical namespaces (`("memories", "episodes")`). Retrieval is vector similarity search on episode content. Episodes are stored as JSON documents with metadata.

**Update mechanisms:**
- **Hot path (active):** Agent explicitly decides what to remember via tool calling before responding. Adds latency but ensures immediate capture.
- **Background (subconscious):** Reflection occurs after conversations, extracting patterns without impacting response time. Better for deeper pattern analysis.

### CrewAI

CrewAI replaced its original four-memory-type system (short-term, long-term, entity, contextual) with a **unified Memory class**. The system uses an LLM to analyze content during storage, inferring scope, categories, and importance.

Record schema:
```
content      -- stored text
scope        -- hierarchical path (e.g., /project/alpha)
categories   -- inferred topic tags
importance   -- numeric score (0-1)
source       -- provenance tag
private      -- access control flag
timestamps   -- creation, update
```

Episodic aspects are handled through **temporal metadata + recency decay**:
```
composite = semantic_weight * similarity + recency_weight * decay + importance_weight * importance
decay = 0.5^(age_days / half_life_days)
```

Default weights: semantic=0.5, recency=0.3, importance=0.2, half-life=30 days. After each task, the crew automatically extracts discrete facts from task output and stores them. Before each task, it recalls relevant context.

### AutoGen

AutoGen's memory proposal (Issue #4564) defines memory banks as **agents in the actor model** that process events published to topics/queues. Five built-in types:

1. **Raw Semantic Search** -- vector DB broker
2. **Episodic Memory** -- "summarizes raw memories, records sequence of events, allows for multiple layers of summary in recall"
3. **Short-term Memory** -- "short, processed, focused store of what an agent is doing right now"
4. **Whiteboard Memory** -- shared task tracking and decision recording across agents
5. **Procedural Memory** -- skills and capability retrieval

AutoGen's current stable implementation exposes a `Memory` protocol with `MemoryContent` entries:
```
content   -- stored information
mime_type -- format (TEXT, etc.)
metadata  -- key-value pairs (source, chunk_index, category, scores)
```

### Semantic Kernel (Microsoft Agent Framework)

Experimental agent memory with two providers:

1. **Mem0Provider** -- extracts memories from thread messages, queries for relevant memories on each invocation. Scoped by Application, Agent, Thread, and User IDs. Cross-thread persistence.

2. **WhiteboardProvider** -- processes each message to extract **requirements, proposals, decisions, actions**. Stored on a whiteboard, provided as additional context. Supports chat history truncation by retaining critical context independently.

The whiteboard pattern is notable: it is structurally similar to an event journal with typed entries (requirement, proposal, decision, action) that survive context window eviction.

### Letta (MemGPT)

Three-tier memory hierarchy modeled on OS memory management:

1. **In-context memory** -- directly writable section of context window (`self.memory` dict mapping labeled sections to `MemoryModule` objects with character limits, default 2K per section)
2. **Archival memory** -- vector DB table for long-running memories and external data
3. **Recall memory** -- table logging **all conversational history** with an agent

All state (memories, user messages, reasoning, tool calls) persists in a database. Even after context compaction/eviction, old messages remain retrievable via API.

Agent has explicit memory tools: `memory_replace`, `memory_insert`, `memory_rethink`, `archival_memory_insert`, `archival_memory_search`, `conversation_search`, `conversation_search_date`.

Key insight: Letta's recall memory IS an episode log. It stores every message and tool call with timestamps, making it queryable by date range or content.

### Zep

Zep implements a **temporal knowledge graph** with three hierarchical subgraph tiers:

1. **Episode subgraph** -- raw input data (messages, text, JSON) as episodic nodes. Non-lossy data store.
2. **Semantic entity subgraph** -- entities and relationships extracted from episodes.
3. **Community subgraph** -- higher-order patterns.

Episode node schema:
```
content        -- raw message or text
actor/speaker  -- producing entity
t_ref          -- reference timestamp (when message was sent)
```

**Bi-temporal model:**
- Timeline T (event timeline): chronological ordering of actual events
- Timeline T' (transaction timeline): when Zep ingested the data

Semantic edges store four timestamps:
```
t'_created, t'_expired  -- transaction timeline markers
t_valid, t_invalid       -- validity range in actual time
```

This enables "when did something happen" vs "when did we learn about it" -- critical for handling contradictions.

### OpenMemory (CaviraOSS)

Multi-sector cognitive memory with five categories: episodic (events), semantic (facts), procedural (skills), emotional (feelings), reflective (insights).

Storage: SQLite/PostgreSQL + vector store. Features a **temporal knowledge graph** with `valid_from`/`valid_to` dates, point-in-time truth reconstruction, and entity evolution tracking.

Composite scoring: salience + recency + coactivation (not just cosine distance). Adaptive forgetting decay engine per sector type.

---

## 2. JSONL Event Journal Patterns

### Core Pattern

JSONL (JSON Lines) is append-friendly, memory-efficient (process line-by-line), and doesn't require loading the entire dataset. Each line is an independent JSON object.

Basic Python pattern:
```python
# Write
with open("events.jsonl", "a") as f:
    f.write(json.dumps(record) + "\n")

# Read
with open("events.jsonl") as f:
    for line in f:
        event = json.loads(line.strip())
```

### Schema Versioning

Best practices:
- Include a `schema_version` field in every record
- Use JSON Schema for validation at ingest time
- Two levels: syntax validation (valid JSON per line) and schema validation (matches expected structure)
- JSONL is schema-less by nature, so versioning must be enforced at the application layer
- Standardize on consistent field names across all services (OpenTelemetry Semantic Conventions is the emerging standard)

### Indexing JSONL at Scale

**SQLite sidecar pattern** (from openclaw-mem and similar projects):
- JSONL files remain the append-only source of truth
- A SQLite sidecar database tracks ingestion state (file offsets) and builds indexes
- File watcher detects new files; tail reader tracks offsets to avoid re-ingestion
- Batch inserts with `Connection.executemany()` achieve ~270K upserts/second with no indexes

**SQLite generated columns for JSON indexing:**
```sql
-- Store raw JSON, create virtual columns, index them
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    data TEXT  -- raw JSON
);

-- Generated column from JSON field
ALTER TABLE events ADD COLUMN event_type TEXT
    GENERATED ALWAYS AS (json_extract(data, '$.event_type'));

CREATE INDEX idx_event_type ON events(event_type);
```

This gives B-tree index speed on JSON fields while preserving the raw document.

### Rotation

Python `TimedRotatingFileHandler` supports daily rotation with `app.log.YYYY-MM-DD` naming. Loguru supports `logger.add("events_{time:YYYY-MM-DD}.jsonl", rotation="00:00", retention="1 week")`.

### Compression

- Completed day files can be gzip-compressed (Python `gzip` module reads/writes transparently)
- Active day file stays uncompressed for append performance
- Compressed JSONL is still line-processable with `gzip.open()`

---

## 3. Daily/Session File Patterns: Trade-offs

### Pattern Comparison

| Pattern | Pros | Cons | Scale Ceiling |
|---------|------|------|---------------|
| **Single JSONL file** | Simplest. One file to manage. Easy append. | No date partitioning. Gets unwieldy. Seek time grows. No partial rotation. | ~50K entries before ergonomics degrade |
| **Daily files (`YYYY-MM-DD.jsonl`)** | Natural partitioning. Old days can compress/archive. Parallel processing per day. Easy date-range queries (just pick files). | More files to manage. Cross-day queries need multi-file scan. Need date routing logic. | 100K-500K total (across files) without indexing |
| **Session files (`session-{id}.jsonl`)** | Perfect isolation per session. Easy to correlate. Can archive/delete per session. | Many small files. Need session index. Cross-session queries expensive. | Similar to daily, but more files |
| **SQLite WAL** | ACID. Concurrent reads during writes. Full SQL querying. Indexes. 70K reads/s, 3.6K writes/s. | More complex than file append. Binary format (not human-readable). Requires schema upfront. | 1M+ entries with proper indexing |
| **Hybrid (JSONL + SQLite sidecar)** | Best of both: human-readable source of truth + queryable index. | Two systems to maintain. Ingestion lag between append and index. | 1M+ with periodic sync |

### Recommendations by Scale

- **10K entries:** Single JSONL or daily files. No indexing needed. `grep` and `jq` suffice.
- **100K entries:** Daily files with SQLite sidecar index. Or move to SQLite WAL directly.
- **1M entries:** SQLite WAL is the right answer. JSONL becomes impractical for random-access queries without indexing. Consider partitioned tables or date-based sharding within SQLite.

### SQLite WAL Details

WAL mode: changes append to a separate WAL file, enabling concurrent reads and writes. Append-only nature makes it faster than rollback journal for write-heavy workloads. Performance: 70K reads/s, 3.6K writes/s in benchmarks. The WAL file can grow large during high-write periods; checkpoint frequency balances performance vs disk usage.

---

## 4. Event Schemas for Agent Sessions

### Composite Schema (Synthesized from Production Systems)

Based on patterns across Zep, LangMem, AutoGen, CrewAI, OpenMemory, and the Principia Agentica reference architecture:

```python
class EpisodicEvent(BaseModel):
    """Single event in an agent session journal."""

    # Identity
    event_id: str           # UUID4
    session_id: str         # Groups events into sessions
    sequence: int           # Monotonic ordering within session

    # Temporal
    timestamp: str          # ISO 8601 with timezone
    t_ref: str | None       # Reference timestamp for relative date resolution (Zep pattern)

    # Classification
    event_type: str         # decision | observation | action | error | milestone | reflection | tool_call | message
    severity: str | None    # info | warning | error | critical (for error events)

    # Context
    agent_id: str           # Which agent produced this event
    project: str | None     # Project context
    namespace: str          # Memory namespace scope

    # Content
    content: str            # The event description / what happened
    summary: str | None     # Optional condensed version

    # Structured data
    metadata: dict          # Flexible key-value (tool_name, input_hash, output_preview, duration_ms, etc.)
    source_ref: str | None  # File path, URL, commit SHA, or other provenance pointer

    # Versioning
    schema_version: int     # For forward compatibility
```

### Event Type Taxonomy

From production systems, the following event types recur:

| Event Type | Description | Examples |
|------------|-------------|----------|
| `message` | User or agent communication | User instruction, agent response |
| `tool_call` | Tool invocation with result | File read, search, API call |
| `decision` | Explicit choice made by agent | "Chose approach A over B because..." |
| `observation` | Something noticed or learned | "Found that config uses YAML not JSON" |
| `action` | Concrete step taken | "Created file X", "Modified function Y" |
| `error` | Something went wrong | Build failure, test failure, API error |
| `milestone` | Significant checkpoint | "All tests passing", "Feature complete" |
| `reflection` | Meta-cognitive assessment | "This approach isn't working, pivoting" |
| `state_change` | System state transition | Session start, session end, compaction |

### Real Schemas from Production

**Principia Agentica (episodic event structure):**
```json
{
  "task_id": "deploy_2025_09_20",
  "ts": "2025-09-20T18:22:10Z",
  "type": "tool_call",
  "tool": "kubectl",
  "result": {"ok": true}
}
```

**Zep episode node:**
```json
{
  "content": "raw message text",
  "actor": "user",
  "t_ref": "2025-09-20T18:22:10Z",
  "episode_type": "message"
}
```

**LangMem episode:**
```json
{
  "observation": "User asked about deployment patterns",
  "thoughts": "They seem to want a comparison, not a tutorial",
  "action": "Provided comparison table with trade-offs",
  "result": "User confirmed this was helpful, asked follow-up about scaling"
}
```

**REMem hybrid memory graph node (gist):**
```
Time-aware natural-language summary with parsed timestamps,
capturing situational dimensions: participants, actions,
locations, intentions. Plus factual triples with temporal
qualifiers (point_in_time, start_time, end_time).
```

---

## 5. Episodic-to-Semantic Extraction

### The Core Pattern

Episodic memory (what happened) serves as a source of truth from which semantic memory (what we know) is derived. This is structurally identical to **event sourcing**: the event log is the source of truth, and current state (semantic memory) is a projection.

### Extraction Approaches

**1. Real-time (hot path)**
- Agent decides what to remember during the conversation via tool calls
- LangMem, Letta, Mem0 all support this
- Adds latency but ensures immediate capture
- Example: Agent calls `write_memory("User prefers YAML over JSON for config")` during conversation

**2. Background (batch)**
- Reflection occurs after conversations
- Better for deeper pattern analysis and higher recall
- LangMem's background formation extracts patterns from completed conversations
- Factory.ai summarizes only newly dropped spans and merges into persisted summary

**3. Offline indexing (research)**
- REMem: converts experiences into a hybrid memory graph (gists + facts)
- SEEM: transforms interaction streams into structured Episodic Event Frames
- Two-phase: offline indexing + online inference

### Zep's Pipeline (Most Detailed Production Example)

1. **Entity extraction:** LLM processes current message + 4 prior messages (2 turns) for context
2. **Entity resolution:** Embeddings + full-text search identify duplicates against existing nodes
3. **Fact extraction:** Semantic relationships between entities
4. **Temporal extraction:** Absolute and relative timestamps parsed using `t_ref`
5. **Edge invalidation:** New facts trigger LLM comparison against existing edges; contradictions update `t_invalid`

This is a **streaming extraction pipeline** -- each new episode triggers incremental graph updates, not batch reprocessing.

### SEEM Framework (Research)

Structured Episodic Event Memory transforms interactions into **Episodic Event Frames (EEFs)**:
- Summary: high-level event description
- Semantic roles: participants, action, time, location, causality, manner
- Provenance pointers: links back to source passages

Two-phase processing:
1. **Extraction:** LLM parses each passage into structured semantic roles
2. **Fusion:** Judgment mechanism identifies related frames, merges via "associative consolidation"

**Reverse Provenance Expansion (RPE):** retrieves initial fact-based passages, identifies associated frames, expands to include all referenced passages -- transforms fragmented evidence into coherent narratives.

### Event Sourcing Parallel

The Tracardi blog articulates the connection explicitly:
- Log every event that contributed to current state
- Reconstruct understanding by replaying events
- **Pruning:** raw events transition to summarized knowledge (forgetting)
- **Reinterpretation:** re-analyze all past events when new critical information emerges

This maps directly to the memory layer architecture: episodes are the immutable log, semantic memories are derived projections that can be rebuilt.

---

## 6. Session Summarization

### Strategies

**1. Rolling summary (Factory.ai pattern)**
- Maintain a "lightweight, persistent conversation state: a rolling summary of the information that actually matters"
- Two-threshold system:
  - `Tmax` (compression threshold): triggers compression when context reaches this limit
  - `Tretained` (retention threshold): max tokens kept after compression (always < Tmax)
- Only newly dropped spans are summarized and merged into existing summary
- Narrow gap = frequent compression + better context; wide gap = less overhead + more aggressive loss

**2. Chunk-and-summarize (Mem0 / general pattern)**
- After N turns (5-10), summarize that chunk
- Summary replaces original messages in history
- Progressive: older summaries can themselves be summarized

**3. Structured section summary (OpenAI Agents SDK)**
- Generates structured summaries with specific sections:
  - Product & Environment
  - Reported Issue
  - Steps Tried & Results
  - Current Status
  - Next Recommended Step
- Includes contradiction checking against system instructions
- Marks uncertain facts as "UNVERIFIED"
- Tracks tool performance (which operations succeeded/failed)

### What Gets Kept vs Discarded

**Always keep:**
- Session intent / user goals
- Key decisions and their rationale
- Final outcomes / results
- Error states and their resolutions
- File paths and artifact identifiers (breadcrumbs)
- Entity relationships discovered

**Safe to discard:**
- Intermediate trial-and-error (once work phase completes)
- Raw tool output (summarize to success/failure + key data)
- Verbose reasoning chains (condense to conclusion)
- Repeated context that hasn't changed

**Keep with compression:**
- Conversation flow (condense to high-level play-by-play)
- Tool call sequences (condense to action + outcome)

### Prompt Template (Synthesized from Production Patterns)

```
You are summarizing an agent work session. Create a structured summary that would
allow a future agent to understand what happened and continue the work.

## Required Sections

### Session Intent
What was the user trying to accomplish? State the goal clearly.

### Key Actions & Outcomes
Chronological list of significant actions taken and their results.
Include: what was done, what the outcome was, what was learned.
Omit: intermediate debugging steps, raw tool output, verbose reasoning.

### Decisions Made
List any choices or trade-offs made during the session, with brief rationale.

### Current State
What is the state of the work at session end?
- What is complete?
- What is in progress?
- What is blocked or unresolved?

### Artifacts Modified
Files created, modified, or deleted. Include paths.

### Next Steps
What should the next session pick up? Be specific and actionable.

### Open Questions
Anything unresolved that needs investigation or human input.

## Rules
- Be concise. Each bullet should be one sentence.
- Preserve file paths, variable names, and technical identifiers exactly.
- Flag any contradictions or reversals that occurred during the session.
- Mark uncertain conclusions as [UNVERIFIED].
- Do not include raw tool output or full code blocks.
```

---

## 7. Cross-Session Continuity

### Patterns in Production

**1. Status file pattern (Claude Code, ADF agents)**
- `status.md` read at session start, updated at session end
- Contains: current state, next steps, blockers, session log
- Advantages: human-readable, version-controlled, no extra infrastructure
- Disadvantages: manual discipline required, no structured query

**2. Session memory object (OpenAI Agents SDK)**
- `session.run("...")` -- SDK handles context length, history, continuity
- `get_full_history()` returns complete records with metadata
- Sessions store complete records enabling new agents to continue
- Metadata includes `synthetic` flags for compressed history

**3. Temporal query (Letta / Zep)**
- Recall memory stores all conversational history
- `conversation_search_date` enables time-range queries
- Zep's bi-temporal model distinguishes event time vs ingestion time
- Enables: "What was I working on last Tuesday?"

**4. Semantic search on episodes (LangMem)**
- Search past episodes by similarity to current context
- Enables: "Have I solved a problem like this before?"
- Episodes surface as few-shot examples in the system prompt

**5. Context injection at session start**
- Query recent + relevant memories and inject into system prompt
- `get_session_context(namespace, query)` returns `{ recent: [...], relevant: [...] }`
- Combines recency (what happened lately) with relevance (what matters now)

### The "Last Time" Pattern

The most effective cross-session continuity combines:

1. **Recent state** -- what was the last session's outcome? (status file or recent episodes)
2. **Relevant context** -- what do we know that's related to current task? (semantic search)
3. **Procedural memory** -- how should we approach this type of task? (few-shot episodes)

OpenAI's session memory, Letta's recall memory, and the ADF status.md pattern all converge on this: **the system must know what happened last, what's relevant now, and how to approach similar problems.**

### Implementation Implications for Memory Layer

The current Memory Layer has `get_session_context` (returns recent + relevant semantic memories) but lacks:
- **Episode storage** -- structured records of what happened in each session
- **Session boundaries** -- no concept of sessions, only individual memories
- **Temporal queries** -- can query by recency but not by session or date range
- **Summarization** -- no mechanism to compress episodes into summaries
- **Few-shot retrieval** -- no way to surface past episodes as examples

---

## 8. Key Takeaways for Memory Layer Evolution

### Architecture Decision: Episode Storage

The research strongly suggests **episodes and semantic memories should be separate stores** with an extraction pipeline between them:

```
Episodes (append-only, immutable)
    |
    |-- extraction pipeline (LLM or rule-based)
    |
    v
Semantic Memories (mutable, deduplicated)
```

This matches the event sourcing pattern. Episodes are the source of truth. Semantic memories are derived projections.

### Recommended Episode Storage

Given the Memory Layer's existing architecture (SQLite WAL + Chroma + local-first):

- **SQLite table `episodes`** for structured event records (not JSONL files)
- Rationale: already have SQLite WAL in the stack, provides ACID, indexing, SQL queries, scales to 1M+ entries
- JSONL could serve as an optional export format or backup medium
- Daily file partitioning adds complexity without benefit when SQLite already handles indexing

### Recommended Episode Schema

```sql
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,           -- UUID4
    session_id TEXT NOT NULL,      -- Groups events into sessions
    sequence INTEGER NOT NULL,     -- Ordering within session
    timestamp TEXT NOT NULL,       -- ISO 8601
    event_type TEXT NOT NULL,      -- decision, observation, action, error, milestone, etc.
    agent_id TEXT NOT NULL,        -- Which agent
    project TEXT,                  -- Project context
    namespace TEXT NOT NULL,       -- Scope
    content TEXT NOT NULL,         -- What happened
    metadata TEXT,                 -- JSON blob for flexible fields
    source_ref TEXT,               -- Provenance pointer
    schema_version INTEGER DEFAULT 1
);

CREATE INDEX idx_episodes_session ON episodes(session_id, sequence);
CREATE INDEX idx_episodes_timestamp ON episodes(timestamp DESC);
CREATE INDEX idx_episodes_project ON episodes(project, timestamp DESC);
CREATE INDEX idx_episodes_type ON episodes(event_type);
```

### Session Lifecycle

```
session_start (auto, on first event)
    |
    |-- events (decisions, observations, actions, errors, milestones)
    |
session_end (explicit or inferred)
    |
    |-- summarization (LLM compress session to structured summary)
    |-- extraction (derive semantic memories from episode content)
```

### Extraction Pipeline

Two options (not mutually exclusive):
1. **Real-time:** Agent calls `write_memory()` for important facts during session (current behavior)
2. **Batch (session-end):** Summarize + extract at session close. Feed episode log to LLM with extraction prompt.

Batch extraction at session end is the higher-value addition -- it catches things the agent didn't explicitly flag.

---

## Sources

### Agent Frameworks
- [LangGraph Memory Overview](https://docs.langchain.com/oss/python/langgraph/memory)
- [LangMem SDK Launch](https://blog.langchain.com/langmem-sdk-launch/)
- [LangMem Episodic Memory Extraction Guide](https://langchain-ai.github.io/langmem/guides/extract_episodic_memories/)
- [LangMem Conceptual Guide](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/)
- [LangChain Memory for Agents](https://blog.langchain.com/memory-for-agents/)
- [CrewAI Memory Documentation](https://docs.crewai.com/en/concepts/memory)
- [AutoGen Memory Proposal (Issue #4564)](https://github.com/microsoft/autogen/issues/4564)
- [AutoGen Memory Documentation](https://microsoft.github.io/autogen/stable//user-guide/agentchat-user-guide/memory.html)
- [Semantic Kernel Agent Memory](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-memory)
- [Letta/MemGPT Intro](https://docs.letta.com/concepts/memgpt/)
- [Letta Memory Management](https://docs.letta.com/advanced/memory-management/)
- [OpenMemory (CaviraOSS)](https://github.com/CaviraOSS/OpenMemory)

### Temporal Knowledge Graphs
- [Zep: Temporal Knowledge Graph Architecture (paper)](https://arxiv.org/html/2501.13956v1)

### Research Papers
- [REMem: Reasoning with Episodic Memory](https://arxiv.org/html/2602.13530)
- [SEEM: Structured Episodic Event Memory](https://arxiv.org/html/2601.06411v1)

### Event Sourcing & Architecture
- [Event Sourcing as AI Memory Backbone (Tracardi)](https://blog.tracardi.com/event-sourcing-as-the-backbone-of-ai-memory-learning-from-how-the-human-mind-works/)
- [Memory in Agents: Episodic vs Semantic (Principia Agentica)](https://principia-agentica.io/blog/2025/09/19/memory-in-agents-episodic-vs-semantic-and-the-hybrid-that-works/)
- [Episodic Memory in AI (DigitalOcean)](https://www.digitalocean.com/community/tutorials/episodic-memory-in-ai)

### Session Management & Summarization
- [OpenAI Agents SDK Session Memory](https://developers.openai.com/cookbook/examples/agents_sdk/session_memory/)
- [Factory.ai Compressing Context](https://factory.ai/news/compressing-context)
- [Claude Code Session Memory](https://claudefa.st/blog/guide/mechanics/session-memory)
- [Claude Code Memory Documentation](https://code.claude.com/docs/en/memory)

### JSONL & Storage
- [JSONL for Log Processing](https://jsonl.help/use-cases/log-processing/)
- [SQLite Write-Ahead Logging](https://sqlite.org/wal.html)
- [SQLite JSON Functions](https://sqlite.org/json1.html)
- [Mem0 Architecture Paper](https://arxiv.org/html/2504.19413v1)
