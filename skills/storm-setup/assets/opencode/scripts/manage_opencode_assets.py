#!/usr/bin/env python3
"""Strict, project-local OpenCode bootstrap for Storm (stdlib only)."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

BEGIN = b"<!-- BEGIN BMAD-STORM MANAGED BLOCK -->"
END = b"<!-- END BMAD-STORM MANAGED BLOCK -->"
APPEND_REL = Path(".opencode/oh-my-opencode-slim/orchestrator_append.md")


def lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def kind(path: Path) -> str:
    if not lexists(path):
        return "absent"
    mode = os.lstat(os.fspath(path)).st_mode
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    return "special"


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def inferred_module_root() -> Path:
    # .../skills/storm-setup/assets/opencode/scripts/manage_opencode_assets.py
    return Path(__file__).resolve().parents[5]


def block_for(source: bytes) -> bytes:
    return BEGIN + b"\n" + source.rstrip(b"\r\n") + b"\n" + END + b"\n"


def marked_block(data: bytes):
    """Return the one full-line block, or ``None`` if markers are malformed."""

    if data.count(BEGIN) != 1 or data.count(END) != 1:
        return None
    lines = data.splitlines(keepends=True)
    offsets: list[tuple[int, int]] = []
    begin_lines: list[int] = []
    end_lines: list[int] = []
    offset = 0
    for number, line in enumerate(lines):
        offsets.append((offset, offset + len(line)))
        plain = line.rstrip(b"\r\n")
        if plain == BEGIN:
            begin_lines.append(number)
        if plain == END:
            end_lines.append(number)
        offset += len(line)
    if len(begin_lines) != 1 or len(end_lines) != 1:
        return None
    if begin_lines[0] >= end_lines[0]:
        return None
    start = offsets[begin_lines[0]][0]
    finish = offsets[end_lines[0]][1]
    return data[start:finish]


def append_projection(existing: bytes | None, expected: bytes):
    """Classify the append and return (new bytes, old mode).

    ``None`` means the target is absent.  A returned new value of ``None``
    means the existing, valid block needs no write.  Marker-bearing content
    is never repaired automatically.
    """

    if existing is None:
        return expected, 0o644
    has_marker = BEGIN in existing or END in existing
    if not has_marker:
        separator = b"" if existing.endswith((b"\n", b"\r")) else b"\n"
        return existing + separator + expected, None
    block = marked_block(existing)
    if block is None:
        raise ValueError("append has a partial, duplicate, or inline Storm marker")
    if block != expected:
        raise ValueError("append Storm block differs from the shipped block")
    return None, None


class Manager:
    def __init__(self, project_root: Path, module_root: Path | None):
        self.project = project_root.resolve()
        self.module = (module_root or inferred_module_root()).resolve()
        self.errors: list[str] = []
        self.opencode = self.project / ".opencode"
        self.skills_dir = self.opencode / "skills"
        self.omo_dir = self.opencode / "oh-my-opencode-slim"
        self.append = self.project / APPEND_REL

    def error(self, message: str) -> None:
        self.errors.append(message)

    def validate_project_containers(self) -> bool:
        if not self.project.is_dir():
            self.error(f"project root is not a directory: {self.project}")
            return False

        # The lexical project/.opencode path is the boundary.  It is never
        # replaced with a resolved symlink target.
        if kind(self.opencode) == "symlink":
            self.error(".opencode must not be a symlink")
            return False
        if kind(self.opencode) not in {"absent", "directory"}:
            self.error(".opencode must be a directory")
            return False
        if kind(self.opencode) == "directory":
            if not inside(self.opencode, self.project):
                self.error(".opencode resolves outside the project")
                return False

        for path, label in (
            (self.skills_dir, ".opencode/skills"),
            (self.omo_dir, ".opencode/oh-my-opencode-slim"),
        ):
            path_kind = kind(path)
            if path_kind == "absent":
                continue
            if path_kind == "symlink":
                self.error(f"{label} must not be a symlink")
            elif path_kind != "directory":
                self.error(f"{label} must be a directory")
            elif not inside(path, self.project) or not inside(path, self.opencode):
                self.error(f"{label} resolves outside the project boundary")
        return not self.errors

    def source_assets(self):
        skills_root = self.module / "skills"
        if not skills_root.is_dir():
            self.error(f"module skills directory is missing: {skills_root}")
            return None
        source_append = (
            self.module
            / "skills"
            / "storm-setup"
            / "assets"
            / "opencode"
            / "oh-my-opencode-slim"
            / "orchestrator_append.md"
        )
        try:
            append_source = source_append.read_bytes()
        except OSError as exc:
            self.error(f"cannot read shipped append: {exc}")
            return None
        if BEGIN in append_source or END in append_source:
            self.error("shipped append unexpectedly contains Storm markers")
            return None

        assets = []
        for path in sorted(skills_root.iterdir(), key=lambda item: item.name):
            if not path.name.startswith("storm-"):
                continue
            if path.is_symlink() or not path.is_dir() or not (path / "SKILL.md").is_file():
                continue
            source = path.resolve()
            target = self.skills_dir / path.name
            expected_link = os.path.relpath(
                os.fspath(source), os.fspath(self.skills_dir)
            )
            assets.append((path.name, source, target, expected_link))
        return assets, append_source

    @staticmethod
    def exact_link(target: Path, source: Path, expected_text: str) -> bool:
        if kind(target) != "symlink":
            return False
        try:
            return (
                os.readlink(os.fspath(target)) == expected_text
                and Path(os.path.realpath(os.fspath(target))) == source
            )
        except OSError:
            return False

    def preflight(self):
        if not self.validate_project_containers():
            return None
        assets_result = self.source_assets()
        if assets_result is None:
            return None
        assets, append_source = assets_result
        expected_names = {asset[0] for asset in assets}

        # Unexpected Storm links have no ownership record to make them safe to
        # adopt.  Install treats them as collisions; check reports them.
        if kind(self.skills_dir) == "directory":
            for child in self.skills_dir.iterdir():
                if child.name.startswith("storm-") and child.name not in expected_names:
                    self.error(f"unexpected Storm skill target: {child.name}")

        links_to_create = []
        for name, source, target, expected_link in assets:
            if kind(target) == "absent":
                links_to_create.append((name, source, target, expected_link))
            elif not self.exact_link(target, source, expected_link):
                self.error(f"skill target collision: .opencode/skills/{name}")

        append_bytes = None
        append_mode = None
        append_original = None
        append_existed = False
        append_kind = kind(self.append)
        if append_kind == "absent":
            append_bytes, append_mode = block_for(append_source), 0o644
        elif append_kind != "file":
            self.error("OMO-Slim append target must be a regular, non-symlink file")
        else:
            try:
                existing = self.append.read_bytes()
                append_mode = stat.S_IMODE(os.lstat(os.fspath(self.append)).st_mode)
                append_original = existing
                append_existed = True
                append_bytes, _ = append_projection(existing, block_for(append_source))
            except (OSError, ValueError) as exc:
                self.error(str(exc))

        if self.errors:
            return None
        return (
            assets,
            links_to_create,
            append_bytes,
            append_mode,
            append_existed,
            append_original,
        )

    @staticmethod
    def atomic_write(path: Path, data: bytes, mode: int) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".storm-opencode-", dir=os.fspath(path.parent))
        temporary_path = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(os.fspath(temporary_path), mode)
            os.replace(os.fspath(temporary_path), os.fspath(path))
        except BaseException:
            try:
                temporary_path.unlink()
            except OSError:
                pass
            raise

    @staticmethod
    def remove_created_links(created: list[tuple[Path, str]]) -> list[str]:
        errors = []
        for path, expected in reversed(created):
            try:
                path_kind = kind(path)
                if path_kind == "absent":
                    continue
                if path_kind != "symlink":
                    errors.append(f"could not remove created link {path}: it is no longer a link")
                elif os.readlink(os.fspath(path)) != expected:
                    errors.append(f"could not remove created link {path}: it was changed")
                else:
                    path.unlink()
            except OSError as exc:
                errors.append(f"could not remove created link {path}: {exc}")
        return errors

    @staticmethod
    def file_image(path: Path) -> tuple[bytes, int]:
        mode = stat.S_IMODE(os.lstat(os.fspath(path)).st_mode)
        try:
            data = path.read_bytes()
        except PermissionError:
            # Verification must also work for a valid 0000 mode.  Temporarily
            # grant owner-read only for the in-process check, then restore the
            # exact mode before returning.
            os.chmod(os.fspath(path), mode | stat.S_IRUSR)
            try:
                data = path.read_bytes()
            finally:
                os.chmod(os.fspath(path), mode)
        return data, mode

    def restore_append(
        self,
        existed: bool,
        original: bytes | None,
        original_mode: int | None,
        post: tuple[bytes, int],
    ) -> list[str]:
        errors = []
        post_bytes, post_mode = post
        current_kind = kind(self.append)
        original_image = (
            (original or b"", original_mode if original_mode is not None else 0o644)
            if existed
            else None
        )
        if not existed and current_kind == "absent":
            return []
        try:
            if existed and current_kind == "file":
                current_image = self.file_image(self.append)
                if current_image == original_image:
                    return []
            if current_kind != "file":
                return ["append recovery refused: target is no longer a regular file"]
            current_bytes, current_mode = self.file_image(self.append)
        except OSError as exc:
            return [f"append recovery could not inspect target: {exc}"]
        if (current_bytes, current_mode) != (post_bytes, post_mode):
            return [
                "append recovery refused: target no longer matches its post-image; "
                "local changes were preserved"
            ]

        if existed:
            restore_mode = original_mode if original_mode is not None else 0o644
            try:
                self.atomic_write(self.append, original or b"", restore_mode)
                restored = self.file_image(self.append)
                if restored != (original or b"", restore_mode):
                    errors.append("append recovery verification did not restore the exact pre-image")
            except (OSError, ValueError) as exc:
                errors.append(f"append recovery failed: {exc}")
        else:
            try:
                self.append.unlink()
                if kind(self.append) != "absent":
                    errors.append("append recovery verification did not remove the created file")
            except OSError as exc:
                errors.append(f"append recovery failed to remove created append: {exc}")
        return errors

    @staticmethod
    def remove_created_dirs(created: list[Path]) -> list[str]:
        errors = []
        for path in reversed(created):
            try:
                path_kind = kind(path)
                if path_kind == "absent":
                    continue
                if path_kind != "directory":
                    errors.append(f"could not remove transaction directory {path}: it changed")
                else:
                    path.rmdir()
            except OSError as exc:
                errors.append(f"could not remove transaction directory {path}: {exc}")
        return errors

    def ensure_dir(self, path: Path, created: list[Path]) -> None:
        path_kind = kind(path)
        if path_kind == "absent":
            path.mkdir()
            created.append(path)
        elif path_kind != "directory":
            raise OSError(f"transaction container is no longer a directory: {path}")

    def ensure_containers(
        self, need_skills: bool, need_omo: bool, created: list[Path]
    ) -> None:
        if not (need_skills or need_omo):
            return
        self.ensure_dir(self.opencode, created)
        if need_skills:
            self.ensure_dir(self.skills_dir, created)
        if need_omo:
            self.ensure_dir(self.omo_dir, created)

    def install(self) -> int:
        plan = self.preflight()
        if plan is None:
            for error in self.errors:
                print(f"ERROR: {error}")
            return 1
        _, links_to_create, append_bytes, append_mode, append_existed, original_append = plan
        original_mode = append_mode if append_existed else None
        changed_append = append_bytes is not None
        created: list[tuple[Path, str]] = []
        created_dirs: list[Path] = []
        append_attempted = False
        post_image = (
            append_bytes if append_bytes is not None else b"",
            append_mode if append_mode is not None else 0o644,
        )
        try:
            self.ensure_containers(bool(links_to_create), changed_append, created_dirs)
            if changed_append:
                append_attempted = True
                self.atomic_write(self.append, append_bytes, post_image[1])
            for _, _, target, expected_link in links_to_create:
                os.symlink(expected_link, os.fspath(target))
                created.append((target, expected_link))
        except BaseException as exc:
            recovery_errors = self.remove_created_links(created)
            if append_attempted:
                recovery_errors.extend(
                    self.restore_append(
                        append_existed,
                        original_append,
                        original_mode,
                        post_image,
                    )
                )
            recovery_errors.extend(self.remove_created_dirs(created_dirs))
            self.error(f"install failed ({exc})")
            if recovery_errors:
                self.errors.extend(f"recovery: {error}" for error in recovery_errors)
            else:
                self.error("recovery completed: original state restored")
            for error in self.errors:
                print(f"ERROR: {error}")
            return 1
        print(
            f"OK: installed {len(links_to_create)} skill link(s)"
            + (" and append" if changed_append else "; append unchanged")
        )
        return 0

    def check(self) -> int:
        plan = self.preflight()
        if plan is not None:
            _, links_to_create, append_bytes, _, _, _ = plan
            for name, _, _, _ in links_to_create:
                self.error(f"missing skill link: .opencode/skills/{name}")
            if append_bytes is not None:
                self.error("OMO-Slim append is missing or not in the shipped state")
        if kind(self.skills_dir) == "directory":
            expected = {asset[0] for asset in (self.source_assets() or ([], b""))[0]}
            for child in self.skills_dir.iterdir():
                if child.name.startswith("storm-") and child.name not in expected:
                    if kind(child) == "symlink":
                        self.error(f"orphaned Storm skill link: {child.name}")
        for error in self.errors:
            print(f"ERROR: {error}")
        if not self.errors:
            print("OK: OpenCode asset check is clean")
            return 0
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("install", "check"):
        command_parser = sub.add_parser(command)
        command_parser.add_argument("--project-root", type=Path, required=True)
        command_parser.add_argument("--module-root", type=Path)
    args = parser.parse_args(argv)
    manager = Manager(args.project_root, args.module_root)
    return manager.install() if args.command == "install" else manager.check()


if __name__ == "__main__":
    sys.exit(main())
