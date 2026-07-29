---
name: storm-grilling
description: Relentless one-question-at-a-time interview to shared understanding, with domain-model capture into the project glossary and ADRs. Use at story authoring, at implementation entry (per the grill_on_implement gate), or whenever the operator wants a plan, decision, or idea stress-tested.
---

# Storm Grilling

Interview the operator relentlessly about every aspect of the topic until you reach a shared understanding. Walk down each branch of the decision tree, resolving dependencies between decisions one by one.

Adapted from `grilling` and `domain-modeling` in [mattpocock/skills](https://github.com/mattpocock/skills) (MIT, © Matt Pocock), specialized for this project's BMAD layout.

## Configuration

Load `{project-root}/_bmad/storm/config.yaml` for `grill_on_implement`. Project anchors:

- **Glossary**: `{project-root}/docs/bmad-output/project-context.md` — the ubiquitous language. Read it before asking anything; speak in its vocabulary.
- **Decisions**: `{project-root}/docs/adr/`
- **Scope authority**: the story's section in `epics.md` and, once published, the spec on its Linear issue.

## Modes

**`full`** — complete interview. Restate the scope faithfully in glossary vocabulary, then walk every branch: ambiguities, seams and their test points, save/schema implications, AI-vs-player parity, modifier gating, out-of-scope boundaries. **Seam agreement is a required outcome**: before convergence, the operator has confirmed the list of seams under test — the public boundaries where behavior will be verified (see `storm-tdd`). Testing effort goes where this list says, nowhere else.

**`gaps-only`** — for implementation entry when a published spec exists. Do NOT re-interview settled scope. Read the spec, list only what it leaves ambiguous or unstated, probe exactly those, then ask for a single confirmation of shared understanding. If the spec settles everything, say so and ask one confirmation question — a two-minute check, not a second interview.

**`off`** — do not run (the caller should not have invoked this skill; exit stating the gate is off).

## Interview rules

1. **One question at a time.** Provide your recommended answer with each question. Wait for the answer before continuing. Multiple questions at once is bewildering.
2. **Facts are yours; decisions are the operator's.** If a fact can be found in the repo — code, tests, glossary, ADRs, scenario data — look it up rather than asking. Every genuine decision goes to the operator. Never answer your own questions.
3. **Skip what is already settled** by acceptance criteria or the published spec. Probe what they don't cover.
4. **Do not act until the operator confirms** you have reached a shared understanding. If the topic turns out too big or foggy for one session, say so and recommend splitting the story via `bmad-correct-course` instead of pressing on.

## Domain-model capture (during the interview)

- **Challenge against the glossary.** When the operator uses a term that conflicts with `project-context.md`, call it out immediately: "The glossary defines 'step loss' as X, but you seem to mean Y — which is it?"
- **Sharpen fuzzy language.** When a term is vague or overloaded, propose a precise canonical term.
- **Stress-test with concrete scenarios.** Invent edge-case scenarios that force precision about the boundaries between concepts.
- **Cross-reference with code.** When the operator states how something works, check whether the code and tests agree. Surface contradictions — code and tests outrank design prose.
- **Update the glossary inline.** When a term is resolved, update `project-context.md` right then; don't batch. The glossary is vocabulary only — no implementation details, no spec content.
- **Offer ADRs sparingly.** Only when all three hold: hard to reverse, surprising without context, and the result of a real trade-off. Follow the existing ADR format in `docs/adr/`.

## Handoff

When the interview converges, state the shared understanding in a compact summary: decisions made, terms resolved, ADRs recorded, open items deliberately deferred, and — from full mode — the agreed **Seams & test points** list. The calling workflow (`bmad-create-story`) must carry that list into the story draft's dev notes under a `Seams & test points` heading; it is what `storm-tdd` tests against during implementation. This skill itself writes no story files and mutates no tracking state.
