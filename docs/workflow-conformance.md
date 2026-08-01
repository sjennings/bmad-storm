# Workflow Conformance

The canonical Storm development workflow, its approved divergence ledger, and the audit procedure that keeps directives, aliases, and tests honest. The machine-readable source of truth is [`skills/storm-contract/workflow-contract.json`](../skills/storm-contract/workflow-contract.json) (contract version **1.0.0**); this document is its human-readable companion. When the two disagree, the JSON contract wins and this document is stale.

## Enforcement honesty

Storm's workflow is enforced at the **directive/prompt and permission-classifier level**, plus the deterministic validators in this repository. Polytoken does **not** provide a physical sandbox that makes plan-facet mutation impossible: the shipped `plan` facet exposes `shell_exec`, so its read-only posture is prompt- and permission-enforced. Therefore:

- The transcript validator (`skills/storm-contract/validate_transcript.py`) and the unit tests prove that the *contract* and recorded event sequences conform. They say nothing about live tool behavior.
- Only the disposable Polytoken smoke scenarios below prove live tool behavior, and they are evidence-gathering exercises, not release gates.
- No Storm document, skill, or diagnostic may claim a physical sandbox, "guaranteed" read-only plan execution, or hard runtime enforcement. Where a safety property rests on directive-level control, say so.

### Approved runtime deviation: `subagent` is not deny-listable on Polytoken 0.5.9

- **Observed error:** a live Polytoken 0.5.9 gate rejected the `storm-fixer`/`storm-designer` definitions at load time because `tools_deny` cannot deny the harness-managed `subagent` tool.
- **Approved redesign (operator-approved, runtime-specific to 0.5.9):** only `subagent` was removed from those two deny lists. `allow_subagent_spawn: false`, the structured exit schemas, and every other lifecycle/Linear/shell denial (including `message_subagent`) are retained.
- **Remaining limitation:** an exact deny-union over `subagent` is unavailable on 0.5.9. The no-spawning boundary is enforced by `allow_subagent_spawn`/runtime semantics plus coordinator convention, **not** by `tools_deny`. No document or diagnostic may claim exact deny-union coverage for `subagent` on 0.5.9. `validate_polytoken_assets.py` encodes the deviation: it requires `allow_subagent_spawn: false` on write roles and flags `subagent` in a write role's deny list.

### Observed capability evidence (live gates, Polytoken 0.5.9)

Recorded during the v0.4.0 development gates against the actual target runtime (`polytoken 0.5.9`):

- **Role loading:** all seven projected specialist roles (Explorer, Librarian, Oracle, Observer, Fixer, Designer, Councillor) were accepted by `polytoken validate subagent` with no definition errors.
- **Facet fixture:** a bounded `polytoken exec --facet plan --max-tool-turns 1` run against the planning fixture returned `{"status":"fixture-loaded"}`.
- **`tools_deny(subagent)` gate:** the exact inherited-union denial gate **failed** — the runtime rejected `storm-fixer`/`storm-designer` at load time because the harness-managed `subagent` tool cannot appear in a subagent's `tools_deny` list (the documented runtime error behind the approved deviation above).
- **What was *not* proven:** inherited-union denial filtering was **not** supported on 0.5.9 and must not be claimed anywhere. The approved redesign enforces the no-spawning boundary with `allow_subagent_spawn: false` plus coordinator convention, and the smoke scenarios below record enforcement as directive/classifier-level, not a physical sandbox.

## Authority rules

| Phase | Authority | Artifacts |
|---|---|---|
| Pre-publication (scope, authoring) | BMAD | `epics.md`, `sprint-status.yaml`, story file |
| Publication (the single handoff) | `storm-linear publish` | spec written to the story-key-anchored Linear issue |
| Post-publication (implementation → Done) | Linear | the Linear issue carrying the published spec |

- The phase-decides rule: pre-publication `sprint-status.yaml` wins; post-publication Linear wins; if the phase cannot be determined, stop and ask rather than overwrite.
- Polytoken planning is read-only until an approved `handoff_plan` activates a saved goal; only then may execution open the issue and mutate implementation files.
- Canonical execution chain: `plan` facet → `write_plan` → plan reviewed → `handoff_plan` approved → goal activated → `execute` facet → `read_goal` verified → `storm-linear open` → open verified → mutation.
- Review rounds come only from `review_loop_max_rounds`; fixes require a complete fresh review pass; non-convergence leaves the issue `In Progress`.
- No Storm role commits without explicit operator authority. `completion_commit_policy` (default `require-explicit`; alternative `allow-without-storm-commit`) controls whether close may proceed.
- The execute session that opens an issue owns closing it. A child-ticket close reconciles nothing and never closes, mutates, or reconciles the parent story.

