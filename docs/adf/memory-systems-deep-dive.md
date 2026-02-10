# Memory Systems Deep Dive — Curation, Architecture, Format, Capture, State, Write-Back

**Date:** 2026-02-10
**Purpose:** Targeted research on 6 open design questions for the Memory Layer project
**Status:** Research complete
**Builds on:** `memory-layer-research.md` (landscape scan)

---

## 1) Curation Workflows

**Question:** How do production memory systems handle memory curation — review, promotion, consolidation, rejection?

### Mem0: LLM-as-Judge Curation

Mem0 uses a two-phase pipeline: **Extraction** then **Update**.

**Extraction phase:** Each new message pair (user + assistant) is processed alongside two types of context: a conversation summary (global understanding) and a sequence of recent messages (temporal context). An LLM extracts "atomic facts" from this combined input.

**Update phase (the curation step):** For each candidate fact, the system retrieves the top-k semantically similar existing memories from the vector store. Rather than using rule-based logic, Mem0 delegates the curation decision to the LLM as a tool-call mechanism. The LLM chooses one of four operations:

- **ADD** — Genuinely new information with no semantic equivalent in existing memories
- **UPDATE** — Augment an existing memory with more recent or detailed information (e.g., "User likes cricket" becomes "User loves playing cricket with friends")
- **DELETE** — Remove memories contradicted by new information
- **NOOP** — Fact already exists or is irrelevant; no action needed

For graph-based memory (Mem0g), conflict detection uses an LLM-based resolver that marks conflicting relationships as invalid, supporting temporal reasoning without deleting data. The system also tracks decay metrics, confidence scoring, and maintains a history/audit trail on memory changes.

**Key insight:** Mem0 has no human-in-the-loop curation. The entire workflow is automated via LLM judgment. Consolidation (deduplication, merge) happens at write-time, not as a separate batch process.

### Letta (MemGPT): Agent-Initiated Self-Editing

Letta takes a fundamentally different approach: the agent itself curates its own memory using explicit tools. There is no separate curation pipeline — the agent decides what to remember during normal operation.

**Memory editing tools:**
- `memory_replace` — Find-and-replace for precise edits to core memory blocks
- `memory_insert` — Add new information to a memory block
- `memory_rethink` — Completely rewrite a memory block (wholesale replacement)

**Archival memory tools:**
- `archival_memory_insert` — Store information in long-term vector-backed storage
- `archival_memory_search` — Retrieve from archival storage

The agent autonomously decides when core memory blocks are stale and rewrites them. There is no external consolidation process — the agent IS the curator. This means curation quality depends entirely on the agent's reasoning ability and how well it uses its tools.

**Sleep-time compute:** Letta offers an option (`enable_sleeptime=True`) where a background process updates memory blocks outside of active conversations. This is essentially deferred curation — a secondary agent reviews and updates the primary agent's memory blocks asynchronously.

**Manual fallback:** Users can use `/remember` to explicitly tell the agent to store something, acknowledging that agents sometimes miss important information.

### LangMem (LangGraph Ecosystem): Dual-Path Curation

LangMem provides two curation pathways:

**Hot path (real-time):** The agent actively saves notes or updates memory during conversation using tools. This is similar to Letta's approach but implemented as LangGraph tool nodes.

**Background path (deferred):** A `ReflectionExecutor` runs after conversations settle. It prompts an LLM to reflect on the conversation, extract patterns, and produce insights — "subconscious" memory formation. Background processing is canceled while conversation is ongoing and only runs after inactivity.

**Memory Managers** handle the consolidation logic: extract new memories, update or remove outdated ones, and consolidate/generalize from existing memories based on new conversation information. The balance between creation and consolidation is developer-configurable via custom instructions.

### ChatGPT (OpenAI): Background Classifier

OpenAI uses background classifiers to identify salient facts during conversation. Memories are stored as short, timestamped single-sentence entries. Users can view, edit, and delete individual memories. There is no visible consolidation process — deduplication and conflict resolution happen internally. The system is opaque by design.

### AWS AgentCore Memory: Extraction + Consolidation Pipeline

AgentCore Memory explicitly separates extraction and consolidation as distinct async stages:
- **Extraction:** Pulls structured information from raw conversation events
- **Consolidation:** Merges newly extracted information with existing memories in the store

Both stages run asynchronously in the background after `CreateEvent` calls. This introduces a refresh delay between event ingestion and memory availability.

