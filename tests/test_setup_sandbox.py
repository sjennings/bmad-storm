"""Setup/distribution/doctor sandbox tests (AC.12, AC.13).

Exercises manage_polytoken_assets.py install/check/rollback and
storm-doctor against temporary consuming-project fixtures. Standard
library only; every test runs the real shipped scripts via subprocess.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/storm-setup/assets/polytoken"
MANAGER = ASSETS / "scripts/manage_polytoken_assets.py"
DOCTOR = ROOT / "skills/storm-doctor/doctor.py"
RENDER_TEAM = ROOT / "skills/storm-team/render_team.py"


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True,
    )


class SandboxCase(unittest.TestCase):
    """Base fixture: a temp source copy (so tests may mutate it) and a temp
    consuming project."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="storm-setup-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = self.tmp / "src"
        shutil.copytree(ASSETS, self.src)
        self.project = self.tmp / "project"
        self.project.mkdir()

    # -- helpers -----------------------------------------------------------

    def manifest(self) -> dict:
        return json.loads((self.src / "manifest.json").read_text())

    def install(self, *extra: str) -> subprocess.CompletedProcess:
        return run(MANAGER, "install", "--source-root", str(self.src),
                   "--project-root", str(self.project), *extra)

    def check(self, *extra: str) -> subprocess.CompletedProcess:
        return run(MANAGER, "check", "--source-root", str(self.src),
                   "--project-root", str(self.project), *extra)

    def rollback(self) -> subprocess.CompletedProcess:
        return run(MANAGER, "rollback", "--project-root", str(self.project))

    def project_file(self, target: str) -> Path:
        return self.project / target

    def repin_source(self, source: str, new_content: str) -> None:
        """Mutate a copied source asset and re-pin its manifest checksum."""
        (self.src / source).write_text(new_content)
        manifest_path = self.src / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        for asset in manifest["assets"]:
            if asset["source"] == source:
                asset["sha256"] = hashlib.sha256(
                    new_content.encode()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    def snapshot_tree(self, base: Path) -> dict[str, str]:
        return {
            str(p.relative_to(base)): sha256_path(p)
            for p in sorted(base.rglob("*")) if p.is_file()
        }


class InstallTests(SandboxCase):
    def test_install_projects_all_manifest_assets(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = self.manifest()
        for asset in manifest["assets"]:
            target = self.project_file(asset["target"])
            if asset["merge"] == "merge-by-name":
                continue  # merged into hooks.json, not written verbatim
            self.assertTrue(target.exists(), asset["target"])
            self.assertEqual(sha256_path(target), asset["sha256"])
        ownership = json.loads(
            self.project_file(".polytoken/storm/ownership.json").read_text())
        self.assertEqual(ownership["storm_version"], manifest["storm_version"])
        self.assertEqual(
            set(ownership["assets"]),
            {asset["target"] for asset in manifest["assets"]},
        )
        self.assertEqual(ownership["merged_hooks"],
                         ["storm-continue-on-idle", "storm-continue-reset"])

    def test_install_does_not_overwrite_rendered_profile(self):
        self.assertEqual(self.install().returncode, 0)
        rendered = self.project_file(".polytoken/subagents/storm-oracle.md")
        rendered.write_text(rendered.read_text().replace("name: storm-oracle", "name: storm-oracle\n# rendered profile"))
        # Simulate renderer ownership record; manager must preserve the rendered file.
        active = self.project_file(".polytoken/storm/active-profile.json")
        active.parent.mkdir(parents=True, exist_ok=True)
        import hashlib
        active.write_text(json.dumps({"profile": "balanced", "role_checksums": {
            "storm-oracle": hashlib.sha256(rendered.read_bytes()).hexdigest()
        }}))
        self.assertEqual(self.install().returncode, 0)
        self.assertIn("rendered profile", rendered.read_text())
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_install_preserves_unrelated_user_files(self):
        user_agent = self.project_file(".polytoken/subagents/user-agent.md")
        user_agent.parent.mkdir(parents=True)
        user_agent.write_text("user-authored agent\n")
        user_other = self.project_file(".polytoken/notes/keep.txt")
        user_other.parent.mkdir(parents=True)
        user_other.write_text("unrelated content\n")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(user_agent.read_text(), "user-authored agent\n")
        self.assertEqual(user_other.read_text(), "unrelated content\n")

    def test_install_writes_nothing_outside_polytoken(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        top_level = {p.name for p in self.project.iterdir()}
        self.assertEqual(top_level, {".polytoken"})

    def test_reserved_storm_target_is_rejected(self):
        manifest_path = self.src / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["assets"].append({"source": "profiles/inherit.json", "target": ".polytoken/storm/evil.json", "kind": "profile", "merge": "managed-file", "required": False, "sha256": manifest["assets"][-1]["sha256"]})
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        result = self.install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("reserved", result.stdout + result.stderr)

    def test_symlink_target_outside_polytoken_is_rejected(self):
        target = self.project / ".polytoken/subagents"
        target.parent.mkdir(parents=True)
        outside = self.tmp / "outside"
        outside.mkdir()
        target.symlink_to(outside, target_is_directory=True)
        result = self.install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside", result.stdout + result.stderr)

    def test_target_escape_is_rejected_before_any_write(self):
        manifest_path = self.src / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["assets"].append({
            "source": "profiles/inherit.json",
            "target": "../evil.txt",
            "kind": "profile",
            "merge": "managed-file",
            "required": False,
            "sha256": manifest["assets"][-1]["sha256"],
        })
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        result = self.install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("escapes", result.stdout + result.stderr)
        self.assertFalse((self.tmp / "evil.txt").exists())
        self.assertFalse((self.project / ".polytoken").exists())


class UpdateTests(SandboxCase):
    def test_unmanaged_collision_refused_without_force(self):
        target = self.project_file(".polytoken/subagents/storm-oracle.md")
        target.parent.mkdir(parents=True)
        target.write_text("someone else's file\n")
        result = self.install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("unmanaged-collision", result.stdout + result.stderr)
        self.assertEqual(target.read_text(), "someone else's file\n")

    def test_modified_target_detected_and_refused_without_force(self):
        self.assertEqual(self.install().returncode, 0)
        target = self.project_file(".polytoken/subagents/storm-oracle.md")
        target.write_text(target.read_text() + "local edit\n")

        check = self.check()
        self.assertEqual(check.returncode, 1)
        self.assertIn("locally-modified", check.stdout)

        reinstall = self.install()
        self.assertEqual(reinstall.returncode, 1)
        self.assertIn("locally-modified", reinstall.stdout)
        self.assertTrue(target.read_text().endswith("local edit\n"))

    def test_force_overwrites_with_backup(self):
        self.assertEqual(self.install().returncode, 0)
        target = self.project_file(".polytoken/subagents/storm-oracle.md")
        edited = target.read_text() + "local edit\n"
        target.write_text(edited)
        forced = self.install("--force")
        self.assertEqual(forced.returncode, 0, forced.stdout + forced.stderr)
        self.assertEqual(
            sha256_path(target),
            sha256_path(self.src / "subagents/storm-oracle.md"),
        )
        backups = list(
            self.project_file(".polytoken/storm/backups").iterdir())
        self.assertTrue(backups, "force install must take a backup")
        latest = sorted(backups, key=lambda p: p.name)[-1]
        manifest = json.loads((latest / "backup.json").read_text())
        entry = next(e for e in manifest["entries"]
                     if e["target"] == ".polytoken/subagents/storm-oracle.md")
        self.assertEqual((latest / entry["backup_file"]).read_text(), edited)

    def test_unchanged_managed_file_updates_to_new_source(self):
        self.assertEqual(self.install().returncode, 0)
        source = "profiles/balanced.json"
        updated = (self.src / source).read_text() + "\n"
        self.repin_source(source, updated)

        check = self.check()
        self.assertEqual(check.returncode, 1)
        self.assertIn("update-available", check.stdout)

        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.project_file(".polytoken/storm/profiles/balanced.json")
            .read_text(),
            updated,
        )
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_failed_install_restores_prior_state(self):
        self.assertEqual(self.install().returncode, 0)
        # Make one managed file need an update, then break hooks.json so the
        # merge step fails after file writes have begun.
        source = "profiles/economy.json"
        original = self.project_file(
            ".polytoken/storm/profiles/economy.json").read_text()
        self.repin_source(source, original + "\n")
        hooks = self.project_file(".polytoken/hooks.json")
        broken = hooks.read_text() + " not json"
        hooks.write_text(broken)

        result = self.install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("restored", result.stdout + result.stderr)
        # The profile write was rolled back and hooks.json is as before.
        self.assertEqual(
            self.project_file(".polytoken/storm/profiles/economy.json")
            .read_text(),
            original,
        )
        self.assertEqual(hooks.read_text(), broken)
        # Ownership state was not advanced by the failed install.
        ownership = json.loads(
            self.project_file(".polytoken/storm/ownership.json").read_text())
        self.assertNotEqual(
            ownership["assets"][".polytoken/storm/profiles/economy.json"]
            ["sha256"],
            hashlib.sha256((original + "\n").encode()).hexdigest(),
        )


class HookMergeTests(SandboxCase):
    def test_hook_merge_preserves_unrelated_entries(self):
        hooks = self.project_file(".polytoken/hooks.json")
        hooks.parent.mkdir(parents=True, exist_ok=True)
        user_hook = {"name": "user-hook", "event": "stop",
                     "handler": {"bash": "true"}}
        hooks.write_text(json.dumps([user_hook]) + "\n")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        merged = json.loads(hooks.read_text())
        names = [entry["name"] for entry in merged]
        self.assertEqual(names[0], "user-hook")
        self.assertIn("storm-continue-on-idle", names)
        self.assertIn("storm-continue-reset", names)
        self.assertEqual(merged[0], user_hook)

    def test_hook_merge_is_idempotent(self):
        self.assertEqual(self.install().returncode, 0)
        first = self.project_file(".polytoken/hooks.json").read_text()
        self.assertEqual(self.install().returncode, 0)
        second = self.project_file(".polytoken/hooks.json").read_text()
        self.assertEqual(first, second)
        names = [e["name"] for e in json.loads(second)]
        self.assertEqual(len(names), len(set(names)))

    def test_hook_merge_supports_object_wrapper_shape(self):
        hooks = self.project_file(".polytoken/hooks.json")
        hooks.parent.mkdir(parents=True, exist_ok=True)
        hooks.write_text(json.dumps({
            "version": 1,
            "hooks": [{"name": "user-hook", "event": "stop",
                       "handler": {"bash": "true"}}],
        }) + "\n")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        merged = json.loads(hooks.read_text())
        self.assertEqual(merged["version"], 1)  # unrelated keys preserved
        names = [entry["name"] for entry in merged["hooks"]]
        self.assertIn("user-hook", names)
        self.assertIn("storm-continue-on-idle", names)

    def test_check_reports_missing_managed_hooks(self):
        self.assertEqual(self.install().returncode, 0)
        hooks = self.project_file(".polytoken/hooks.json")
        hooks.write_text(json.dumps([
            e for e in json.loads(hooks.read_text())
            if e.get("name") != "storm-continue-on-idle"
        ]) + "\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("hook-missing", result.stdout)


class CheckAndRollbackTests(SandboxCase):
    def test_check_is_read_only(self):
        self.assertEqual(self.install().returncode, 0)
        target = self.project_file(".polytoken/subagents/storm-fixer.md")
        target.write_text(target.read_text() + "local edit\n")
        before = self.snapshot_tree(self.project)
        result = self.check("--json")
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertTrue(any(f["code"] == "locally-modified"
                            for f in report["findings"]))
        self.assertEqual(self.snapshot_tree(self.project), before)

    def test_check_clean_install_passes(self):
        self.assertEqual(self.install().returncode, 0)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_reports_orphaned_ownership_entries(self):
        self.assertEqual(self.install().returncode, 0)
        # Remove an asset from the copied manifest; its ownership entry
        # becomes an orphan.
        manifest_path = self.src / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["assets"] = [
            a for a in manifest["assets"]
            if a["target"] != ".polytoken/storm/profiles/inherit.json"
        ]
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("orphaned", result.stdout)

    def test_rollback_restores_prior_content(self):
        self.assertEqual(self.install().returncode, 0)
        target = self.project_file(".polytoken/subagents/storm-oracle.md")
        edited = target.read_text() + "local edit\n"
        target.write_text(edited)
        self.assertEqual(self.install("--force").returncode, 0)
        result = self.rollback()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(target.read_text(), edited)

    def test_rollback_removes_files_the_install_created(self):
        self.assertEqual(self.install().returncode, 0)
        self.assertTrue(
            self.project_file(".polytoken/subagents/storm-oracle.md").exists())
        result = self.rollback()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(
            self.project_file(".polytoken/subagents/storm-oracle.md").exists())
        self.assertFalse(self.project_file(".polytoken/hooks.json").exists())

    def test_rollback_without_backups_fails_cleanly(self):
        result = self.rollback()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no backups", result.stdout + result.stderr)


class SymlinkConfinementTests(SandboxCase):
    """Runtime paths and restore targets must not follow symlinks out of
    the project root or .polytoken/ (AC.12 hardening)."""

    def test_symlinked_storm_dir_rejected_before_writes(self):
        storm = self.project / ".polytoken/storm"
        storm.parent.mkdir(parents=True)
        outside = self.tmp / "outside-storm"
        outside.mkdir()
        storm.symlink_to(outside, target_is_directory=True)
        result = self.install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside", result.stdout + result.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_hooks_json_rejected_and_untouched(self):
        outside_file = self.tmp / "outside-hooks.json"
        outside_file.write_text("[]\n")
        hooks = self.project / ".polytoken/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.symlink_to(outside_file)
        result = self.install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside", result.stdout + result.stderr)
        self.assertEqual(outside_file.read_text(), "[]\n")

    def test_symlinked_polytoken_root_rejected(self):
        outside = self.tmp / "outside-polytoken"
        outside.mkdir()
        (self.project / ".polytoken").symlink_to(
            outside, target_is_directory=True)
        result = self.install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside", result.stdout + result.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_rollback_refuses_symlinked_restore_target(self):
        self.assertEqual(self.install().returncode, 0)
        target = self.project_file(".polytoken/subagents/storm-oracle.md")
        outside_file = self.tmp / "outside-oracle.md"
        outside_file.write_text("outside\n")
        target.unlink()
        target.symlink_to(outside_file)
        result = self.rollback()
        self.assertEqual(result.returncode, 1)
        self.assertIn("refused", result.stdout + result.stderr)
        self.assertEqual(outside_file.read_text(), "outside\n")


class MixedBackupTests(SandboxCase):
    """Fresh-review fix: storm-team and asset-manager backups are isolated.

    Team activation snapshots live under ``.polytoken/storm/team-backups/``
    with ``kind: "storm-team"`` records; manager snapshots live under
    ``.polytoken/storm/backups/`` with ``kind: "manage-polytoken-assets"``
    records. Each rollback path must select only its own kind, even when a
    foreign record is present (or co-located) with a newer timestamp.
    """

    def render(self, *args: str) -> subprocess.CompletedProcess:
        return run(RENDER_TEAM, *args)

    def activate(self, profile: str = "balanced") -> subprocess.CompletedProcess:
        return self.render(
            "--profile", str(self.src / "profiles" / f"{profile}.json"),
            "--templates", str(self.src / "subagents"),
            "--target", str(self.project / ".polytoken/subagents"))

    def team_rollback(self) -> subprocess.CompletedProcess:
        return self.render("--rollback", "--target",
                           str(self.project / ".polytoken/subagents"))

    def test_manager_backups_carry_kind_marker(self):
        self.assertEqual(self.install().returncode, 0)
        backups = list(self.project_file(".polytoken/storm/backups").iterdir())
        self.assertTrue(backups)
        record = json.loads((backups[0] / "backup.json").read_text())
        self.assertEqual(record["kind"], "manage-polytoken-assets")
        self.assertIsInstance(record["entries"], list)

    def test_install_activate_install_check_team_rollback(self):
        # Full mixed lifecycle: setup install → team activate → setup
        # install/check (manager backups again) → team rollback.
        self.assertEqual(self.install().returncode, 0)
        result = self.activate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        oracle = self.project_file(".polytoken/subagents/storm-oracle.md")
        rendered = oracle.read_text()
        self.assertIn("model:", rendered)
        # A second activation makes the balanced set the rollback target
        # (economy renders a different oracle model, so restore is visible).
        result = self.activate("economy")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("model: default_model:mini", oracle.read_text())
        self.assertTrue(
            self.project_file(".polytoken/storm/team-backups").is_dir(),
            "team backups live apart from manager backups")
        self.assertEqual(self.install().returncode, 0)
        check = self.check()
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        # Corrupt a role; team rollback restores the balanced set from its
        # own backup, never a (newer) manager backup.
        oracle.write_text(oracle.read_text() + "corrupt\n")
        result = self.team_rollback()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(oracle.read_text(), rendered)

    def test_manager_rollback_ignores_team_shaped_backups(self):
        self.assertEqual(self.install().returncode, 0)
        target = self.project_file(".polytoken/subagents/storm-oracle.md")
        edited = target.read_text() + "local edit\n"
        target.write_text(edited)
        self.assertEqual(self.install("--force").returncode, 0)
        # Plant a storm-team-shaped record that sorts newest by name; manager
        # rollback must skip it and restore the real manager backup instead.
        stray = self.project_file(
            ".polytoken/storm/backups/99999999-999999-team")
        stray.mkdir(parents=True)
        (stray / "backup.json").write_text(json.dumps({
            "kind": "storm-team",
            "roles": [{"name": "storm-oracle", "existed": False}],
        }))
        result = self.rollback()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(target.read_text(), edited)


class DoctorTests(SandboxCase):
    def doctor(self, *extra: str) -> subprocess.CompletedProcess:
        return run(DOCTOR, *extra)

    def test_doctor_module_only_is_clean_and_machine_readable(self):
        result = self.doctor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["error_count"], 0)
        for name in ("module_metadata", "source_assets", "projection",
                     "profiles_roles", "capabilities", "hook_safety",
                     "alias_contract", "config_keys"):
            self.assertIn(name, report["checks"])
        self.assertEqual(report["checks"]["projection"]["status"], "skipped")

    def test_doctor_reports_projection_drift(self):
        self.assertEqual(self.install().returncode, 0)
        target = self.project_file(".polytoken/subagents/storm-fixer.md")
        target.write_text(target.read_text() + "local edit\n")
        result = self.doctor("--project-root", str(self.project))
        self.assertEqual(result.returncode, 0)  # warnings don't fail the run
        report = json.loads(result.stdout)
        codes = [f["code"] for f in report["checks"]["projection"]["findings"]]
        self.assertIn("locally-modified", codes)

    def test_doctor_is_read_only(self):
        self.assertEqual(self.install().returncode, 0)
        before = self.snapshot_tree(self.project)
        result = self.doctor("--project-root", str(self.project))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot_tree(self.project), before)

    def test_doctor_never_emits_secret_values(self):
        config = self.project / "_bmad/storm/config.yaml"
        config.parent.mkdir(parents=True)
        secret_value = "shh-do-not-leak-0123456789"
        config.write_text(
            "linear_team: Example\n"
            f"polytoken_review_models: {secret_value}\n"
        )
        result = self.doctor("--project-root", str(self.project))
        self.assertNotIn(secret_value, result.stdout)
        self.assertNotIn(secret_value, result.stderr)
        report = json.loads(result.stdout)
        # The key name is reported; the value never is.
        self.assertIn("config_keys", report["checks"])


if __name__ == "__main__":
    unittest.main()
