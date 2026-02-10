# Agent Operating Requirements

These requirements are mandatory for all agent work in this repository.

## Required Operational Loop

1. Review `docs/status.md` and `docs/backlog.md` at the start of a work session.
2. Execute work by pulling items from `docs/backlog.md` in priority order.
3. Update task state in `docs/backlog.md` as work progresses.
4. Update `docs/status.md` at meaningful milestones (what changed, what is next, blockers).
5. Create regular commits during implementation, not one large commit at the end.

## Backlog Rules

- `docs/backlog.md` is the source of truth for active and upcoming work.
- Every substantive code task must be represented in the backlog.
- Each backlog item must include: `id`, `priority`, `status`, `owner`, `description`, `done_when`.
- Status values: `todo`, `in_progress`, `blocked`, `done`.

## Commit Cadence Rules

- Commit after each coherent, tested unit of work.
- Prefer small commits scoped to one step or one concern.
- Commit message format: `<area>: <change summary>`, e.g. `storage: add sqlite lifecycle APIs`.
- Before each commit:
  - run relevant tests
  - ensure backlog/status updates for that slice are included

## Definition Of Done For Any Slice

- Code implemented
- Tests passing for the changed scope
- `docs/backlog.md` updated
- `docs/status.md` updated
- Commit created
