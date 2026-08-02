"""Isolated tests for the strict native OpenCode projection."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import contextlib
import importlib.util
import io
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/storm-setup/assets/opencode/scripts/manage_opencode_assets.py"
ASSET_ROOT = ROOT / "skills/storm-setup/assets/opencode"
BEGIN = b"<!-- BEGIN BMAD-STORM MANAGED BLOCK -->"
END = b"<!-- END BMAD-STORM MANAGED BLOCK -->"

sys.dont_write_bytecode = True
_SPEC = importlib.util.spec_from_file_location("storm_opencode_manager", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
MANAGER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MANAGER)


class OpenCodeAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.module = self.root / "module"
        self.project.mkdir()
        shutil.copytree(
            ASSET_ROOT,
            self.module / "skills/storm-setup/assets/opencode",
        )
        for name in ("storm-alpha", "storm-beta"):
            skill = self.module / "skills" / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_manager(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                command,
                "--project-root",
                str(self.project),
                "--module-root",
                str(self.module),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    @property
    def append(self) -> Path:
        return self.project / ".opencode/oh-my-opencode-slim/orchestrator_append.md"

    def skill(self, name: str) -> Path:
        return self.project / ".opencode/skills" / name

    def snapshot(self):
        result = []
        if not self.project.exists() and not self.project.is_symlink():
            return result
        for current, directories, files in os.walk(self.project, followlinks=False):
            current_path = Path(current)
            for name in sorted(directories + files):
                path = current_path / name
                relative = str(path.relative_to(self.project))
                mode = stat.S_IMODE(os.lstat(path).st_mode)
                if path.is_symlink():
                    result.append((relative, "link", os.readlink(path), mode))
                elif path.is_file():
                    result.append((relative, "file", path.read_bytes(), mode))
                else:
                    result.append((relative, "directory", None, mode))
        return result

    @staticmethod
    def snapshot_path(root: Path):
        result = []
        for current, directories, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            for name in sorted(directories + files):
                path = current_path / name
                mode = stat.S_IMODE(os.lstat(path).st_mode)
                if path.is_symlink():
                    result.append((str(path.relative_to(root)), "link", os.readlink(path), mode))
                elif path.is_file():
                    result.append((str(path.relative_to(root)), "file", path.read_bytes(), mode))
                else:
                    result.append((str(path.relative_to(root)), "directory", None, mode))
        return result

    def install_ok(self) -> None:
        result = self.run_manager("install")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_clean_install_and_idempotence_without_state_or_backups(self) -> None:
        self.install_ok()
        first = self.snapshot()
        self.assertFalse((self.project / ".opencode/storm").exists())
        for name in ("storm-alpha", "storm-beta"):
            link = self.skill(name)
            self.assertTrue(link.is_symlink())
            self.assertFalse(os.path.isabs(os.readlink(link)))
            self.assertEqual(link.resolve(), (self.module / "skills" / name).resolve())
        content = self.append.read_bytes()
        self.assertEqual(content.count(BEGIN), 1)
        self.assertEqual(content.count(END), 1)

        second = self.run_manager("install")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(first, self.snapshot())
        self.assertFalse((self.project / ".opencode/storm").exists())

    def test_check_is_read_only(self) -> None:
        self.install_ok()
        before = self.snapshot()
        result = self.run_manager("check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_crlf_user_append_bytes_and_mode_are_preserved(self) -> None:
        self.append.parent.mkdir(parents=True)
        user_bytes = b"# Existing OMO policy\r\nKeep this text exactly.\r\n"
        self.append.write_bytes(user_bytes)
        os.chmod(self.append, 0o640)
        self.install_ok()
        projected = self.append.read_bytes()
        self.assertTrue(projected.startswith(user_bytes))
        self.assertEqual(projected.count(BEGIN), 1)
        self.assertEqual(projected.count(END), 1)
        self.assertEqual(stat.S_IMODE(os.lstat(self.append).st_mode), 0o640)

    def test_collision_aborts_before_any_write(self) -> None:
        target = self.skill("storm-alpha")
        target.parent.mkdir(parents=True)
        target.write_text("operator-owned\n", encoding="utf-8")
        before = self.snapshot()
        result = self.run_manager("install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("collision", result.stdout)
        self.assertEqual(before, self.snapshot())

    def test_changed_partial_and_inline_duplicate_markers_abort_without_mutation(self) -> None:
        shipped = (
            self.module
            / "skills/storm-setup/assets/opencode/oh-my-opencode-slim/orchestrator_append.md"
        ).read_bytes()
        expected = BEGIN + b"\n" + shipped.rstrip(b"\r\n") + b"\n" + END + b"\n"
        cases = {
            "changed": expected.replace(b"Before publication", b"Changed publication", 1),
            "partial": b"operator text\n" + BEGIN + b"\nunfinished\n",
            "inline": expected + b"inline " + BEGIN + b"\n",
        }
        for label, content in cases.items():
            with self.subTest(label=label):
                self.project = self.root / f"project-{label}"
                self.project.mkdir()
                append = self.project / ".opencode/oh-my-opencode-slim/orchestrator_append.md"
                append.parent.mkdir(parents=True)
                append.write_bytes(content)
                before = self.snapshot()
                result = self.run_manager("install")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(before, self.snapshot())

    def test_opencode_self_symlink_is_refused(self) -> None:
        for target_kind in ("project-root", "internal"):
            with self.subTest(target_kind=target_kind):
                self.project = self.root / f"project-opencode-{target_kind}"
                self.project.mkdir()
                target = self.project if target_kind == "project-root" else self.project / "internal-opencode"
                if target_kind == "internal":
                    target.mkdir()
                    (target / "sentinel").write_bytes(b"must remain untouched\n")
                target_before = self.snapshot_path(target)
                self.project.joinpath(".opencode").symlink_to(target, target_is_directory=True)
                before = self.snapshot()
                result = self.run_manager("install")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(before, self.snapshot())
                if target_kind == "internal":
                    self.assertEqual(target_before, self.snapshot_path(target))

    def test_internal_container_symlinks_are_refused(self) -> None:
        cases = (
            ("skills", "outside", False),
            ("oh-my-opencode-slim", "outside", False),
            ("skills", "internal", True),
            ("oh-my-opencode-slim", "internal", True),
        )
        for container, target_kind, internal in cases:
            with self.subTest(container=container, target_kind=target_kind):
                self.project = self.root / f"project-{container}-{target_kind}"
                self.project.mkdir()
                opencode = self.project / ".opencode"
                opencode.mkdir()
                target = self.root / f"target-{container}-{target_kind}"
                if internal:
                    target = self.project / f"internal-{container}"
                target.mkdir()
                sentinel = target / "sentinel"
                sentinel.write_bytes(b"must remain untouched\n")
                target_before = self.snapshot_path(target)
                (opencode / container).symlink_to(target, target_is_directory=True)
                before = self.snapshot()
                result = self.run_manager("install")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(before, self.snapshot())
                self.assertEqual(target_before, self.snapshot_path(target))

    def test_expected_link_replacement_is_refused(self) -> None:
        self.install_ok()
        link = self.skill("storm-alpha")
        link.unlink()
        os.symlink(os.path.relpath(self.module / "skills/storm-beta", link.parent), link)
        before = self.snapshot()
        result = self.run_manager("install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("collision", result.stdout)
        self.assertEqual(before, self.snapshot())

    def test_check_reports_unexpected_storm_link_as_orphan(self) -> None:
        self.install_ok()
        orphan = self.skill("storm-orphan")
        os.symlink(os.path.relpath(self.module / "skills/storm-alpha", orphan.parent), orphan)
        before = self.snapshot()
        result = self.run_manager("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("orphaned Storm skill link", result.stdout)
        self.assertEqual(before, self.snapshot())

    def test_zero_mode_reaches_atomic_write_without_reading_a_file(self) -> None:
        manager = MANAGER.Manager(self.project, self.module)
        with (
            mock.patch.object(MANAGER, "kind", return_value="file"),
            mock.patch.object(
                MANAGER.Manager,
                "file_image",
                side_effect=[(b"post", 0), (b"post", 0), (b"original", 0)],
            ),
            mock.patch.object(MANAGER.Manager, "atomic_write") as atomic_write,
        ):
            errors = manager.restore_append(
                True,
                b"original",
                0,
                (b"post", 0),
            )
        self.assertEqual(errors, [])
        atomic_write.assert_called_once_with(manager.append, b"original", 0)

    def test_second_symlink_failure_restores_exact_snapshot_and_dirs(self) -> None:
        self.append.parent.mkdir(parents=True)
        original = b"# user\r\nKeep CRLF bytes.\r\n"
        self.append.write_bytes(original)
        os.chmod(self.append, 0o640)
        before = self.snapshot()
        manager = MANAGER.Manager(self.project, self.module)
        real_symlink = MANAGER.os.symlink
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second symlink failure")
            return real_symlink(source, target)

        output = io.StringIO()
        with mock.patch.object(MANAGER.os, "symlink", side_effect=fail_second):
            with contextlib.redirect_stdout(output):
                result = manager.install()
        self.assertEqual(result, 1)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.append.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(os.lstat(self.append).st_mode), 0o640)
        self.assertIn("recovery completed", output.getvalue())

    def test_recovery_cleanup_failure_is_reported(self) -> None:
        self.append.parent.mkdir(parents=True)
        self.append.write_bytes(b"# user\r\n")
        manager = MANAGER.Manager(self.project, self.module)
        real_symlink = MANAGER.os.symlink
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second symlink failure")
            return real_symlink(source, target)

        output = io.StringIO()
        with (
            mock.patch.object(MANAGER.os, "symlink", side_effect=fail_second),
            mock.patch.object(Path, "rmdir", side_effect=OSError("injected cleanup failure")),
        ):
            with contextlib.redirect_stdout(output):
                result = manager.install()
        self.assertEqual(result, 1)
        self.assertEqual(self.append.read_bytes(), b"# user\r\n")
        self.assertIn("could not remove transaction directory", output.getvalue())
        self.assertIn("injected cleanup failure", output.getvalue())

    def test_atomic_write_failure_before_replace_recovers_cleanly(self) -> None:
        self.append.parent.mkdir(parents=True)
        original = b"# user\r\nKeep bytes.\r\n"
        self.append.write_bytes(original)
        os.chmod(self.append, 0o640)
        before = self.snapshot()
        manager = MANAGER.Manager(self.project, self.module)
        output = io.StringIO()
        with mock.patch.object(
            MANAGER.Manager,
            "atomic_write",
            side_effect=OSError("injected pre-replacement failure"),
        ):
            with contextlib.redirect_stdout(output):
                result = manager.install()
        self.assertEqual(result, 1)
        self.assertEqual(before, self.snapshot())
        self.assertIn("recovery completed", output.getvalue())
        self.assertNotIn("recovery refused", output.getvalue())

    def test_second_link_failure_preserves_distinct_local_append_conflict(self) -> None:
        self.append.parent.mkdir(parents=True)
        self.append.write_bytes(b"# original\r\n")
        manager = MANAGER.Manager(self.project, self.module)
        local_bytes = b"# concurrent local replacement\n"
        real_symlink = MANAGER.os.symlink
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                manager.append.write_bytes(local_bytes)
                raise OSError("injected second symlink failure")
            return real_symlink(source, target)

        output = io.StringIO()
        with mock.patch.object(MANAGER.os, "symlink", side_effect=fail_second):
            with contextlib.redirect_stdout(output):
                result = manager.install()
        self.assertEqual(result, 1)
        self.assertEqual(self.append.read_bytes(), local_bytes)
        self.assertIn("append recovery refused", output.getvalue())
        self.assertIn("local changes were preserved", output.getvalue())

    def test_empty_project_second_link_failure_removes_all_created_containers(self) -> None:
        manager = MANAGER.Manager(self.project, self.module)
        real_symlink = MANAGER.os.symlink
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second symlink failure")
            return real_symlink(source, target)

        output = io.StringIO()
        with mock.patch.object(MANAGER.os, "symlink", side_effect=fail_second):
            with contextlib.redirect_stdout(output):
                result = manager.install()
        self.assertEqual(result, 1)
        self.assertFalse(os.path.lexists(self.project / ".opencode"))
        self.assertEqual(self.snapshot(), [])
        self.assertIn("recovery completed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
