---
name: storm-tdd
description: Test-driven development at pre-agreed seams - the red-green loop, what a good test is, where tests go, and the anti-patterns. Use during story implementation whenever building features or fixing bugs test-first.
---

# Storm TDD

TDD is the red → green loop. This skill makes that loop produce tests worth keeping: what a good test is, where tests go, the anti-patterns, and the rules of the loop. Every section applies on every cycle — consult them before and during the loop, not after.

Adapted from `tdd` in [mattpocock/skills](https://github.com/mattpocock/skills) (MIT, © Matt Pocock), specialized for this project's C#/gdUnit4 stack.

Read the glossary (`docs/bmad-output/project-context.md`) so test names and interface vocabulary match the domain language, and respect the ADRs and the `source/*/CLAUDE.md` contract for the area you're touching.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification — "retreating into enemy ZOC applies a step loss" tells you exactly what capability exists — and survives refactors because it doesn't care about internal structure. One logical assertion per test; expected values come from an independent source of truth (the spec, a worked example, a known-good literal), never recomputed the way the code computes them.

## Seams — where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

**Test only at pre-agreed seams.** The seams under test are agreed during grilling and recorded in the story's spec/dev notes under *Seams & test points*. Before writing any test, load that list. **No test is written at an unconfirmed seam** — if implementation reveals a seam the list doesn't cover, stop and confirm it with the operator (a one-question `storm-grilling` gaps exchange), then record it. You can't test everything; agreeing the seams up front is how testing effort lands on the critical paths and complex logic instead of every edge case.

## Project conventions (non-negotiable)

- Unit tests go in the corresponding source-area subtree under `tests/`, named `Method_Condition_ExpectedResult`.
- Random behavior takes an injected `IRandom`; tests use deterministic scripted draws — never live randomness in a test.
- Use scenario bundles under `data/scenarios/` and treat `tests/fixtures/` and visual-test scenarios as evidence anchors; frozen fixtures change only when the story requires reviewed updates.
- `dotnet build` (zero warnings) before any test run; targeted gdUnit4 suite for the loop, full suite before completion. Inspect Godot shutdown output: any RID/Canvas/ObjectDB leak, orphan/stray node, or resource still in use is a blocker even when the test exit code is zero; fix and rerun before completion.
- Expected failures use `Result<T, LoadError>` / typed results — test the typed failure path, don't assert on exceptions for expected conditions.

## Anti-patterns

- **Implementation-coupled** — mocks internal collaborators, tests private methods, or verifies through a side channel (inspecting serialized state instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological** — the assertion recomputes the expected value the way the code does, so it passes by construction and can never disagree with the code.
- **Horizontal slicing** — writing all tests first, then all implementation. Bulk tests verify *imagined* behavior and go insensitive to real changes. Work in **vertical slices**: one test → one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.
- **Over-mocking** — this codebase prefers pure rules with an imperative shell; most core/AI logic needs no mocks at all. Mock only at genuine external boundaries (engine adapters, platform services), never internal collaborators.

## Rules of the loop

- **Red before green.** Write the failing test first, then only enough code to pass it. Don't anticipate future tests or add speculative features.
- **One slice at a time.** One seam, one test, one minimal implementation per cycle.
- **Refactoring is not part of the loop.** It belongs to the review stage (`bmad-code-review` + `storm-cross-review`), not the red → green cycle.
