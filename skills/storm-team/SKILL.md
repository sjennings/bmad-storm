---
name: storm-team
description: Activate a named Storm role/model profile (quality, balanced, economy, inherit, or a custom override) as one atomic managed-set swap, with validation, backup, rollback, and a /reload reminder. Profile changes are always approval-gated.
---

# Storm Team

Polytoken has no native atomic team-preset command, so this skill is Storm's managed equivalent: `storm-team activate <profile>` renders the complete managed subagent set from one profile manifest and swaps it in transactionally. `/model` remains the independent session-model switch; this skill does not claim `/preset` parity.

## Profiles

Built-in manifests ship under `storm-setup/assets/polytoken/profiles/` and are installed to `.polytoken/storm/profiles/`:

- `quality` — full-size default model everywhere.
- `balanced` — full-size for judgment/implementation roles, mid-size for recon/media roles.
- `economy` — mid-size judgment/implementation, smallest recon/media.
- `inherit` — no pinning; every specialist inherits the session's active model.

Portable aliases (`default_model:full|mini|nano`) are the default references. Operators who need exact provider/model assignments create a custom profile JSON in the same shape with fully qualified references (optionally with effort suffixes). Role entries may never set `fallback_models`: exact model references are runtime-gated, and any unavailable model must surface as a reported failure, never a silent substitution.

## Activate (transactional)

Profile changes are **approval-gated**: show the operator the target profile, the per-role model assignments, and the diff against the active manifest before doing anything. `storm-harness-improvement` may recommend a profile change but never applies one.

Then run the deterministic renderer:

```bash
python3 {storm-module}/skills/storm-team/render_team.py \
  --profile .polytoken/storm/profiles/<profile>.json \
  --templates {storm-module}/skills/storm-setup/assets/polytoken/subagents \
  --target .polytoken/subagents
```

The script:

1. validates the profile (roles exist, model reference shapes valid, no fallbacks);
2. renders every managed role into a temporary directory, injecting each role's model reference (or omitting `model:` for `inherit`);
3. validates the entire candidate set with the asset validator — one invalid role aborts everything;
4. backs up the current managed set to `.polytoken/storm/team-backups/<timestamp>/` with a `kind: "storm-team"` record — separate from the asset manager's `.polytoken/storm/backups/` snapshots, so neither rollback path can select the other's backups;
5. swaps in the validated candidate set and records the new active manifest at `.polytoken/storm/active-profile.json`;
6. on any failure after the swap begins, restores the backup so the prior set is left intact;
7. never touches unmanaged (user-authored) subagent files.

## After activation

- Tell the operator to run `/reload` — definition changes take effect only on reload.
- The activation script cannot observe the reload result. If `/reload` rejects the new set, run rollback explicitly:

```bash
python3 {storm-module}/skills/storm-team/render_team.py --rollback --target .polytoken/subagents
```

Rollback restores the most recent backup and the prior active-profile record; the operator then runs `/reload` again.

## Check

`storm-team check` (or storm-doctor) reports the active profile, drift between installed role files and the profile render, and model-reference validity — read-only, proposing rather than applying repairs.

```bash
python3 {storm-module}/skills/storm-team/render_team.py --check --target .polytoken/subagents
```

The script reads `.polytoken/storm/active-profile.json`, verifies each recorded role checksum against the installed file, and validates the recorded model references. Exit 0 means clean; 1 means findings (including a missing active-profile record); 2 means usage error. It never writes anything.
