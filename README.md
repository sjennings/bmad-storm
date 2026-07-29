# bmad-storm

Custom [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) module for the **August Storm** project harness. Module code: `storm`.

It folds the project's development harness into BMAD's native extension architecture: **Linear** as phase-split source of truth, **grilling** interviews at story authoring and implementation entry, **cross-model spec and code review** panels, mechanical **tracker drift reconciliation**, and the bounded **harness-improvement** loop.

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

Install prompts (stored in `_bmad/storm/config.yaml`): `linear_team`, `linear_team_key`, `grill_on_implement` (`full` | `gaps-only` | `off`), `external_reviewers`, `polytoken_review_models`, and `review_loop_max_rounds`.

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

## Requirements

BMAD v6.10+ with the BMM module; the `linear-server` MCP tools; `uv` (or Python 3.11+) for the customization resolver; optionally, authenticated external reviewer CLIs for cross-model panels (missing reviewers are skipped with a warning).

## License

MIT. `storm-grilling` adapts `grilling` and `domain-modeling` from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT, © Matt Pocock).
