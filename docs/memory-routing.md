# Memory Routing Heuristic

> POST-01 deliverable — defines when agents should use Memory Layer MCP vs client-local memory.

## The Problem

Multiple memory systems coexist in the agent ecosystem:

1. **Client-local memory** — each CLI agent has its own local persistence (Claude Code's `MEMORY.md`, Gemini's `GEMINI.md`, Codex's session transcripts)
2. **Memory Layer MCP** — shared, structured, searchable memory accessible to any MCP-connected agent
3. **Project files** — `status.md`, `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`, backlog, docs

Without a routing rule, agents duplicate facts across systems, or worse, write to the wrong one and the knowledge becomes invisible to other agents.

## Core Routing Rule

> **Does this knowledge matter beyond the current project and current client?**
>
> - **Yes** → Memory Layer MCP (`write_memory`)
> - **No** → Client-local memory or project files

## Decision Table

| What you learned | Where it goes | Why |
|-----------------|---------------|-----|
| Project-specific pattern (e.g., "this repo uses pnpm") | Project instructions file (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`) | Only relevant inside this project; loaded automatically every session |
| User preference (e.g., "user prefers bullets over paragraphs") | Client-local memory OR Memory MCP | If the preference applies across all projects → MCP. If only relevant to one client → local. |
| Cross-project learning (e.g., "ADF Deliver phase can be collapsed for small projects") | Memory Layer MCP | Valuable to any agent in any project |
| Debugging insight (e.g., "FastMCP returns `content[0].text`, not `.result`") | Memory Layer MCP | Reusable across projects and clients |
| Architectural decision (e.g., "chose SQLite over Postgres for local-first") | Project docs (`design.md`, `ADR/`) | Project-scoped, versioned with code |
| Session state (e.g., "completed steps 1-3, next is step 4") | `status.md` | Ephemeral session tracking, not memory |
| Task status | `backlog.md` / task tracker | Operational state, not memory |
| Reusable technique (e.g., "use `uv run` for MCP stdio transport") | Memory Layer MCP | Cross-project utility |
| Relationship between projects (e.g., "Krypton depends on Memory Layer and KB") | Memory Layer MCP | Ecosystem-level knowledge |
| Client-specific workflow (e.g., "Claude Code hook X does Y") | Client-local memory | Only useful to that client |

## The Litmus Tests

When unsure, ask these in order:

1. **Would another project's agent benefit from knowing this?** → MCP memory
2. **Would a different client (Codex, Gemini, Claude) benefit?** → MCP memory
3. **Is this a project-local convention or config?** → Project instructions file
4. **Is this operational state (what's done, what's next)?** → `status.md` / backlog
5. **Is this only useful inside one client's workflow?** → Client-local memory

## Client-Specific Guidance

### Claude Code

| System | What | Scope | Auto-loaded? |
|--------|------|-------|-------------|
| `CLAUDE.md` (project) | Project conventions, commands, architecture | Project | Yes — every session |
| `~/.claude/CLAUDE.md` (global) | Cross-project agent protocols | All Claude sessions | Yes — every session |
| Auto-memory (`MEMORY.md`) | Session-discovered patterns for this project | Project | Yes — injected into system prompt |
| Memory Layer MCP | Cross-project knowledge, ecosystem facts, reusable learnings | All agents, all projects | No — must be explicitly queried |

**Claude-specific rule:** Don't duplicate into auto-memory (`MEMORY.md`) what belongs in Memory MCP. Auto-memory is for project-scoped patterns that only matter inside Claude Code sessions for *this project*. If it crosses project boundaries, use MCP.

### Codex CLI

| System | What | Scope | Auto-loaded? |
|--------|------|-------|-------------|
| `AGENTS.md` (project) | Project conventions, instructions | Project | Yes — every session |
| `~/.codex/AGENTS.md` (global) | Cross-project agent instructions | All Codex sessions | Yes — every session |
| `AGENTS.override.md` | Per-level overrides (global or project) | Varies | Yes — takes priority over `AGENTS.md` at same level |
| Session transcripts | Resumable conversation history | Session | Only on `codex resume` |
| Memory Layer MCP | Cross-project knowledge | All agents, all projects | No — must be explicitly queried |

**Codex-specific rule:** Codex has no persistent cross-project *memory* of its own — only instructions files and session transcripts. The Memory Layer MCP fills this gap entirely. Any learning that should survive beyond a single session transcript belongs in MCP memory.

### Gemini CLI

| System | What | Scope | Auto-loaded? |
|--------|------|-------|-------------|
| `GEMINI.md` (project) | Project conventions, instructions | Project | Yes — every session |
| `~/.gemini/GEMINI.md` (global) | Cross-project instructions | All Gemini sessions | Yes — every session |
| `/memory add` | Appends to global `GEMINI.md` | All Gemini sessions | Yes (via global file) |
| Memory Layer MCP | Cross-project knowledge | All agents, all projects | No — must be explicitly queried |

**Gemini-specific rule:** `/memory add` writes to Gemini's *own* global file — invisible to Claude and Codex. Use it only for Gemini-specific workflow instructions. Cross-agent knowledge goes to MCP memory.

## Memory MCP vs Knowledge Base

The Memory Layer and Knowledge Base are both cross-project MCP services, but they serve different purposes:

| Dimension | Memory Layer MCP | Knowledge Base MCP |
|-----------|-----------------|-------------------|
| **What** | Atomic facts, observations, decisions, preferences | Reference articles, research, curated knowledge |
| **Granularity** | Single insight (1-3 sentences) | Structured document (paragraphs, sections) |
| **Lifecycle** | Write-and-forget; agents query when needed | Curated — topics, completeness tracking, publication pipeline |
| **Write trigger** | Agent discovers something worth remembering | Agent completes research, synthesis, or deep analysis |
| **Examples** | "FastMCP returns `content[0].text`", "user prefers bun over npm" | "Comparison of 7 memory systems", "ADF stage transition patterns" |

**The routing test:** If it's a single fact or observation → Memory. If it's structured knowledge that benefits from topics, completeness tracking, or curation → KB.

When in doubt, start with Memory. Facts can be promoted to KB later when enough related memories accumulate on a topic.

## What Memory Layer MCP Is NOT For

- **Session state** — use `status.md` (gets overwritten each session)
- **Task tracking** — use `backlog.md` or task tools
- **Project configuration** — use project-level instructions files
- **Secrets/credentials** — never store these anywhere agents can read
- **Large documents** — memory stores atomic facts, not full docs (use KB for these)

## Integration with Session Protocol

At **session start**, agents MUST:
1. Read project `status.md` (current state)
2. Call `search_memories` or `get_session_context` for relevant cross-project context — this surfaces learnings from other projects and prior sessions that may inform the current task

At **session end**, agents MUST:
1. Update `status.md` (operational state)
2. Call `write_memory` for any cross-project learnings discovered during the session — even if only one fact was learned, capture it
3. Update project instructions file if a new project-local pattern was established

Consistent usage is essential for tuning and improving the memory system. Under-capture now means missed signal later.

### Delegation via Krypton

Agents that are unsure whether something belongs in Memory, KB, or elsewhere can delegate the routing decision to Krypton's `/capture` command. Krypton analyzes the content and routes it to the appropriate system automatically. This is optional — agents can always route directly using the heuristics above.

## Namespace Conventions

| Namespace | Used for | Example |
|-----------|----------|---------|
| `global` | Knowledge useful across all projects | "ADF Deliver phase can collapse for small projects" |
| `project-<name>` | Project-specific memories that benefit from search/structure | "memory-layer uses 0.92 dedup threshold" |
| Private namespaces | Sensitive or experimental | Per client-profile policy |

**Default to `global`** unless the memory is clearly project-scoped. The dedup engine (0.92 similarity threshold) prevents accidental duplication within the MCP store.