### MemAct (Research, Oct 2025): Memory-as-Policy

The Memory-as-Action framework treats memory curation as learnable policy actions. Rather than relying on external curation mechanisms, the agent learns when and how to edit its working memory through reinforcement learning. Memory operations (deletion, insertion) are optimized jointly with task performance through end-to-end RL. Results show MemAct-RL-14B matches models 16x larger while reducing context length by 51%.

### Summary: Curation Pattern Taxonomy

| Pattern | System | Who Curates | When | Consolidation |
|---------|--------|-------------|------|---------------|
| LLM-as-Judge | Mem0 | External LLM | At write-time | Automatic (ADD/UPDATE/DELETE/NOOP) |
| Agent Self-Edit | Letta | The agent itself | During conversation | Agent rewrites its own blocks |
| Dual-Path | LangMem | LLM (hot) + Reflector (background) | Real-time + deferred | Configurable manager |
| Background Classifier | ChatGPT | Hidden classifier | During conversation | Opaque/internal |
| Async Pipeline | AgentCore | External pipeline | Post-event (async) | Separate consolidation stage |
| Learned Policy | MemAct | RL-trained agent | During task execution | Integrated into policy |

**Implication for Memory Layer:** The Mem0 pattern (LLM-as-judge at write-time) is the most practical for a multi-writer ecosystem. Agent self-editing (Letta) works for single-agent scenarios but breaks down with multiple writers. LangMem's dual-path approach is worth considering — hot path for immediate writes, background reflection for consolidation.

---

## 2) Store Architecture

**Question:** Single store with metadata vs partitioned stores. What do production systems use?

### What Production Systems Actually Use

**Mem0 — Hybrid multi-store (parallel writes):**
When a memory is added via `add()`, it updates multiple systems in parallel:
- Vector database (Chroma, Qdrant, pgvector, etc.) for semantic similarity search
- Graph database (Neo4j, Memgraph, Neptune, Kuzu) for entity relationships
- Key-value store for fast fact retrieval
- History log for audit trail

Each memory object contains: the fact/data (core content), a vector embedding, and metadata (unique ID, hash, timestamps, user_id, agent_id). This is a **partitioned store** approach — different storage backends for different query patterns — but with a unified API that abstracts the partitioning.

**Letta — Single store with tool-based access:**
Core memory blocks live in the agent's context window (always loaded). Archival memory is backed by a single vector database (Chroma or pgvector). Recall memory stores raw conversation history. The architecture is effectively three partitions, but accessed through a unified tool interface.

**LangGraph — Single store with namespace scoping:**
Uses a single store implementation (InMemoryStore for dev, PostgreSQL+pgvector for production) with namespace-based organization. Memories are JSON documents organized hierarchically: `(org_id, user_id, memory_type)`. Single store, but logically partitioned via namespaces.

**ChatGPT — No vector database at all:**
Reverse engineering revealed ChatGPT uses NO vector database, no semantic RAG, no embeddings for retrieval. Instead, it uses a 4-layer pre-computed injection system:
1. Session metadata (temporary environment context)
2. Explicit facts (permanent, stored as short timestamped sentences)
3. Recent conversation summaries (lightweight notes from past chats)
4. Current session messages (sliding window)

All layers are injected directly into the prompt. No search step at retrieval time.

**AWS AgentCore — Namespace-partitioned with strategy routing:**
Uses namespaces where each memory strategy (semantic, summary, episodic) writes to its own configured namespace. Different strategies extract different types of information and store them in separate logical partitions.

### Unified Database Approach (PostgreSQL)

A growing pattern uses PostgreSQL as a single database for all memory types:
- Hypertables partition conversation history by time
- pgvector indexes enable semantic search
- Standard tables handle user preferences with ACID guarantees
- One connection constructs complete context windows spanning episodic, semantic, and procedural memory

This eliminates the need to manage separate vector databases, time-series stores, and relational systems.

### Tradeoff Analysis

| Approach | Latency | Complexity | Query Flexibility | Consistency | Best For |
|----------|---------|------------|-------------------|-------------|----------|
| **Single store + metadata** | Low (one hop) | Low | Limited by one engine | Strong (ACID) | MVP, sub-100M vectors |
| **Hybrid multi-store** (Mem0) | Higher (parallel writes) | High | Best (specialized engines) | Eventual | Rich query patterns, scale |
| **Single store + namespaces** (LangGraph) | Low | Low-Medium | Good (JSON + vector) | Strong | Namespace-heavy scoping |
| **Pre-computed injection** (ChatGPT) | Lowest (no search) | Low | None (fixed layers) | N/A | Consumer product, single-user |
| **Unified PostgreSQL** | Low-Medium | Medium | Good (SQL + vector) | Strong | Production, sub-100M scale |

