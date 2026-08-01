#!/usr/bin/env python3
"""Install, check, and roll back Storm-managed Polytoken assets (stdlib only).

Projects the versioned asset manifest shipped in the bmad-storm module
(``skills/storm-setup/assets/polytoken/manifest.json``) into a consuming
project's ``.polytoken/`` surface, with ownership metadata, backups, and
read-only drift checking.

Ownership model:

  * Every manifest asset targets a path under ``.polytoken/`` and nowhere
    else; targets are validated lexically before any write.
  * ``managed-file`` assets are written verbatim from the module source.
    ``.polytoken/storm/ownership.json`` records the checksum of each file
    *as installed*. On later runs a target whose current content differs
    from the recorded ownership checksum is a local edit: the manager
    refuses to overwrite it unless the operator passes ``--force`` (the
    explicit approved action). A pre-existing file at a managed target
    that Storm never installed is an unmanaged collision and is likewise
    refused without ``--force``.
  * ``merge-by-name`` assets (the hook fragment) are merged into
    ``.polytoken/hooks.json`` by unique hook ``name``: Storm-managed
    entries are replaced, unrelated user entries are preserved.
  * Before any mutation the manager snapshots every file it is about to
    touch into ``.polytoken/storm/backups/<timestamp>/``. A failure
    mid-install restores the snapshot. ``rollback`` restores the most
    recent snapshot on demand.
  * ``check`` never writes anything.

Security: the manager reports relative paths and checksums only. It never
prints file contents, so secrets inside project files cannot leak into
logs or model context through this tool.

Usage:
    manage_polytoken_assets.py install  --source-root DIR --project-root DIR [--force] [--json]
    manage_polytoken_assets.py check    --source-root DIR --project-root DIR [--json]
    manage_polytoken_assets.py rollback --project-root DIR [--json]

Exit code 0 means success / no findings; 1 means failure or findings;
2 means usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True  # never litter the consuming project

OWNERSHIP_TARGET = ".polytoken/storm/ownership.json"
HOOKS_TARGET = ".polytoken/hooks.json"
BACKUP_KIND = "manage-polytoken-assets"


# --------------------------------------------------------------------------
# helpers


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def read_json(path: Path):
    return json.loads(path.read_text())


def validate_target(target: str, *, allow_runtime: bool = False) -> str:
    """Return the normalized target, or raise ValueError.

    Every managed asset must live under ``.polytoken/``; absolute paths,
    ``..`` escapes, and anything outside that root are rejected.
    """
    pure = PurePosixPath(target)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"target {target!r} escapes the project")
    if (not allow_runtime and len(pure.parts) > 1 and pure.parts[1] == "storm"
            and not (len(pure.parts) > 2 and pure.parts[2] == "profiles")): 
        raise ValueError(f"target {target!r} is reserved for Storm runtime state")
    if not pure.parts or pure.parts[0] != ".polytoken":
        raise ValueError(f"target {target!r} is outside .polytoken/")
    return str(pure)


class Manager:
    def __init__(self, source_root: Path, project_root: Path | None):
        self.source_root = source_root
        # Resolve once so symlink-escape checks compare real paths.
        self.project_root = project_root.resolve() if project_root else None
        self.findings: list[dict] = []

    def confined_path(self, target: str, *, allow_runtime: bool = False) -> Path:
        """Validate a target lexically, then reject symlink escapes.

        Every existing component (the target itself or any parent, including
        ``.polytoken`` and ``.polytoken/storm``) is resolved; the result must
        stay inside the real project root and under ``.polytoken/``. Raises
        ValueError otherwise. Call this before any write through a path a
        project could have replaced with a symlink.
        """
        pure = validate_target(target, allow_runtime=allow_runtime)
        resolved = (self.project_root / pure).resolve(strict=False)
        try:
            rel = resolved.relative_to(self.project_root)
        except ValueError:
            raise ValueError(
                f"target {target!r} resolves outside the project root "
                f"(symlink escape: {resolved})") from None
        if not rel.parts or rel.parts[0] != ".polytoken":
            raise ValueError(
                f"target {target!r} resolves outside .polytoken/ "
                f"(symlink escape: {resolved})")
        return resolved

    # -- reporting ---------------------------------------------------------

    def finding(self, severity: str, code: str, subject: str, message: str) -> None:
        self.findings.append({
            "severity": severity,
            "code": code,
            "subject": subject,
            "message": message,
        })

    # -- manifest ----------------------------------------------------------

    def load_manifest(self) -> dict | None:
        manifest_path = self.source_root / "manifest.json"
        if not manifest_path.exists():
            self.finding("error", "manifest-missing", "manifest.json",
                         f"no manifest at {manifest_path}")
            return None
        try:
            manifest = read_json(manifest_path)
        except json.JSONDecodeError as exc:
            self.finding("error", "manifest-invalid", "manifest.json",
                         f"invalid JSON: {exc}")
            return None
        assets = manifest.get("assets")
        if not isinstance(assets, list):
            self.finding("error", "manifest-invalid", "manifest.json",
                         "manifest has no assets array")
            return None
        ok = True
        for asset in assets:
            source = asset.get("source", "")
            target = asset.get("target", "")
            try:
                asset["target"] = validate_target(target)
                self.confined_path(asset["target"])
            except ValueError as exc:
                self.finding("error", "target-escape", source, str(exc))
                ok = False
            source_path = self.source_root / source
            if not source_path.exists():
                self.finding("error", "source-missing", source,
                             "manifest source file is missing")
                ok = False
                continue
            digest = sha256_path(source_path)
            if digest != asset.get("sha256"):
                self.finding("error", "source-drift", source,
                             "source checksum does not match the manifest; "
                             "re-pin with validate_polytoken_assets.py --refresh")
                ok = False
        if not ok:
            return None
        return manifest

    # -- ownership state ---------------------------------------------------

    @property
    def storm_dir(self) -> Path:
        return self.project_root / ".polytoken" / "storm"

    @property
    def ownership_path(self) -> Path:
        return self.project_root / OWNERSHIP_TARGET

    def load_ownership(self) -> dict:
        if not self.ownership_path.exists():
            return {"assets": {}, "merged_hooks": []}
        try:
            state = read_json(self.ownership_path)
        except json.JSONDecodeError:
            self.finding("warning", "ownership-corrupt", OWNERSHIP_TARGET,
                         "ownership manifest is not valid JSON; treating all "
                         "managed targets as unmanaged (use --force to re-adopt)")
            return {"assets": {}, "merged_hooks": []}
        state.setdefault("assets", {})
        state.setdefault("merged_hooks", [])
        return state

    # -- classification ----------------------------------------------------

    def check_runtime_paths(self) -> bool:
        """Reject symlink escapes on the fixed runtime paths before writes.

        Covers the ownership manifest, the backups root, and hooks.json —
        paths a project could have replaced with symlinks pointing outside
        the project root or outside ``.polytoken/``.
        """
        ok = True
        for runtime in (HOOKS_TARGET, OWNERSHIP_TARGET,
                        ".polytoken/storm/backups"):
            try:
                self.confined_path(runtime, allow_runtime=True)
            except ValueError as exc:
                self.finding("error", "runtime-escape", runtime, str(exc))
                ok = False
        return ok

    # -- classification ----------------------------------------------------

    def classify(self, asset: dict, ownership: dict) -> str:
        """Classify one managed-file asset against the project.

        Returns one of: create, unchanged, update, adopt, locally-modified,
        unmanaged-collision.
        """
        target_path = self.project_root / asset["target"]
        if not target_path.exists():
            return "create"
        current = sha256_path(target_path)
        active = ownership.get("active_profile", {})
        active_path = self.storm_dir / "active-profile.json"
        if active_path.exists():
            try:
                active = read_json(active_path)
            except json.JSONDecodeError:
                pass
        rendered = active.get("role_checksums", {}) if isinstance(active, dict) else {}
        role = Path(asset["target"]).stem
        if Path(asset["target"]).parent.name == "subagents" and rendered.get(role) == current:
            return "unchanged"
        owned = ownership["assets"].get(asset["target"])
        if owned is None:
            return "adopt" if current == asset["sha256"] else "unmanaged-collision"
        if current == owned.get("sha256"):
            return "unchanged" if current == asset["sha256"] else "update"
        return "locally-modified"

    # -- backup ------------------------------------------------------------

    def new_backup_dir(self) -> Path:
        backups_root = self.storm_dir / "backups"
        backups_root.mkdir(parents=True, exist_ok=True)
        stamp = utc_stamp()
        candidate = backups_root / stamp
        counter = 1
        while candidate.exists():
            counter += 1
            candidate = backups_root / f"{stamp}-{counter}"
        candidate.mkdir()
        return candidate

    @staticmethod
    def _backup_name(target: str) -> str:
        return target.replace("/", "__")

    def capture(self, backup_dir: Path, records: list[dict], target: str) -> None:
        """Snapshot one file (or record its absence) into the backup."""
        path = self.project_root / target
        entry = {"target": target, "existed": path.exists()}
        if path.exists():
            name = self._backup_name(target)
            shutil.copy2(path, backup_dir / name)
            entry["backup_file"] = name
        records.append(entry)

    def write_backup_manifest(self, backup_dir: Path, records: list[dict]) -> None:
        (backup_dir / "backup.json").write_text(
            json.dumps({"kind": BACKUP_KIND, "created_at": utc_stamp(),
                        "entries": records},
                       indent=2) + "\n")

    def restore_backup(self, backup_dir: Path) -> int:
        """Restore a snapshot. Returns the number of files restored/removed."""
        manifest = read_json(backup_dir / "backup.json")
        restored = 0
        for entry in manifest.get("entries", []):
            target = entry["target"]
            self.confined_path(target, allow_runtime=True)
            path = self.project_root / target
            if entry.get("existed"):
                shutil.copy2(backup_dir / entry["backup_file"], path)
                restored += 1
            elif path.exists():
                path.unlink()
                restored += 1
        return restored

    # -- hooks merge ---------------------------------------------------------

    def merge_hooks(self, fragment_entries: list) -> None:
        """Merge fragment entries into .polytoken/hooks.json by unique name.

        Storm-owned entries (matching names) are replaced; unrelated user
        entries are preserved in their original position. Supports both a
        top-level JSON array and an object with a ``hooks`` array; other
        top-level keys are preserved.
        """
        hooks_path = self.project_root / HOOKS_TARGET
        self.confined_path(HOOKS_TARGET, allow_runtime=True)
        wrapper = None
        base: list = []
        if hooks_path.exists():
            raw = read_json(hooks_path)
            if isinstance(raw, list):
                base = raw
            elif isinstance(raw, dict) and isinstance(raw.get("hooks"), list):
                wrapper = raw
                base = raw["hooks"]
            else:
                raise ValueError(
                    f"{HOOKS_TARGET} must be a JSON array or an object with a "
                    "'hooks' array; refusing to guess its shape")
        names = [entry["name"] for entry in fragment_entries]
        kept = [
            entry for entry in base
            if not (isinstance(entry, dict) and entry.get("name") in names)
        ]
        merged = kept + fragment_entries
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        if wrapper is not None:
            wrapper["hooks"] = merged
            hooks_path.write_text(json.dumps(wrapper, indent=2) + "\n")
        else:
            hooks_path.write_text(json.dumps(merged, indent=2) + "\n")

    # -- install -----------------------------------------------------------

    def cmd_install(self, force: bool) -> int:
        manifest = self.load_manifest()
        if manifest is None:
            return 1
        if not self.check_runtime_paths():
            self.finding("error", "install-aborted", "install",
                         "runtime paths failed confinement checks; "
                         "no files were written")
            return 1
        ownership = self.load_ownership()

        blocked = []
        actions = []  # (action, asset)
        for asset in manifest["assets"]:
            if asset.get("merge") == "merge-by-name":
                actions.append(("merge-hooks", asset))
                continue
            action = self.classify(asset, ownership)
            if action in {"locally-modified", "unmanaged-collision"}:
                if not force:
                    blocked.append((action, asset))
                    continue
                # Approved overwrite: treat as an update; the backup below
                # still snapshots the prior content first.
                action = "update"
            actions.append((action, asset))

        if blocked:
            for action, asset in blocked:
                if action == "locally-modified":
                    self.finding("error", action, asset["target"],
                                 "target has local edits relative to the "
                                 "ownership checksum; review the difference "
                                 "and re-run with --force to overwrite "
                                 "(a backup is taken first)")
                else:
                    self.finding("error", action, asset["target"],
                                 "an unmanaged file already occupies this "
                                 "managed target; move it aside or re-run "
                                 "with --force to overwrite (a backup is "
                                 "taken first)")
            self.finding("error", "install-aborted", "install",
                         f"{len(blocked)} target(s) refused; no files were written")
            return 1

        writes = [a for a in actions if a[0] in {"create", "update", "adopt"}]
        merges = [a for a in actions if a[0] == "merge-hooks"]

        # Back up everything we are about to touch, plus ownership state.
        backup_dir = None
        records: list[dict] = []
        if writes or merges:
            backup_dir = self.new_backup_dir()
            for _, asset in writes:
                self.capture(backup_dir, records, asset["target"])
            if merges:
                self.capture(backup_dir, records, HOOKS_TARGET)
            self.capture(backup_dir, records, OWNERSHIP_TARGET)
            self.write_backup_manifest(backup_dir, records)

        created: list[Path] = []  # populated for clarity; restore uses backup records
        try:
            for action, asset in writes:
                target_path = self.project_root / asset["target"]
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.source_root / asset["source"], target_path)
                if action == "create":
                    created.append(target_path)
            merged_hook_names: list[str] = []
            for _, asset in merges:
                fragment = read_json(self.source_root / asset["source"])
                if not isinstance(fragment, list) or not all(
                    isinstance(e, dict) and e.get("name") for e in fragment
                ):
                    raise ValueError(
                        f"hook fragment {asset['source']!r} must be an array "
                        "of objects with unique names")
                names = [e["name"] for e in fragment]
                if len(names) != len(set(names)):
                    raise ValueError(
                        f"hook fragment {asset['source']!r} has duplicate names")
                self.merge_hooks(fragment)
                merged_hook_names.extend(names)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if backup_dir is not None:
                try:
                    self.restore_backup(backup_dir)
                except (OSError, ValueError) as restore_exc:
                    self.finding("error", "restore-failed", "install",
                                 f"backup restore also failed ({restore_exc}); "
                                 "manual inspection required")
            self.finding("error", "install-failed", "install",
                         f"install failed ({exc}); prior state restored from backup")
            return 1

        # Preserve renderer-managed role checksums/profile across installs so a
        # later source projection does not overwrite an activated team.
        active_profile = ownership.get("active_profile", {})
        active_path = self.storm_dir / "active-profile.json"
        if active_path.exists():
            try:
                active_profile = read_json(active_path)
            except json.JSONDecodeError:
                self.finding("warning", "active-profile-invalid", str(active_path),
                             "ignoring invalid active profile record")
        # Record ownership for every manifest asset (managed files and the
        # hook fragment source), even ones that were unchanged this run.
        state = {
            "storm_version": manifest.get("storm_version"),
            "manifest_version": manifest.get("manifest_version"),
            "installed_at": utc_stamp(),
            "assets": {
                asset["target"]: {
                    "sha256": asset["sha256"],
                    "kind": asset.get("kind"),
                    "merge": asset.get("merge"),
                }
                for asset in manifest["assets"]
            },
            "merged_hooks": merged_hook_names or ownership.get("merged_hooks", []),
            "active_profile": active_profile,
            "last_backup": (
                str(backup_dir.relative_to(self.project_root))
                if backup_dir is not None else ownership.get("last_backup")
            ),
        }
        self.ownership_path.parent.mkdir(parents=True, exist_ok=True)
        self.ownership_path.write_text(json.dumps(state, indent=2) + "\n")

        counts: dict[str, int] = {}
        for action, _ in actions:
            counts[action] = counts.get(action, 0) + 1
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"OK: install complete ({summary or 'nothing to do'})")
        if backup_dir is not None:
            print(f"backup: {backup_dir.relative_to(self.project_root)}")
        if merges:
            print("hooks merged by name into .polytoken/hooks.json; "
                  "unrelated entries preserved")
        print("run /reload in Polytoken to load the installed definitions")
        return 0

    # -- check -------------------------------------------------------------

    def cmd_check(self) -> int:
        manifest = self.load_manifest()
        if manifest is None:
            return 1
        ownership = self.load_ownership()

        for asset in manifest["assets"]:
            target = asset["target"]
            if asset.get("merge") == "merge-by-name":
                self._check_hook_fragment(asset)
                continue
            action = self.classify(asset, ownership)
            if action == "create":
                severity = "error" if asset.get("required") else "warning"
                self.finding(severity, "missing", target,
                             "managed asset is not installed")
            elif action == "update":
                self.finding("warning", "update-available", target,
                             "installed file matches the ownership checksum "
                             "but the module ships a newer version; run install")
            elif action == "locally-modified":
                self.finding("warning", "locally-modified", target,
                             "target has local edits relative to the ownership "
                             "checksum; merge or approve overwrite via install --force")
            elif action == "unmanaged-collision":
                self.finding("warning", "unmanaged-collision", target,
                             "an unmanaged file occupies this managed target")
            elif action == "adopt":
                self.finding("info", "unmanaged-identical", target,
                             "file matches the module source but is not "
                             "recorded in the ownership manifest; run install")

        # Orphans: ownership entries the manifest no longer ships.
        shipped = {asset["target"] for asset in manifest["assets"]}
        for target in sorted(set(ownership["assets"]) - shipped):
            self.finding("warning", "orphaned", target,
                         "ownership manifest records an asset the module no "
                         "longer ships; remove it deliberately, not by hand")

        return 1 if self.findings else 0

    def _check_hook_fragment(self, asset: dict) -> None:
        hooks_path = self.project_root / HOOKS_TARGET
        try:
            fragment = read_json(self.source_root / asset["source"])
        except json.JSONDecodeError as exc:
            self.finding("error", "fragment-invalid", asset["source"],
                         f"hook fragment is invalid JSON: {exc}")
            return
        names = [e.get("name") for e in fragment if isinstance(e, dict)]
        if not hooks_path.exists():
            severity = "error" if asset.get("required") else "warning"
            self.finding(severity, "hooks-missing", HOOKS_TARGET,
                         f"managed hooks {names} are not installed "
                         "(no hooks.json)")
            return
        try:
            raw = read_json(hooks_path)
        except json.JSONDecodeError:
            self.finding("error", "hooks-invalid", HOOKS_TARGET,
                         "hooks.json is not valid JSON")
            return
        entries = raw if isinstance(raw, list) else raw.get("hooks", [])
        installed = {
            e.get("name"): e for e in entries if isinstance(e, dict) and e.get("name")
        }
        expected = {e.get("name"): e for e in fragment if isinstance(e, dict)}
        for name, expected_entry in expected.items():
            actual = installed.get(name)
            if actual is None:
                self.finding("warning", "hook-missing", name,
                             f"managed hook {name!r} is absent from hooks.json")
            elif actual != expected_entry:
                self.finding("warning", "hook-drift", name,
                             f"managed hook {name!r} differs from the module entry")

    # -- rollback ----------------------------------------------------------

    def manager_backup_dirs(self, backups_root: Path) -> list[Path]:
        """Return only this tool's own backup directories, name-ordered.

        A candidate qualifies only when its ``backup.json`` parses and is
        unambiguously an asset-manager record: ``kind`` absent (legacy) or
        ``manage-polytoken-assets``, and an ``entries`` list present.
        storm-team activation backups (``kind: "storm-team"``, ``roles``
        records instead of ``entries``) and unparseable records are skipped
        so rollback never selects a backup it cannot restore.
        """
        if not backups_root.exists():
            return []
        candidates = []
        for path in backups_root.iterdir():
            if not path.is_dir() or not (path / "backup.json").exists():
                continue
            try:
                manifest = read_json(path / "backup.json")
            except (json.JSONDecodeError, OSError):
                continue
            if manifest.get("kind", BACKUP_KIND) != BACKUP_KIND:
                continue
            if not isinstance(manifest.get("entries"), list):
                continue
            candidates.append(path)
        return sorted(candidates, key=lambda p: p.name)

    def cmd_rollback(self) -> int:
        backups_root = self.storm_dir / "backups"
        candidates = self.manager_backup_dirs(backups_root)
        if not candidates:
            self.finding("error", "no-backups", "rollback",
                         "no backups found; nothing to roll back")
            return 1
        backup_dir = candidates[-1]
        try:
            restored = self.restore_backup(backup_dir)
        except ValueError as exc:
            self.finding("error", "rollback-refused", "rollback",
                         f"rollback refused: {exc}")
            return 1
        print(f"OK: restored {restored} file(s) from "
              f"{backup_dir.relative_to(self.project_root)}")
        print("run /reload in Polytoken to load the restored definitions")
        return 0


# --------------------------------------------------------------------------
# CLI


def emit_json(manager: Manager, command: str, exit_code: int) -> None:
    report = {
        "command": command,
        "ok": exit_code == 0,
        "findings": manager.findings,
        "error_count": sum(1 for f in manager.findings if f["severity"] == "error"),
        "warning_count": sum(1 for f in manager.findings if f["severity"] == "warning"),
    }
    print(json.dumps(report, indent=2))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "check"):
        p = sub.add_parser(name)
        p.add_argument("--source-root", type=Path, required=True)
        p.add_argument("--project-root", type=Path, required=True)
        p.add_argument("--json", action="store_true",
                       help="emit a machine-readable JSON report")
    sub.choices["install"].add_argument(
        "--force", action="store_true",
        help="approved action: overwrite locally-modified or unmanaged "
             "files at managed targets (a backup is taken first)")
    p = sub.add_parser("rollback")
    p.add_argument("--project-root", type=Path, required=True)
    p.add_argument("--json", action="store_true",
                   help="emit a machine-readable JSON report")
    args = parser.parse_args(argv[1:])

    source_root = getattr(args, "source_root", None)
    if source_root is not None:
        source_root = source_root.resolve()
    project_root = args.project_root.resolve()
    manager = Manager(source_root, project_root)
    if source_root is not None and not (source_root / "manifest.json").exists():
        print(f"error: no manifest.json under source root {source_root}",
              file=sys.stderr)
        return 2

    if args.command == "install":
        code = manager.cmd_install(force=args.force)
    elif args.command == "check":
        code = manager.cmd_check()
    else:
        code = manager.cmd_rollback()

    if args.json:
        emit_json(manager, args.command, code)
    else:
        for finding in manager.findings:
            print(f"{finding['severity'].upper()}: {finding['code']}: "
                  f"{finding['subject']}: {finding['message']}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
