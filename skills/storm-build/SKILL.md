---
name: storm-build
description: Run an explicit Storm-managed BMAD lifecycle. Use only as storm-build author <story-key>, storm-build implement <story-key-or-issue>, or storm-build validate <scope>; direct bmad-build and upstream legacy shims are intentionally unwrapped.
---

# Storm Build — explicit lifecycle wrapper

`storm-build` owns Storm's route because the current upstream `bmad-build` does
not expose a supported selected-route or phase callback. Do not infer a route
from `bmad-build` activation steps, mutable sprint state, or its post-workflow
`on_complete` surface. The wrapper's mode and target are the authoritative run
context, captured before any Storm tracker or sprint side effect.

## Syntax and fail-closed parsing

The only supported forms are:

```text
storm-build author <story-key>
storm-build implement <story-key-or-issue>
storm-build validate <scope>
```

Require exactly one mode and a non-empty target. Missing, unknown, or malformed
modes stop immediately and report the accepted syntax. They perform **zero**
Storm tracker operations, sprint-planning calls, sprint-status writes, code
changes, or completion actions. Do not treat a generic request or a quick-dev
request as one of these modes by guessing.

Record the explicit mode, target, target kind, and the wrapper run identifier in
run context before invoking any Storm skill. Retain that context through
completion. Never replace it with a route inferred later from BMAD state.

## Adaptive sprint-planning call

`storm-build` is the only owner of the planner call in the author and
story-implementation paths. `storm-linear publish` and `storm-linear close`
perform only Linear mutations and return responsibility to this wrapper.

When a planner call is required, perform **exactly one adaptive planner call**
using this procedure:

1. Inspect the installed `bmad-sprint-planning` skill's documented usage/help
   for its advertised headless capability and JSON/script interface. Do not
   assume a universal flag or invent renderer metadata.
2. Pass `--autonomous` only when that installed skill explicitly advertises
   that flag. Otherwise invoke the installed native headless intent (for
   example, the documented natural-language headless request) or its documented
   script subcommand with JSON output. Use the exact installed spelling.
3. Inspect the returned result. Treat a non-success result, an unavailable
   advertised interface, or an unparseable result as planner failure. Do not
   retry with another guessed form; report the completed Linear side effect and
   the planner repair required.

The planner owns readiness, status, validate, repair, legacy status output, and
all `sprint-status.yaml` projection writes. This wrapper never writes that file
directly.

## `storm-build author <story-key>`

1. Capture `author`, the story key, and the run context before doing anything
   else. Resolve the story scope from BMAD planning artifacts.
2. Invoke `storm-grilling` in `full` mode **before invoking `bmad-build`**.
   Require shared understanding. Capture the returned **Seams & test points**
   handoff payload as explicit wrapper input; if it is absent, incomplete, or
   the story is too large or unclear, stop and recommend `bmad-correct-course`.
3. Invoke `bmad-build` with an explicit authoring request for the captured story
   key **and the captured Seams & test points payload**. Do not depend on an
   upstream route callback; the wrapper already owns the route.
4. Verify the resulting story/spec artifact contains the captured
   `Seams & test points` payload exactly before offering spec review or allowing
   publication. If the payload is absent or altered, stop with no
   `storm-linear publish` and do not offer publication.
5. After that artifact verification, offer `storm-spec-review`. Fold accepted
   findings into the artifact and record an explicit decline when the operator
   skips it.
6. Invoke `storm-linear publish` for the finished artifact. This writes only
   the Linear publication. If publication fails, report exactly what should
   have been written and do not call sprint planning.
7. After successful publication, call sprint planning exactly once using the
   adaptive procedure above to refresh readiness. If that call fails, report
   **published but blocked before implementation** and direct repair to
   `bmad-sprint-planning`.

## `storm-build implement <story-key-or-issue>`

1. Capture `implement`, the target, and the run context before any tracker
   mutation. Resolve the target with Linear relations and determine whether it
   is the story issue or a child ticket; do not infer this from sprint status.
2. Read `grill_on_implement` from the Storm config and run the configured
   explicit preflight grill. In `full` or `gaps-only` mode, wait for shared
   understanding; in `off`, record that the gate was disabled.
3. Under Polytoken, preserve this order without opening the issue or mutating
   implementation files early:

   ```text
   plan -> review -> handoff_plan -> active goal -> execute -> read_goal
   -> storm-linear open -> verify In Progress -> mutation
   ```

   Use the shipped `plan` facet, record and review the plan, submit
   `handoff_plan`, verify the saved goal after entering `execute`, then invoke
   `storm-linear open` and reread the issue to verify `In Progress`. A rejected
   handoff, missing goal, or failed open verification stops before mutation.
   Outside Polytoken, preserve the same semantic ordering with the host's
   documented equivalent; do not invent facet or mode names.
4. Invoke `bmad-build` with an explicit implementation request for the captured
   target. Bind implementation to `storm-tdd` at the confirmed seams and keep
   the wrapper's route context authoritative.
5. After the Build/native review completes, invoke `storm-cross-review`. Fix or
   explicitly disposition findings and require a fresh complete pass per the
   configured round cap.
6. Inspect shutdown output from every required Godot run, including targeted and
   full-suite runs. Any RID allocation leak, Canvas/CanvasItem RID leak, ObjectDB
   leaked instance, orphan/stray node, or resource still in use is a blocker:
   fix it and rerun; a zero test exit code does not waive the leak. Record
   `godot_shutdown_clean` only when those diagnostics are absent.
7. The explicit `storm-build implement` invocation grants the execute session
   bounded authority for exactly one task-scoped completion commit; it does not
   authorize push. After clean review and verification, create that commit and
   verify it contains the intended task snapshot. A failed commit leaves the
   target `In Progress`. Only after the commit is complete invoke `storm-linear
   close`, which comments before moving the Linear target to `Done`.
8. If the target is the story issue, call sprint planning exactly once through
   the adaptive procedure for reconciliation. If it is a child ticket, do not
   call sprint planning and never close or reconcile the parent. If Linear is
   `Done` but the story reconciliation call fails, report **Linear Done with
   reconciliation repair required**; do not imply rollback.

## `storm-build validate <scope>`

1. Capture `validate`, the scope, and the run context before any work.
2. Invoke `bmad-build` with an explicit validation/review request. The wrapper
   must not publish, open, or close Linear work. It never publishes, opens,
   closes, or reconciles from validation.
3. When code review is requested, invoke `storm-cross-review` after the
   Build/native review and return the combined evidence/findings. Do not call
   sprint planning, reconcile, or write `sprint-status.yaml` from validation.

## Authority and failure reporting

The upstream direct Build workflow remains available, but it is not a Storm
lifecycle. The sparse direct-build customization states this boundary and does
not add route-specific activation or completion hooks. `storm-build` owns only
the explicit wrapper route, its one planner call where specified, and honest
reporting of partial cross-system outcomes; it does not claim cross-system
atomicity or a physical sandbox.
