---
name: storm-orchestrate
description: Coordinate multi-lane work with Storm specialists inside the shipped plan and execute facets. Builds the dependency graph, records lanes in native todos, dispatches only the independent frontier, and reconciles every terminal result before finalizing.
---

# Storm Orchestrate

Coordinator procedure for delegating work to the Storm specialist subagents. This skill augments the shipped `plan` and `execute` facets; it never replaces their handoff or goal semantics. First action: establish which facet you are in and which capabilities are active, because that decides which specialists you may dispatch.

## Phase decides the roster

- **plan facet:** read-only roles only — `storm-explorer`, `storm-librarian`, `storm-oracle`, `storm-observer`, `storm-councillor` (via storm-council). The shipped `plan` facet exposes `shell_exec`, so "read-only" for these roles is real (they carry no mutation tools and `inherit_tools: false`), but a write role dispatched here would be protected only by its deny list and the permission classifier — **never dispatch `storm-fixer` or `storm-designer` from `plan`**. Read-only visual review from `plan` routes to `storm-observer`.
- **execute facet with an approved handoff:** before dispatching any writer, call `read_goal` and verify the implementation goal is active, then verify the story's Linear issue is `In Progress` through the normal MCP path. No active goal or unverified state → halt; do not open or mutate anything yourself outside the canonical storm-linear flow.

## Lane records

Every delegated lane gets a native todo whose title/description carries the scheduling fields in this parseable convention (one per line in the description). The marker is `storm-lane:` and the field names below are exactly what `scheduler.py` parses — no other marker or field names are valid:

```
storm-lane: <todo-id>
specialist: storm-explorer|storm-librarian|storm-oracle|storm-observer|storm-fixer|storm-designer|storm-councillor
objective: <one line>
ownership: <comma-separated files/folders, or empty for none>
dependencies: <comma-separated todo-ids, or empty for none>
edits: allowed|read-only
state: pending|working|completed|failed|cancelled|timed-out|rejected-fit|reconciled|dispositioned
validation: <what proves the result>
result: <expected result summary before dispatch; terminal result summary once terminal>
partial_changes: <files touched before a failed/cancelled/timed-out lane stopped, or empty>
partial_inspected: true  # required before a replacement writer may start on the same ownership
disposition: <the explicit reroute/replace/operator decision; required when and only when state is dispositioned>
```

A concrete, parseable example (todo 7's description):

```
storm-lane: 7
specialist: storm-fixer
objective: Implement hex-grid neighbor lookup
ownership: source/core/hex/Grid.cs, source/core/hex/
dependencies: 2, 3
edits: allowed
state: pending
validation: dotnet build; gdUnit4 core suite
result: neighbor lookup returns the six adjacent hexes in cube coordinates
```

Native todo status/dependencies and native job status/output are the live state; this convention makes them parseable. Do not create a second task database. Results that must survive compaction live in durable evidence artifacts (review/conformance packets, tracker completion records), not in conversation memory. On resume after compaction, reconstruct lane state by joining retained todos/jobs with those artifacts — never from memory.

## Scheduling

Mechanical gates must not depend on prompt compliance. Use the scheduler module's CLI:

```bash
python3 {storm-module}/skills/storm-orchestrate/scheduler.py frontier lanes.json
python3 {storm-module}/skills/storm-orchestrate/scheduler.py conflicts lanes.json
python3 {storm-module}/skills/storm-orchestrate/scheduler.py finalize lanes.json [--required 1,2,3]
```

`lanes.json` is a JSON array of lane entries — `{"todo_id": 1, "description": "<the todo description carrying the storm-lane record>", "native_status": "in_progress", "native_dependencies": [2]}` — where `native_status` and `native_dependencies` are optional and, when present, override the record fields. Exit codes: `0` the gate passes, `1` the gate fails (conflicts found / finalization blocked), `2` malformed input or record error (including dependency cycles); every report is a single JSON object on stdout. `frontier` prints the dispatchable todo ids plus lanes blocked by failed/dispositioned dependencies; `conflicts` prints overlapping writer ownership; `finalize` prints the finalization gate result with reasons.

The scheduler parses lane records, computes the dependency-ready frontier, rejects overlapping writer ownership, detects dependency cycles and self-dependencies, classifies native job terminal states, and reports whether every required result is reconciled before finalization. You keep judgment and task routing; the scheduler keeps the rules.

1. Build the dependency graph before dispatch. Create the todos with dependencies, then dispatch only the current independent frontier, as background jobs.
2. **Exclusive writer ownership:** only one worker may own a file at a time; overlapping folder ownership is prohibited unless the plan serializes the lanes. The scheduler rejects overlaps — do not override it.
3. Review never runs concurrently with edits it is intended to review.
4. While jobs run you may continue only independent planning/synthesis. Dependent work waits for terminal results (`job_block` / `job_result`).
5. Respect the configured maximum parallel specialist jobs; default conservatively.

## Writer dispatch contract

Every `storm-fixer` / `storm-designer` dispatch prompt must include: objective, acceptance criteria, exact file/folder ownership, dependencies, exclusions, allowed edits, and required validation. Writers are execute-context-only (their definitions enforce lifecycle/tracker denials and no subagent spawning). `shell_exec` is denied in the shipped definitions; if the approved task genuinely requires the worker to run validation commands, run them yourself or get operator approval for a project-local role variant under ask/deny-gated permissions — never silently widen a role.

## Reconciliation and finalization

Specialist output is evidence/input, not authority. Before any final response, close, or completion comment:

1. Every relevant job is terminal and its structured exit consumed.
2. Results are checked against the original goal, the published specification, acceptance criteria, and each other; conflicts are resolved explicitly.
3. Required verification is complete (tests, visual evidence, conformance checks as applicable).

The scheduler's finalization check must pass. If it does not, the work is not done.

## Failure handling

- No generic automatic retry. A failed lane is diagnosed before any replacement.
- `rejected-fit` means reroute or ask the operator — never redispatch unchanged.
- Failed/timed-out/cancelled lanes are explicit terminal records in the lane state.
- A failure-state lane blocks finalization until it is explicitly dispositioned: set state `dispositioned` with a recorded `disposition` reason (reroute, replacement, or operator decision). Dispositioning is a decision record, never a retry, and a lane depending on a dispositioned lane stays blocked until its `dependencies` are re-pointed at the replacement.
- Cancellation is not rollback: inspect a cancelled writer's `partial_changes` before any replacement writer starts on the same ownership.
- No silent model, reviewer, host, or foreground fallback — substitutions are reported.
- Blocked or non-clean work leaves the Linear issue `In Progress` and the saved goal active (or explicitly blocked) per the parent workflow.
