---
type: "tasks"
project: "Memory Layer"
stage: "deliver"
current_phase: "Phase 7: Validation & Testing"
created: "2026-02-11"
---

# Delivery Tasks

## Handoff

| Field | Value |
|-------|-------|
| Phase | Phase 5+6: Infrastructure + Deployment (collapsed) |
| Status | Complete |
| Next | Phase 7: Validation & Testing |
| Blocker | None |

**Done this phase:**
- DEL-05/06: Venv current, embedding model provisioned
- DEL-07: Claude Code already registered (user scope, stdio, uv-based). Verified connected.
- DEL-08: Codex CLI not installed — deferred (env issue, not memory-layer)
- DEL-09: Gemini CLI requires GEMINI_API_KEY — deferred (env issue, not memory-layer)
- DEL-10: Tier 1 — 36/36 pytest, 15/15 smoke, 7/7 stdio all pass
- DEL-11: Tier 2 — all 13 live scenarios pass from Claude Code

**Next phase requires:**
- DEL-12: Tier 3 manual validation (human-driven)

## Active Tasks

| ID | Task | Status | Acceptance Criteria | Testing | Depends | Capability |
|----|------|--------|---------------------|---------|---------|------------|
| DEL-03 | Draft plan.md and tasks.md | done | Plan covers deployment phases, 3-tier testing, rollback | Self-review | DEL-02 | — |

## Active Tasks

| ID | Task | Status | Acceptance Criteria | Testing | Depends | Capability |
|----|------|--------|---------------------|---------|---------|------------|
| DEL-12 | Tier 3 manual validation | pending | Human confirms persistence and namespace isolation | human testing | DEL-11 | human |

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
| DEL-04 | Phase 4 Review & Approval (simplified) | done | Self-review passed, human approved plan |
| DEL-05 | Verify venv and editable install | done | Venv current, pytest passes |
| DEL-06 | Provision embedding model | done | all-MiniLM-L6-v2 loaded, dim=384 |
| DEL-07 | Register MCP in Claude Code | done | Already registered at user scope, connected |
| DEL-08 | Register MCP in Codex | deferred | Codex CLI not installed (env issue) |
| DEL-09 | Register MCP in Gemini | deferred | Gemini CLI requires API key config (env issue) |
| DEL-10 | Tier 1 automated tests | done | 36/36 pytest, 15/15 smoke, 7/7 stdio |
| DEL-11 | Tier 2 live client testing | done | 13/13 scenarios pass from Claude Code |
