---
name: storm-linear
description: Execute tracker operations against Linear under the phase-split authority contract - publish a story spec to its issue, open/close execution state, comment completion records, slice child tickets, and answer "which system owns this status" questions. Use from the explicit storm-build authoring and implementation routes whenever a workflow needs to touch Linear.
---

# Storm Linear — tracker operations

Linear (team `{linear_team}`, key `{linear_team_key}`) is the durable store for
epics, stories, specs, and tickets, and owns execution state from `In Progress`
to `Done`. BMAD planning owns scope; `bmad-sprint-planning` owns readiness,
status, validation/repair, legacy status compatibility, and every
`sprint-status.yaml` projection write. **Neither system is subordinate; each
owns its phase, and there is exactly one handoff point.** Storm Linear performs
Linear publication/open/close operations and never invokes sprint planning or
writes the sprint projection itself. `storm-build` owns the one adaptive
headless planner call where the wrapper contract requires it.

## Before any operation

1. Load `{project-root}/_bmad/storm/config.yaml` (`linear_team`, `linear_team_key`).
2. Read `reference/issue-tracker.md` in this skill's directory — the full
   contract: the three roles, workspace facts, API conventions, the two traps,
   publishing format, phase-split authority table, partial outcomes, and
   wayfinding operations. Follow it exactly; this SKILL.md is a dispatcher, not
   a summary you can substitute for it.

## Operations

**`publish <story-key>`** — the handoff from the `storm-build author` route.
Publish a finished story spec to the story's Linear issue per the contract's
*Publishing a story to Linear* section: one issue per story, update in place if
it exists, story-key anchor line first, full spec as description, state `Todo`,
labels `ready-for-agent` + `type:*`. After the Linear write succeeds, return to
the caller: `storm-build author` is responsible for exactly one adaptive,
capability-checked headless `bmad-sprint-planning` call. `storm-linear` never
invokes the planner, writes `sprint-status.yaml`, or assumes an `--autonomous`
flag exists.

**`open <story-key-or-issue>`** — implementation start from the `storm-build`
implementation route. Resolve the issue, move it to `In Progress`, and verify
that state before mutation. The execute session that opens an issue owns closing
it out; say so in the run log.

**`close <story-key-or-issue>`** — implementation end, only after a clean exit
(native Build review plus storm-cross-review clean, build and full suite green,
and `completion_commit_policy` satisfied — under the default `require-explicit`
that means an explicitly authorized, completed commit; under
`allow-without-storm-commit` close may proceed without a Storm-created commit).
Comment the completion record on the issue **before** changing state: what
shipped, verification actually run with results, every review finding declined
with its reason, anything deferred to a named follow-up. Then move the issue to
`Done`. Return to the caller: `storm-build` decides whether this is the story
issue and, only for a story target, performs exactly one adaptive,
capability-checked headless `bmad-sprint-planning` reconciliation call. A child
ticket close never reconciles or closes the parent. `storm-linear` never invokes
the planner or writes the projection. If Linear reaches `Done` but the caller's
planner call fails, report Linear `Done` with repair required. If exit was not
clean, the issue stays `In Progress` — report why instead.

**`slice <story-key>`** — create child tickets under a published story issue in
dependency order with native blocking relations, per the contract's *Slicing a
story into tickets* section. Only against a published spec.

**`mirror <change-summary>`** — after `bmad-correct-course` changes scope:
create/update Linear issues so every new or rescoped story in `epics.md` has its
issue (project = epic, state per phase), and report anything in Linear that no
longer maps to a tracked story.

**`intake <description>`** — unsolicited work (a found bug, ticket-shaped work
with no story): create an issue labelled `needs-triage` with **no project**;
real work then flows through `bmad-correct-course` to get a story.

## Non-negotiables

- Do not create epics or stories in Linear outside `mirror`/`intake` — scope is
  created and rescoped only through BMAD workflows.
- Respect phase authority: before publication, BMAD planning and
  `bmad-sprint-planning`'s projection win; after publication, Linear wins for
  execution state; on disagreement, the phase decides — if you cannot tell the
  phase, stop and ask rather than overwrite.
- Do not parse or write sprint status from this skill. Readiness, status,
  validation, repair, legacy-compatible output, and all sprint projection
  writes belong to `bmad-sprint-planning`.
- On any Linear write failure: report the failure, print exactly what should
  have been written, and hand off to the operator. Never silently drop a
  publication and never leave state half-moved without saying so.
- Publication/readiness and Linear `Done`/reconciliation are separate
  cross-system operations, not atomic transactions. Report the completed side
  effect and the failed side effect honestly; planner ownership remains with
  the calling `storm-build` wrapper.