**Key finding:** For personal/single-user systems at sub-100M scale, specialized vector databases add complexity without proportional benefit. Unified PostgreSQL or SQLite+Chroma handles the workload with lower operational burden.

**Implication for Memory Layer:** The existing KB pattern (SQLite + Chroma) is validated by the landscape. A single-store approach with metadata-based scoping (similar to LangGraph namespaces) is the right call for MVP. Mem0's multi-store approach is only justified at scale or when graph queries become critical.

---

## 3) Memory Entry Format

**Question:** Short atomic facts vs longer narrative summaries vs structured entries. What works best?

### What Each System Uses

**Mem0 — Atomic facts:**
The extraction module transforms conversations into "atomic facts" — short, self-contained statements. Each memory entry is a single fact with metadata:
- Fact: "User prefers TypeScript over JavaScript"
- Vector embedding of the fact
- Metadata: user_id, agent_id, timestamps, hash, category

Facts are designed to be composable — you retrieve multiple relevant facts and combine them in the prompt. Example memory updates show facts like "User likes to play cricket" being updated to "Loves to play cricket with friends" — still atomic, just refined.

**ChatGPT — Short timestamped sentences:**
Memories are stored as short, single-sentence entries with timestamps. Example: `[2025-04-10] User is allergic to shellfish`. Recent conversation summaries use a compact format: `<Timestamp>: <Chat Title> |||| user message snippet ||||`. Only user messages are summarized, not assistant responses.

**Letta — Structured blocks (core) + free-text (archival):**
Core memory uses structured blocks with labeled sections:
- `persona` block: Agent's own personality and behavior notes
- `human` block: Information about the user

These blocks are free-text but constrained by character limits (configurable). The agent rewrites entire blocks when information changes. Archival memory entries are longer free-text passages stored in a vector database — more narrative than atomic.

**LangGraph/LangMem — Two formats depending on memory type:**
- **Profiles:** JSON documents with key-value pairs following a strict schema. Updated by passing the previous profile to the LLM and requesting a new version. Best for well-scoped information about entities.
- **Collections:** Individual memory documents that are narrowly scoped, continuously extended over time. Each document is more atomic and easier to generate than updating a full profile.

The docs explicitly note the tradeoff: profiles are easier to look up but harder to update (must regenerate the whole document). Collections are easier to generate per-item but require search at retrieval time.

**AWS AgentCore — Strategy-dependent:**
- Semantic strategy: Stores extracted facts and knowledge (atomic)
- Summary strategy: Stores running session summaries (narrative)
- Episodic strategy: Stores complete interaction episodes (structured events)

### Format Tradeoffs

| Format | Retrieval Quality | Write Complexity | Composability | Context Efficiency | Staleness Risk |
|--------|-------------------|-----------------|---------------|-------------------|----------------|
| **Atomic facts** | High (precise matches) | Medium (extraction needed) | Excellent (mix and match) | Good (compact) | Low (easy to update one fact) |
| **Narrative summaries** | Medium (broad matches) | Low (summarize whole session) | Poor (hard to combine) | Poor (verbose) | High (whole summary may be stale) |
| **Structured profiles** | High (direct lookup) | High (regenerate entire profile) | Medium | Good | Medium (must regenerate on change) |
| **Hybrid (facts + summaries)** | Best of both | Highest | Good | Depends on mix | Low for facts, high for summaries |

### Key Research Finding

The "Memory in the Age of AI Agents" survey (Dec 2025) identifies three memory formation stages:
1. **Storage** — Trajectory preservation (raw logs)
2. **Reflection** — Trajectory refinement (extracting patterns)
3. **Experience** — Trajectory abstraction (generalizing insights)

Atomic facts correspond to the Reflection stage. Narrative summaries sit between Storage and Reflection. Structured profiles are at the Experience stage.

**Implication for Memory Layer:** Atomic facts for the primary memory store (matches Mem0 pattern, best retrieval quality, most composable). Session summaries as a secondary format for episodic/progress records. Structured profiles only if we need entity-level aggregation (defer to post-MVP). The LangMem insight is key: collections (atomic) for unbounded knowledge, profiles for well-scoped entity information.

