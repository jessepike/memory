# Memory Layer â€” Research Synthesis
**Date:** 2026-02-05
**Purpose:** Landscape scan of agent memory architectures to inform Krypton Tier 2 memory layer design
**Status:** Research complete, design decisions pending

---

## 1) Context

Krypton's 3-layer architecture requires a persistent memory system (the "Tier 2" layer) that sits alongside the KB (reference knowledge) and Work OS (operational state). This layer needs to:

- Support **multiple writers** (ADF agents, Krypton, manual input, "save to memory" commands)
- Support **scoped access** (dev pipeline memory vs. personal assistant memory vs. private memory)
- Be **independent** â€” its own project, own MCP server, own API surface (like KB)
- Complement, not duplicate, KB (reference knowledge) or Work OS (operational state)

**Tier 1 (Context Loading)** already exists via ADF project files (CLAUDE.md, status.md, tasks.md) read on agent session start. Tier 2 extends beyond project-local, file-based state into persistent, queryable, cross-context memory.

---

## 2) Landscape: Four Design Paradigms

The current landscape clusters around four distinct approaches to agent memory. Each makes different trade-offs relevant to our design.

### A) The OS Paradigm â€” MemGPT / Letta

**Core idea:** Treat LLM context as RAM, persistent storage as disk. The agent manages its own memory via explicit paging operations (search, store, delete).

**Architecture:**
- Primary context (fast, limited) = current prompt window
- Recall storage (searchable logs) = full interaction history
- Archival storage (vector-based) = long-term semantic memory
- Agent autonomously pages data between tiers via function calls

**Strengths:** Elegant abstraction. Agent decides what to remember/forget. Creates illusion of infinite context.

**Weaknesses:** Single agent manages all memory operations â€” consumes reasoning bandwidth. Unstructured storage makes relational queries difficult. No native multi-agent or scoping support.

**Relevance to us:** The paging metaphor is useful for thinking about how Krypton loads context from memory into its active reasoning. But the "agent manages its own memory" pattern won't work for multi-writer scenarios â€” we need an external system, not self-managed context.

### B) Product-First â€” OpenAI Memory / Claude Memory

**Core idea:** Memory as a product feature for personalization. Global (OpenAI) or project-scoped (Claude) fact extraction.

**Architecture (OpenAI):**
- Saved memories = curated fact store, prepended to every prompt
- Chat history reference = RAG over all past conversations
- Automatic extraction = background classifiers identify salient facts
- User can view/edit/delete

**Architecture (Claude):**
- Project memory = editable summary per project, injected into project chats
- CLAUDE.md = file-based context injection (versioned, Git-managed)
- Conversation search = project-scoped keyword/semantic search
- Mostly user-curated, not auto-extracted

**Strengths:** Simple mental model. User control. Immediate personalization value.

**Weaknesses:** Not designed for multi-agent writing. No programmatic API for agent-driven memory operations. Limited scoping (global or per-project, nothing in between). Memory as flat facts, not structured/relational.

**Relevance to us:** Claude's project-scoped model and CLAUDE.md pattern are essentially what we already have as Tier 1. The Tier 2 system needs to go beyond this â€” programmable, multi-writer, with richer scoping than "per project."

### C) Memory-as-a-Service â€” Mem0

**Core idea:** Standalone memory layer that any agent can plug into. Extraction, consolidation, and retrieval handled by the service.

**Architecture:**
- Unified API: `add()`, `search()`, `update()`, `delete()`
- Three scoping dimensions: `user_id`, `agent_id`, `run_id` (combinable for hierarchical scoping)
- Extraction phase: LLM processes messages â†’ extracts structured facts
- Update phase: compares new facts against existing â†’ add/update/delete operations
- Storage: vector store + optional graph memory for relational queries
- Memory consolidation: deduplication, conflict resolution, decay

**Key features:**
- Memory categories (auto-classified)
- Metadata filters and per-request toggles
- Graph memory variant captures entity relationships (multi-hop reasoning)
- Quality scoring on memories
- History/audit trail on memory changes
- Framework integrations (LangChain, LangGraph, CrewAI, AutoGen, etc.)

