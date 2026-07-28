# bmad-storm

Custom [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) module for the **August Storm** project harness. Module code: `storm`.

It folds the project's development harness into BMAD's native extension architecture: **Linear** as phase-split source of truth, **grilling** interviews at story authoring and implementation entry, **cross-model spec and code review** panels, mechanical **tracker drift reconciliation**, and the bounded **harness-improvement** loop.

Design doctrine: *module for behavior, baseline overrides for wiring.* No installed BMAD file is ever edited; all wiring goes through the documented-stable customization surface (`persistent_facts`, `activation_steps_*`, `on_complete`) so upstream `quick-update` is always safe. Deep surfaces (e.g. v6.10's `review_layers`, removed on the v7 branch) are deliberately not depended on.

## Skills

| Skill | Role |
|---|---|
| `storm-setup` | Writes and verifies the sparse `_bmad/custom/` overrides; `check` mode audits wiring after upstream updates |
| `storm-grilling` | One-question-at-a-time interview to shared understanding, with glossary/ADR capture (ported from [mattpocock/skills](https://github.com/mattpocock/skills), MIT) |
| `storm-linear` | Tracker operations (publish/open/close/slice/mirror/intake) under the phase-split authority contract in `reference/issue-tracker.md` |
| `storm-spec-review` | Adversarial spec review panel: BMAD lenses + host-selected Polytoken subagents or external CLI reviewers, before publication |
| `storm-cross-review` | Cross-model code review panel after `bmad-code-review`'s native pass; shared `reference/panel-protocol.md` |
| `storm-reconcile` | Three-way drift audit: `epics.md` ↔ Linear ↔ `sprint-status.yaml`, phase-decides rule applied |
| `storm-harness-improvement` | Bounded improvement loop; promotes trajectory lessons into their narrowest authoritative home |

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

Install prompts are stored in `_bmad/storm/config.yaml`: `linear_team`, `linear_team_key`, `grill_on_implement` (`full` | `gaps-only` | `off`), the two host-specific review rosters below, and `review_loop_max_rounds`.

- `external_reviewers`: comma-separated reviewer CLI command names for hosts outside Polytoken (for example, `codex,gemini`); the backward-compatible default is `codex`.
- `polytoken_review_models`: comma-separated fully qualified model references used only under Polytoken; empty by default. Each entry may be a bare model ID such as `codex/gpt-5`, or append Polytoken's optional `<model-id>(<effort-level>)` suffix, such as `codex/gpt-5(high)`. These are examples, not guaranteed installed models or supported effort levels. Effort levels are model-specific; omitting the suffix uses the model's configured default effort.

Polytoken sessions use native subagents and never invoke or fall back to `external_reviewers`. Empty, unavailable, or failed Polytoken model rosters are reported prominently. Detailed backend detection, execution, artifacts, and failure behavior are authoritative in `skills/storm-cross-review/reference/panel-protocol.md`.

Existing installations must rerun the BMAD module installer/update flow to materialize `polytoken_review_models`, then run `> use the storm-setup skill with argument check` to verify wiring. Run the same setup check after any BMAD update.

## How the wiring lands

`storm-setup` writes sparse overrides (deltas only, per BMAD doctrine) into `_bmad/custom/`:

- `bmad-agent-dev.toml`, `bmad-agent-pm.toml` — tracker contract injected agent-wide via `persistent_facts`
- `bmad-create-story.toml` — grilling at authoring; `on_complete` → spec review offer → `storm-linear publish` → `ready-for-dev`
- `bmad-dev-story.toml` — issue → `In Progress` + gated pre-flight grill at entry; `on_complete` → completion record → `Done` → sprint reconcile
- `bmad-code-review.toml` — `on_complete` → `storm-cross-review` merge-and-loop
- `bmad-correct-course.toml` — `on_complete` → `storm-linear mirror`

## Requirements

BMAD v6.10+ with the BMM module; the `linear-server` MCP tools; `uv` (or Python 3.11+) for the customization resolver; and, for Tier 2 cross-model panels, either Polytoken with operator-configured and available fully qualified model IDs or authenticated external reviewer CLIs on non-Polytoken hosts. Missing or failed reviewers are reported and skipped without failing the review step.

## License

MIT. `storm-grilling` adapts `grilling` and `domain-modeling` from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT, © Matt Pocock).
