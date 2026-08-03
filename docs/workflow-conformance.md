# Workflow Conformance

This document describes the BMAD-METHOD v7 workflow contract, its approved
divergence ledger, and the audit procedure that keeps the explicit Storm wrapper
boundary, compatibility shims, directives, and tests honest. The documented
contract version is **2.0.0**. The machine-readable companion is
[`skills/storm-contract/workflow-contract.json`](../skills/storm-contract/workflow-contract.json).

## Canonical upstream Build and Storm wrapper

Upstream `bmad-build` is canonical for current BMAD work. Its activation occurs
before route selection, it exposes no stable selected-route metadata, and its
`on_complete` is post-workflow. Storm therefore does not attach authoring,
implementation, or validation lifecycle hooks directly to Build.

`bmad-create-story`, `bmad-dev-story`, and `bmad-quick-dev` are upstream
deprecation shims. They warn and forward their original input directly to
`bmad-build`. Direct Build and shim calls are intentionally **unwrapped** by
Storm: they have no automatic Linear publish/open/close and no automatic sprint
readiness or reconciliation.

The explicit Storm-managed lifecycle is:

| Wrapper | Responsibility | Planner/tracker boundary |
|---|---|---|
| `storm-build author <story-key>` | Grill before Build with explicit `Seams & test points` input; verify artifact; optional spec review and publish | Exactly one planner readiness call after the author path; no direct projection write |
| `storm-build implement <story-key-or-issue>` | Polytoken handoff/open/TDD/review/close chain | Exactly one planner reconciliation for a story target; none for a child target |
| `storm-build validate <scope>` | Build validation with optional cross-review | No tracker or sprint side effects |

The wrapper owns these boundaries because upstream provides no safe phase callback.
It captures the explicit subcommand and target before invoking Build, does not
infer a route from mutable state, and does not claim to observe or prove
upstream's internal route selection.

Standalone `bmad-code-review` plus `storm-cross-review` remains an active,
independent review surface. It has not been renamed or removed. The preferred
explicit lifecycle-safe validation option is `storm-build validate`; standalone
validation may remain transitional or upstream-owned compatibility.

## Enforcement honesty

Storm's workflow is enforced at the **directive/prompt and permission-classifier
level**, plus the deterministic validators in this repository. Polytoken does
**not** provide a physical sandbox that makes plan-facet mutation impossible: the
shipped `plan` facet exposes `shell_exec`, so its read-only posture is prompt- and
permission-enforced. Therefore:

- The transcript validator (`skills/storm-contract/validate_transcript.py`) and
  the unit tests prove that the *contract* and recorded event sequences conform.
  They say nothing about live tool behavior, upstream Build route selection, or
  whether a live upstream callback fired.
- The disposable Polytoken and wrapper-boundary smoke scenarios below provide
  evidence about live behavior; they are evidence-gathering exercises, not
  release gates.
- No Storm document, skill, or diagnostic may claim a physical sandbox,
  "guaranteed" read-only plan execution, hard runtime enforcement, or tests that
  prove live upstream routing. Where a safety property rests on directive-level
  control, say so.

### Approved runtime deviation: `subagent` is not deny-listable on Polytoken 0.5.9

- **Observed error:** a live Polytoken 0.5.9 gate rejected the
  `storm-fixer`/`storm-designer` definitions at load time because `tools_deny`
  cannot deny the harness-managed `subagent` tool.
- **Approved redesign (operator-approved, runtime-specific to 0.5.9):** only
  `subagent` was removed from those two deny lists.
  `allow_subagent_spawn: false`, the structured exit schemas, and every other
  lifecycle/Linear/shell denial (including `message_subagent`) are retained.
- **Remaining limitation:** an exact deny-union over `subagent` is unavailable on
  0.5.9. The no-spawning boundary is enforced by
  `allow_subagent_spawn`/runtime semantics plus coordinator convention, **not**
  by `tools_deny`. No document or diagnostic may claim exact deny-union coverage
  for `subagent` on 0.5.9. `validate_polytoken_assets.py` encodes the deviation:
  it requires `allow_subagent_spawn: false` on write roles and flags `subagent`
  in a write role's deny list.

### Observed capability evidence (live gates, Polytoken 0.5.9)

Recorded during the v0.4.0 development gates against the actual target runtime
(`polytoken 0.5.9`):

- **Role loading:** all seven projected specialist roles (Explorer, Librarian,
  Oracle, Observer, Fixer, Designer, Councillor) were accepted by `polytoken
  validate subagent` with no definition errors.
- **Facet fixture:** a bounded `polytoken exec --facet plan --max-tool-turns 1`
  run against the planning fixture returned `{"status":"fixture-loaded"}`.
