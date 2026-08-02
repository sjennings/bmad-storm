---
name: storm-setup
description: Write and verify the sparse _bmad/custom/ overrides that wire the storm module into stock BMM workflows. Run once after install, and in check mode after every BMAD update. Invoked as storm-setup [check].
---

# Storm Setup

Wires the narrowly scoped Storm compatibility facts into BMAD through the documented-stable customization surface. This skill owns the overrides so the wiring is reproducible and versioned in the module — never hand-maintained. Current upstream `bmad-build` has no supported route/phase callback, so the explicit `storm-build` skill owns Storm lifecycle routing; direct Build and legacy shim calls remain intentionally unwrapped.

## Preconditions

- The BMM module is installed (`{project-root}/_bmad/bmm/config.yaml` exists). If not, stop: storm requires BMM.
- Storm's own config exists (`{project-root}/_bmad/storm/config.yaml`, written by the installer from module.yaml prompts). If not, tell the operator to re-run `npx bmad-method install` with the storm module selected.
- For the native OpenCode route, OMO-Slim must already be installed; Storm never installs or configures it.
- The `linear-server` MCP must already be installed and configured. This is a hard requirement; Storm does not provide a Linear endpoint or auth flow.

## Install mode (default)

The versioned template inventory is exactly:

- `bmad-agent-dev.toml`
- `bmad-agent-pm.toml`
- `bmad-build.toml` — the only active direct-Build compatibility override; it contains one unconditional wrapper-boundary fact
- `bmad-sprint-planning.toml`
- `bmad-retrospective.toml`
- `bmad-code-review.toml`
- `bmad-correct-course.toml`

The deprecated consumer overrides `bmad-create-story.toml`, `bmad-dev-story.toml`, and `bmad-quick-dev.toml` are migration blockers, not templates. Before installing or checking the inventory:

