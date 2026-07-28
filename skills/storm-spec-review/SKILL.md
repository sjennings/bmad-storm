---
name: storm-spec-review
description: Adversarial cross-model spec review panel. Run on a finished story spec BEFORE it is published to Linear - BMAD review lenses via context-free subagents plus external-model reviewers over a self-contained packet, merged into one triage.
---

# Storm Spec Review

Harden a story spec before it becomes authoritative. Follows the shared panel protocol at `../storm-cross-review/reference/panel-protocol.md` — read it first; this skill defines only the packet and the lens roster.

## Packet

Assemble per protocol §1, containing:

1. The full spec under review.
2. The story's `epics.md` section: title, story statement, acceptance criteria, epic-level constraints, cross-story dependencies.
3. Glossary entries (`docs/bmad-output/project-context.md`) for every domain term the spec uses.
4. Project invariants relevant to the spec's area, pulled from the root and per-subtree contract files (e.g. save-version policy, coordinate invariants, engine-boundary rules).
5. The review instruction block below.

## Lens roster

**Tier 1 (context-free subagents):**

- `adversarial` — via `bmad-review`, adversarial lens only, on the packet.
- **Testability auditor** — every acceptance criterion and every spec claim must be verifiable with this project's actual machinery (build, unit suites, headless runner, visual procedure at both required resolutions). Flag any AC that cannot be objectively verified, and any verification the spec assumes but the project cannot perform.
- **Scope-boundary auditor** — the spec must fit its story: flag anything that contradicts epic constraints, silently absorbs another story's scope, leaves a stated AC unaddressed, or depends on unbuilt mechanics without saying so.
- **Glossary auditor** — flag terms used contrary to the glossary, and new terms the spec introduces without defining.

**Tier 2 (external models):** the configured `external_reviewers` roster, each with the full packet and instructed: *"You are reviewing a specification, not code. Find defects in the spec itself: ambiguity an implementor could resolve two ways, contradictions, missing failure/edge behavior, untestable claims, hidden scope. Output findings only, in the stated format."*

## After triage

Findings the operator accepts are folded into the spec **now**, before publication; rebuttals are recorded in the review file. Loop per protocol §6. When clean (or halted with operator sign-off on the remainder), return control — the calling hook proceeds to `storm-linear publish`. This skill never publishes and never mutates tracking state itself.