- **`tools_deny(subagent)` gate:** the exact inherited-union denial gate
  **failed** — the runtime rejected `storm-fixer`/`storm-designer` at load time
  because the harness-managed `subagent` tool cannot appear in a subagent's
  `tools_deny` list (the documented runtime error behind the approved deviation
  above).
- **What was *not* proven:** inherited-union denial filtering was **not**
  supported on 0.5.9 and must not be claimed anywhere. The approved redesign
  enforces the no-spawning boundary with `allow_subagent_spawn: false` plus
  coordinator convention, and the smoke scenarios below record enforcement as
  directive/classifier-level, not a physical sandbox.

## Authority and route rules

| Phase or intent | Authority/owner | Contracted effects |
|---|---|---|
| Scope | BMAD planning | `epics.md` and scope changes |
| Authoring | upstream `bmad-build`, invoked by `storm-build author` | grilled artifact with verified seam transfer, optional spec review, publication |
| Publication | `storm-linear publish` inside the author wrapper | story-key-anchored Linear specification |
| Implementation | upstream `bmad-build`, invoked by `storm-build implement` | gated open, implementation, tests, review, close |
| Validation/review | `storm-build validate` or standalone review surface | evidence/findings; wrapper validate has no publish/open/close |
| Readiness, status, validation, repair, local projection | `bmad-sprint-planning` | internal planning intents and `sprint-status.yaml` |

- Before publication, `sprint-status.yaml`, `epics.md`, and the story file are
  authoritative. After publication, Linear owns implementation context and
  execution state. If the phase is unknown, stop and ask rather than overwrite.
- `bmad-sprint-planning` is the single native owner of readiness, the sprint
  status view, validation, repair, and the local sprint-status projection. A
  request such as “what's the status” uses its status intent, not a separate
  status workflow. Retired `bmad-sprint-status` and
  `check-implementation-readiness` compatibility calls forward to the installed
  planner's corresponding intents.
- Planning is deterministic. Inference is a warning-only fallback when
  deterministic inputs are unavailable, and legacy `sprint-plan`/status handling
  remains compatible. Storm does not invent a replacement output schema.
- Headless operation uses the installed planner's documented native headless
  intent and JSON interface. Use `--autonomous` only if the installed planner
  explicitly advertises it; the current script is not claimed to universally
  accept that flag. Otherwise use the native headless intent, including natural
  language such as “run sprint planning headless.”
- Polytoken planning is read-only until an approved `handoff_plan` activates a
  saved goal; only then may execution open the issue and mutate implementation
  files.
- Canonical implementation chain:
  `plan` facet → `write_plan` → plan reviewed → `handoff_plan` approved → goal
  activated → `execute` facet → `read_goal` verified → `storm-linear open` →
  open verified → mutation.
- Review rounds come only from `review_loop_max_rounds`; fixes require a complete
  fresh review pass; non-convergence leaves the issue `In Progress`.
- The explicit `storm-build implement` request authorizes exactly one
  task-scoped completion commit after clean verification; it does not authorize
  push. The commit must be created and verified before the completion comment or
  Linear `Done`; workers never commit independently.
- The execute session that opens a target owns closing it. A child-ticket close
  reconciles nothing and never closes, mutates, or reconciles the parent story.
- `storm-build validate` does not publish, open, close, refresh readiness, or
  reconcile sprint status. Standalone validation, if present, is transitional or
  upstream-owned compatibility only and is not a Storm dependency.

## Override inventory and migration blockers

The versioned Storm override inventory is exactly:

- `bmad-agent-dev.toml`
- `bmad-agent-pm.toml`
- `bmad-build.toml` — upstream Build guidance, not the lifecycle wrapper
- `bmad-sprint-planning.toml` — internal planning intents and projection guidance
- `bmad-retrospective.toml` — lean evidence and proposal-only follow-up
- `bmad-code-review.toml` — standalone review completion wiring to
  `storm-cross-review`
- `bmad-correct-course.toml` — scope-change completion wiring to
  `storm-linear mirror`

The deprecated consumer files `bmad-create-story.toml`, `bmad-dev-story.toml`,
and `bmad-quick-dev.toml` are migration blockers, not installed templates and
not accepted lifecycle hooks. `storm-setup check` reports them and requires
operator-led migration into the current inventory. It never installs a second
Storm hook for an upstream shim. After every BMAD update or upstream
`quick-update`, run `storm-setup check`; no blanket "quick-update is always
safe" claim is made.

## Approved divergence ledger (D1–D17)

