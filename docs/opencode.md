# Native OpenCode / OMO-Slim route

Storm integrates with an existing OpenCode installation and an already-installed
OMO-Slim runtime. It does not install, duplicate, vendor, configure globally, or
replace either runtime. It also does not configure or replace OpenCode providers,
presets, hook runtime, or Linear credentials.

## Prerequisites

- BMAD with the BMM module is installed in the consuming project.
- OMO-Slim is already installed and available to OpenCode.
- `linear-cli` 0.3.27 or later is installed and authenticated. This is a hard
  requirement. Storm verifies auth status but never reads credential/token files.

Install or update BMAD using the paths in the repository README. Upstream
`--tools opencode` is currently valid; use `npx bmad-method install --list-tools`
when checking other supported selectors. For a first install with a local Storm
source, the shape is:

```bash
npx bmad-method install --directory <project> \
  --custom-source /path/to/bmad-storm --tools opencode --yes
```

For URL/Git custom sources, use the full `--action update` path from the README,
not Quick Update. Before updates, back up or commit the project-owned BMAD
configuration and overrides listed there. Do not invent a Polytoken BMAD tool
identifier: upstream BMAD has no `--tools polytoken` selector.

## Project-local bootstrap

After BMAD installs the `storm` module, the module-owned OpenCode asset source is
`_bmad/storm/skills/storm-setup/assets/opencode/`. Its project-local manager is:

```text
_bmad/storm/skills/storm-setup/assets/opencode/scripts/manage_opencode_assets.py
```

Run it from the consuming project root:

```bash
python3 _bmad/storm/skills/storm-setup/assets/opencode/scripts/manage_opencode_assets.py \
  install --project-root .
```

The install creates and the check validates the exact project-local Storm skill
links shipped by the module under:

- `.opencode/skills/storm-*`; and
- `.opencode/oh-my-opencode-slim/orchestrator_append.md`.

The append file contains one marked Storm orchestrator block. The manager
preserves unmarked operator append text. The installer refuses collisions and
modified or malformed Storm blocks, as well as unsafe symlinked containers,
rather than overwriting them. A later policy update that changes the shipped
append requires explicit manual operator review; it is not automatically replaced.

It does not modify the global OpenCode installation, OMO-Slim source/runtime,
providers, presets, hook runtime, or credentials. After `install`, restart
OpenCode or run its native reload command (`/reload` where supported) before
using the projected assets. `check --project-root .` is read-only and does not
need a reload.

## Run one story through Storm orchestration in OpenCode

This walkthrough uses the project-local Storm projection and the OpenCode
coordinator. It does not install or globally configure OpenCode or OMO-Slim.