1. Look for each legacy file under `{project-root}/_bmad/custom/`. If one exists, report it as a blocker and propose that the operator manually merge its intentional customization into `bmad-build.toml`. Never auto-delete, auto-merge, or silently reinterpret a legacy file. Do not install a second Storm hook for a deprecated upstream shim.
2. For every template in the inventory above, confirm the skill or agent it names is actually installed (its directory with a `customize.toml` exists under the tool's skills path or `_bmad/bmm/`). A missing `bmad-build`, `bmad-sprint-planning`, or `bmad-retrospective` target is a hard failure: stop setup/check and report the missing required BMM capability. Other missing targets may be reported and skipped, never written blind.

3. **Check upstream scalar collisions before writing** — read the shipped `customize.toml` for the target. If upstream already supplies a non-empty scalar that Storm would override, especially `workflow.on_complete`, stop and require explicit composition of the two behaviors. Never silently replace a non-empty upstream scalar. This is a hard stop for that install/check operation, not a warning to ignore.
4. **Write or merge** — if `_bmad/custom/<name>.toml` does not exist, copy the template. If it exists, do NOT clobber: diff the existing file against the template, show the operator what storm wants to add or change, and merge only with approval — preserving any non-storm customizations the operator has authored. Storm-owned blocks are delimited so future runs can update them surgically. Legacy files from step 1 are excluded from this merge path.
5. **Verify customization resolution** — run the resolver and confirm the storm fields landed:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py \
     --skill <installed-skill-dir> --key workflow   # or `agent` for agent overrides
   ```

   (Fall back to `python3` if `uv` is unavailable.) The resolved JSON must contain the storm entries (the appended activation steps / persistent facts and, where used, the `on_complete` text). A field that didn't land is a hard finding — report it, don't proceed silently.

6. **Verify the direct-Build boundary, not an invented rendered route contract** — confirm the resolved `bmad-build` customization contains only the unconditional fact that direct Build and upstream create-story/dev-story/quick-dev shims are unwrapped, and that the installed `storm-build` skill advertises exactly `author`, `implement`, and `validate`. Do not claim that rendered `bmad-build` exposes route-specific gates, selected-route callbacks, or phase metadata. Report a hard validation failure if a route-specific Build hook, `on_complete`, inferred route capture, or duplicate Storm lifecycle is present.

7. Never write into `_bmad/core/`, `_bmad/bmm/`, or any installed skill folder. Overrides go in `_bmad/custom/` only.

8. If the consuming project uses the native OpenCode route, also run the
   project-local OpenCode asset manager described below. Its source/module path
   is `{project-root}/_bmad/storm/skills/storm-setup/assets/opencode/`, and its
   manager is
   `{project-root}/_bmad/storm/skills/storm-setup/assets/opencode/scripts/manage_opencode_assets.py`.

Finish with a summary: overrides written, merged, skipped (and why), and verification results. Then remind the operator to confirm `grill_on_implement` and both cross-model rosters in `_bmad/storm/config.yaml`: `polytoken_review_models` supplies fully qualified model references only when running under Polytoken, while `external_reviewers` supplies CLI command names only outside Polytoken. Polytoken does not fall back to the CLI roster.

## Check mode (`storm-setup check`)

Run after every BMAD update. Mutates nothing; reports four classes of problems:

1. **Orphaned overrides** — a `_bmad/custom/*.toml` written by storm whose target skill no longer exists or was renamed upstream. Overrides fail *quiet*, so this is the check that catches upstream renames.
2. **Landing failures** — for each override, re-run the resolver verification from install mode; report any storm field that no longer resolves.
3. **Default collisions** — for each hooked workflow, read the shipped `customize.toml`; if upstream now ships a non-empty default for a scalar Storm overrides (especially `on_complete`), stop and require composition. The check must not bless a silent replacement.

4. **Legacy migration blockers and inventory drift** — flag consumer `bmad-create-story.toml`, `bmad-dev-story.toml`, and `bmad-quick-dev.toml` overrides, propose a manual merge into `bmad-build`, and never delete or merge them automatically. Compare the exact seven-template inventory above against the module and written files; legacy template files are an error, not an expected compatibility hook.

Also compare the templates in `assets/overrides/` against the written files and flag drift in the storm-owned blocks (someone edited the wiring by hand instead of the template). Re-run the direct-Build boundary and `storm-build` explicit-mode validation from install mode; resolver success alone is insufficient, and no renderer-internal route/gate claim is valid.

For a consuming project using OpenCode, also run the OpenCode manager's
read-only `check` procedure described below. Report asset drift and apply
repairs only with operator approval.

Report findings with proposed fixes; apply only what the operator approves.

## Native OpenCode asset projection

The OpenCode module source path is
`{module-root}/skills/storm-setup/assets/opencode/` and, after installation,
`{project-root}/_bmad/storm/skills/storm-setup/assets/opencode/` in the consuming
project. The project-local manager is
`{project-root}/_bmad/storm/skills/storm-setup/assets/opencode/scripts/manage_opencode_assets.py`.
It exposes exactly two procedures. Run these from `{project-root}` when the
native OpenCode route is in use:

```bash
MGR={project-root}/_bmad/storm/skills/storm-setup/assets/opencode/scripts/manage_opencode_assets.py

python3 "$MGR" install --project-root .
python3 "$MGR" check   --project-root .
```

`install` creates and `check` validates the exact project-local Storm skill links
shipped by the module under `.opencode/skills/storm-*`, plus one marked Storm
orchestrator append block in
`.opencode/oh-my-opencode-slim/orchestrator_append.md`. The manager preserves
unmarked operator append text. It refuses collisions and modified or malformed Storm blocks,
as well as unsafe symlinked containers, rather than overwriting them. A later
policy update that changes the shipped append requires explicit manual operator
review instead of automatic replacement.

The manager does not install, vendor, or configure OMO-Slim, OpenCode
providers/presets/hook runtime, or Linear credentials. After `install`, restart
OpenCode or run its native reload command (`/reload` where supported); `check` is
read-only and needs no reload.

## Polytoken asset projection

In addition to the `_bmad/custom/` overrides, storm-setup projects the module's versioned Polytoken assets (`assets/polytoken/`: specialist subagents, role/model profiles, the continuation hook fragment and script) into the consuming project's `.polytoken/` surface. The executable contract lives in `assets/polytoken/scripts/manage_polytoken_assets.py`; run it, don't reimplement it:

```bash
MGR={module-root}/skills/storm-setup/assets/polytoken/scripts/manage_polytoken_assets.py
SRC={module-root}/skills/storm-setup/assets/polytoken

python3 $MGR install  --source-root $SRC --project-root {project-root} [--force] [--json]
python3 $MGR check    --source-root $SRC --project-root {project-root} [--json]
python3 $MGR rollback --project-root {project-root} [--json]
```

### The asset manifest

`assets/polytoken/manifest.json` is the versioned source of truth. Each asset declares its module `source`, project `target`, `kind` (`subagent`, `profile`, `hook-script`, `hook-fragment`), `merge` strategy (`managed-file` or `merge-by-name`), whether it is `required`, and a pinned `sha256`. `validate_polytoken_assets.py --refresh` re-pins checksums after a deliberate source edit; the manager refuses to install from a drifted manifest. Every target must live under `.polytoken/` — targets are validated lexically and anything else is rejected before any write.

### Install / update semantics

- Missing managed targets are created from the module source. Never hand-author copies in the consuming project; generated files are projections of `bmad-storm` source, not independent forks.
- `.polytoken/storm/ownership.json` records the checksum of every asset **as installed**. A target whose current content differs from its ownership checksum is a **local edit**: the manager refuses to overwrite it and reports the conflict. The approved actions are: merge the local change back into module source, or re-run `install --force` (a backup is taken first). Never pass `--force` without explicit operator approval.
- A pre-existing file at a managed target that storm never installed is an **unmanaged collision** and is likewise refused without `--force`. Unrelated user files anywhere else under `.polytoken/` are never touched.
- An unchanged managed file (current content matches the ownership checksum) is updated in place when the module ships a newer version.
- Before any mutation, the manager snapshots every file it will touch — managed targets, `.polytoken/hooks.json`, and the ownership manifest — into `.polytoken/storm/backups/<timestamp>/` with a `kind: "manage-polytoken-assets"` record. A failure mid-install restores the snapshot automatically. `storm-team` activation backups live separately under `.polytoken/storm/team-backups/` with `kind: "storm-team"` records; each rollback path selects only its own kind, so neither can restore the other's backup.
- After install, tell the operator to run `/reload` to load the new definitions.

### Check mode (read-only)

`manage_polytoken_assets.py check` writes nothing. It reports missing required assets, `update-available` (module newer than the unchanged install), `locally-modified`, `unmanaged-collision`, `orphaned` ownership entries (assets the module no longer ships), missing managed hooks, and source-manifest drift. Any finding exits 1. Run it after every module update and before enabling writers or continuation.

### Rollback

`rollback` restores the most recent backup snapshot: files that existed are copied back, files the install created are removed, and the prior `hooks.json`/ownership state returns. Use it when `/reload` rejects new definitions or an install proves bad, then `/reload` again.

### Hook and project-vars merge rules

- `hooks/hooks.fragment.json` merges into `.polytoken/hooks.json` **by unique hook `name`**: storm-managed entries (`storm-` prefixed) are replaced with the shipped version; unrelated user entries are preserved in place. Both the top-level array shape and an object with a `hooks` array are supported; any other shape is refused rather than guessed.
- The continuation hook is **off by default**. Installing the fragment and script does not enable it; enablement is the separate operator-approved `storm-continue-on-idle.enabled` marker written only after the operator opts in via the `polytoken_continue_on_idle` configuration. When enabled, confirm `auto_drain_notifications` is set to a compatible value per `docs/polytoken-orchestration.md` (or keep the hook stopped on ambiguity).
- Project variables are merged only in storm-owned key namespaces; never overwrite unrelated project or global facets, subagents, skills, permissions, or config.

### Capability checks before writing

Before installing, validate the target environment and stop with an actionable diagnostic rather than assuming a numeric version:

1. The source manifest verifies cleanly (checksums pinned, targets confined to `.polytoken/`).
2. `validate_polytoken_assets.py` reports no findings on the source assets — this is the load-time contract (frontmatter rules, tool grants/denies, exit schemas, hook safety, no secrets).
3. The consuming project actually uses Polytoken (a `.polytoken/` directory exists or the operator confirms first-time projection).
4. After install and `/reload`, run `storm-doctor` and `storm-setup check` and resolve findings before enabling write roles, profile activation, or continuation.

Run the disposable smoke scenarios in `docs/workflow-conformance.md` (or `tests/smoke/` when present) before enabling writers or continuation in any real project.
