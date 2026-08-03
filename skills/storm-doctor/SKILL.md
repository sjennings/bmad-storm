---
name: storm-doctor
description: Read-only machine-readable audit of the Storm module and a consuming project's managed Polytoken projection — version/manifest integrity, asset drift, profile/role references, permission safety, hook safety, alias/contract drift, and configuration key names. Proposes repairs; never applies them. Invoked as storm-doctor.
---

# Storm Doctor

Diagnoses; never prescribes-and-applies. Doctor produces a single JSON report and leaves every repair to an explicitly approved `storm-setup` / `manage_polytoken_assets.py` / `storm-team` action.

## Run

```bash
python3 {module-root}/skills/storm-doctor/doctor.py \
  [--module-root DIR] [--project-root DIR]
```

- `--module-root` defaults to the checkout containing this skill.
- `--project-root` is the consuming project. Omit it to audit the module source only; projection, active-profile, and config-key checks report `skipped`.
- Exit 0 means no error-severity findings; exit 1 means at least one. Warnings never fail the run on their own, but report them all to the operator.

## What it checks

| Check | Covers |
|---|---|
| `module_metadata` | `module.yaml` version vs asset-manifest `storm_version` vs marketplace plugin version; workflow contract parses and declares `contract_version`. |
| `source_assets` | The full `validate_polytoken_assets.py` ruleset over the shipped Polytoken assets (frontmatter, tool grants/denies, exit schemas, profiles, hooks, manifest checksums, secret patterns). |
| `projection` | `manage_polytoken_assets.py check` semantics: missing, drifted, locally-modified, unmanaged-collision, and orphaned managed assets; merged-hook presence in `.polytoken/hooks.json`. |
| `profiles_roles` | The active profile recorded by `storm-team` exists under `.polytoken/storm/profiles/` and every role it references has an installed subagent definition. |
| `capabilities` | Write-role deny lists cover lifecycle/control tools and deny `shell_exec`/`shell_monitor`, the only route to `linear-cli`. After a Polytoken or linear-cli update, inspect the CLI mutation commands in an operator session and confirm no writer role can invoke them. |
| `hook_safety` | Managed hook names/events/choke-point markers; whether the continuation enable marker exists (default is off; an enabled marker is a warning to re-confirm approval and a compatible `auto_drain_notifications` setting). |
| `alias_contract` | Every alias in `workflow-contract.json` resolves to declared canonical operations; required settings keys (`review_loop_max_rounds`, `completion_commit_policy`) exist. |
| `config_keys` | `_bmad/storm/config.yaml` exists and carries the expected configuration **key names**. Values are never read into the report. |

## Security contract

Doctor reports paths, checksums, tool names, and configuration key names only. It never prints file contents or configuration values, so no secret can leak through its output. Do not "improve" it by adding content diffs or value dumps.

## Acting on findings

Map finding codes to the owning repair action, then ask the operator before running any of them:

- `missing` / `update-available` / `hooks-missing` → `manage_polytoken_assets.py install` (approval-gated).
- `locally-modified` / `unmanaged-collision` → show the operator the situation; merge by hand or approve `install --force` (a backup is taken first).
- `orphaned` → deliberate removal by the operator; never delete by script suggestion alone.
- `deny-list-gap` / `asset-invalid` / `hook-unsafe` → module-source repair in `bmad-storm`, then re-install.
- `version-mismatch` / `alias-drift` / `contract-invalid` → release-metadata or contract repair in `bmad-storm`; do not patch the consuming project.
- `continuation-enabled` → confirm the approval and `auto_drain_notifications` compatibility, or remove the enable marker.
- `config-missing` / `config-keys-missing` → re-run the BMAD module installer.

Never mutate project files, tracker state, goals, or configuration from doctor itself.
