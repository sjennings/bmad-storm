# Issue tracker contract: Linear

Issues and stories for this repo live in Linear, team **{linear_team}** (key `{linear_team_key}`). Use the `linear-server` MCP tools — there is no CLI for this tracker.

## The three roles

This repo splits planning, storage, and implementation across systems. Know which one you are acting as before you write anything.

| Role | System | Owns |
|---|---|---|
| **Scoping** | BMAD planning workflows | Creating and changing epic/story scope in `epics.md` |
| **Storage** | Linear (team `{linear_team_key}`) | The durable record of epics, stories, specs, and tickets, and execution state |
| **Authoring + implementation** | BMM implementation workflows + storm hooks | Turning a scoped story into a spec (grilled, reviewed) and working code |

- **BMAD scopes.** `bmad-create-epics-and-stories` (or the current BMM planning equivalent) and `bmad-correct-course` are the only sanctioned ways to create or rescope an epic or story. New work — including a new bug or a mid-sprint change — goes through `bmad-correct-course`, not through a hand-written Linear issue.
- **Linear stores.** Every BMAD epic is a Linear project; every story is a Linear issue inside it, carrying the story's spec once published. Large stories carry child ticket issues. Linear is where an implementor looks to find work and where execution state lives.
- **BMM + storm author and implement.** `bmad-create-story` (with the storm grilling hook) authors the story; `storm-spec-review` hardens the spec; the create-story `on_complete` publishes it via `storm-linear publish`; `bmad-dev-story` (with storm hooks) drives it to done through `bmad-code-review` + `storm-cross-review`. These do not invent scope. If an implementor finds the story is wrong or incomplete, stop and report — the fix is a `bmad-correct-course` run, not an edit to the Linear issue.

**Do not create epics or stories directly in Linear.** An issue with no BMAD origin is untracked work: `epics.md` will not know about it and the next BMAD run will not reconcile it. Triage intake (`storm-linear intake`) is the documented exception, and intake issues carry no project until BMAD gives them a story.

## Workspace facts

- **Team**: `{linear_team}` (`{linear_team_key}`) — the only team. Pass `team: "{linear_team}"` on create.
- **Projects** are the BMAD epics, named identically to their `### Epic N:` headings in `epics.md`. Epics gated in the roadmap must not receive stories until their named gate clears.
- **States**: `Backlog`, `Todo`, `In Progress`, `Done`, `Canceled`, `Duplicate`.
- **Labels** beyond triage: `type:task`, `type:bug`, `meta`, `deferred`, `retrospective`, `ready-for-agent`, `needs-triage`. Legacy label families (`wave:*`, `project:*`, `mode:*`) predate the current roadmap — do not apply them to new work without checking they still mean something.

## Conventions

- **Create**: `save_issue { team, title, description, project?, labels? }`
- **Read**: `get_issue { id: "{linear_team_key}-123", includeRelations: true }`, then `list_comments { issueId }`
- **List**: `list_issues { team, state?, label?, project?, includeArchived: false }`
- **Comment**: `save_comment { issueId, body }`
- **Close**: `save_issue { id, state: "Done" }`. Use `Canceled` for won't-fix, `duplicateOf` + `state: "Duplicate"` for duplicates.

### Two traps

1. **`labels` replaces the entire label set.** To *add* a label, `get_issue` first and send the full intended array. Sending one label name strips every other label on the issue.
2. **`list_issues` defaults `includeArchived: true`.** Pass `includeArchived: false` for any query about live work — a large archived backlog will otherwise pollute results.

Descriptions and comment bodies are Markdown: literal newlines, never `\n` escapes.

## Publishing a story to Linear

A story is published when its authoring run (grilled, spec-reviewed) completes and `storm-linear publish` fires from the create-story `on_complete`. One issue per story; if the issue already exists, update it in place — never create a second issue for the same story key.

- **Project**: the Linear project matching the story's epic.
- **Title**: the `epics.md` story heading, without the `Story N.M:` prefix.
- **State**: `Todo`.
- **Labels**: `ready-for-agent` (a published spec is already specified, so it never enters as `needs-triage`), plus `type:task` or `type:bug`.
- **Description**: the story key line, then the full spec. The issue description **is** the durable spec:

  ```markdown
  **Story key:** `1-11-enforce-indirect-fire-combat-cap`

  ## Problem Statement
  …

  ## Solution
  …
  ```

The **story key** line is the round-trip anchor between Linear and `sprint-status.yaml`. Always include it. Immediately after publication, set the story's `sprint-status.yaml` entry to `ready-for-dev`.

## Slicing a story into tickets

`storm-linear slice` is the only sanctioned way to create implementation tickets, and it runs only against a published spec. Small stories skip it and are implemented straight from the spec.

- **Create** each ticket as a **child issue** of the story issue, in dependency order: `save_issue { team, title, parentId: "<story issue>", labels: ["ready-for-agent", "type:task"] }`.
- **Blocking**: native relations — `save_issue { id: "<ticket>", blockedBy: [...] }`. Read with `get_issue { id, includeRelations: true }`; clear with `removeBlockedBy`. A ticket is unblocked when every blocker sits in a completed or canceled state.
- **Execution**: implementors work the frontier (tickets whose blockers are all done) and move ticket state `In Progress` → `Done`. A ticket session never closes or modifies the parent story issue.
- **Roll-up**: the story issue moves to `Done` only when every child ticket is done; that is the moment the story key is reconciled back into `sprint-status.yaml`.

## Status ownership is split by phase

Each system owns the phase it actually drives. There is exactly one handoff point.

| Phase | Authority | Notes |
|---|---|---|
| `backlog` → publication | **`sprint-status.yaml`** | Story is being scoped/grilled. The Linear issue, if it exists, is not yet authoritative. |
| **publish** (`storm-linear publish`) | — | The handoff. Spec lands on the Linear issue in `Todo`; sprint entry moves to `ready-for-dev`. |
| `In Progress` → `Done` | **Linear** | Implementors move Linear state — on tickets when the story is sliced, on the story issue when not. |
| story closes | — | All tickets done → story issue `Done` → write `done` back to `sprint-status.yaml` under the story key. |

Rules that follow:

- **Before `ready-for-dev`, `sprint-status.yaml` wins.** Do not read execution intent from Linear for a story that was never published.
- **After publish, Linear wins.** An implementor moving an issue to `In Progress` is the real state. Do not update `sprint-status.yaml` mid-implementation.
- **On close, reconcile once.** Setting a Linear issue to `Done` is incomplete until `sprint-status.yaml` records `done` for that story key. The two are consistent at story boundaries, not continuously.
- **If they disagree, the phase decides.** Pre-publish → trust the YAML. Post-publish → trust Linear, and reconcile the YAML. If you cannot tell which phase a story is in, stop and ask; do not guess and overwrite.

`storm-reconcile` audits all of the above mechanically; run it whenever drift is suspected and after any bulk change.

## Unsolicited intake

A bug you found, a question, ticket-shaped work with no story behind it: create a Linear issue on team `{linear_team}` labelled `needs-triage`, with **no project**. Leaving it project-less is the signal that it has no epic home yet. Anything that turns out to be real work goes through `bmad-correct-course` to get a story, and the intake issue is closed as a duplicate of the published story.

## Fetching work

`get_issue { id, includeRelations: true }` followed by `list_comments { issueId }`. If the issue is a child ticket, read the parent story issue too — the parent's description is the spec, and a ticket alone is not it. Legacy issues may carry a **Brief:** pointer to a retired on-disk file; if the file is gone, the issue's spec (or its published-spec comment) is the authority.
