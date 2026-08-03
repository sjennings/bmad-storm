#!/usr/bin/env python3
"""Storm doctor: read-only, machine-readable audit of a Storm installation.

Audits the bmad-storm module source and (optionally) a consuming project's
projected ``.polytoken/`` surface. Doctor never writes: it proposes repairs
(as finding codes the operator can act on via ``storm-setup`` /
``manage_polytoken_assets.py``) and never applies them.

Checks:

  * module_metadata   — module.yaml version vs asset manifest storm_version
                        vs marketplace plugin version; workflow contract
                        parses and declares a contract_version.
  * source_assets     — the full validate_polytoken_assets.py ruleset over
                        the module's shipped Polytoken assets.
  * projection        — manage_polytoken_assets.py check semantics over the
                        consuming project: missing/drifted/locally-modified/
                        orphaned managed assets and merged-hook presence.
  * profiles_roles    — active profile exists, its roles all resolve to
                        installed subagent definitions.
  * capabilities      — write-role deny lists still cover every known
                        lifecycle/control and Linear-mutation tool; reports
                        what is statically verifiable and flags that live
                        MCP tool enumeration requires an operator session.
  * hook_safety       — managed hook names/events, continuation enable
                        marker state (default-off expectation).
  * alias_contract    — every advertised alias resolves to declared
                        canonical operations; required settings keys exist.
  * config_keys       — configuration KEY NAMES only, never values: storm
                        config presence and missing expected keys.

Security: doctor reports paths, checksums, tool names, and configuration
key names only. It never prints file contents or configuration values, so
no secret can leak through its output.

Usage:
    doctor.py [--module-root DIR] [--project-root DIR]

Output is a single JSON report on stdout. Exit 0 means no error-severity
findings; 1 means at least one error; 2 means usage error.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

MODULE_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_CONFIG_KEYS = [
    "linear_team", "linear_team_key", "grill_on_implement",
    "external_reviewers", "polytoken_review_models",
    "review_loop_max_rounds",
    "polytoken_team_profile", "polytoken_role_model_overrides",
    "polytoken_council_models", "polytoken_max_parallel_jobs",
    "polytoken_continue_on_idle",
]

REQUIRED_CONTRACT_SETTINGS = ["review_loop_max_rounds"]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Doctor:
    def __init__(self, module_root: Path, project_root: Path | None):
        self.module_root = module_root
        self.project_root = project_root
        self.checks: dict[str, dict] = {}
        self.assets_root = (
            module_root / "skills/storm-setup/assets/polytoken"
        )
        self.validator_path = (
            self.assets_root / "scripts/validate_polytoken_assets.py"
        )
        self.manager_path = (
            self.assets_root / "scripts/manage_polytoken_assets.py"
        )
        self.contract_path = (
            module_root / "skills/storm-contract/workflow-contract.json"
        )
        self.module_yaml = module_root / "skills/module.yaml"
        self.marketplace_json = module_root / ".claude-plugin/marketplace.json"

    def finding(self, check: str, severity: str, code: str,
                subject: str, message: str) -> None:
        entry = self.checks.setdefault(check, {"status": "ok", "findings": []})
        entry["findings"].append({
            "severity": severity, "code": code,
            "subject": subject, "message": message,
        })
        if severity == "error":
            entry["status"] = "findings"
        elif severity == "warning" and entry["status"] == "ok":
            entry["status"] = "findings"

    def note(self, check: str, message: str) -> None:
        self.finding(check, "info", "note", check, message)

    # -- module metadata ---------------------------------------------------

    def check_module_metadata(self) -> None:
        check = "module_metadata"
        module_version = None
        if not self.module_yaml.exists():
            self.finding(check, "error", "module-missing", "skills/module.yaml",
                         "module metadata file is missing")
        else:
            text = self.module_yaml.read_text()
            match = re.search(r"^module_version:\s*(\S+)", text, re.MULTILINE)
            if not match:
                self.finding(check, "error", "version-missing",
                             "skills/module.yaml", "no module_version field")
            else:
                module_version = match.group(1).strip().strip('"\'')

        manifest_version = None
        manifest_path = self.assets_root / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text())
            manifest_version = manifest.get("storm_version")
        except (OSError, json.JSONDecodeError) as exc:
            self.finding(check, "error", "manifest-invalid", "manifest.json",
                         f"cannot read asset manifest: {exc}")

        if module_version and manifest_version and module_version != manifest_version:
            self.finding(check, "error", "version-mismatch", "module_version",
                         f"module.yaml {module_version} != asset manifest "
                         f"{manifest_version}; release metadata is out of sync")

        if self.marketplace_json.exists():
            try:
                marketplace = json.loads(self.marketplace_json.read_text())
                for plugin in marketplace.get("plugins", []):
                    plugin_version = plugin.get("version")
                    if plugin_version and module_version \
                            and plugin_version != module_version:
                        self.finding(check, "error", "version-mismatch",
                                     "marketplace.json",
                                     f"plugin {plugin.get('name')!r} version "
                                     f"{plugin_version} != module.yaml "
                                     f"{module_version}")
            except json.JSONDecodeError as exc:
                self.finding(check, "error", "marketplace-invalid",
                             "marketplace.json", f"invalid JSON: {exc}")
        else:
            self.note(check, "no marketplace.json; skipping plugin version check")

        try:
            contract = json.loads(self.contract_path.read_text())
            if not contract.get("contract_version"):
                self.finding(check, "error", "contract-version-missing",
                             "workflow-contract.json",
                             "contract declares no contract_version")
        except (OSError, json.JSONDecodeError) as exc:
            self.finding(check, "error", "contract-invalid",
                         "workflow-contract.json", f"cannot parse: {exc}")

    # -- source assets -------------------------------------------------------

    def check_source_assets(self) -> None:
        check = "source_assets"
        try:
            validator = load_module(self.validator_path, "validate_polytoken_assets")
        except Exception as exc:  # validator import must never crash doctor
            self.finding(check, "error", "validator-unusable",
                         "validate_polytoken_assets.py", f"cannot load: {exc}")
            return
        runner = validator.Validator(self.assets_root)
        for finding in runner.run():
            self.finding(check, "error", "asset-invalid",
                         "assets/polytoken", finding)

    # -- projection ----------------------------------------------------------

    def check_projection(self) -> None:
        check = "projection"
        if self.project_root is None:
            self.checks[check] = {"status": "skipped", "findings": [{
                "severity": "info", "code": "no-project-root",
                "subject": check,
                "message": "no --project-root given; projection not audited",
            }]}
            return
        if not (self.project_root / ".polytoken").exists():
            self.finding(check, "warning", "not-installed", ".polytoken/",
                         "project has no .polytoken directory; run storm-setup "
                         "to project the managed assets")
            return
        try:
            manager = load_module(self.manager_path, "manage_polytoken_assets")
        except Exception as exc:
            self.finding(check, "error", "manager-unusable",
                         "manage_polytoken_assets.py", f"cannot load: {exc}")
            return
        runner = manager.Manager(self.assets_root, self.project_root)
        runner.cmd_check()  # read-only; findings accumulate on the runner
        for finding in runner.findings:
            self.finding(check, finding["severity"], finding["code"],
                         finding["subject"], finding["message"])

    # -- profiles / roles ----------------------------------------------------

    def check_profiles_roles(self) -> None:
        check = "profiles_roles"
        if self.project_root is None:
            self.checks[check] = {"status": "skipped", "findings": [{
                "severity": "info", "code": "no-project-root",
                "subject": check,
                "message": "no --project-root given; active profile not audited",
            }]}
            return
        storm_dir = self.project_root / ".polytoken" / "storm"
        active_path = storm_dir / "active-profile.json"
        if not active_path.exists():
            self.note(check, "no active profile recorded; storm-team has not "
                             "activated one (subagent templates run unrendered)")
            return
        try:
            active = json.loads(active_path.read_text())
        except json.JSONDecodeError as exc:
            self.finding(check, "error", "active-profile-invalid",
                         "active-profile.json", f"invalid JSON: {exc}")
            return
        profile_name = active.get("profile")
        profile_path = storm_dir / "profiles" / f"{profile_name}.json"
        if not profile_path.exists():
            self.finding(check, "error", "profile-missing", str(profile_name),
                         "active profile is not installed under "
                         ".polytoken/storm/profiles/")
            return
        try:
            profile = json.loads(profile_path.read_text())
        except json.JSONDecodeError as exc:
            self.finding(check, "error", "profile-invalid",
                         str(profile_name), f"invalid JSON: {exc}")
            return
        subagents_dir = self.project_root / ".polytoken" / "subagents"
        for role in sorted(profile.get("roles", {})):
            if not (subagents_dir / f"{role}.md").exists():
                self.finding(check, "error", "role-missing", role,
                             "active profile references a role with no "
                             "installed subagent definition")

    # -- capabilities / permission safety ------------------------------------

    def check_capabilities(self) -> None:
        check = "capabilities"
        try:
            validator = load_module(self.validator_path, "validate_polytoken_assets")
        except Exception as exc:
            self.finding(check, "error", "validator-unusable",
                         "validate_polytoken_assets.py", f"cannot load: {exc}")
            return
        for role in sorted(validator.WRITE_ROLES):
            path = self.assets_root / "subagents" / f"{role}.md"
            try:
                frontmatter = validator.parse_frontmatter(path)
            except (ValueError, json.JSONDecodeError) as exc:
                self.finding(check, "error", "role-unparseable", role, str(exc))
                continue
            deny = set(frontmatter.get("polytoken", {}).get("tools_deny", []))
            missing = [t for t in validator.WRITE_ROLE_REQUIRED_DENY
                       if t not in deny]
            if missing:
                self.finding(check, "error", "deny-list-gap", role,
                             f"write role does not deny: {missing}")
        self.note(check, "deny-list coverage is audited against the tools "
                         "known at authoring time; after any Polytoken or "
                         "linear-cli update, inspect the installed CLI's "
                         "mutation commands in an operator session and confirm "
                         "no new mutating tool is missing from the write-role "
                         "deny lists (static audit cannot observe the server)")

    # -- hook safety -----------------------------------------------------------

    def check_hook_safety(self) -> None:
        check = "hook_safety"
        try:
            validator = load_module(self.validator_path, "validate_polytoken_assets")
        except Exception as exc:
            self.finding(check, "error", "validator-unusable",
                         "validate_polytoken_assets.py", f"cannot load: {exc}")
            return
        runner = validator.Validator(self.assets_root)
        runner.check_hooks()
        for finding in runner.findings:
            self.finding(check, "error", "hook-unsafe",
                         "assets/polytoken/hooks", finding)
        if self.project_root is not None:
            marker = (self.project_root / ".polytoken" / "hooks"
                      / "storm-continue-on-idle.enabled")
            if marker.exists():
                self.finding(check, "warning", "continuation-enabled",
                             "storm-continue-on-idle.enabled",
                             "bounded continuation is enabled; confirm the "
                             "operator approved it and auto_drain_notifications "
                             "is set to a compatible value")
            else:
                self.note(check, "continuation is off (default); enable marker "
                                 "absent")

    # -- alias / contract drift -------------------------------------------------

    def check_alias_contract(self) -> None:
        check = "alias_contract"
        try:
            contract = json.loads(self.contract_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            self.finding(check, "error", "contract-invalid",
                         "workflow-contract.json", f"cannot parse: {exc}")
            return
        operations = set(contract.get("operations", {}))
        for alias, spec in sorted(contract.get("aliases", {}).items()):
            for operation in spec.get("canonical_operations", []):
                if operation not in operations:
                    self.finding(check, "error", "alias-drift", alias,
                                 f"alias references undeclared operation "
                                 f"{operation!r}")
        settings = contract.get("settings", {})
        for key in REQUIRED_CONTRACT_SETTINGS:
            if key not in settings:
                self.finding(check, "error", "setting-missing",
                             "workflow-contract.json",
                             f"contract does not define required setting {key!r}")

    # -- configuration key names (never values) ----------------------------------

    def check_config_keys(self) -> None:
        check = "config_keys"
        if self.project_root is None:
            self.checks[check] = {"status": "skipped", "findings": [{
                "severity": "info", "code": "no-project-root",
                "subject": check,
                "message": "no --project-root given; config keys not audited",
            }]}
            return
        config_path = self.project_root / "_bmad" / "storm" / "config.yaml"
        if not config_path.exists():
            self.finding(check, "warning", "config-missing",
                         "_bmad/storm/config.yaml",
                         "storm config not found; re-run the module installer")
            return
        # Top-level key names only; values are never read into the report.
        keys = re.findall(r"^([a-z_][a-z0-9_]*):", config_path.read_text(),
                          re.MULTILINE)
        missing = [key for key in EXPECTED_CONFIG_KEYS if key not in keys]
        if missing:
            self.finding(check, "warning", "config-keys-missing",
                         "_bmad/storm/config.yaml",
                         f"expected configuration keys absent: {missing} "
                         "(re-run the installer to add them)")
        self.note(check, f"observed {len(keys)} configuration key(s); "
                         "values intentionally not inspected")

    # -- runner ------------------------------------------------------------------

    def run(self) -> dict:
        self.check_module_metadata()
        self.check_source_assets()
        self.check_projection()
        self.check_profiles_roles()
        self.check_capabilities()
        self.check_hook_safety()
        self.check_alias_contract()
        self.check_config_keys()
        for name in (
            "module_metadata", "source_assets", "projection",
            "profiles_roles", "capabilities", "hook_safety",
            "alias_contract", "config_keys",
        ):
            self.checks.setdefault(name, {"status": "ok", "findings": []})
        all_findings = [
            finding
            for entry in self.checks.values()
            for finding in entry["findings"]
        ]
        return {
            "doctor": "storm-doctor",
            "module_root": str(self.module_root),
            "project_root": (
                str(self.project_root) if self.project_root else None
            ),
            "checks": self.checks,
            "error_count": sum(
                1 for f in all_findings if f["severity"] == "error"),
            "warning_count": sum(
                1 for f in all_findings if f["severity"] == "warning"),
            "repairs": (
                "doctor is read-only; apply repairs through storm-setup / "
                "manage_polytoken_assets.py with operator approval"
            ),
        }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--module-root", type=Path, default=MODULE_ROOT,
                        help="bmad-storm checkout (default: this repository)")
    parser.add_argument("--project-root", type=Path, default=None,
                        help="consuming project to audit (optional)")
    args = parser.parse_args(argv[1:])

    module_root = args.module_root.resolve()
    if not (module_root / "skills").exists():
        print(f"error: {module_root} does not look like a bmad-storm checkout",
              file=sys.stderr)
        return 2
    project_root = args.project_root.resolve() if args.project_root else None

    doctor = Doctor(module_root, project_root)
    report = doctor.run()
    print(json.dumps(report, indent=2))
    return 1 if report["error_count"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
