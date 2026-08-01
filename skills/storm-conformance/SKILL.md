---
name: storm-conformance
description: Validate canonical workflow transcripts, aliases, and authority transitions against the machine-readable Storm contract. Deterministic and standard-library only; proves the contract, not live tool behavior. Invoked as storm-conformance or storm-conformance validate <transcript>.
---

# Storm Conformance

Owns executable workflow conformance. The machine-readable source of truth is `skills/storm-contract/workflow-contract.json`; its human companion and the audit procedure live in `docs/workflow-conformance.md`. This skill validates event transcripts and alias mappings deterministically — it does not observe live Polytoken tool behavior (that is the job of the disposable-session smoke scenarios in the conformance doc).

## Validate a transcript

```bash
python3 {storm-module}/skills/storm-contract/validate_transcript.py <transcript.json>
```

- Exit 0 with `"valid": true` means the transcript conforms; exit 1 reports the first violation with the event index, state, and rule.
- Transcript format, event vocabulary, and required scenario coverage are defined in `docs/workflow-conformance.md` (section "Transcript and event format"). Fixtures live in `tests/fixtures/transcripts/`.
- Any new scenario is validated directly before being added to the fixture set.

## Full audit

1. `python3 -m unittest discover -s tests -v` — runs the contract structure, alias-equivalence, and every transcript fixture against the real validator.
2. After any BMAD or Polytoken update: re-run the suite, then `storm-setup check` in the consuming project, then the smoke scenarios if the update touched facets, goals, hooks, or subagent tool contracts.
3. New divergences are logged as D-entries in the approved divergence ledger with an operator-approved disposition before directives change.

## Boundaries

- Read-only over the contract, fixtures, and docs. Never mutates project files, tracker state, goals, or configuration.
- Enforcement honesty: these checks prove the *contract* and recorded event sequences conform. No conformance output may claim a physical sandbox or guaranteed live read-only plan execution — the shipped `plan` facet exposes `shell_exec`, so live enforcement is directive/permission-classifier level.