---

## 4) Capture Mechanisms

**Question:** How do different systems capture memories? Event-driven vs agent-initiated vs hybrid.

### Pattern Taxonomy

**A) Agent-Initiated (Pull model)**
The agent explicitly decides to write a memory using tools during conversation.

- **Letta:** The agent calls `memory_replace`, `memory_insert`, `archival_memory_insert` when it judges information is worth preserving. The agent IS the capture mechanism. No external hooks.
- **LangMem (hot path):** Agent uses memory tools during graph execution to save notes in real-time.

**Pros:** Agent has full context for relevance judgment. No redundant captures.
**Cons:** Consumes reasoning bandwidth. Agent may miss important information. Quality depends on agent capability.

**B) Event-Driven (Push model)**
An external process monitors conversations and extracts memories automatically.

- **Mem0:** The `add()` API call triggers automatic extraction. The application (not the agent) decides when to send messages to Mem0 for processing. Mem0's extraction pipeline then runs independently.
- **ChatGPT:** Background classifiers continuously monitor conversation for salient facts. Extraction is invisible to both user and assistant.
- **AWS AgentCore:** `CreateEvent` API sends raw conversation events. An asynchronous pipeline handles extraction and consolidation in the background.

**Pros:** No reasoning bandwidth consumed. Consistent extraction quality. Works across any agent.
**Cons:** May extract irrelevant information. Latency between event and memory availability. Cost of running extraction LLM on all messages.

**C) Hybrid (Most Common in Practice)**

- **LangMem:** Explicitly supports both hot-path (agent-initiated) and background (event-driven via `ReflectionExecutor`). Background processing only runs after conversation inactivity.
- **Letta with sleep-time:** Primary agent self-edits during conversation. Optional sleep-time background process reviews and updates blocks asynchronously.
- **Mem0 in practice:** While Mem0 itself is event-driven, the calling application decides when to invoke `add()` — this could be after every message, at session end, or triggered by specific events. The trigger is hybrid even if Mem0's pipeline is push-based.

### Trigger Patterns in Production

| Trigger | When | Used By | Best For |
|---------|------|---------|----------|
| **Every message** | After each user/assistant exchange | Mem0 (default), ChatGPT | Maximum capture, higher cost |
| **Session end** | When conversation closes | LangMem background, many custom systems | Batch efficiency, lower cost |
| **Inactivity timeout** | After N seconds of silence | LangMem ReflectionExecutor | Long-running conversations |
| **Explicit command** | User says "remember this" | Letta `/remember`, Claude "save to memory" | High-signal, low-noise |
| **Milestone event** | Phase completion, decision made | ADF-style workflows | Structured capture points |
| **Agent judgment** | Agent decides in-context | Letta self-editing | Context-aware, but bandwidth-heavy |

### AWS AgentCore's Three Write-Back Strategies

AgentCore explicitly documents three approaches:
1. **Batch processing** — Process entire conversation after session ends
2. **Periodic intervals** — For long-running conversations, transfer at defined intervals
3. **Real-time updates** — For use cases requiring immediate memory availability

The choice depends on latency requirements vs. cost tradeoffs.

**Implication for Memory Layer:** A hybrid approach with two primary capture paths:
1. **Agent-initiated** via MCP tool calls (`add_memory`) — for explicit, high-signal captures during sessions
2. **Session-end extraction** — batch process session artifacts (status.md updates, decisions logged) into memories

Defer "every message" extraction to post-MVP (cost/complexity). The milestone-event trigger aligns naturally with ADF workflows (phase transitions, reviews completed, decisions made).

---

## 5) State-Based vs Retrieval-Based

**Question:** Pure vector retrieval vs entity/belief state tracking vs hybrid. What does each system do?

### Pure Retrieval-Based

**Vector similarity search only:**
- Query arrives, encode as embedding, find top-k similar memories, inject into prompt
- No persistent state representation of the user or world
- Every query starts fresh — relevance is computed at query time

**Who uses this:** Basic RAG implementations, simple memory stores, LangGraph's default BaseStore.

**Pros:** Simple. No state maintenance. Works for any query type.
**Cons:** No entity coherence. Contradictory facts can coexist. No way to say "what do we currently believe about X?" — only "what memories match this query?"

