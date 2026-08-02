# Issue tracker contract: Linear

Issues and stories for this repo live in Linear, team **{linear_team}** (key
`{linear_team_key}`). Use the `linear-server` MCP tools — there is no CLI for
this tracker.

## The three roles

This repo splits planning, storage, and implementation across systems. Know
which one you are acting as before you write anything.

| Role | System | Owns |
|---|---|---|
| **Scoping** | BMAD planning workflows | Creating and changing epic/story scope in `epics.md` |
| **Planning projection** | `bmad-sprint-planning` | Readiness, status, validate/repair, legacy-compatible sprint plan/status handling, and every `sprint-status.yaml` write |
| **Storage** | Linear (team `{linear_team_key}`) | The durable record of epics, stories, specs, and tickets, and execution state |
| **Authoring + implementation** | `storm-build` routes + upstream `bmad-build` | Turning scoped work into a grilled/reviewed spec and working code |

- **BMAD scopes.** `bmad-create-epics-and-stories` (or the current BMM
  planning equivalent) and `bmad-correct-course` are the only sanctioned ways
  to create or rescope an epic or story. New work — including a new bug or a
  mid-sprint change — goes through `bmad-correct-course`, not through a
  hand-written Linear issue.
- **Sprint planning owns the projection.** Readiness, status, validation,
  repair, legacy status compatibility, and all parsing/writing of
  `sprint-status.yaml` belong to `bmad-sprint-planning`, using upstream's
  deterministic script. Storm Linear returns responsibility to `storm-build`
  after publication or close; it never invokes the planner or performs that
  write.
- **Linear stores.** Every BMAD epic is a Linear project; every story is a
  Linear issue inside it, carrying the story's spec once published. Large
  stories carry child ticket issues. Linear is where an implementor looks to
  find work and where execution state lives.
- **Storm Build author and implement.** `storm-build author` runs
  `storm-grilling` in full mode before invoking upstream `bmad-build`, carries
  `Seams & test points`, offers `storm-spec-review`, and publishes through
  `storm-linear publish`. `storm-build implement` preserves the Polytoken
  plan/review/handoff/goal/execute/read-goal/open gate, configured grilling,
  storm-tdd, native Build review, `storm-cross-review`, and close.
  `storm-build validate` uses upstream Build and cross-review without tracker or
  planner side effects. Direct `bmad-build` and upstream legacy shims are
  intentionally unwrapped. These routes do not invent scope. If an implementor
  finds the story wrong or incomplete, stop and report — the fix is a
  `bmad-correct-course` run, not an edit to the Linear issue.

**Do not create epics or stories directly in Linear.** An issue with no BMAD
origin is untracked work: `epics.md` will not know about it and the next BMAD
run will not reconcile it. Triage intake (`storm-linear intake`) is the
documented exception, and intake issues carry no project until BMAD gives them
a story.

## Workspace facts

- **Team**: `{linear_team}` (`{linear_team_key}`) — the only team. Pass
  `team: "{linear_team}"` on create.
- **Projects** are the BMAD epics, named identically to their `### Epic N:`
  headings in `epics.md`. Epics gated in the roadmap must not receive stories
  until their named gate clears.
- **States**: `Backlog`, `Todo`, `In Progress`, `Done`, `Canceled`, `Duplicate`.
- **Labels** beyond triage: `type:task`, `type:bug`, `meta`, `deferred`,
  `retrospective`, `ready-for-agent`, `needs-triage`. Legacy label families
  (`wave:*`, `project:*`, `mode:*`) predate the current roadmap — do not apply
  them to new work without checking they still mean something.

## Conventions

- **Create**: `save_issue { team, title, description, project?, labels? }`
- **Read**: `get_issue { id: "{linear_team_key}-123", includeRelations: true }`,
  then `list_comments { issueId }`
- **List**: `list_issues { team, state?, label?, project?, includeArchived: false }`
- **Comment**: `save_comment { issueId, body }`
- **Close**: `save_issue { id, state: "Done" }`. Use `Canceled` for won't-fix,
  `duplicateOf` + `state: "Duplicate"` for duplicates.

### Two traps

1. **`labels` replaces the entire label set.** To *add* a label, `get_issue`
   first and send the full intended array. Sending one label name strips every
   other label on the issue.
2. **`list_issues` defaults `includeArchived: true`.** Pass
   `includeArchived: false` for any query about live work — a large archived
   backlog will otherwise pollute results.

Descriptions and comment bodies are Markdown: literal newlines, never `\n`
escapes.

## Publishing a story to Linear

