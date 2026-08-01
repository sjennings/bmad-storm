---
name: storm-verification-planning
description: Before non-trivial work, define the claim, uncertainty, failure modes, evidence paths, observability needs, reversibility, and limits. Feeds the plan's acceptance criteria and test strategy.
---

# Storm Verification Planning

Run this before non-trivial implementation — during planning, not after the fact. Its output feeds the acceptance criteria and test strategy of the plan (and, under Polytoken, the `handoff_plan` that gates execution).

## The verification brief

Answer, in order:

1. **Claim** — the single behavioral statement this work must make true.
2. **Uncertainty** — what we do not know that could falsify the claim, ranked.
3. **Failure modes** — how this change can break: wrong behavior, regression elsewhere, data corruption, performance, security. For each, the cheapest observation that would catch it.
4. **Evidence paths** — the concrete tests, fixtures, smoke scripts, and runtime checks that will demonstrate the claim, mapped to failure modes. Name where each lives and who runs it (worker, coordinator, CI).
5. **Observability needs** — what must be visible to verify the work in a running system (logs, metrics, traces, screenshots).
6. **Reversibility** — how the change is undone, and what evidence survives a revert.
7. **Limits** — what this verification does *not* cover, stated explicitly so nobody over-trusts a green suite.

## Approval gates

- Verification-only dependencies (a test library, a fixture generator), persistent instrumentation, and any production debug surface require explicit operator approval before they are added — call them out in the brief rather than smuggling them into the work.
- The brief is evidence for the plan; it never substitutes for the required review gates or the TDD seams of the implementation workflow.

## Integration

- In the `plan` facet, attach the brief to the plan so `plan-reviewer` sees it.
- During execution, the coordinator checks every specialist result against this brief during reconciliation; a result that satisfies its own claim but not the brief's evidence paths is not reconciled.
- At close, the completion record cites which evidence paths ran and their results.
