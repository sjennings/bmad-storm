---
name: storm-cross-review
description: Cross-model code review panel. Runs AFTER bmad-code-review's native subagent pass - backend-selected Polytoken subagents or external CLI reviewers over a diff+spec packet, merged into the same triage format, looping until clean or max rounds.
---

# Storm Cross Review

Add genuinely different model families to code review. `bmad-code-review`'s native pass already runs same-model context-free subagent layers; this skill runs the shared protocol's host-selected Tier 2 roster over the same material and merges everything into one triage. Follows the authoritative shared panel protocol at `reference/panel-protocol.md` — read it first and use its backend selection and execution procedure unchanged.

## Inputs

- The diff under review (same baseline `bmad-code-review` used — take `{diff_output}` when invoked from its `on_complete`, otherwise compute from the story's `baseline_commit`).
- The story spec (the Linear issue description, fetched via `storm-linear`, or the local spec file when pre-publication).
- The native pass's already-triaged findings, so Tier 2 findings from either backend can be deduped against them.

## Packet

Per protocol §1: the diff; the spec's acceptance criteria and constraints; the invariants for the touched subtrees; and the instruction block: *"Review this diff against the spec and invariants. Find real defects: correctness, edge cases, invariant violations, spec deviations, missing or wrong tests, unverified claims. You must find issues or explicitly justify why none exist. Output findings only, in the stated format."*

## Execution

1. Tier 2 only by default — select and run the cross-model roster exactly as specified by protocol §3 (tier 1 already ran inside `bmad-code-review`). If invoked standalone (no native pass this session), run tier 1 lenses (`adversarial`, `edge-case-hunter`, `verification-gap`) first, per protocol §2.
2. Merge Tier 2 findings from either backend with the native pass's findings per protocol §5 — dedupe across passes, rank up findings independently confirmed by multiple model families.
3. Present the combined triage. Every actionable finding is fixed or explicitly rebutted with a reason.
4. After fixes: re-run build and the full test suite, then loop per protocol §6 — a complete fresh panel pass over the fixed diff using the selected backend, up to `review_loop_max_rounds`. Exit clean, or halt and report non-convergence. These merge, loop, and close-out rules apply identically to Polytoken model subagents and external CLI reviewers.

## Contract with close-out

The implementation session's close-out (`storm-linear close`) may only run after this loop exits clean. The completion record on the issue must include every panel finding that was declined and its rebuttal — a rebuttal that exists only in chat is lost when the session ends. If the loop halted non-converged, the issue stays `In Progress` and the outstanding findings go to the operator.
