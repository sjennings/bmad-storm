---
name: storm-status
description: Project native Polytoken /jobs and /todo state into a concise orchestration board — role, objective, ownership, dependencies, runtime state, result availability, reconciliation — without creating a competing authority store.
---

# Storm Status

Synthesize the native job and todo state into one board. This skill is a **projection, not a store**: native todos/jobs remain the live state, durable evidence artifacts remain the historical record, and Linear remains execution authority. `storm-status` never writes state anywhere.

## Procedure

1. Read the native surfaces: list todos (with their lane-record descriptions per the storm-orchestrate convention) and inspect jobs (`job_status` / `job_result` for terminal lanes).
2. Join with durable evidence where it exists (review/conformance packets, tracker completion records) to determine reconciliation state. On resume after compaction, this join — not conversation memory — is how the board is rebuilt.
3. Render one row per lane:

| lane | specialist | objective | ownership | depends-on | state | elapsed/progress | result | reconciliation |
|---|---|---|---|---|---|---|---|---|

- `state` comes from native todo status plus native job status: `pending`, `working`, `completed`, `failed`, `cancelled`, `timed-out`, `rejected-fit`, `reconciled`.
- `elapsed/progress` uses subagent `progress_update` notes as **liveness only**. A progress note is never a result; only a structured `exit_tool` payload from a terminal job counts.
- `result` is "available" only when the job is terminal and its exit payload has been consumed.
- `reconciliation` records whether the result has been checked against goal/spec/acceptance criteria and peer results.

4. Summarize: current frontier (what can dispatch now), blocked lanes and why, terminal-but-unreconciled results, and what blocks finalization.

## Cancellation, timeout, and failure guidance

- Cancelling a job stops the worker; it does **not** undo filesystem changes the worker already made. A cancelled writer's `partial_changes` must be inspected before any replacement starts on the same ownership.
- A timed-out lane is terminal: record it, inspect partial work, and decide replacement explicitly — no automatic retry.
- `rejected-fit` lanes are rerouted or escalated to the operator, never redispatched unchanged.

## Boundaries

- No second task database, no custom TUI, no edits to todos/jobs from this skill beyond ordinary native todo maintenance the coordinator already owns.
- If the board and Linear disagree about execution state, Linear wins and the discrepancy is reported, not papered over.
