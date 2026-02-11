---
type: "patch-list"
project: "Memory Layer"
stage: "pre-develop"
created: "2026-02-10"
updated: "2026-02-10"
source: "./design.md"
---

# Pre-Develop Design Patch List (Critical + High)

## How To Use This

Use this as the gate before starting implementation. Process patches in order. A patch is done only when:

1. Decision is made.
2. `docs/design.md` is updated.
3. Acceptance checks in this file are satisfied.

## Patch Order

1. [x] P1 - Trust boundary and scope enforcement model (Critical)
2. [x] P2 - ID-based tool authorization rules (Critical)
3. [x] P3 - Offline/runtime model provisioning contract (Critical)
4. [x] P4 - Dual-store consistency and reconciliation policy (High)
5. [x] P5 - Failed-state lifecycle and visibility invariants (High)
6. [x] P6 - Concurrency-safe dedup path (High)
7. [x] P7 - Deterministic dedup floor (exact/canonical before semantic) (High)
8. [x] P8 - Uniform scope semantics for all read tools (High)
9. [x] P9 - Consolidation filter/schema mismatch fix (High)
10. [x] P10 - Requirement language alignment: "authorized" vs "no auth" (High)

---

## P1 - Trust Boundary And Scope Enforcement Model (Critical)

### Problem

Current design allows caller-provided namespace and omitted namespace cross-scope reads, but does not define verifiable caller trust/privilege boundaries.

### Recommendation (Goldilocks)

Trusted-local policy with explicit client profiles:

- Add a static `client_profiles` config map keyed by `writer_id` or `client_id`.
- Each profile has: `allowed_namespaces`, `can_cross_scope`, `can_access_private`.
- Default profile is least privilege: own namespace only + global.
- Cross-scope access (`namespace` omitted) is allowed only when `can_cross_scope=true`.

This keeps MVP simple (no auth stack) while making scope rules enforceable.

### Design Edits Required

- Add a new "Trust Model" subsection in Security.
- Update Decision D1 to include validated caller identity input + profile lookup.
- Update all tool contracts to state that requested namespace is checked against caller profile.

### Acceptance Checks

- A non-privileged caller cannot read outside own namespace + global.
- Only privileged callers can execute cross-scope queries.
- Rules are deterministic and testable from config alone.

---

## P2 - ID-Based Tool Authorization Rules (Critical)

### Problem

`get_memory`, `update_memory`, `archive_memory` currently accept only `id`; spec does not require scope checks on fetched row.

### Recommendation (Goldilocks)

Mandatory row-level scope check for all ID-based tools:

- Fetch memory by `id`.
- Evaluate caller profile against memory namespace.
- Deny with structured error if unauthorized.
- For non-privileged callers, optional defense-in-depth: require `namespace` param and enforce `row.namespace == namespace`.

### Design Edits Required

- Add authorization flow notes to each ID-based tool.
- Define shared helper in core (`authorize_memory_access(caller, memory)`).
- Add explicit error contract: `{ error_code: "forbidden_scope", id, namespace }`.

### Acceptance Checks

- Knowing an ID is insufficient to read/update/archive across scope.
- Tool behavior is consistent across all ID-based endpoints.

---

## P3 - Offline/Runtime Model Provisioning Contract (Critical)

### Problem

Design states no external network calls but also states first-use model download.

### Recommendation (Goldilocks)

Split install-time network from runtime behavior:

- Runtime contract: zero network calls.
- Install/setup command fetches model artifact (one-time).
- Startup preflight validates model presence; if missing, fail fast with clear remediation.
- Optional config toggle: `allow_model_download_during_setup` (not runtime).

### Design Edits Required

- Update Security "Local-only" language.
- Add "Operational Constraints" section defining install-time vs runtime network policy.
- Add startup preflight requirement to Implementation Guidance.

### Acceptance Checks

- Runtime works in fully offline environment once provisioned.
- Missing model causes deterministic startup error, not silent fallback.

---

## P4 - Dual-Store Consistency And Reconciliation Policy (High)

### Problem

Archive flow can leave SQLite and Chroma divergent with no repair policy.

### Recommendation (Goldilocks)

Define SQLite as source of truth + reconciliation utility:

- Add periodic/manual `reconcile_dual_store` operation.
- For each committed SQLite record missing in Chroma: re-embed and upsert.
- For archived SQLite record present in Chroma: delete from Chroma.
- Record reconciliation metrics in logs/stats.

### Design Edits Required

- Add consistency policy section under Architecture or Storage.
- Extend `get_stats` with drift counters (optional but recommended).
- Add integration test cases for simulated partial failures.

### Acceptance Checks

- Any injected divergence can be repaired deterministically.
- Archive/update failure modes are not permanent corruption states.

---

## P5 - Failed-State Lifecycle And Visibility Invariants (High)

### Problem

`failed` exists in state machine but read visibility and recovery process are unspecified.

### Recommendation (Goldilocks)

Global invariant: only `status="committed"` is query-visible in all read tools.

- `failed` and `staged` are internal states only.
- Add `retry_failed_memory(id)` and `list_failed_memories(limit, age)` as manage tools or internal maintenance API.
- Include garbage-collection guidance for long-lived failures.

### Design Edits Required

- Update Search/Read sections to explicitly filter `status="committed"`.
- Add failure recovery flow in Manage tools or operational notes.
- Update Status State Machine with allowed transitions from `failed`.

### Acceptance Checks

- Failed/staged rows never appear in user-facing reads or stats unless explicitly requested via maintenance path.
- Operators have a documented way to recover failed writes.

---

## P6 - Concurrency-Safe Dedup Path (High)

### Problem

Check-then-write dedup can race and create duplicates under concurrent writers.

### Recommendation (Goldilocks)