### State-Based (Entity/Belief Tracking)

**Letta's Core Memory:**
Core memory blocks ARE the state. The `human` block is a living document that represents the agent's current understanding of the user. When the agent learns something new, it rewrites the relevant section. Old information is overwritten, not accumulated.

This is a **belief state** — the system maintains a single, coherent representation that is always up-to-date. There is no retrieval step for core information; it is always in context.

**LangMem Profiles:**
Profiles serve a similar function — a JSON document that represents current state of an entity. When new information arrives, the entire profile is regenerated by passing the old profile + new information to an LLM. The profile IS the state.

**ChatGPT's Saved Memories:**
The explicit facts store is essentially a flat belief state. Each fact represents a current belief about the user. When beliefs change (new allergy discovered), old facts are updated or removed. The full set of current beliefs is injected into every prompt — no retrieval needed.

### Hybrid (State + Retrieval)

**Mem0:**
Mem0 operates primarily as a retrieval system (vector search + graph traversal) but incorporates state-like properties through its consolidation mechanism. The UPDATE and DELETE operations in the curation pipeline ensure that the memory store converges toward a coherent representation over time. However, there is no single "current state" document — the state is the aggregate of all non-contradicted memories.

Mem0's graph memory adds entity-level structure: nodes represent entities, edges represent relationships. You can query "what do we know about entity X?" by traversing the graph — this is closer to state tracking than pure vector retrieval.

**Mem0 retrieval methods:**
1. Entity-based retrieval — Identify key entities in the query, then use semantic similarity to locate corresponding graph nodes
2. Relation-group retrieval — Encode the full query as a dense vector and match against knowledge graph embeddings

**AWS AgentCore:**
The semantic strategy extracts facts (retrieval-based), while the summary strategy maintains a running session summary (state-based). Different strategies can coexist for the same agent.

### Comparison

| Approach | Coherence | Query Flexibility | Maintenance Cost | Context Efficiency | Staleness Handling |
|----------|-----------|-------------------|-----------------|--------------------|--------------------|
| **Pure retrieval** | Low (contradictions possible) | High (any query) | Low | Variable (depends on k) | Poor (old memories persist) |
| **Pure state** (Letta core, ChatGPT facts) | High (single truth) | Low (fixed structure) | High (must update on every change) | Excellent (always loaded) | Good (overwritten on change) |
| **Hybrid** (Mem0, AgentCore) | Medium-High | High | Medium | Good | Good (consolidation handles it) |

### Key Insight from Letta

Letta's architecture makes the clearest distinction:
- **Core memory** (state) = Always in context, always coherent, agent-editable. Small and focused.
- **Archival memory** (retrieval) = Large, searchable, vector-backed. For overflow and deep history.
- **Recall memory** (retrieval) = Conversation history, searchable by date or content.

The state layer (core) handles the "what do we currently believe?" question. The retrieval layer (archival + recall) handles "what do we know about this topic?" — which may include historical/superseded information.

**Implication for Memory Layer:** A hybrid approach is the clear winner:
- **State component:** Per-entity profiles or summary blocks that represent current understanding (e.g., "current user preferences," "current project status"). Always injected, no retrieval needed. Similar to Letta's core memory or LangMem profiles.
- **Retrieval component:** The broader memory store with semantic search for on-demand queries. Similar to Letta's archival or Mem0's vector store.

For MVP, start with retrieval-only (vector search over atomic facts). Add state profiles when specific entities need coherent current-state representations. The retrieval store can be the source of truth that feeds periodic state profile regeneration.

---

## 6) Write-Back Patterns

**Question:** Real-time capture vs session-end summaries vs batch processing. What paths exist?

### Real-Time (Synchronous)

**How it works:** Memory is written during the conversation, in the hot path.

- **Letta:** Agent calls memory tools during conversation. Memory updates are synchronous — they happen as part of the agent's turn.
- **LangMem hot path:** Agent writes to LangGraph store during graph execution.
- **Mem0 (default usage):** `add()` is typically called after each message exchange. The extraction + update pipeline runs synchronously (or near-synchronously) before the next turn.

**Tradeoffs:**
- (+) Memory is immediately available for subsequent turns
- (+) Captures context while it is fresh
- (-) Adds latency to each turn (Mem0 extraction takes LLM calls)
- (-) Consumes reasoning bandwidth (Letta)
- (-) May capture noise from intermediate/exploratory conversation