**Strengths:** Purpose-built for multi-agent scenarios. Clean scoping model. Handles extraction/consolidation automatically. Open source (Apache 2.0) with self-hosted option. Production-proven (raised $24M, Oct 2025).

**Weaknesses:** Requires LLM calls for extraction (cost/latency). Graph memory only on paid tier. Opinionated about extraction â€” may not match all use cases. Designed for SaaS, self-hosting adds operational burden.

**Relevance to us:** **Highest relevance.** Mem0's scoping model (`user_id` + `agent_id` + `run_id`) maps well to our needs. The extraction + consolidation pipeline is a pattern worth adopting. The open-source self-hosted option aligns with local-first principles. Could use as a reference architecture even if we build custom.

### D) Framework Primitives â€” LangGraph / LangChain / AutoGen

**Core idea:** Provide building blocks (stores, checkpointers, reducers) for developers to compose their own memory systems.

**Architecture (LangGraph):**
- Short-term memory = thread-scoped state, persisted via checkpointers
- Long-term memory = stores with custom namespaces (`org_id`, `user_id`, custom keys)
- Namespaces are hierarchical and arbitrary â€” you define the scoping
- Checkpointers handle state persistence (SQLite, Postgres, MongoDB)
- No built-in extraction â€” you design the write-back loop yourself

**Key patterns:**
- Memory as explicit graph state (reducers merge updates deterministically)
- Namespace-scoped stores for cross-thread persistence
- Session vs. global separation
- Agent can read/write stores as tool calls during graph execution

**Strengths:** Maximum flexibility. Namespace model handles any scoping pattern. Production-grade persistence (Postgres, MongoDB). Integrates with any extraction strategy.

**Weaknesses:** No opinions = you build everything. No extraction, no consolidation, no decay â€” all DIY. Higher engineering effort.

**Relevance to us:** LangGraph's namespace concept is architecturally clean and maps well to our multi-scope needs. If we build custom (rather than adopting Mem0), LangGraph's store pattern is the closest conceptual match to what we need.

---

## 3) Key Patterns Across the Landscape

### Memory Types (Cognitive Model)

Most systems recognize multiple memory types that serve different functions:

| Type | Function | Example | Persistence |
|------|----------|---------|-------------|
| **Episodic** | Specific events/experiences | "Last Tuesday's deploy failed because of auth timeout" | Decays over time |
| **Semantic** | Facts and knowledge | "Jess prefers concise updates" | Long-lived, updateable |
| **Procedural** | How-to / workflow patterns | "When deploying, always run smoke tests first" | Stable until revised |
| **Working** | Current task context | Active conversation state | Session-scoped |

Our Tier 2 system primarily needs **semantic** (facts, preferences, relationships) and **episodic** (session summaries, project progress, decisions made) memory. Procedural memory likely lives in KB or ADF specs. Working memory is Tier 1.

### Scoping Models

| System | Scoping | Granularity |
|--------|---------|-------------|
| OpenAI | Global (all chats) | User-level only |
| Claude | Per-project | Project-level |
| Mem0 | user_id Ã— agent_id Ã— run_id | Combinable dimensions |
| LangGraph | Custom namespaces | Arbitrary hierarchical |
| CLAUDE.md | Per-repo/project | File-level |

**Our need:** Multiple scoping dimensions â€” at minimum: project scope, agent scope, privacy scope. Likely a namespace model similar to LangGraph or Mem0's dimensional approach.

### Multi-Writer Patterns

The SIGARCH paper (Jan 2026) identifies the core tension: **shared pool vs. distributed memory.**

- **Shared pool:** All agents read/write same store. Simple but requires coherence management (race conditions, stale reads, conflicting writes).
- **Distributed:** Each agent owns local memory, shares via sync. Better isolation but requires explicit synchronization.
- **Hybrid (most common):** Local working memory + selectively shared artifacts. This is where most production systems land.

