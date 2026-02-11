---
type: "tasks"
project: "Memory Layer"
stage: "deliver"
current_phase: "Phase 3: Delivery Planning"
created: "2026-02-11"
---

# Delivery Tasks

## Handoff

| Field | Value |
|-------|-------|
| Phase | Phase 2: Delivery Capability Assessment |
| Status | Complete |
| Next | Phase 3: Delivery Planning |
| Blocker | None |

**Done this phase:**
- DEL-02: Created manifest.md (deployment deps) and capabilities.md (registry summary, testing tools, CLIs)

**Next phase requires:**
- plan.md and tasks.md drafted (this file)
- Ready for Phase 4 review loop

## Active Tasks

| ID | Task | Status | Acceptance Criteria | Testing | Depends | Capability |
|----|------|--------|---------------------|---------|---------|------------|
| DEL-03 | Draft plan.md and tasks.md | done | Plan covers deployment phases, 3-tier testing, rollback | Self-review | DEL-02 | — |

## Upcoming — Phase 5: Infrastructure Setup

| ID | Task | Status | Acceptance Criteria | Testing | Depends | Capability |
|----|------|--------|---------------------|---------|---------|------------|
| DEL-05 | Verify venv and editable install current | pending | `pip install -e ".[dev]"` succeeds, pytest passes | pytest | — | python |
| DEL-06 | Provision embedding model | pending | `all-MiniLM-L6-v2` downloaded and cached | smoke test | DEL-05 | python |

## Upcoming — Phase 6: Deployment Execution

| ID | Task | Status | Acceptance Criteria | Testing | Depends | Capability |
|----|------|--------|---------------------|---------|---------|------------|
| DEL-07 | Register MCP server in Claude Code | pending | `claude mcp add` succeeds, server appears in tool list | `health` tool call | DEL-06 | claude CLI |
| DEL-08 | Register MCP server in Codex | pending | `codex mcp add` succeeds | `health` tool call | DEL-06 | codex CLI |
| DEL-09 | Register MCP server in Gemini | pending | `gemini mcp add` succeeds | `health` tool call | DEL-06 | gemini CLI |

## Upcoming — Phase 7: Validation & Testing

| ID | Task | Status | Acceptance Criteria | Testing | Depends | Capability |
|----|------|--------|---------------------|---------|---------|------------|
| DEL-10 | Tier 1 automated tests | pending | 36/36 pytest, 15/15 smoke, 7/7 stdio | test scripts | DEL-07 | pytest |
| DEL-11 | Tier 2 live client testing | pending | All 12 scenarios pass from Claude Code; health+write+search from Codex/Gemini | live tool calls | DEL-10 | claude/codex/gemini |
| DEL-12 | Tier 3 manual validation | pending | Human confirms cross-client persistence and isolation | human testing | DEL-11 | human |

## Upcoming — Phase 8: Milestone Closeout

| ID | Task | Status | Acceptance Criteria | Testing | Depends | Capability |
|----|------|--------|---------------------|---------|---------|------------|
| DEL-13 | Map success criteria to evidence | pending | All 10 brief criteria mapped with pass/fail | — | DEL-12 | — |
| DEL-14 | Write access documentation | pending | README or ACCESS.md has connection instructions per client | — | DEL-12 | — |
| DEL-15 | Archive deliver artifacts, seal status.md | pending | Artifacts archived, status sealed | — | DEL-13, DEL-14 | — |

## Completed

| ID | Task | Status | Acceptance Criteria |
|----|------|--------|---------------------|
| DEL-01 | Phase 1 Intake & Readiness Check | done | All Develop outputs verified, delivery scope understood |
| DEL-02 | Phase 2 Delivery Capability Assessment | done | manifest.md + capabilities.md created with registry summary |
| DEL-03 | Phase 3 Draft plan.md and tasks.md | done | Plan and tasks drafted |
