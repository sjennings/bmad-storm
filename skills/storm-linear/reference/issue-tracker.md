# Issue tracker contract: Linear

Issues and stories for this repo live in Linear, team **{linear_team}** (key
`{linear_team_key}`). Use `linear-cli` 0.3.27 or later for every tracker read
and write. Storm owns the workflow; the CLI is its transport.

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

## CLI conventions

Preflight once per tracker operation:

```bash
linear-cli --version
linear-cli auth status --output json --compact --no-pager
linear-cli issues get "{linear_team_key}-123" \
  --output json --compact --no-cache --no-pager
```

Authentication may come from `LINEAR_API_KEY`, OAuth, or the OS keyring. Check
only `auth status`; never print the environment value or read token/config files.
Use `--output json --compact --no-cache --no-pager` for reads and parse the JSON.
The installed CLI may emit human text for mutation dry-runs despite JSON flags,
so verify every write by rereading the affected issue, comments, or relations.

- **Create**: `linear-cli issues create "$title" --team "{linear_team}" ...`
- **Read**: `linear-cli issues get "{linear_team_key}-123" --output json --compact --no-cache --no-pager`, then `linear-cli comments list "{linear_team_key}-123" --output json --compact --no-cache --no-pager`
- **List**: `linear-cli issues list --team "{linear_team}" ... --output json --compact --no-cache --no-pager`
- **Update description/spec safely**: construct the JSON payload mechanically, then pipe it to `linear-cli issues update "$issue" --data - --output json --compact --no-pager`
- **Comment**: `linear-cli issues comment "$issue" --body "$body" --no-pager`
- **State**: `linear-cli issues update "$issue" --state "In Progress|Done|Canceled|Duplicate" --no-pager`
- **Relations**: `linear-cli relations add "$from" "$to" --relation blocks`; parent with `linear-cli relations parent "$child" "$parent"`

For multiline Markdown, keep literal newlines in the shell variable or JSON
payload; never encode prose as `\n` escapes by hand. Quote every variable.

### Two traps

1. **Issue-update labels replace the intended label set.** Before changing
   labels, reread the issue and pass every label that must remain. Never use a
   one-label update as an append operation.
2. **Cached reads can conceal a just-completed write.** Verification reads use
   `--no-cache`; a write is not complete until the fresh JSON reflects it.

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

- **Create** each ticket in dependency order with `linear-cli issues create`,
  then parent it using `linear-cli relations parent "$ticket" "$story"`.
  Apply the complete `ready-for-agent` + `type:task` label set at creation.
- **Blocking**: native relations — `linear-cli relations add "$blocker" "$ticket" --relation blocks`. Read with `linear-cli relations list "$ticket" --output json --compact --no-cache --no-pager`; clear with `linear-cli relations remove` using the exact installed help syntax. A ticket is unblocked when every blocker sits in a completed or canceled state.
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

Run `linear-cli issues get "$issue" --output json --compact --no-cache --no-pager`, `linear-cli comments list "$issue" --output json --compact --no-cache --no-pager`, and `linear-cli relations list "$issue" --output json --compact --no-cache --no-pager`. If the issue is a child ticket, fetch the parent story issue too — the parent's description is the spec, and a ticket alone is not it. Legacy issues may carry a **Brief:** pointer to a retired on-disk file; if the file is gone, the issue's spec (or its published-spec comment) is the authority.