A story is published when `storm-build author` has grilled and optionally
spec-reviewed the artifact, invokes `storm-linear publish`, and receives a
successful Linear write. One issue per story; if the issue already exists,
update it in place — never create a second issue for the same story key.

- **Project**: the Linear project matching the story's epic.
- **Title**: the `epics.md` story heading, without the `Story N.M:` prefix.
- **State**: `Todo`.
- **Labels**: `ready-for-agent` (a published spec is already specified, so it
  never enters as `needs-triage`), plus `type:task` or `type:bug`.
- **Description**: the story key line, then the full spec. The issue
  description **is** the durable spec:

  ```markdown
  **Story key:** `1-11-enforce-indirect-fire-combat-cap`

  ## Problem Statement
  …

  ## Solution
  …
  ```

The **story key** line is the round-trip anchor between Linear and
`sprint-status.yaml`. Publication itself does not write the local projection and
does not invoke planning; after a successful Linear write, return to
`storm-build author`, which performs exactly one capability-checked headless
planner call. If that planner operation fails, the issue is published but
blocked before implementation and requires planner repair.

## Slicing a story into tickets

`storm-linear slice` is the only sanctioned way to create implementation
tickets, and it runs only against a published spec. Small stories skip it and
are implemented straight from the spec.

- **Create** each ticket as a **child issue** of the story issue, in dependency
  order: `save_issue { team, title, parentId: "<story issue>", labels:
  ["ready-for-agent", "type:task"] }`.
- **Blocking**: native relations — `save_issue { id: "<ticket>", blockedBy:
  [...] }`. Read with `get_issue { id, includeRelations: true }`; clear with
  `removeBlockedBy`. A ticket is unblocked when every blocker sits in a
  completed or canceled state.
- **Execution**: implementors work the frontier (tickets whose blockers are
  all done) and move ticket state `In Progress` → `Done`. A ticket session
  never closes or modifies the parent story issue.
- **Roll-up**: when every child ticket is done, the story issue can be closed
  by its own implementation session. The resulting local projection is
  reconciled by `bmad-sprint-planning`, not by the child session or
  `storm-linear`.

## Status ownership is split by phase

Each system owns the phase it actually drives. There is exactly one handoff
point, and the cross-system operations are not atomic.

| Phase | Authority | Notes |
|---|---|---|
| `backlog` → publication | **BMAD planning + bmad-sprint-planning** | BMAD scope and readiness projection are local; Linear is not authoritative for an unpublished story. |
| **publish** (`storm-linear publish`) | — | The handoff. Spec lands on the Linear issue in `Todo`; `storm-build author` performs the one planner readiness call afterward. |
| `In Progress` → `Done` | **Linear** | Implementors move Linear state — on tickets when the story is sliced, on the story issue when not. |
| story closes | **bmad-sprint-planning after Linear close** | `storm-linear close` records and moves the issue to `Done`; `storm-build implement` performs the one planner reconciliation call for a story target. |

Rules that follow:

- **Before publication,** BMAD planning and the sprint planner's local
  projection win. Do not read execution intent from Linear for a story that was
  never published.
- **After publish,** Linear wins for execution state. An implementor moving an
  issue to `In Progress` is the real state. Do not update `sprint-status.yaml`
  mid-implementation.
- **On close,** `storm-build implement` reconciles once through
  `bmad-sprint-planning` for a story target only. A successful Linear `Done`
  transition followed by planner failure leaves Linear `Done` and requires
  repair; it is not rolled back. A child-ticket close reconciles nothing.
- **If they disagree,** the phase decides. If you cannot tell which phase a
  story is in, stop and ask; do not guess and overwrite.
- **Storm Linear never invokes the planner or writes sprint status.** It returns
  responsibility to `storm-build`, which reports both the Linear result and the
  planner result.

`storm-reconcile` audits all of the above mechanically; run it whenever drift is
suspected and after any bulk change.

## Unsolicited intake

A bug you found, a question, ticket-shaped work with no story behind it: create a
Linear issue on team `{linear_team}` labelled `needs-triage`, with **no project**.
Leaving it project-less is the signal that it has no epic home yet. Anything
that turns out to be real work goes through `bmad-correct-course` to get a
story, and the intake issue is closed as a duplicate of the published story.

## Fetching work

`get_issue { id, includeRelations: true }` followed by `list_comments { issueId
}`. If the issue is a child ticket, read the parent story issue too — the
parent's description is the spec, and a ticket alone is not it. Legacy issues
may carry a **Brief:** pointer to a retired on-disk file; if the file is gone,
the issue's spec (or its published-spec comment) is the authority.
