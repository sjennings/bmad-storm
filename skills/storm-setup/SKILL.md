---
name: storm-setup
description: Write and verify the sparse _bmad/custom/ overrides that wire the storm module into stock BMM workflows. Run once after install, and in check mode after every BMAD update. Invoked as storm-setup [check].
---

# Storm Setup

Wires storm into BMAD exclusively through the documented-stable customization surface. This skill owns the overrides so the wiring is reproducible and versioned in the module — never hand-maintained.

## Preconditions

- The BMM module is installed (`{project-root}/_bmad/bmm/config.yaml` exists). If not, stop: storm requires BMM.
- Storm's own config exists (`{project-root}/_bmad/storm/config.yaml`, written by the installer from module.yaml prompts). If not, tell the operator to re-run `npx bmad-method install` with the storm module selected.

## Install mode (default)

For each template in this skill's `assets/overrides/` directory (`bmad-agent-dev.toml`, `bmad-agent-pm.toml`, `bmad-create-story.toml`, `bmad-dev-story.toml`, `bmad-code-review.toml`, `bmad-correct-course.toml`):

1. **Target check** — confirm the skill the override names is actually installed (its directory with a `customize.toml` exists under the tool's skills path or `_bmad/bmm/`). A template whose target is missing is reported and skipped, never written blind.
2. **Write or merge** — if `_bmad/custom/<name>.toml` does not exist, copy the template. If it exists, do NOT clobber: diff the existing file against the template, show the operator what storm wants to add or change, and merge only with approval — preserving any non-storm customizations the operator has authored. Storm-owned blocks are delimited so future runs can update them surgically.
3. **Verify the merge** — run the resolver and confirm the storm fields landed:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py \
     --skill <installed-skill-dir> --key workflow   # or `agent` for agent overrides
   ```

   (Fall back to `python3` if `uv` is unavailable.) The resolved JSON must contain the storm entries (the appended activation steps / persistent facts, the `on_complete` text). A field that didn't land is a hard finding — report it, don't proceed silently.

4. Never write into `_bmad/core/`, `_bmad/bmm/`, or any installed skill folder. Overrides go in `_bmad/custom/` only.

Finish with a summary: overrides written, merged, skipped (and why), and verification results. Then remind the operator to confirm `grill_on_implement` and both cross-model rosters in `_bmad/storm/config.yaml`: `polytoken_review_models` supplies fully qualified model references only when running under Polytoken, while `external_reviewers` supplies CLI command names only outside Polytoken. Polytoken does not fall back to the CLI roster.

## Check mode (`storm-setup check`)

Run after every BMAD update. Mutates nothing; reports three classes of problems:

1. **Orphaned overrides** — a `_bmad/custom/*.toml` written by storm whose target skill no longer exists or was renamed upstream. Overrides fail *quiet*, so this is the check that catches upstream renames.
2. **Landing failures** — for each override, re-run the resolver verification from install mode; report any storm field that no longer resolves.
3. **Default collisions** — for each hooked workflow, read the shipped `customize.toml`; if upstream now ships a non-empty default for a scalar storm overrides (especially `on_complete`), flag it: our override is silently replacing behavior upstream considers standard, and the operator must reconcile the two.

Also compare the templates in `assets/overrides/` against the written files and flag drift in the storm-owned blocks (someone edited the wiring by hand instead of the template).

Report findings with proposed fixes; apply only what the operator approves.

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