### Session-End Summary (Deferred)

**How it works:** After a conversation ends or goes idle, a process summarizes the session and writes relevant memories.

- **LangMem background:** `ReflectionExecutor` runs after inactivity timeout. Processes the entire conversation transcript, extracts patterns and insights, writes to store.
- **ChatGPT recent summaries:** Lightweight summaries of recent chats are pre-computed and stored in a compact format (`Timestamp: Title |||| snippet`).
- **AWS AgentCore (batch strategy):** Process the entire conversation after session ends.

**Tradeoffs:**
- (+) No latency impact during conversation
- (+) Full session context available for better extraction
- (+) More cost-efficient (one extraction pass vs. per-message)
- (-) Memories not available until session ends
- (-) May lose nuance from early conversation by the time extraction runs
- (-) Requires session boundary detection

### Periodic Intervals

**How it works:** For long-running conversations, memory is written at defined intervals.

- **AWS AgentCore (periodic strategy):** Transfer session data to long-term memory at configured intervals
- **Letta sleep-time:** Background agent periodically reviews and updates blocks

**Tradeoffs:**
- (+) Balances freshness and efficiency
- (+) Works for conversations without clear end boundaries
- (-) Requires interval tuning
- (-) May split related information across extraction windows

### Async Background Processing

**How it works:** Write events are queued, and extraction/consolidation runs asynchronously.

- **AWS AgentCore:** Long-term memory generation is explicitly async. `CreateEvent` stores raw data; extraction and consolidation run in background pipelines.
- **Mem0 (async mode):** v1.0.0 shipped async-by-default behavior, allowing non-blocking memory writes.

**Tradeoffs:**
- (+) No blocking of the main conversation flow
- (+) Can batch multiple events for efficiency
- (-) Delay between event and memory availability
- (-) Application must handle "memory not yet available" gracefully

### Production Pattern Summary

| Pattern | Latency Impact | Memory Freshness | Cost | Complexity | Best For |
|---------|---------------|-----------------|------|------------|----------|
| **Real-time sync** | High | Immediate | High (per-turn LLM) | Medium | Single-agent, critical memories |
| **Session-end batch** | None | After session | Low (one pass) | Low | Most use cases |
| **Periodic interval** | None | Periodic | Medium | Medium | Long-running sessions |
| **Async background** | None | Delayed | Medium | High (queue infra) | Production multi-user |
| **Hybrid (real-time + batch)** | Low (selective) | Mixed | Medium | Medium-High | Best coverage |

### What ChatGPT Actually Does

The reverse-engineered architecture reveals ChatGPT does NOT do per-message extraction to a database. Instead:
- Saved memories (explicit facts) are extracted during conversation and stored immediately
- Recent conversation summaries are pre-computed asynchronously after sessions
- Both are injected directly into the prompt — no search step at retrieval time

This is essentially a hybrid: real-time for explicit fact capture, async batch for conversation summaries. The key insight is that retrieval is eliminated by pre-computing and injecting everything.

**Implication for Memory Layer:** For MVP, two write-back paths:
1. **Explicit write** (real-time): Agent calls `add_memory` MCP tool during session for high-signal captures. Synchronous, immediately available.
2. **Session-end extraction** (deferred): Process session artifacts (status.md diffs, completed tasks, logged decisions) into memories after session close. Lower cost, higher quality extraction with full session context.

Defer periodic intervals and async queuing to post-MVP. The explicit + session-end hybrid covers the primary use cases without infrastructure complexity.

---

## Cross-Cutting Findings

### Emerging Consensus Across Systems

1. **LLM-powered extraction is standard.** Every production system uses LLMs for memory extraction and curation decisions. Rule-based extraction is insufficient for the nuance required.

2. **Atomic facts win for retrieval.** Mem0, ChatGPT, and LangMem all converge on short, self-contained facts as the primary memory unit. Narrative summaries are used as a secondary format for session logs, not primary retrieval targets.

3. **No production system uses pure state OR pure retrieval.** Every real system is hybrid — some form of current-state representation (Letta core blocks, ChatGPT saved facts, LangMem profiles) combined with a searchable archive.

4. **Curation at write-time dominates.** Mem0's ADD/UPDATE/DELETE/NOOP pattern, Letta's self-editing, ChatGPT's background classifiers — all handle curation when memories are created, not as a separate batch job. LangMem's background reflection is the exception, offering deferred consolidation.

