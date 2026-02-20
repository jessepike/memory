# Memory Capture Problem

> Generated: 2026-02-19. Covers the core adoption/enforcement gap: agents don't reliably write to the Memory Layer, and there's no mechanism to make them.

---

## The Core Problem

The Memory Layer MCP is built on a flawed assumption: **that agents will remember to use it.**

Claude's auto-memory works because it's **passive** — zero agent action required, zero routing decision, zero friction. It just happens. Our Memory Layer MCP requires the agent to:

1. Notice that something worth remembering just happened
2. Decide it crosses project/client boundaries (not just local)
3. Choose the right namespace
4. Choose the right memory_type
5. Actually call `write_memory` before the session ends

That's a 5-step decision made under time pressure, at session end, after the agent's focus has already shifted to wrapping up. **It gets skipped.** Not sometimes — reliably.

The ADF session protocol in CLAUDE.md says "MUST call write_memory at session end." But a MUST in a markdown file is not enforcement. It's aspiration. The ACK prototype had the same approach and worked inconsistently — that's why they built hooks, and the hooks captured too much noise.

---

## Auto-Memory vs Memory Layer MCP

| Dimension | Claude Auto-Memory | Memory Layer MCP |
|-----------|-------------------|-----------------|
| Trigger | Passive — happens automatically | Active — agent must call write_memory |
| Scope | Project-scoped, Claude Code only | Cross-project, all agents |
| Routing decision required | No | Yes (namespace, type, cross-project?) |
| Friction | Zero | High (5+ decisions per write) |
| Reliability | Consistent | Inconsistent |
| Coverage | Everything Claude observes | Only what agent explicitly captures |

The problem is asking agents to make a real-time routing decision: *"Is what I just learned cross-project? Which namespace? Is it a preference or a decision? Is it worth the tool call?"* This cognitive overhead gets skipped under pressure.

---

## The Fundamental Design Mistake

We put the routing decision on the agent **at the moment of capture**. The right design is:

> **Capture broadly, route later** — not **route at capture**

- Agent captures anything that seems worth remembering, minimal metadata required
- A separate process (hook, Krypton, curation review) decides where it belongs
- Storage is cheap; missed capture is permanent loss

Claude's auto-memory does this. We need a similar passive layer.

---

## What's Available: Claude Code Hooks

Claude Code fires hooks we haven't used for memory capture:

| Hook | Fires when | Capture opportunity |
|------|-----------|---------------------|
| `SessionStart` | Session begins | Retrieve context (already partially addressed in protocol) |
| `PreCompact` | **Before** context compaction | **Highest value** — context is richest, agent is about to lose it |
| `Stop` | Session ends | Session-end summary capture |
| `PostToolUse` | After any tool call | ACK used this — too noisy, captured everything |

**PreCompact is the highest-leverage hook.** Context compaction is triggered by:
1. Count-based: approaching token limits
2. Time-based: after idle periods
3. Event-based: conclusion of a task

Right before compaction, the context is at its richest — all session work is present. The agent is about to lose it. This is the exact moment to inject a capture prompt. It's enforced (hook fires automatically) rather than aspirational (agent remembers to do it).

---

## Solution Directions

### 1. PreCompact Hook — highest leverage

Inject a structured prompt into the compaction process:

```
Before compacting this context, take 60 seconds to capture:

1. EPISODIC: Write 2-3 sentences about what was done this session to
   data/episodes/YYYY-MM-DD.jsonl (append-only, no routing decision needed)

2. SEMANTIC: Identify any cross-project learnings — facts, patterns,
   debugging insights that would help agents in other projects. Call
   write_memory for each (namespace=global, type=observation is fine).

You are about to lose this context. Capture what matters now.
```

Agent acts because it's prompted at the moment of loss. No need to remember — the hook forces it.

### 2. Stop Hook — session-end fallback

Same pattern on session end, lighter version. Catches sessions that end without compaction. Prompt focuses on: did anything happen this session worth preserving beyond this project?

### 3. Lower Friction for Semantic Capture

Current friction: 6 parameters, namespace taxonomy, memory_type taxonomy — agents overthink it.

Solution: a `quick_memory(content)` wrapper that defaults everything:
- `namespace = "global"`
- `memory_type = "observation"`
- `writer_id = caller's identifier`
- `confidence = 0.8`

One parameter. Zero routing decision. More captures happen. Curation happens later via `review_candidates` or Krypton.

### 4. Episodic Daily Log — near-zero friction tier

`data/episodes/YYYY-MM-DD.jsonl` — append-only session event log. No routing decision, no dedup, no type taxonomy. Just: "what happened."

```json
{"ts": "2026-02-19T15:00:00Z", "project": "memory-layer", "event": "validator found missing client_profiles — root cause of scope narrowing bug"}
```

The Stop hook writes an episodic summary automatically. No agent decision required. Raw material that gets distilled into semantic memories later (or stays as audit trail).

### 5. Krypton `/capture` as the Uncertain-Case Escape Hatch

When the agent isn't sure where something belongs, delegate to Krypton. This already exists. Problem: agents don't know to use it in the moment. Should be included in session-end hook prompt: "If unsure where something belongs, use `/krypton:capture`."

---

## What Needs Research

The hooks implementation is the critical unknown before building this:

1. **PreCompact hook behavior** — what context does it receive? Can it inject into the compaction prompt? Can it make MCP tool calls? What format does the injection take?

2. **Stop hook behavior** — can it call MCP tools, or only shell commands? Does it have access to conversation history?

3. **Prompt injection pattern for extraction** — what prompt produces the best signal-to-noise for session-end capture? The ACK lesson: PostToolUse captured too much noise. Quality over quantity.

4. **Existing Claude Code hook patterns for memory** — how have others solved session-end capture? What's the state of the art for hook-based memory?

---

## Next Project: Memory Capture Automation

This should be a concrete project, not a backlog item. The storage layer is built; the capture layer is the missing piece that makes it actually work.

**Proposed deliverables:**
1. PreCompact hook with structured extraction prompt
2. Stop hook with session-end episodic write
3. Episodic tier (`data/episodes/`) with schema and MCP tool (`write_episode`, `get_episodes`)
4. `quick_memory()` low-friction wrapper
5. Session-start hook to call `get_session_context` automatically (the retrieval side of the same problem)

**Research required first:**
- Claude Code hook capabilities for PreCompact and Stop
- MCP tool availability within hook execution context
- Prompt design for high-quality extraction (not everything — just what matters)
