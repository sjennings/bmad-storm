#!/usr/bin/env python3
"""Render and atomically activate a Storm role/model profile (stdlib only).

Reads one profile manifest, renders the complete managed subagent set from
the Storm source templates with each role's model reference injected,
validates the whole candidate set, then swaps it into the consuming
project's ``.polytoken/subagents/`` with backup and rollback.

Transactional contract:

  * validate profile -> render to temp dir -> validate candidate set ->
    backup current managed set -> swap -> record active profile;
  * any failure after the swap begins restores the prior managed set;
  * unmanaged (user-authored) subagent files are never touched;
  * the target and its parents are resolved before any operation and
    symlink escapes outside the consuming project/``.polytoken`` boundary
    are refused;
  * activation backups live in ``.polytoken/storm/team-backups/`` with
    ``kind: "storm-team"`` records, separate from the asset manager's
    ``.polytoken/storm/backups/`` snapshots, so neither rollback path can
    select the other's backups.

Usage:
    render_team.py --profile PROFILE.json --templates DIR --target DIR
    render_team.py --check --target DIR
    render_team.py --rollback --target DIR

Exit codes: 0 success/clean, 1 failure or check findings (including a
missing active-profile record), 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

MODEL_ALIAS_RE = re.compile(r"^default_model:(full|mini|nano)$")
# Qualified reference: provider/model with an optional effort suffix such as
# ``(high)``. Keep in sync with validate_polytoken_assets.MODEL_QUALIFIED_RE;
# tests assert the two agree on a battery of valid and invalid references.
MODEL_QUALIFIED_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:/-]*"
    r"(\((low|medium|high|xhigh|max|nano|mini|full)\))?$"
)

TEAM_BACKUP_KIND = "storm-team"

VALIDATOR_PATH = (
    Path(__file__).resolve().parents[1]
    / "storm-setup/assets/polytoken/scripts/validate_polytoken_assets.py"
)


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_polytoken_assets", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True  # never litter the consuming project's assets
    spec.loader.exec_module(module)
    return module


class ConfinementError(ValueError):
    """The target or a parent symlink escapes the managed boundary."""


def storm_dir_for(target: Path) -> Path:
    return target.parent / "storm"


def team_backups_root(storm: Path) -> Path:
    """Renderer backups live apart from manage_polytoken_assets backups.

    The asset manager snapshots into ``.polytoken/storm/backups/``; team
    activation snapshots into ``.polytoken/storm/team-backups/``. Separate
    roots plus ``kind`` markers in every ``backup.json`` mean neither
    rollback path can select the other's backup records.
    """
    return storm / "team-backups"


def confine_target(target: Path) -> None:
    """Reject symlink escapes before activation/check/rollback touches disk.

    ``target`` is expected at ``<project>/.polytoken/subagents`` with Storm
    runtime state beside it in ``<project>/.polytoken/storm``. Every
    component — project root, ``.polytoken``, the target, and the storm
    state dir — is resolved, and the results must nest: real ``.polytoken``
    inside the real project root, real target and storm dir inside the real
    ``.polytoken``. A symlink anywhere in that chain that points outside
    its boundary raises ConfinementError before any read or write.
    """
    polytoken_dir = target.parent
    project_real = polytoken_dir.parent.resolve()
    polytoken_real = polytoken_dir.resolve()
    target_real = target.resolve()
    storm_real = storm_dir_for(target).resolve()
    checks = (
        (polytoken_dir, polytoken_real, project_real, "the project root"),
        (target, target_real, polytoken_real, ".polytoken/"),
        (storm_dir_for(target), storm_real, polytoken_real, ".polytoken/"),
    )
    for label, resolved, boundary, boundary_name in checks:
        try:
            resolved.relative_to(boundary)
        except ValueError:
            raise ConfinementError(
                f"{label} resolves outside {boundary_name} "
                f"(symlink escape: {resolved})") from None


def managed_names(templates: Path) -> list[str]:
    return sorted(p.stem for p in templates.glob("*.md"))


def render_candidate(profile: dict, templates: Path, candidate: Path) -> list[str]:
    """Render every managed role into candidate/subagents/. Returns problems."""
    problems = []
    roles = profile.get("roles", {})
    out_dir = candidate / "subagents"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in managed_names(templates):
        spec = roles.get(name)
        if spec is None:
            problems.append(f"profile is missing role {name!r}")
            continue
        if not isinstance(spec, dict):
            problems.append(f"role {name} must be an object")
            continue
        if "fallback_models" in spec:
            problems.append(f"role {name} sets fallback_models; silent fallback is forbidden")
            continue
        model = spec.get("model")
        if model is not None and (not isinstance(model, str) or "\n" in model or "\r" in model
                                  or not (MODEL_ALIAS_RE.fullmatch(model)
                                          or MODEL_QUALIFIED_RE.fullmatch(model))):
            problems.append(f"role {name} has invalid model reference {model!r}")
            continue
        lines = (templates / f"{name}.md").read_text().splitlines()
        rendered = []
        injected = False
        for line in lines:
            rendered.append(line)
            if line.strip() == "polytoken:" and model and not injected:
                rendered.append(f"  model: {model}")
                injected = True
        if model and not injected:
            problems.append(f"could not inject model into template {name!r}")
            continue
        (out_dir / f"{name}.md").write_text("\n".join(rendered) + "\n")
    return problems


def validate_candidate(candidate: Path) -> list[str]:
    validator = load_validator()
    checker = validator.Validator(candidate)
    checker.check_subagents()
    return checker.findings


def activate(profile_path: Path, templates: Path, target: Path) -> int:
    confine_target(target)
    profile = json.loads(profile_path.read_text())
    target.mkdir(parents=True, exist_ok=True)
    storm = storm_dir_for(target)
    names = managed_names(templates)

    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp)
        problems = render_candidate(profile, templates, candidate)
        problems += validate_candidate(candidate)
        if problems:
            for problem in problems:
                print(f"FINDING: {problem}")
            print("activation aborted; existing set untouched")
            return 1

        backups_root = team_backups_root(storm)
        backups_root.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(
            prefix=time.strftime("%Y%m%d-%H%M%S-"), dir=backups_root))
        swapped: list[Path] = []
        try:
            backup_entries = []
            for name in names:
                existing = target / f"{name}.md"
                entry = {"name": name, "existed": existing.exists()}
                if existing.exists():
                    shutil.copy2(existing, backup / existing.name)
                backup_entries.append(entry)
            (backup / "backup.json").write_text(json.dumps({
                "kind": TEAM_BACKUP_KIND,
                "roles": backup_entries,
                "active_profile_existed": (storm / "active-profile.json").exists(),
            }, indent=2) + "\n")
            active = storm / "active-profile.json"
            if active.exists():
                shutil.copy2(active, backup / "active-profile.json")
            for name in names:
                shutil.copy2(candidate / "subagents" / f"{name}.md", target / f"{name}.md")
                swapped.append(target / f"{name}.md")
        except OSError as exc:
            print(f"swap failed ({exc}); restoring backup")
            for name in names:
                backed = backup / f"{name}.md"
                if backed.exists():
                    shutil.copy2(backed, target / f"{name}.md")
                elif (target / f"{name}.md").exists():
                    (target / f"{name}.md").unlink()
            return 1

    storm.mkdir(parents=True, exist_ok=True)
    record = {
        "profile": profile.get("name"),
        "activated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "roles": profile.get("roles", {}),
        "role_checksums": {
            name: hashlib.sha256((target / f"{name}.md").read_bytes()).hexdigest()
            for name in names
        },
        "backup": str(backup),
    }
    (storm / "active-profile.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"activated profile {profile.get('name')!r}: {len(swapped)} managed roles swapped")
    print(f"backup at {backup}")
    print("run /reload to load the new definitions; if reload fails, run with --rollback")
    return 0


def check(target: Path) -> int:
    """Read-only audit of the active managed team.

    Reports the active profile, drift between installed role files and the
    recorded role checksums, and model-reference validity. Proposes repairs;
    never writes. Exit 0 clean, 1 on findings or a missing/invalid record.
    """
    confine_target(target)
    storm = storm_dir_for(target)
    active_path = storm / "active-profile.json"
    if not active_path.exists():
        print("FINDING: no active profile recorded at "
              f"{active_path}; run activation first")
        return 1
    try:
        record = json.loads(active_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"FINDING: active-profile.json is invalid JSON: {exc}")
        return 1

    findings: list[str] = []
    profile_name = record.get("profile")
    if not profile_name:
        findings.append("active-profile.json does not name a profile")
    else:
        print(f"active profile: {profile_name}")

    checksums = record.get("role_checksums")
    if not isinstance(checksums, dict) or not checksums:
        findings.append("active-profile.json records no role checksums")
    else:
        for name, expected in sorted(checksums.items()):
            path = target / f"{name}.md"
            if not path.exists():
                findings.append(f"{name}: recorded role file is missing")
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                findings.append(
                    f"{name}: drifted from the recorded checksum "
                    "(local edit or partial swap); re-run activation or "
                    "rollback to restore a known set"
                )

    roles = record.get("roles")
    if not isinstance(roles, dict):
        findings.append("active-profile.json records no roles mapping")
    else:
        for role, spec in sorted(roles.items()):
            if not isinstance(spec, dict):
                findings.append(f"{role}: profile entry is not an object")
                continue
            if "fallback_models" in spec:
                findings.append(f"{role}: fallback_models is forbidden; "
                                "silent model substitution is never allowed")
            model = spec.get("model")
            if model is not None and not (
                isinstance(model, str)
                and (MODEL_ALIAS_RE.fullmatch(model)
                     or MODEL_QUALIFIED_RE.fullmatch(model))
            ):
                findings.append(f"{role}: invalid model reference {model!r}")

    for finding in findings:
        print(f"FINDING: {finding}")
    if findings:
        print("check is read-only: repairs are proposed, never applied")
        return 1
    print("OK: installed role files match the recorded active profile")
    return 0


def team_backup_dirs(backups: Path) -> list[Path]:
    """Return only this tool's own backup directories, oldest first.

    A candidate qualifies when it has no ``backup.json`` (legacy renderer
    backup — only renderer backups ever live under ``team-backups/``) or
    when its ``backup.json`` parses and is unambiguously a team record:
    ``kind == "storm-team"`` or a ``roles`` list. Anything else — a
    manage_polytoken_assets snapshot or an unparseable record — is skipped
    so rollback can never select a backup that lacks role records.
    """
    if not backups.exists():
        return []
    candidates = []
    for path in backups.iterdir():
        if not path.is_dir():
            continue
        manifest_path = path / "backup.json"
        if not manifest_path.exists():
            candidates.append(path)  # legacy renderer backup
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if (manifest.get("kind") == TEAM_BACKUP_KIND
                or isinstance(manifest.get("roles"), list)):
            candidates.append(path)
    return sorted(candidates, key=lambda p: p.stat().st_mtime)


def rollback(target: Path) -> int:
    confine_target(target)
    storm = storm_dir_for(target)
    backups = team_backups_root(storm)
    latest = team_backup_dirs(backups)
    if not latest:
        print("no team backups found; nothing to roll back")
        return 1
    backup = latest[-1]
    restored = 0
    manifest_path = backup / "backup.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for entry in manifest.get("roles", []):
            path = target / f"{entry['name']}.md"
            backed = backup / path.name
            if entry.get("existed"):
                shutil.copy2(backed, path)
                restored += 1
            elif path.exists():
                path.unlink()
                restored += 1
    else:
        for path in backup.glob("*.md"):
            shutil.copy2(path, target / path.name)
            restored += 1
    prior = backup / "active-profile.json"
    if prior.exists():
        shutil.copy2(prior, storm / "active-profile.json")
    elif (storm / "active-profile.json").exists():
        (storm / "active-profile.json").unlink()
    print(f"restored {restored} managed roles from {backup}")
    print("run /reload to load the restored definitions")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--templates", type=Path)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--check", action="store_true",
                        help="read-only audit of the active managed team")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args(argv[1:])
    if args.check and args.rollback:
        parser.error("--check and --rollback are mutually exclusive")
    if args.check:
        if args.profile or args.templates:
            parser.error("--check takes no --profile/--templates")
        command = lambda: check(args.target)  # noqa: E731
    elif args.rollback:
        command = lambda: rollback(args.target)  # noqa: E731
    else:
        if not args.profile or not args.templates:
            parser.error("--profile and --templates are required for activation")
        command = lambda: activate(args.profile, args.templates, args.target)  # noqa: E731
    try:
        return command()
    except ConfinementError as exc:
        print(f"refused: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
