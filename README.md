# bmad-storm

Custom [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) module for the **August Storm** project harness. Module code: `storm`.

It folds the project's development harness into BMAD's native extension architecture: **Linear** as phase-split source of truth, **grilling** interviews at story authoring and implementation entry, **cross-model spec and code review** panels, mechanical **tracker drift reconciliation**, the bounded **harness-improvement** loop, and a native **Polytoken orchestration package**.

Design doctrine: *module for behavior, baseline overrides for wiring.* No installed BMAD file is ever edited; all wiring goes through the documented-stable customization surface (`persistent_facts`, `activation_steps_*`, `on_complete`) so upstream `quick-update` is always safe. Deep surfaces (e.g. v6.10's `review_layers`, removed on the v7 branch) are deliberately not depended on.

## Skills

| Skill | Role |
|---|---|
| `storm-setup` | Writes and verifies the sparse `_bmad/custom/` overrides; `check` mode audits wiring after upstream updates |
| `storm-grilling` | One-question-at-a-time interview to shared understanding, with glossary/ADR capture and required seam agreement (ported from [mattpocock/skills](https://github.com/mattpocock/skills), MIT) |
| `storm-tdd` | Red-green loop at the story's pre-agreed seams, with project gdUnit4 conventions (ported from mattpocock/skills `tdd`) |
| `storm-linear` | Tracker operations (publish/open/close/slice/mirror/intake) under the phase-split authority contract in `reference/issue-tracker.md` |
| `storm-spec-review` | Adversarial spec review panel: BMAD lenses + external-model reviewers, before publication |
| `storm-cross-review` | Cross-model code review panel after `bmad-code-review`'s native pass; shared `reference/panel-protocol.md` |
| `storm-reconcile` | Three-way drift audit: `epics.md` ↔ Linear ↔ `sprint-status.yaml`, phase-decides rule applied |
| `storm-harness-improvement` | Bounded improvement loop; promotes trajectory lessons into their narrowest authoritative home |
| `storm-orchestrate` | Scheduler-centered Polytoken coordination using native todos/jobs and exclusive ownership |
| `storm-council` | Manual advisory multi-model Council with explicit model selection and no silent fallback |
| `storm-status` | Projection of native `/jobs` and `/todo` state with reconciliation visibility |
| `storm-team` | Approval-gated managed role/profile activation with rollback and `/reload` guidance |
| `storm-doctor` | Read-only machine-readable audit of module, assets, capabilities, hooks, aliases, and projection |
| `storm-conformance` | Deterministic workflow-contract and transcript validation |
| `storm-verification-planning` | Claim/evidence planning before non-trivial changes |
| `storm-codemap` | Explicit architectural map generation without a competing authority |
| `storm-worktrees` | Approval-gated isolated Git lanes and pre-integration checks |
| `storm-clonedeps` | Pinned, read-only direct dependency source inspection |

## Install

```bash
# From the project that already has BMAD (bmm) installed:
npx bmad-method install --directory . \
  --custom-source /path/to/bmad-storm \
  --tools claude-code --yes
```

Then finish wiring from your agent:

```
> use the storm-setup skill
```

Install prompts (stored in `_bmad/storm/config.yaml`): `linear_team`, `linear_team_key`, `grill_on_implement` (`full` | `gaps-only` | `off`), `external_reviewers`, `polytoken_review_models`, `review_loop_max_rounds`, `completion_commit_policy`, `polytoken_team_profile`, `polytoken_role_model_overrides`, `polytoken_council_models`, `polytoken_max_parallel_jobs`, and `polytoken_continue_on_idle` (off by default).

Review backends are host-specific:

- `external_reviewers` configures comma-separated authenticated reviewer CLIs (for example `codex,gemini`) outside Polytoken.
- `polytoken_review_models` configures operator-configured, fully qualified model IDs for Polytoken subagents and is empty by default. Under Polytoken, review uses only operator-configured and available fully qualified model IDs; never invoke or fall back to reviewer CLIs.

After changing either roster, rerun the BMAD module installer/update flow so `_bmad/storm/config.yaml` is refreshed. After any BMAD update, run `> use the storm-setup skill with argument check`.

## How the wiring lands

`storm-setup` writes sparse overrides (deltas only, per BMAD doctrine) into `_bmad/custom/`:

- `bmad-agent-dev.toml`, `bmad-agent-pm.toml` — tracker contract injected agent-wide via `persistent_facts`
- `bmad-create-story.toml` — grilling at authoring; `on_complete` → spec review offer → `storm-linear publish` → `ready-for-dev`
- `bmad-dev-story.toml` — Polytoken plans and grills in `plan`, then an approved handoff activates a goal and enters `execute` before issue → `In Progress`; other hosts retain issue-open + gated grill at entry; `on_complete` → completion record → `Done` → sprint reconcile
- `bmad-code-review.toml` — `on_complete` → `storm-cross-review` merge-and-loop
- `bmad-correct-course.toml` — `on_complete` → `storm-linear mirror`

## Native Polytoken orchestration

Version 0.4.0 adds Storm-owned Polytoken assets projected by `storm-setup` into a consuming project's `.polytoken/` surface. The package provides Explorer, Librarian, Oracle, Observer, Fixer, Designer, and Councillor roles; scheduler-centered orchestration through native todos/jobs; manual Council; status projection; managed role profiles; deterministic conformance and asset validation; and a read-only doctor.

The shipped Polytoken `plan` and `execute` facets remain authoritative. Plan-phase work routes to read-only roles. Fixer and Designer are bounded writers dispatched only after an approved goal-backed handoff and verified Linear `In Progress`; their definitions deny tracker, goal, plan, facet, finalization, and shell mutation surfaces, and specialists cannot spawn subagents under the runtime-compatible boundary (`allow_subagent_spawn: false` plus coordinator convention — Polytoken 0.5.9 cannot deny the harness-managed `subagent` tool; see `docs/workflow-conformance.md`). Because the shipped `plan` facet exposes `shell_exec`, Storm documents plan safety as directive/permission-classifier enforcement rather than a physical sandbox.

`storm-team activate <profile>` is Storm's managed equivalent of a team profile switch: it validates and swaps the complete managed set, preserves unrelated definitions, records a backup, and instructs the operator to run `/reload`. It is not `/preset` parity. `storm-team rollback` restores the prior managed set when a later reload validation fails.

Continuation is disabled by default. When explicitly enabled, a named stop hook is goal/execute-gated, one-shot per user cycle, auto-drain-aware, and emits an explicit stop outcome on uncertainty or handler failure. It performs no Linear/MCP calls.

The OmO Slim ideas ported here are scheduler dependency frontiers, exclusive ownership, structured worker results, Council, Observer, verification planning, codemap, approval-gated worktrees, pinned dependency inspection, Oracle simplification, and evidence-based harness improvement. OpenCode installation/configuration, provider presets, ACP subprocess agents, multiplexer panes, desktop Companion, OpenCode job-board injection, and OpenCode recovery code are intentionally omitted.

Full architecture, operations, and v0.3.0 migration guide: [`docs/polytoken-orchestration.md`](docs/polytoken-orchestration.md). Canonical workflow contract and audit procedure: [`docs/workflow-conformance.md`](docs/workflow-conformance.md).

## Requirements

BMAD v6.10+ with the BMM module; the `linear-server` MCP tools; `uv` (or Python 3.11+) for the customization resolver and standard-library Storm validators; optionally, authenticated external reviewer CLIs for cross-model panels outside Polytoken (missing reviewers are skipped with a warning).

After setup, run `/reload`, then `storm-doctor` and `storm-setup check`. Review the generated asset ownership manifest before enabling writers or continuation. Run the numbered smoke scenarios in `docs/workflow-conformance.md` in a disposable project before using the package on production work.

## License

MIT. `storm-grilling` adapts `grilling` and `domain-modeling` from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT, © Matt Pocock). Polytoken orchestration adapts ideas from [oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim) (MIT). Pinned revisions and adaptation scope: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