Namespace-level write serialization + idempotency key:

- Use SQLite transaction lock for write path per namespace.
- Compute content hash idempotency key (`namespace + canonical_content_hash`).
- Add unique index on idempotency key for committed/staged active records.
- On unique conflict, treat as SKIP and return existing id.

### Design Edits Required

- Add concurrency control note in Write-Time Consolidation.
- Add schema field for deterministic idempotency key.
- Add test case for two concurrent identical writes.

### Acceptance Checks

- Concurrent same-fact writes produce one committed record.
- Success criterion "same fact twice != two entries" holds under concurrency.

---

## P7 - Deterministic Dedup Floor Before Semantic Dedup (High)

### Problem

Semantic threshold alone is probabilistic and may miss near-identical repeats.

### Recommendation (Goldilocks)

Two-stage dedup:

1. Deterministic stage: normalize content and exact hash match.
2. Semantic stage: embedding similarity threshold (0.92) for fuzzy duplicates.

Canonicalization should include whitespace fold, case normalization, and punctuation trimming.

### Design Edits Required

- Update consolidation algorithm to include stage 0 exact-match check.
- Define canonicalization function in `utils/consolidation.py`.
- Document precedence: exact match wins over semantic.

### Acceptance Checks

- Exact same content always dedups regardless of embedding variance.
- Semantic dedup remains for paraphrases.

---

## P8 - Uniform Scope Semantics For All Read Tools (High)

### Problem

`search_memories` defines omitted namespace behavior; `get_recent` and `get_stats` do not.

### Recommendation (Goldilocks)

Single shared scope resolver applied to every read tool:

- Input: caller profile + optional namespace param.
- Output: effective allowed namespace set.
- Private namespace excluded by default unless caller has explicit permission and requests it.

### Design Edits Required

- Add one "Scope Resolution Contract" section referenced by every read tool.
- Update `get_recent`, `get_stats`, `review_candidates`, `get_session_context` docs for parity.

### Acceptance Checks

- No read tool has bespoke scope behavior.
- Behavior with omitted namespace is consistent across endpoints.

---

## P9 - Consolidation Filter/Schema Mismatch Fix (High)

### Problem

Consolidation algorithm references Chroma filter on `status='committed'`, but vector metadata schema does not include `status`.

### Recommendation (Goldilocks)

Keep status filtering in SQLite, not Chroma:

- Query SQLite first for candidate IDs (`status='committed'` and scope constraint).
- Query Chroma restricted to those candidate IDs.
- Avoid duplicating status into Chroma metadata.

This reduces cross-store sync burden.

### Design Edits Required

- Update Chroma metadata table to remain status-free.
- Rewrite consolidation step 2 to SQL-prefilter + vector compare.
- Add performance note: acceptable at MVP scale; revisit with ANN partitioning later.

### Acceptance Checks

- Consolidation never evaluates archived/failed entries.
- Spec does not require unsupported or missing metadata filters.

---

## P10 - Requirement Language Alignment (High)

### Problem

Brief/design contain conflicting language: "authorized consumers" vs "no auth/no access control."

### Recommendation (Goldilocks)

Pick one explicit contract and align all docs:

- Preferred for MVP: "trusted local clients with policy-based scope controls; not multi-user security."
- Replace "authorized" wording with "policy-allowed trusted client" where needed.
- Reserve real authn/authz for post-MVP multi-user roadmap.

### Design Edits Required

- Update wording in brief success criteria mapping and security sections.
- Add note in limitations: this is policy enforcement, not cryptographic/client authentication.

### Acceptance Checks

- No contradictory claims about auth or authorization remain.
- Reader can clearly understand what protections exist and what do not.

---

## Recommended Working Session Format

For each patch:

1. Confirm decision.
2. Apply exact doc edits.
3. Re-run conflict scan across `docs/design.md`, `docs/discover-brief.md`, and `docs/status.md`.
4. Mark patch complete in this file with date + initials.

## Next Patch To Tackle

All critical/high patches are complete. Next step is a final human sign-off pass and then transition to Develop.

## Completion Log

- 2026-02-10 - P1 completed (JP/AI): Added trusted-local client profile trust model, privilege-gated cross-scope behavior, and aligned success-criteria wording.
- 2026-02-10 - P2 completed (JP/AI): Added row-level authorization flow for ID-based tools, namespace match guard for non-privileged callers, and standard forbidden error contract.
- 2026-02-10 - P3 completed (JP/AI): Split setup-time provisioning from runtime network policy, added operational constraints, and added startup model preflight fail-fast requirement.
- 2026-02-10 - P4 completed (JP/AI): Defined SQLite source-of-truth consistency contract, added `reconcile_dual_store` repair policy, added drift metrics in stats, and added drift-injection test guidance.
- 2026-02-10 - P5 completed (JP/AI): Added committed-only read visibility invariant, defined failed-state transitions, and specified core maintenance APIs for failed-row recovery.
- 2026-02-10 - P6 completed (JP/AI): Added `idempotency_key` schema/index, explicit staged reservation flow with unique-conflict SKIP behavior, and concurrent-writer stress test guidance.
- 2026-02-10 - P7 completed (JP/AI): Added canonicalization contract, made deterministic stage explicit in consolidation algorithm, and documented deterministic-before-semantic precedence.
- 2026-02-10 - P8 completed (JP/AI): Added shared Scope Resolution Contract and aligned all read/stats/manage-read tools to use it.
- 2026-02-10 - P9 completed (JP/AI): Replaced implicit Chroma status filtering with SQLite committed-prefilter + candidate-ID-constrained vector search.
- 2026-02-10 - P10 completed (JP/AI): Aligned trusted-local policy wording across design/brief/status and removed remaining auth-language ambiguity.