**Our need:** Hybrid. ADF agents write project-scoped memory (local). Krypton reads across all scopes (shared). Manual entries go to appropriate scope. The system needs to handle concurrent writes gracefully but doesn't need real-time consistency (eventual consistency is fine).

### Memory Lifecycle

| Phase | What happens | Who does it |
|-------|-------------|-------------|
| **Capture** | Raw input arrives (conversation, event, manual entry) | Any writer |
| **Extract** | Structured facts/observations pulled from raw input | LLM or rule-based |
| **Consolidate** | New facts compared against existing â†’ add/update/delete | LLM or deterministic |
| **Store** | Persisted to appropriate scope with metadata | System |
| **Retrieve** | Queried by semantic search, filters, or direct lookup | Any reader |
| **Decay** | Low-relevance items deprioritized or pruned over time | System (scheduled) |

### The KB/Memory Boundary

Based on research, the clearest distinction:

| Dimension | KB (Reference Knowledge) | Memory (Contextual Knowledge) |
|-----------|------------------------|------------------------------|
| **About** | The world, domains, frameworks | You, your work, your patterns |
| **Stability** | Relatively stable | Evolves with context |
| **Source** | External content, research, learning | Internal observations, preferences, history |
| **Scope** | Universal (true regardless of who reads it) | Scoped (true relative to a person, project, moment) |
| **Decay** | Rarely (content stays relevant) | Often (observations become stale) |
| **Example** | "Progressive autonomy models escalate trust incrementally" | "We chose progressive autonomy for Krypton because of Jess's security background" |
| **Example** | "NIST AI RMF has 4 core functions" | "Jess tends to context-switch away from blocked items" |

**Gray area:** "Jess learned that progressive autonomy works well" â€” this is a *learning* (KB) that's also *personal context* (memory). The practical answer: put the reusable knowledge in KB, put the personal context in memory. Some things may exist in both, and that's okay.

---

## 4) Architecture Recommendations for Tier 2

### Recommended Approach: Custom Build, Mem0-Inspired

**Why not adopt Mem0 directly:**
- Mem0 is optimized for SaaS/multi-tenant. We need local-first, single-user.
- Mem0's extraction pipeline is opinionated. We need flexibility for different writer types (ADF agents write structured data; manual entries are freeform; Krypton writes observations).
- We already have KB infrastructure (SQLite + Chroma + MCP) that proves the pattern works.

**Why not LangGraph stores directly:**
- Too low-level. We'd build the entire extraction/consolidation/decay layer ourselves.
- Our system needs to be framework-agnostic (not tied to LangGraph).

**Recommended:** Build an independent memory service following KB's proven architecture (SQLite + Chroma + MCP), incorporating Mem0's scoping model and lifecycle patterns.

### Proposed Architecture

```
Memory System (independent project, like KB)
â”œâ”€â”€ Storage: SQLite (structured metadata) + Chroma (vector search)
â”œâ”€â”€ API: MCP server (primary) + REST (future)
â”œâ”€â”€ Scoping: namespace-based (project, agent, privacy level)
â”œâ”€â”€ Writers: any agent via MCP tools (add_memory, update_memory)
â”œâ”€â”€ Readers: any agent via MCP tools (search_memory, get_memories)
â”œâ”€â”€ Extraction: configurable per-writer (LLM-based or structured passthrough)
â””â”€â”€ Lifecycle: consolidation, decay, manual curation
```

### Scoping Model (Namespace-Based)

Each memory entry has scoping metadata:

| Dimension | Values | Purpose |
|-----------|--------|---------|
| **scope** | `project:{id}`, `global`, `private` | What context this memory belongs to |
| **writer_type** | `agent`, `human`, `system` | Who wrote it |
| **writer_id** | `krypton`, `claude-code`, `jess`, etc. | Specific writer |
| **memory_type** | `observation`, `preference`, `decision`, `progress`, `relationship` | What kind of memory |
| **visibility** | `public`, `restricted`, `private` | Who can read it |

**Access patterns:**
- ADF agent in project X â†’ reads `scope:project:X` + `scope:global` (not other projects, not private)
- Krypton â†’ reads all scopes except `visibility:private` (unless explicitly granted)
- Jess (manual query) â†’ reads everything
- Private scope â†’ only Jess, never agents

