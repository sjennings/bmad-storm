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