5. **The ChatGPT surprise: no vector DB.** OpenAI proved that for single-user scenarios, pre-computed injection (loading all relevant context into the prompt) can outperform retrieval-based approaches. This is viable when the memory store is small enough to fit in context.

6. **Single store is sufficient at personal scale.** No personal-scale system uses Mem0's multi-store architecture. PostgreSQL+pgvector or SQLite+Chroma handles the workload. Multi-store adds complexity justified only at production SaaS scale.

### Mapping to Memory Layer Design Decisions

| Open Question | Research Finding | Recommended Direction |
|--------------|-----------------|----------------------|
| Curation workflow | LLM-as-judge (Mem0 pattern) is most practical for multi-writer | Adopt ADD/UPDATE/DELETE/NOOP at write-time |
| Store architecture | Single store + namespaces at personal scale | SQLite + Chroma with namespace metadata (existing KB pattern) |
| Memory entry format | Atomic facts for primary store, summaries for session logs | Atomic facts primary; session summaries secondary |
| Capture mechanism | Hybrid: agent-initiated + event-driven | MCP tool for explicit writes + session-end extraction |
| State vs retrieval | Hybrid wins everywhere | Retrieval-first MVP; add state profiles when needed |
| Write-back pattern | Explicit real-time + session-end batch | Two-path: sync MCP writes + deferred session extraction |

---

## Sources

### Primary (Papers and Documentation)

- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory (arXiv)](https://arxiv.org/abs/2504.19413)
- [Mem0 Documentation](https://docs.mem0.ai/platform/overview)
- [Mem0 Architecture Analysis (Medium)](https://medium.com/@zeng.m.c22381/mem0-overall-architecture-and-principles-8edab6bc6dc4)
- [Letta MemGPT Documentation](https://docs.letta.com/concepts/memgpt/)
- [Letta Memory Overview](https://docs.letta.com/guides/agents/memory/)
- [Letta Memory Management (Advanced)](https://docs.letta.com/advanced/memory-management/)
- [Letta Memory Blocks Blog](https://www.letta.com/blog/memory-blocks)
- [LangMem Conceptual Guide](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/)
- [LangMem SDK Launch Blog](https://blog.langchain.com/langmem-sdk-launch/)
- [LangGraph Memory Overview](https://docs.langchain.com/oss/python/langgraph/memory)
- [Memory as Action: Autonomous Context Curation (arXiv)](https://arxiv.org/abs/2510.12635)
- [Memory in the Age of AI Agents: A Survey (arXiv)](https://arxiv.org/abs/2512.13564)
- [Claude Memory Tool (Anthropic)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- [Claude Code Memory Docs](https://docs.anthropic.com/en/docs/claude-code/memory)
- [OpenAI Memory Controls](https://openai.com/index/memory-and-new-controls-for-chatgpt/)
- [AWS AgentCore Memory Strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-strategies.html)
- [AWS AgentCore Memory Types](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-types.html)

### Reverse Engineering and Analysis

- [ChatGPT Memory Reverse Engineered (Manthan)](https://manthanguptaa.in/posts/chatgpt_memory/)
- [How ChatGPT Memory Works (LLMRefs)](https://llmrefs.com/blog/reverse-engineering-chatgpt-memory)
- [Demystifying Mem0 Architecture (Medium)](https://medium.com/@parthshr370/from-chat-history-to-ai-memory-a-better-way-to-build-intelligent-agents-f30116b0c124)
- [Mem0 & Mem0-Graph Breakdown](https://memo.d.foundation/breakdown/mem0)

### Production Architecture

- [Redis: AI Agent Memory Stateful Systems](https://redis.io/blog/ai-agent-memory-stateful-systems/)
- [MongoDB: Powering Long-Term Memory for LangGraph Agents](https://www.mongodb.com/company/blog/product-release-announcements/powering-long-term-memory-for-agents-langgraph)
- [Tiger Data: Building AI Agents with Persistent Memory (Unified PostgreSQL)](https://www.tigerdata.com/learn/building-ai-agents-with-persistent-memory-a-unified-database-approach)
- [AWS: Building Persistent Memory with Mem0 Open Source](https://aws.amazon.com/blogs/database/build-persistent-memory-for-agentic-ai-applications-with-mem0-open-source-amazon-elasticache-for-valkey-and-amazon-neptune-analytics/)
