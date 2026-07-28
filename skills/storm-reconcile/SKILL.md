---
name: storm-reconcile
description: Three-way consistency audit of epics.md vs Linear vs sprint-status.yaml with the phase-decides rule applied. Use when drift is suspected, after any bulk scope change, after a BMAD update, or on operator request.
---

# Storm Reconcile — tracker drift audit

Drift between the scope file, the tracker, and the sprint file is handled here mechanically, not by discipline. This skill **reports and proposes; it mutates nothing without operator approval.**

## Load

1. `{project-root}/_bmad/storm/config.yaml` → `linear_team`, `linear_team_key`.
2. The authority contract: `../storm-linear/reference/issue-tracker.md` (phase-split table).
3. `epics.md` (planning artifacts), `sprint-status.yaml` (implementation artifacts), and the live Linear state: all projects, plus `list_issues { team, includeArchived: false }` with relations.

## Checks

**A. Scope ↔ sprint.** Every `epics.md` story has a `sprint-status.yaml` key and vice versa. Orphan sprint keys (no epics section) and unscoped epics stories (no sprint key) are findings.

**B. Scope ↔ Linear.** Every epic maps to a same-named Linear project. Every story with sprint status `ready-for-dev` or later has exactly one Linear issue carrying its story-key anchor line; duplicates are findings. Issues in a project with no BMAD story behind them (and no `needs-triage`/intake explanation) are untracked work — findings.

**C. Status coherence (phase decides).** For each story, compare sprint status against Linear state:

| Sprint says | Linear should be | If it isn't |
|---|---|---|
| `backlog` | no authoritative issue | pre-publish: YAML wins — flag the issue as premature |
| `ready-for-dev` | `Todo` (or `In Progress` if a session opened it) | post-publish: Linear wins — flag YAML if Linear is `Done` |
| `in-progress`/`review` | `In Progress` | post-publish: Linear wins |
| `done` | `Done` | whichever is behind gets a reconcile proposal |

A story whose phase cannot be determined (e.g. issue exists with a spec but sprint still says `backlog`) is a **stop-and-ask** finding — never auto-resolved.

**D. Structural.** Sliced stories: parent issue not `Done` while any child ticket is open; blocking edges only among siblings; every child carries `ready-for-agent`. Completion records: every `Done` issue has a completion-record comment.

**E. Label hygiene.** Live issues carrying only legacy label families (`wave:*`, `project:*`, `mode:*`) or missing `type:*`.

## Report

Write `{implementation_artifacts}/storm-reviews/reconcile-<date>.md`: one section per check, each finding with the evidence from both sides and a **proposed fix** stating which system gets written and under which rule of the contract. Summarize counts up front; "no drift" is a valid, explicit result.

Then present the proposals. Apply only the fixes the operator approves, via `storm-linear` operations and minimal YAML edits, and append an "applied" section to the report. Findings the operator declines are recorded with the reason so the next audit doesn't re-litigate them.