Operator-approved dispositions for divergences found during the v7 wrapper
migration. Status legend: **repair** = change directives/tests to match the
canonical rule; **retire** = remove the divergent path; **allow** = divergence is
accepted and documented.

| ID | Divergence | Disposition | Canonical rule |
|---|---|---|---|
| D1 | Command-name drift between docs, help, and overrides | repair | Upstream `bmad-build` is canonical; `storm-build` is the explicit Storm lifecycle wrapper; old upstream names warn and forward directly. |
| D2 | Direct Build customization attempted to own phase lifecycle | retire | Build's activation/route metadata/completion boundary is unsafe for Storm lifecycle hooks; use `storm-build`. |
| D3 | Direct Build or shim calls caused tracker side effects | repair | Direct calls are unwrapped; only explicit `storm-build` subcommands own publish/open/close. |
| D4 | Planner calls duplicated across hooks | repair | Author has exactly one readiness call; implementation has exactly one reconciliation for a story target and zero for a child. |
| D5 | Review-loop limits hard-coded in several places | repair | Exactly one setting, `review_loop_max_rounds`, is read; templates reference it by name. |
| D6 | Commit/close behavior varied by route | repair | `storm-build implement` authorizes one task-scoped completion commit; every story or child ticket must complete and verify that commit before comment/close, while push remains separately authorized. |
| D7 | A worker owned tracker/commit/close independently | retire | Retired; any retained worker is bounded and parent-controlled and never owns tracker, commit, or close. |
| D8 | References to retired or archived workflows remained active | repair | Retired names appear only in tested compatibility or migration context and are not active advertising. |
| D9 | Parallel authoritative brief/spec keys | repair | One artifact lifecycle: BMAD authoring artifact before publication, published Linear specification after. |
| D10 | Fixed native reviewer-layer names were treated as a contract | retire | Build and standalone review surfaces are observable at their boundaries; internal layer labels are not advertised. |
| D11 | Ticket slicing was a mandatory workflow step | allow (reduced) | Slicing remains a thin, post-publication, operator-invoked adapter to `storm-linear slice`. |
| D12 | Background workers lacked dependency/ownership rules | repair | Dependency and file/subsystem ownership are enforced mechanically by `skills/storm-orchestrate/scheduler.py`. |
| D13 | Substring-only confidence in workflow conformance | repair | Executable workflow scenarios and fixtures are contract evidence; smokes are live observations, not proof of upstream routing. |
| D14 | Provenance ambiguity for generated files | repair | Generated ownership, version pinning, archive markers, and setup checks keep consuming-project copies as projections of `bmad-storm`. |
| D15 | A separate status workflow competed with sprint planning | retire | Planner status/readiness/validation/repair are internal planning intents; retired compatibility names forward there. |
| D16 | Cross-system publish/close sequences were described as atomic | repair | Report each system's completed or failed side effect; publication/readiness and Done/reconciliation are not atomic. |
| D17 | Retrospectives defaulted to theatrical or unsourced output | repair | Default to lean, sourced, headless-capable evidence; optional party/role-play and proposed actions only. |

## Canonical wrapper mapping

| Intent | Canonical route | Tracker boundary |
|---|---|---|
| Authoring | `storm-build author <story-key>` → grill captures seam input → upstream Build → wrapper verifies artifact → optional review/publish → one planner readiness call | Missing `Seams & test points` is a hard stop before review/publication. |
| Implementation | `storm-build implement <story-key-or-issue>` → Polytoken handoff/open → TDD/build → review → close → one story-only planner reconciliation | Child targets receive no planner reconciliation. |
| Validation/review | `storm-build validate <scope>` → Build validation/review → optional cross-review | No publish, open, close, readiness, or sprint reconciliation. |
| Status/readiness/validation/repair | internal intents of `bmad-sprint-planning` | Single native owner of local projection. |
| Standalone code review | `bmad-code-review` + `storm-cross-review` | Independent review surface; not renamed or removed. |
| Direct upstream Build | `bmad-build` or a deprecation shim | Unwrapped by Storm; no automatic tracker/planner effects. |

### Compatibility and migration-only mapping