1. **Preflight and install.** Ensure BMAD with BMM, authenticated
   `linear-cli` 0.3.27 or later, and the existing OMO-Slim runtime are present. Follow
   [the BMAD update checklist](../README.md#updating-bmad-method-and-storm),
   including the backup/commit of `_bmad/custom/`, `_bmad/config.toml`,
   `_bmad/config.user.toml`, and `_bmad/_config/manifest.yaml`. Use
   `--tools opencode` for the BMAD install/update; do not pass a fabricated
   Polytoken selector.
2. **Project-local assets.** From the consuming project root, install the
   module-owned OpenCode projection if needed, then run its read-only check:

   ```bash
   MGR=_bmad/storm/skills/storm-setup/assets/opencode/scripts/manage_opencode_assets.py
   python3 "$MGR" install --project-root .
   python3 "$MGR" check   --project-root .
   ```

   If Polytoken assets are not projected yet, install them using the
   [Polytoken walkthrough](polytoken-orchestration.md#run-one-story-through-storm-orchestration-in-polytoken);
   otherwise run their read-only check too:

   ```bash
   PMGR=_bmad/storm/skills/storm-setup/assets/polytoken/scripts/manage_polytoken_assets.py
   SRC=_bmad/storm/skills/storm-setup/assets/polytoken
   python3 "$PMGR" check --source-root "$SRC" --project-root . --json
   ```

   Run `storm-setup check` and resolve findings before using writers. Reload
   OpenCode with `/reload` (or its native reload command) after installation.
3. **Start the wrapper.** In the OpenCode coordinator, invoke:

   ```text
   storm-build implement <story-key-or-issue>
   ```

   Use the coordinator's native `/todo` and `/jobs` state for scheduling. Do not
   dispatch a writer directly. The scheduler checks dependency frontiers and
   exclusive file/subsystem ownership before a lane is dispatched; overlapping
   ownership and unresolved dependencies are stops, not prompts to override.
4. **Plan and hand off.** The coordinator inspects the Todo story or child issue
   without opening it, then records and reviews the implementation plan. Preserve
   the required semantic order:

   ```text
   plan → reviewed handoff_plan → active goal → execute → read_goal
   → storm-linear open → verify In Progress → mutation
   ```

   When the host exposes Polytoken's `plan` and `execute` facets, use them for
   this transition. Otherwise use the OpenCode coordinator's documented planning
   and goal mechanism; do not invent Polytoken facet names. A rejected/cancelled
   handoff, missing goal, or failed open verification leaves the target unmodified
   or pre-open and blocks the next gate.
5. **Implement and review.** Only after the goal and `In Progress` state are
   verified may the coordinator dispatch a bounded writer. Apply the configured
   `storm-tdd` seams, then run the native Build review and the existing
   `storm-cross-review` loop as configured. Every fix requires a fresh review
   pass. Inspect Godot shutdown output: any RID/Canvas/ObjectDB leak,
   orphan/stray node, or resource still in use blocks completion even with exit
   code zero. Fix and rerun; workers never commit or close independently.
6. **Close and reconcile.** After a clean review, verified task commit, and completion record,
   `storm-linear close` moves the target to `Done`. The wrapper makes exactly
   one `bmad-sprint-planning` reconciliation for a story target. A child-ticket
   target gets no planner reconciliation and never closes or changes its parent
   story projection.
7. **Inspect the run.** Look at `.opencode/skills/storm-*` and the marked
   `.opencode/oh-my-opencode-slim/orchestrator_append.md` for projected assets;
   `/todo` and `/jobs` for live lane/job state; durable review packets and
   completion records for retained evidence; and
   `_bmad/_config/manifest.yaml` for BMAD ownership/version state. `storm-status`
   is only an operational projection of native jobs/todos, not the sprint-status
   owner.

### Recovery and evidence

- If asset check or `/reload` fails, stop before enabling writers. Inspect the
  manager findings and backups; for a bad Polytoken projection, use the
  documented asset-manager `rollback --project-root . --json`, rerun `check`,
  and reload after approval.
- If a lane fails, times out, or is cancelled, inspect its native job output,
  todo state, `partial_changes`, and ownership before rerouting. There is no
  generic automatic retry, and cancellation does not undo filesystem changes.
- If Linear reaches `Done` but planner reconciliation fails, leave Linear `Done`
  and hand local repair to `bmad-sprint-planning`; do not retry the Linear
  transition as if it were atomic.
- Static validators, asset manifests, scheduler checks, and transcript tests
  prove declared contracts. A disposable smoke run is the evidence for live
  tool behavior. Neither proves a physical sandbox or upstream Build route
  callbacks; record observations without turning them into guarantees.

Direct `bmad-build` and its deprecated shims remain unwrapped in OpenCode: they
do not automatically publish, open, close, or reconcile. Use `storm-build` for
the lifecycle above.

## BMAD and Linear authority

- Before publication, BMAD is the authority through its planning artifacts and
  workflows.
- From `In Progress` through `Done`, Linear is the authority.
- `storm-linear` is the sole route for tracker mutations. OpenCode must not
  bypass it with direct tracker calls or invented credentials/endpoints.
- If the authority phase is unknown, stop and ask; do not guess or overwrite.
- Upstream `bmad-build` is canonical for current BMAD work. Its
  `bmad-create-story`, `bmad-dev-story`, and `bmad-quick-dev` deprecation shims
  warn and forward their original input directly to `bmad-build`. Direct Build
  and shim calls are intentionally unwrapped by Storm: they do not automatically
  publish, open, or close Linear work or reconcile sprint status.
- The explicit Storm-managed lifecycle is exposed through:
  `storm-build author <story-key>`, `storm-build implement
  <story-key-or-issue>`, and `storm-build validate <scope>`. The wrapper owns
  route selection and Storm's pre/post lifecycle because upstream does not expose
  a safe phase callback. The OpenCode route only exposes this existing Storm
  wiring; it does not replace BMAD or invent a parallel workflow.
- Slash aliases delegate exactly: `/create-story` delegates to
  `storm-build author <story-key>`, `/implement` delegates to
  `storm-build implement <story-key-or-issue>`, and `/quick-dev` forwards
  directly to unwrapped upstream `bmad-build`.
- `bmad-sprint-planning` is the single native owner of readiness, the sprint
  status view, validation, repair, and the local `sprint-status.yaml`
  projection. Status and implementation readiness are internal planning intents;
  use it for requests such as “what's the status” rather than a separate status
  workflow. Retired `bmad-sprint-status` and
  `check-implementation-readiness` compatibility calls forward here. Use the
  installed planner's documented native headless intent and JSON interface.
  Use `--autonomous` only if the installed planner explicitly advertises it;
  otherwise use natural language such as “run sprint planning headless.”
- `storm-reconcile` reports drift and, after approval, hands local projection
  repair to `bmad-sprint-planning`; it does not invoke the planner itself or
  write `sprint-status.yaml` directly.
