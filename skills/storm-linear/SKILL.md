---
name: storm-linear
description: Execute tracker operations against Linear under the phase-split authority contract - publish a story spec to its issue, open/close execution state, comment completion records, slice child tickets, and answer "which system owns this status" questions. Use whenever a workflow or hook needs to touch Linear.
---

# Storm Linear — tracker operations

Linear (team `{linear_team}`, key `{linear_team_key}`) is the durable store for epics, stories, specs, and tickets, and owns execution state from `In Progress` to `Done`. BMAD's planning artifacts own scope and pre-publication status. **Neither system is subordinate; each owns its phase, and there is exactly one handoff point.**

## Before any operation

1. Load `{project-root}/_bmad/storm/config.yaml` (`linear_team`, `linear_team_key`).
2. Read `reference/issue-tracker.md` in this skill's directory — the full contract: the three roles, workspace facts, API conventions, the two traps, publishing format, phase-split authority table, and wayfinding operations. Follow it exactly; this SKILL.md is a dispatcher, not a summary you can substitute for it.

## Operations

**`publish <story-key>`** — the handoff. Publish a finished story spec to the story's Linear issue per the contract's *Publishing a story to Linear* section: one issue per story, update in place if it exists, story-key anchor line first, full spec as description, state `Todo`, labels `ready-for-agent` + `type:*`. Then set the story's `sprint-status.yaml` entry to `ready-for-dev`. Called from `bmad-create-story`'s `on_complete`.

**`open <story-key-or-issue>`** — implementation start. Resolve the issue, move it to `In Progress`. The session that opens an issue owns closing it out; say so in the run log. Called from `bmad-dev-story` activation.

**`close <story-key-or-issue>`** — implementation end, only after a clean exit (review loop clean, build and full suite green, work committed). Comment the completion record on the issue **before** changing state: what shipped, verification actually run with results, every review finding declined with its reason, anything deferred to a named follow-up. Then move the issue to `Done`. If it was an unsliced story issue, reconcile `sprint-status.yaml` to `done` under its story key; a child-ticket close reconciles nothing. If exit was not clean, the issue stays `In Progress` — report why instead.

**`slice <story-key>`** — create child tickets under a published story issue in dependency order with native blocking relations, per the contract's *Slicing a story into tickets* section. Only against a published spec.

**`mirror <change-summary>`** — after `bmad-correct-course` or `bmad-sprint-planning` changes scope: create/update Linear issues so every new or rescoped story in `epics.md` has its issue (project = epic, state per phase), and report anything in Linear that no longer maps to a tracked story.

**`intake <description>`** — unsolicited work (a found bug, ticket-shaped work with no story): create an issue labelled `needs-triage` with **no project**; real work then flows through `bmad-correct-course` to get a story.

## Non-negotiables

- Do not create epics or stories in Linear outside `mirror`/`intake` — scope is created and rescoped only through BMAD workflows.
- Respect phase authority: pre-publication, `sprint-status.yaml` wins; post-publication, Linear wins; on disagreement, the phase decides — if you cannot tell the phase, stop and ask rather than overwrite.
- On any Linear write failure: report the failure, print exactly what should have been written, and hand off to the operator. Never silently drop a publication and never leave state half-moved without saying so.