## Approved divergence ledger (D1–D12)

Operator-approved dispositions for divergences found between the v0.3.0 directive surface and the canonical workflow. Status legend: **repair** = change directives/tests to match the canonical rule; **retire** = remove the divergent path; **allow** = divergence is accepted and documented.

| ID | Divergence | Disposition | Canonical rule |
|---|---|---|---|
| D1 | Command-name drift between docs, help, and overrides | repair | One canonical mapping (below) with alias-equivalence tests; every name resolves to a canonical operation ID. |
| D2 | Direct `/implement` execution bypassed the Polytoken handoff | repair | Polytoken always follows `plan → reviewed handoff_plan → active goal → execute → read_goal → storm-linear open → mutation`; no direct open or mutation. |
| D3 | Review-loop limits hard-coded in several places | repair | Exactly one setting, `review_loop_max_rounds`, is read; templates reference it by name. |
| D4 | Commit/close behavior varied by skill | repair | No commit without explicit authority; one completion policy, `completion_commit_policy` (default `require-explicit`, alternative `allow-without-storm-commit`), controls close. |
| D5 | `story-execute`-style worker owned tracker/commit/close independently | retire | Retired; any retained worker is bounded and parent-controlled and never owns tracker, commit, or close. |
| D6 | References to missing/archived skills (`/wayfinder`, `story-plan`, `story-execute`) | repair | Retired aliases are removed from active advertising or installed only as tested aliases; see the alias table. |
| D7 | Parallel authoritative brief/spec keys | repair | One artifact lifecycle (below): BMAD authoring artifact before publication, published Linear specification after; no parallel authority. |
| D8 | Generic three-lens reviewer as a separate gate | allow | Permitted only as an implementation detail feeding the single native-plus-cross-review triage and loop. |
| D9 | `/to-tickets` as a workflow step | allow (reduced) | Tracer-bullet slicing design retained; `/to-tickets` is a thin post-publication adapter to `storm-linear slice`, operator-invoked only. |
| D10 | Background workers without dependency/ownership rules | repair | Dependency and file/subsystem ownership enforced mechanically by `skills/storm-orchestrate/scheduler.py`. |
| D11 | Substring-only confidence in workflow conformance | repair | Executable workflow scenarios (transcript validator + fixtures) are the conformance evidence. |
| D12 | Provenance ambiguity for generated files | repair | Generated ownership, version pinning, archive markers, and setup checks; consuming-project copies are projections of `bmad-storm` source, never independent forks. |

## Canonical alias mapping

Aliases delegate to canonical operations. They never reimplement state transitions, and they never independently publish, open, implement, review, commit, close, or reconcile.

| Public alias | Canonical operation(s) | Status |
|---|---|---|
| `/create-story` | `bmad-create-story` (+ storm overrides: grilling, publish hook) | alias |
| `/to-spec` | `storm-linear publish` (inside `bmad-create-story` `on_complete`) | alias |
| `/to-tickets` | `storm-linear slice` (post-publication, operator-invoked) | alias |
| `/implement` | `bmad-dev-story` (with `storm-linear open`, `storm-tdd`, `storm-linear close`) | alias |
| `/tdd` | `storm-tdd` | alias |
| `/code-review` | `bmad-code-review` + `storm-cross-review` | alias |
| `/wayfinder` | — | retired; not advertised |
| `story-plan` | — | retired; not advertised |
| `story-execute` | — | retired; not advertised |

The machine-readable copy of this table is `aliases` in the JSON contract; `tests/test_workflow_contract.py` fails if an alias embeds an independent lifecycle, references an unknown operation, or if a retired alias is advertised in `skills/module-help.csv`.

## Artifact lifecycle

1. **Before publication:** `epics.md`, `sprint-status.yaml`, and the BMAD story file own scope/context.
2. **At publication:** `storm-linear publish` writes the story-key-anchored specification to the Linear issue, sets `Todo` + `ready-for-agent`, and only then moves the sprint entry to `ready-for-dev`. Publication is atomic: a failed publish leaves `sprint-status.yaml` untouched and is reported with exactly what should have been written.
3. **After publication:** Linear owns implementation context/state. Local authoring files are evidence/history, not competing authority. There are no parallel authoritative brief/spec keys.

## Transcript and event format

Conformance scenarios are event transcripts validated deterministically by `skills/storm-contract/validate_transcript.py` against the JSON contract. A transcript is a JSON object:

