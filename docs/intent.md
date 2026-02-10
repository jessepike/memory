---
type: "intent"
project: "Memory Layer"
version: "0.1"
created: "2026-02-10"
updated: "2026-02-10"
---

# Intent: Memory Layer

## Problem/Opportunity

Krypton's 3-layer architecture needs a persistent memory system (Tier 2) that sits between project-local context (Tier 1 — CLAUDE.md, status.md) and reference knowledge (KB). Today, contextual knowledge about the user, their work patterns, decisions, and project history has no structured home. It's either trapped in conversation history (ephemeral) or manually noted in project files (fragmented, unqueryable).

## Desired Outcome

An independent, queryable memory service that any agent can write to and read from — capturing observations, preferences, decisions, and progress across projects and sessions. Scoped access ensures the right context reaches the right agent at the right time.

## Why It Matters

Without persistent contextual memory, every agent session starts partially blind. Krypton can't synthesize across projects. ADF agents can't learn from past sessions. Personal patterns and preferences must be restated. The memory layer closes this gap — making the agent ecosystem contextually aware rather than perpetually amnesic.