### Tier 1 â†’ Tier 2 Bridge

**Graduation pattern:** When an ADF project completes a phase or reaches a milestone, key decisions and learnings can be promoted to Tier 2:

- **Automatic candidates:** Decisions logged in status.md, completed phase summaries, key blockers resolved
- **Manual trigger:** "Save to memory" command during or after a session
- **Extraction:** LLM summarizes project artifacts into memory entries scoped to that project

This is a design decision that needs prototyping â€” start manual, automate later.

---

## 5) Open Design Questions

| # | Question | Options | Notes |
|---|----------|---------|-------|
| 1 | Storage engine | SQLite + Chroma (KB pattern) vs. Postgres + pgvector vs. Mem0 self-hosted | KB pattern proven and consistent |
| 2 | Extraction strategy | LLM-based (like Mem0) vs. structured passthrough vs. hybrid per-writer | Different writers need different extraction |
| 3 | Consolidation approach | LLM dedup/merge vs. manual curation vs. both | Start manual, add LLM consolidation later? |
| 4 | Decay model | Time-based vs. access-frequency vs. explicit archival vs. none initially | Can defer â€” start without decay, add when volume demands |
| 5 | MCP tool surface | Mirror KB tools? Separate design? How many tools? | KB has 16 tools â€” memory may need fewer initially |
| 6 | Tier 1 â†’ Tier 2 bridge | Auto-promote vs. manual "save to memory" vs. both | Start manual, instrument for automation later |
| 7 | Graph memory | Flat entries + vector search vs. knowledge graph for relationships | Flat for MVP, graph if relational queries prove necessary |
| 8 | Memory size/format | Short facts (Mem0-style) vs. longer summaries vs. both | Short facts are more composable; summaries for session logs |
| 9 | Cross-scope queries | Allow queries across scopes or strict isolation? | Krypton needs cross-scope; ADF agents need isolation |
| 10 | Conflict resolution | Last-write-wins vs. versioned vs. manual | Last-write-wins for MVP; version history as audit trail |

---

## 6) Recommended Next Steps

1. **Design the memory schema** â€” Entity model, scoping fields, metadata. Follow KB's pattern (source â†’ extraction â†’ chunk) but adapted for memory semantics.
2. **Define MCP tool surface** â€” What tools do memory writers and readers need? Start minimal.
3. **Prototype with 2-3 use cases:**
   - ADF agent writing project progress memories
   - Manual "save to memory" from a Claude session
   - Krypton reading cross-project memories for digest commentary
4. **Build MVP** â€” SQLite + Chroma + MCP server, following KB project structure.
5. **Test Tier 1 â†’ Tier 2 bridge** â€” Manual promotion first, then evaluate automation.

---

## 7) Sources

- [Serokell: Design Patterns for Long-Term Memory in LLM-Powered Architectures](https://serokell.io/blog/design-patterns-for-long-term-memory-in-llm-powered-architectures) (Dec 2025)
- [SIGARCH: Multi-Agent Memory from a Computer Architecture Perspective](https://www.sigarch.org/multi-agent-memory-from-a-computer-architecture-perspective-visions-and-challenges-ahead/) (Jan 2026)
- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413) (Apr 2025)
- [Memoria: A Scalable Agentic Memory Framework for Personalized Conversational AI](https://arxiv.org/abs/2512.12686) (Dec 2025)
- [Memory in the Age of AI Agents: A Survey](https://github.com/Shichun-Liu/Agent-Memory-Paper-List) (Dec 2025, updated Jan 2026)
- [LangGraph Memory Documentation](https://docs.langchain.com/oss/python/langgraph/memory)
- [Mem0 Documentation and GitHub](https://docs.mem0.ai/platform/overview)
- [The New Stack: Memory for AI Agents â€” A New Paradigm of Context Engineering](https://thenewstack.io/memory-for-ai-agents-a-new-paradigm-of-context-engineering/) (Jan 2026)