```json
{
  "policy": "require-explicit",
  "max_rounds": 3,
  "events": [
    {"event": "scope_resolved"},
    {"event": "grill_confirmed"},
    {"event": "publish_succeeded"},
    {"event": "sprint_ready_updated"},
    {"event": "plan_created"},
    {"event": "plan_reviewed"},
    {"event": "handoff_approved"},
    {"event": "execute_entered"},
    {"event": "goal_verified"},
    {"event": "issue_opened", "target": "story"},
    {"event": "open_verified"},
    {"event": "mutation"}
  ]
}
```

- `policy` and `max_rounds` are optional; defaults come from the contract's `completion_commit_policy` and `review_loop_max_rounds`.
- `issue_opened` carries `target: "story" | "child"`; close guards match against it.
- Event vocabulary (defined in `transitions` in the contract): `scope_resolved`, `grill_confirmed`, `spec_review_completed`, `publish_succeeded`, `publish_failed`, `sprint_ready_updated`, `slice_completed`, `plan_created`, `plan_reviewed`, `handoff_approved`, `handoff_rejected`, `handoff_cancelled`, `execute_entered`, `goal_verified`, `issue_opened`, `open_verified`, `mutation`, `seam_confirmed`, `red_evidence`, `green_evidence`, `native_review_passed`, `cross_review_passed`, `finding_dispositioned`, `fix_applied`, `review_halted_non_converged`, `commit_authorized`, `commit_completed`, `completion_commented`, `issue_closed`, `child_closed`, `sprint_reconciled`, `child_roll_up_reported`.
- The validator stops at the first violation and reports the event index, the state, and the rule. Run it directly: `python3 skills/storm-contract/validate_transcript.py <transcript.json>`; fixtures live in `tests/fixtures/transcripts/`.

Scenario coverage required of the fixture set: publish success; atomic publish failure (sprint untouched); rejected/cancelled handoff leaves `Todo` and blocks mutation; absent goal blocks open; pre-open mutation rejected; failed open verification blocks mutation; child-ticket close never closes/reconciles the parent; review fixes require a complete fresh pass; max-round non-convergence leaves `In Progress`; commit without explicit authority rejected; story close comments before `Done` then reconciles.

## Required smoke scenarios (disposable Polytoken sessions)

These are run by a human/operator in a disposable Polytoken session with no production credentials or tracker writes. They prove live tool behavior; the deterministic tests above prove the contract. Record observations and evidence artifacts per run.

### `smoke_plan_handoff_goal_open_gate`

1. Install storm into a scratch consuming project and `/reload`; confirm no definition errors.
2. Start `bmad-dev-story` against a fixture story whose issue is `Todo`. Confirm the session enters/uses the shipped `plan` facet and does **not** call `storm-linear open`.
3. Record a plan with `write_plan`, then call `handoff_plan`. **Reject** the handoff. Expected: issue stays `Todo`; no implementation file changes; session reports the halt.
4. Re-plan, approve the handoff. Expected: saved goal active, facet `execute`; `read_goal` returns the goal; only then `storm-linear open` moves the issue to `In Progress`; mutation begins after open is verified.
5. Negative probe: in a fresh session without an active goal, attempt `storm-linear open`. Expected: the directive halts before opening and reports that plan integration must produce a goal. (Directive-level enforcement — observe and record actual behavior.)

### `smoke_role_tool_contracts`

1. After the install above, invoke each read-only role against fixtures and confirm no mutation tools are exposed and no mutations occur.
2. Confirm the coordinator routes plan-phase work to read-only roles.
3. Deliberately attempt a Fixer/Designer dispatch from the `plan` facet with the full 0.5.9 deny set (every lifecycle/Linear/shell denial except the harness-managed `subagent`, which 0.5.9 cannot deny — see the approved runtime deviation above). Expected: no observed mutation. Record that enforcement here is directive/classifier-level, not a physical sandbox.
4. Enter an approved fixture goal/execution context, then confirm bounded writers operate and denied lifecycle tools (tracker mutation, goal/plan/facet control, final completion) remain unavailable, and that nested delegation is refused (`allow_subagent_spawn: false` plus convention — not a deny-list entry on 0.5.9).
5. Exercise `/jobs`, `/todo`, cancellation (confirming it does not undo filesystem changes), auto-drained job completion, and the continuation hook in its default-off state.

## Audit procedure

1. `python3 -m unittest discover -s tests -v` — all deterministic checks, including every transcript fixture.
2. `python3 skills/storm-contract/validate_transcript.py <fixture>` for any new scenario before adding it to the fixture set.
3. After any BMAD or Polytoken update: re-run the suite, then `storm-setup check` in the consuming project, then the smoke scenarios if the update touched facets, goals, hooks, or subagent tool contracts.
4. Any new divergence is logged as a D-entry in the ledger above with an operator-approved disposition before directives change.