| Migration name | Destination/behavior | Rule |
|---|---|---|
| `bmad-create-story` | upstream `bmad-build` | Warn, then forward the original input directly; no Storm wrapper. |
| `bmad-dev-story` | upstream `bmad-build` | Warn, then forward the original input directly; no Storm wrapper. |
| `bmad-quick-dev` | upstream `bmad-build` | Warn, then forward the original input directly; no Storm wrapper. |
| `bmad-sprint-status` | planner status intent | Retired compatibility name; forward to installed `bmad-sprint-planning`. |
| `check-implementation-readiness` | planner readiness intent | Retired compatibility name; forward to installed `bmad-sprint-planning`. |
| `validate-story` | `storm-build validate` or upstream compatibility | Transitional/upstream-owned only; not a Storm dependency. |
| `/create-story` | `storm-build author <story-key>` | Delegates to the explicit Storm author wrapper. |
| `/implement` | `storm-build implement <story-key-or-issue>` | Delegates to the explicit Storm implementation wrapper. |
| `/quick-dev` | unwrapped upstream `bmad-build` | Forwards directly; no Storm lifecycle effects. |
| `/wayfinder`, `story-plan`, `story-execute` | — | Retired; not advertised as active routes. |

The slash aliases have fixed destinations: `/create-story` delegates to
`storm-build author <story-key>`, `/implement` delegates to
`storm-build implement <story-key-or-issue>`, and `/quick-dev` forwards directly
to unwrapped upstream `bmad-build`. `/to-spec` is retired; direct publication
would bypass the wrapper's single readiness call.

## Artifact lifecycle and partial failures

1. **Before publication:** `epics.md`, `sprint-status.yaml`, and the BMAD story
   file own scope and context.
2. **Author publication:** `storm-build author` runs the artifact and
   `storm-linear publish`, then makes its one planner readiness call. The two
   systems are separate; the wrapper does not claim an atomic transaction.
3. **Publish success, readiness failure:** the Linear issue remains published
   but blocked while the local readiness projection is unresolved. The operator
   uses `bmad-sprint-planning` to inspect and repair it.
4. **Implementation close:** `storm-build implement` closes the target in
   Linear. Only a story target gets the one planner reconciliation; a child
   target gets none.
5. **Done success, reconciliation failure:** Linear remains `Done` and requires
   planner repair. It is not rolled back and the sequence is not atomic.

`storm-reconcile` reports drift across scope, Linear, and the local projection.
After the operator approves a local repair, it hands that repair to
`bmad-sprint-planning`; it does not invoke the planner itself and never writes
`sprint-status.yaml` directly.

## Retrospective contract

Retrospectives use a lean, evidence-based default and support headless use.
Party/role-play is optional. Findings must cite their source evidence. The
aggregate view calls out duplication, pattern divergence, god-class growth,
cross-story seams, and specification drift when supported by evidence.

The resulting actions are proposals, never auto-applied changes. Product or
scope changes go through `bmad-correct-course`; harness/process changes go
through `storm-harness-improvement`.

## Transcript and event format

Conformance scenarios are event transcripts validated deterministically by
`skills/storm-contract/validate_transcript.py` against the machine-readable
contract. A transcript is a JSON object:

```json
{
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

- `max_rounds` is optional; its default comes from the contract's
  `review_loop_max_rounds`. Completion-commit policy overrides are rejected:
  every implementation close requires a completed commit.
- `issue_opened` carries `target: "story" | "child"`; close guards match
  against it.
- Event vocabulary (defined in `transitions` in the contract) includes
  `scope_resolved`, `grill_confirmed`, `spec_review_completed`,
  `publish_succeeded`, `publish_failed`, `sprint_ready_updated`,
  `slice_completed`, `plan_created`, `plan_reviewed`, `handoff_approved`,
  `handoff_rejected`, `handoff_cancelled`, `execute_entered`, `goal_verified`,
  `issue_opened`, `open_verified`, `mutation`, `seam_confirmed`, `red_evidence`,
  `green_evidence`, `native_review_passed`, `cross_review_passed`,
  `finding_dispositioned`, `fix_applied`, `review_halted_non_converged`,
  `commit_authorized`, `commit_completed`, `completion_commented`,
  `issue_closed`, `child_closed`, `sprint_reconciled`, and
  `child_roll_up_reported`.
- The validator stops at the first violation and reports the event index, the
  state, and the rule. Run it directly:
  `python3 skills/storm-contract/validate_transcript.py <transcript.json>`;
  fixtures live in `tests/fixtures/transcripts/`.

The transcript validator does not prove wrapper call counts or upstream route
selection. Wrapper-specific count and boundary checks belong to the disposable
smoke scenarios below.

Scenario coverage required of the deterministic fixture set: publish success;
rejected or cancelled handoff leaves `Todo` and blocks mutation; absent goal
blocks open; pre-open mutation is rejected; failed open verification blocks
mutation; child-ticket close never closes or reconciles the parent; review fixes
require a complete fresh pass; max-round non-convergence leaves `In Progress`;
commit without explicit authority is rejected; and story close comments before
`Done` then reconciles. Planner call counts and direct Build unwrapped behavior
are wrapper smoke checks, not claims about the upstream renderer.

## Required smoke scenarios (disposable Polytoken sessions)

These are run by a human/operator in a disposable Polytoken session with no
production credentials or tracker writes. They provide live observations of the
wrapper boundary and Polytoken behavior; the deterministic tests prove only the
contract. They do not prove live upstream Build route selection or callback
semantics. Record observations and evidence artifacts per run.

### `smoke_storm_build_wrapper_boundary`

1. Install Storm into a scratch consuming project and `/reload`; confirm no
   definition errors. Run `storm-setup check` and resolve findings first.
2. Invoke direct `bmad-build` with an explicit route, then each deprecated shim.
   Confirm the calls remain upstream/unwrapped: no automatic
   `storm-linear publish`, `storm-linear open`, `storm-linear close`, readiness
   refresh, or sprint reconciliation. Record this as observed wrapper absence,
   not proof of internal upstream routing.
3. Run `storm-build author <story-key>`. Confirm grilling occurs before Build
   and captures `Seams & test points` as explicit input to the Build authoring
   request. Confirm the completed artifact carries that list before optional
   spec review/publication; if it does not, confirm the wrapper stops without
   publishing. For a valid artifact, confirm exactly one planner readiness call
   occurs and Storm does not write `sprint-status.yaml` directly.
4. Force planner/readiness failure after a successful Linear publish. Confirm
   the issue remains published but blocked and that repair is directed to
   `bmad-sprint-planning`.
5. Run `storm-build validate <scope>` with optional cross-review enabled.
   Confirm no Linear publish/open/close and no sprint/readiness side effect.
6. Run `storm-build implement <story-key>` through the Polytoken plan,
   handoff, goal, open, TDD, review, and close gates. Confirm exactly one
   planner reconciliation after a story-target `Done`.
7. Run `storm-build implement <child-ticket>` and close the child. Confirm no
   planner reconciliation and no parent close, mutation, or projection change.
8. Force story-target planner reconciliation failure after Linear `Done`.
   Confirm Linear remains `Done` and repair ownership is reported as
   `bmad-sprint-planning`.

### `smoke_plan_handoff_goal_open_gate`

1. Start `storm-build implement <story-key>` against a fixture story whose issue
   is `Todo`. Confirm the Polytoken `plan` facet is used and
   `storm-linear open` is not called before handoff approval.
2. Record a plan with `write_plan`, then call `handoff_plan`. **Reject** the
   handoff. Expected: issue stays `Todo`; no implementation file changes; the
   session reports the halt.
3. Re-plan and approve the handoff. Expected: saved goal active, facet
   `execute`; `read_goal` returns the goal; only then `storm-linear open` moves
   the issue to `In Progress`; mutation begins after open is verified.
4. Negative probe: in a fresh session without an active goal, attempt
   `storm-linear open`. Expected: the directive halts before opening and reports
   that plan integration must produce a goal. (Directive-level enforcement —
   observe and record actual behavior.)

### `smoke_role_tool_contracts`

1. After the install above, invoke each read-only role against fixtures and
   confirm no mutation tools are exposed and no mutations occur.
2. Confirm the coordinator routes plan-phase work to read-only roles.
3. Deliberately attempt a Fixer/Designer dispatch from the `plan` facet with the
   full 0.5.9 deny set (every lifecycle/Linear/shell denial except the
   harness-managed `subagent`, which 0.5.9 cannot deny — see the approved
   runtime deviation above). Expected: no observed mutation. Record that
   enforcement here is directive/classifier-level, not a physical sandbox.
4. Enter an approved fixture goal/execution context, then confirm bounded
   writers operate and denied lifecycle tools (tracker mutation, goal/plan/facet
   control, final completion) remain unavailable, and that nested delegation is
   refused (`allow_subagent_spawn: false` plus convention — not a deny-list entry
   on 0.5.9).
5. Exercise `/jobs`, `/todo`, cancellation (confirming it does not undo
   filesystem changes), auto-drained job completion, and the continuation hook
   in its default-off state.

## Audit procedure

1. `python3 -m unittest discover -s tests -v` — all deterministic checks,
   including every transcript fixture.
2. `python3 skills/storm-contract/validate_transcript.py <fixture>` for any new
   scenario before adding it to the fixture set.
3. After any BMAD or Polytoken update: run `storm-setup check` in the consuming
   project before relying on any override, then re-run the suite and the smoke
   scenarios if the update touched facets, goals, hooks, or subagent tool
   contracts.
4. Any new divergence is logged as a D-entry in the ledger above with an
   operator-approved disposition before directives change.
