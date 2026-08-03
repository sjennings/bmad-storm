# bmad-storm

Custom [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) module for the **August Storm** project harness. Module code: `storm`.

It folds the project's development harness into BMAD's native extension architecture: **Linear** as phase-split source of truth, upstream's canonical **`bmad-build`** flow, explicit Storm-managed **`storm-build`** lifecycle wrappers, **grilling** interviews at story authoring and implementation entry, **cross-model spec and code review** panels, mechanical **tracker drift reconciliation**, the bounded **harness-improvement** loop, and a native **Polytoken orchestration package**.

Design doctrine: *module for behavior, baseline overrides for wiring.* No installed BMAD file is ever edited; upstream guidance uses the documented-stable customization surface (`persistent_facts`, `activation_steps_*`, `on_complete`) where appropriate, while Storm lifecycle ownership stays in `storm-build` when Build's callback boundary is unsafe. After any BMAD update or upstream `quick-update`, `storm-setup check` is required before relying on the wiring; Storm does not claim that an update is automatically safe. Deep or removed upstream internals are deliberately not depended on.

## Skills

| Skill | Role |
|---|---|
| `storm-setup` | Writes and verifies the sparse `_bmad/custom/` overrides; `check` mode audits wiring after upstream updates |
| `storm-grilling` | One-question-at-a-time interview to shared understanding, with glossary/ADR capture and required seam agreement (ported from [mattpocock/skills](https://github.com/mattpocock/skills), MIT) |
| `storm-tdd` | Red-green loop at the story's pre-agreed seams, with project gdUnit4 conventions (ported from mattpocock/skills `tdd`) |
| `storm-linear` | Tracker operations (publish/open/close/slice/mirror/intake) under the phase-split authority contract in `reference/issue-tracker.md` |
| `storm-spec-review` | Adversarial spec review panel: BMAD lenses + external-model reviewers, before publication |
| `storm-cross-review` | Cross-model panel after the standalone `bmad-code-review` pass; shared `reference/panel-protocol.md` |
| `storm-reconcile` | Three-way drift audit: `epics.md` ↔ Linear ↔ `sprint-status.yaml`; reports drift and hands approved local repair to `bmad-sprint-planning` |
| `storm-harness-improvement` | Bounded improvement loop; promotes trajectory lessons into their narrowest authoritative home |
| `storm-orchestrate` | Scheduler-centered Polytoken coordination using native todos/jobs and exclusive ownership |
| `storm-council` | Manual advisory multi-model Council with explicit model selection and no silent fallback |
| `storm-status` | Projection of native `/jobs` and `/todo` state with reconciliation visibility; not the sprint-status owner |
| `storm-team` | Approval-gated managed role/profile activation with rollback and `/reload` guidance |
| `storm-doctor` | Read-only machine-readable audit of module, assets, capabilities, hooks, aliases, and projection |
| `storm-conformance` | Deterministic workflow-contract and transcript validation |
| `storm-verification-planning` | Claim/evidence planning before non-trivial changes |
| `storm-codemap` | Explicit architectural map generation without a competing authority |
| `storm-worktrees` | Approval-gated isolated Git lanes and pre-integration checks |
| `storm-clonedeps` | Pinned, read-only direct dependency source inspection |

## Canonical BMAD v7 Build and Storm wrappers

Upstream `bmad-build` is canonical for current BMAD work. Its documented routes
are authoring, implementation, and validation/review. `bmad-create-story`,
`bmad-dev-story`, and `bmad-quick-dev` are upstream deprecation shims: they warn
and forward their original input directly to `bmad-build`.

Direct `bmad-build` and shim calls are intentionally **unwrapped** by Storm.
They do not automatically publish, open, or close Linear work, and they do not
reconcile sprint status. The upstream Build activation happens before its route
selection, exposes no stable selected-route metadata, and completes before
`on_complete`; it therefore cannot safely carry Storm's phase lifecycle hooks.

Use the explicit Storm wrapper when tracker and planner lifecycle behavior is
required:

```text
storm-build author <story-key>
storm-build implement <story-key-or-issue>
storm-build validate <scope>
```

The wrapper owns the explicit route and its boundaries:

- `author` grills before Build, passes the captured `Seams & test points` as
  explicit authoring input, then verifies the completed artifact before the
  optional spec review and publication path, followed by exactly one planner
  readiness call.
- `implement` preserves the Polytoken handoff/open/TDD/review/close chain, then
  reconciles exactly once for a story target and never reconciles a child target.
- `validate` runs Build validation with optional cross-review and has no tracker
  or sprint side effects.

The slash aliases delegate exactly as follows: `/create-story` delegates to
`storm-build author <story-key>`; `/implement` delegates to
`storm-build implement <story-key-or-issue>`; `/quick-dev` forwards directly to
the unwrapped upstream `bmad-build`.

`storm-build validate` is the preferred explicit lifecycle-safe validation
route. Standalone `bmad-code-review` plus `storm-cross-review` remains an
independent review surface; standalone validation may remain transitional or
upstream-owned. See [`docs/dev-story-flow.md`](docs/dev-story-flow.md) for the
full route and migration mapping.

`bmad-sprint-planning` is the single native owner of readiness, the sprint status
view, validation, repair, and the local `sprint-status.yaml` projection. Status
and implementation readiness are internal planning intents: requests such as
“what's the status” use this route, and retired `bmad-sprint-status` and
`check-implementation-readiness` compatibility calls forward here. Planning is
deterministic, with warning-only inference fallback and legacy-compatible
handling. Headless use must follow the installed planner's documented native
headless intent and JSON interface. Use `--autonomous` only after checking that
the installed planner explicitly advertises it; Storm does not claim that the
current script universally accepts that flag.

## Updating BMAD-METHOD and Storm

Treat BMAD updates as migrations, not harmless refreshes. Before updating, inspect
the working tree and commit or back up the project-owned `_bmad/custom/`,
`_bmad/config.toml`, `_bmad/config.user.toml`, and
`_bmad/_config/manifest.yaml`. Future installers may drop undeclared config.
Start with:

```bash
git status --short
```

For installer behavior that is unclear, use:

```bash
npx bmad-method install --help
```

Choose the update path deliberately:

1. **Existing-project interactive update:** run `npx bmad-method install`.
   The installer offers **Quick Update** for a minor/stable refresh, reuses the
   current settings, and refuses major upgrades; **Modify Install** is the
   interactive path for changing the installation or handling a major/channel
   change.
2. **Scripted ordinary refresh:** reuse the configured installation with:

   ```bash
   npx bmad-method install --directory <project> --action quick-update --yes
   ```

3. **Local custom source:** for a local Storm checkout, Quick Update can reread
   that source:

   ```bash
   npx bmad-method install --directory <project> --action quick-update \
     --custom-source /path/to/bmad-storm --yes
   ```

4. **URL/Git custom source:** do not use Quick Update. Use the full update path
   and select the exact official module set to retain:

   ```bash
   npx bmad-method install --directory <project> --action update \
     --modules bmm --custom-source <storm-git-url> --tools opencode --yes
   ```

   `--modules` is an exact set, not an additive selection: replace `bmm` with
   every official module the project must keep. Do not omit non-Storm modules
   from the set. The custom source supplies Storm.
   Upstream `--tools opencode` is valid. For major upgrades or channel changes,
   prefer the interactive Modify Install/full update path and confirm the
   installer behavior with `--help` rather than guessing flags.

After any update, inspect `_bmad/_config/manifest.yaml`, the BMAD config files,
and `_bmad/custom/` for dropped modules, settings, or override drift. Then run
`storm-setup check` and resolve every finding; no automatic update is safe to
use until that check passes. For OpenCode or Polytoken projects, also run the
applicable project-local asset manager `check`, then reload the host. Run
`storm-doctor` and the relevant disposable smoke scenario when the update
touched Storm or Polytoken assets.

If an update fails or drops declared project state, stop and restore the commit or
backup made during preflight before retrying. For a bad Storm Polytoken
projection, inspect the manager's backup and use its documented `rollback` only
after approval; then rerun the asset check and `/reload`. Do not overwrite local
customizations with `--force` casually. Recheck the manifest, configs, custom
overrides, and `storm-setup check` before resuming work.

## Run a story with orchestration

- [Polytoken story walkthrough](docs/polytoken-orchestration.md#run-one-story-through-storm-orchestration-in-polytoken)
- [OpenCode story walkthrough](docs/opencode.md#run-one-story-through-storm-orchestration-in-opencode)

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

For an OpenCode host, `--tools opencode` is a valid upstream selector. If a
host-specific selector is needed, inspect the supported names with
`npx bmad-method install --list-tools`; otherwise use the generic BMAD install
route above.

Install prompts (stored in `_bmad/storm/config.yaml`): `linear_team`, `linear_team_key`, `grill_on_implement` (`full` | `gaps-only` | `off`), `external_reviewers`, `polytoken_review_models`, `review_loop_max_rounds`, `polytoken_team_profile`, `polytoken_role_model_overrides`, `polytoken_council_models`, `polytoken_max_parallel_jobs`, and `polytoken_continue_on_idle` (off by default). Every `storm-build implement` completion requires one verified task-scoped commit before Linear `Done`; push remains separately authorized.

Review backends are host-specific:

- `external_reviewers` configures comma-separated authenticated reviewer CLIs (for example `codex,gemini`) outside Polytoken.
- `polytoken_review_models` configures operator-configured, fully qualified model IDs for Polytoken subagents and is empty by default. Under Polytoken, review uses only operator-configured and available fully qualified model IDs; never invoke or fall back to reviewer CLIs.

After changing either roster, rerun the BMAD module installer/update flow so `_bmad/storm/config.yaml` is refreshed. After any BMAD update, run `> use the storm-setup skill with argument check`.

## Native OpenCode / OMO-Slim route

OpenCode and OMO-Slim are existing runtime prerequisites, not Storm-managed
dependencies. Storm does not install, duplicate, vendor, configure globally, or
replace OMO-Slim, OpenCode providers/presets/hook runtime, or Linear
credentials. The native project-local projection and its restart/reload steps
are documented in [`docs/opencode.md`](docs/opencode.md). Its manager supports
only `install --project-root .` and read-only `check --project-root .`; it
preserves unmarked operator append text and refuses unsafe or conflicting Storm
content rather than overwriting it.

## How the wiring lands

`storm-setup` writes the exact sparse override inventory (deltas only, per BMAD
doctrine) into `_bmad/custom/`:

- `bmad-agent-dev.toml`, `bmad-agent-pm.toml` — tracker contract injected
  agent-wide via `persistent_facts`
- `bmad-build.toml` — upstream Build guidance; it is not the Storm lifecycle
  wrapper
- `bmad-sprint-planning.toml` — internal readiness, status, validation, repair,
  legacy compatibility, and projection guidance
- `bmad-retrospective.toml` — lean evidence and proposal-only retrospective
  behavior
- `bmad-code-review.toml` — standalone native review completion wiring to
  `storm-cross-review`
- `bmad-correct-course.toml` — scope-change completion wiring to
  `storm-linear mirror`

The deprecated consumer files `bmad-create-story.toml`, `bmad-dev-story.toml`,
and `bmad-quick-dev.toml` are migration blockers, not installed templates and
not accepted lifecycle hooks. `storm-setup check` flags them and requires
operator-led merging into the current inventory; it never installs a second
Storm hook for a shim.

## Native Polytoken orchestration

Version 0.5.1 includes Storm-owned Polytoken assets projected by `storm-setup` into a consuming project's `.polytoken/` surface. The package provides Explorer, Librarian, Oracle, Observer, Fixer, Designer, and Councillor roles; scheduler-centered orchestration through native todos/jobs; manual Council; status projection; managed role profiles; deterministic conformance and asset validation; and a read-only doctor.

The shipped Polytoken `plan` and `execute` facets remain authoritative. Plan-phase work routes to read-only roles. Fixer and Designer are bounded writers dispatched only after an approved goal-backed handoff and verified Linear `In Progress`; their definitions deny tracker, goal, plan, facet, finalization, and shell mutation surfaces, and specialists cannot spawn subagents under the runtime-compatible boundary (`allow_subagent_spawn: false` plus coordinator convention — Polytoken 0.5.9 cannot deny the harness-managed `subagent` tool; see `docs/workflow-conformance.md`). Because the shipped `plan` facet exposes `shell_exec`, Storm documents plan safety as directive/permission-classifier enforcement rather than a physical sandbox.

`storm-team activate <profile>` is Storm's managed equivalent of a team profile switch: it validates and swaps the complete managed set, preserves unrelated definitions, records a backup, and instructs the operator to run `/reload`. It is not `/preset` parity. `storm-team rollback` restores the prior managed set when a later reload validation fails.

Continuation is disabled by default. When explicitly enabled, a named stop hook is goal/execute-gated, one-shot per user cycle, auto-drain-aware, and emits an explicit stop outcome on uncertainty or handler failure. It performs no Linear/MCP calls.

The OMO-Slim ideas ported here are scheduler dependency frontiers, exclusive ownership, structured worker results, Council, Observer, verification planning, codemap, approval-gated worktrees, pinned dependency inspection, Oracle simplification, and evidence-based harness improvement. OpenCode and OMO-Slim installation/global configuration, provider presets, hook runtime, ACP subprocess agents, multiplexer panes, desktop Companion, OpenCode job-board injection, and OpenCode recovery code are intentionally omitted; the native project-local extension route is documented separately.

Full architecture, operations, and v0.3.0 migration guide: [`docs/polytoken-orchestration.md`](docs/polytoken-orchestration.md). Canonical workflow contract and audit procedure: [`docs/workflow-conformance.md`](docs/workflow-conformance.md).

## Requirements

BMAD-METHOD v7 with the BMM module; OMO-Slim already installed for the native OpenCode route; installed and authenticated `linear-cli` 0.3.27 or later (a hard requirement); `uv` (or Python 3.11+) for the customization resolver and standard-library Storm validators; optionally, authenticated external reviewer CLIs for cross-model panels outside Polytoken (missing reviewers are skipped with a warning). Storm verifies Linear auth status but never reads credential/token files or configures authentication.

After setup, run `/reload`, then `storm-doctor` and `storm-setup check`. Review the generated asset ownership manifest before enabling writers or continuation. Run the numbered smoke scenarios in `docs/workflow-conformance.md` in a disposable project before using the package on production work.

## License

MIT. `storm-grilling` adapts `grilling` and `domain-modeling` from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT, © Matt Pocock). Polytoken orchestration adapts ideas from [oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim) (MIT). Pinned revisions and adaptation scope: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
