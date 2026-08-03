"""Executable contracts for Storm's Polytoken asset package (AC.5, AC.8, AC.10, AC.13)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/storm-setup/assets/polytoken"
VALIDATOR_PATH = ASSETS / "scripts/validate_polytoken_assets.py"
HOOK_SCRIPT = ASSETS / "hooks/storm-continue-on-idle.sh"
RENDER_TEAM = ROOT / "skills/storm-team/render_team.py"

spec = importlib.util.spec_from_file_location("validate_polytoken_assets", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(validator)

spec_rt = importlib.util.spec_from_file_location("render_team", RENDER_TEAM)
render_team = importlib.util.module_from_spec(spec_rt)
spec_rt.loader.exec_module(render_team)


def load_frontmatter(role: str) -> dict:
    return validator.parse_frontmatter(ASSETS / "subagents" / f"{role}.md")


def polytoken_block(role: str) -> dict:
    return load_frontmatter(role)["polytoken"]


class SubagentDefinitionTests(unittest.TestCase):
    """AC.5: least-privilege specialist package."""

    def test_validator_reports_no_findings_on_shipped_assets(self):
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_frontmatter_name_matches_filename(self):
        for role in validator.ALL_ROLES:
            self.assertEqual(load_frontmatter(role)["name"], role)

    def test_no_role_grants_exit_tool(self):
        for role in validator.ALL_ROLES:
            poly = polytoken_block(role)
            self.assertNotIn("exit_tool", poly.get("tools", []))
            self.assertNotIn("exit_tool", poly.get("tools_deny", []))

    def test_read_only_roles_have_no_mutation_tools(self):
        forbidden = (validator.MUTATION_BUILTIN_TOOLS
                     | set(validator.LIFECYCLE_CONTROL_TOOLS))
        for role in validator.READ_ONLY_ROLES:
            poly = polytoken_block(role)
            self.assertFalse(set(poly.get("tools", [])) & forbidden,
                             f"{role} grants mutating tools")
            self.assertIs(poly.get("inherit_tools"), False)
            self.assertIs(poly.get("allow_subagent_spawn"), False)

    def test_write_roles_deny_lifecycle_tracker_and_shell_tools(self):
        for role in validator.WRITE_ROLES:
            deny = set(polytoken_block(role).get("tools_deny", []))
            missing = [t for t in validator.WRITE_ROLE_REQUIRED_DENY if t not in deny]
            self.assertEqual(missing, [], f"{role} deny list is missing {missing}")

    def test_write_roles_are_execute_dispatch_only_and_cannot_spawn(self):
        for role in validator.WRITE_ROLES:
            poly = polytoken_block(role)
            self.assertIs(poly.get("inherit_tools"), True)
            self.assertIs(poly.get("allow_subagent_spawn"), False)
            body = (ASSETS / "subagents" / f"{role}.md").read_text()
            self.assertIn("approved execute context", body)
            self.assertIn("plan` facet exposes `shell_exec`", body)
            self.assertIn("directive", body)

    def test_exit_schemas_require_partial_work_and_task_fit_on_writers(self):
        for role in validator.WRITE_ROLES:
            schema = polytoken_block(role)["exit_tool_schema"]
            required = set(schema["required"])
            self.assertTrue(
                {"task_fit", "files_changed", "partial_changes", "blockers",
                 "validation", "remaining_risk"} <= required,
                f"{role} schema incomplete: {required}",
            )

    def test_all_roles_have_explicit_object_schemas(self):
        for role in validator.ALL_ROLES:
            schema = polytoken_block(role)["exit_tool_schema"]
            self.assertEqual(schema["type"], "object")
            self.assertTrue({"success", "summary"} <= set(schema["required"]))

    def test_councillor_omits_fallback_models_and_tools(self):
        poly = polytoken_block("storm-councillor")
        self.assertNotIn("fallback_models", poly)
        self.assertEqual(poly.get("tools"), [])


class SubagentDenyRedesignTests(unittest.TestCase):
    """Approved Polytoken 0.5.9 deviation: the harness-managed `subagent`
    tool cannot appear in tools_deny; write roles rely on
    allow_subagent_spawn: false instead of an exact deny-union."""

    def test_write_roles_do_not_deny_harness_managed_subagent(self):
        for role in validator.WRITE_ROLES:
            poly = polytoken_block(role)
            self.assertNotIn("subagent", poly.get("tools_deny", []),
                             f"{role}: subagent is harness-managed on "
                             "Polytoken 0.5.9 and cannot be denied")
            self.assertIs(poly.get("allow_subagent_spawn"), False)
            self.assertIn("message_subagent", poly.get("tools_deny", []))

    def test_required_deny_excludes_only_the_undeniable_tool(self):
        self.assertEqual({"subagent"}, validator.HARNESS_MANAGED_UNDENIABLE)
        self.assertNotIn("subagent", validator.WRITE_ROLE_REQUIRED_DENY)
        for still_required in ("message_subagent", "shell_exec",
                               "shell_monitor", "complete_goal"):
            self.assertIn(still_required, validator.WRITE_ROLE_REQUIRED_DENY)
        self.assertFalse(any(
            tool.startswith("mcp__linear__")
            for tool in validator.WRITE_ROLE_REQUIRED_DENY
        ))

    def test_write_roles_document_the_059_limitation(self):
        for role in validator.WRITE_ROLES:
            body = (ASSETS / "subagents" / f"{role}.md").read_text()
            self.assertIn("0.5.9", body)
            self.assertIn("allow_subagent_spawn", body)

    def test_validator_flags_write_role_that_denies_subagent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ASSETS / "subagents", root / "subagents")
            fixer = root / "subagents" / "storm-fixer.md"
            fixer.write_text(fixer.read_text().replace(
                "switch_facet, message_subagent",
                "switch_facet, subagent, message_subagent", 1))
            checker = validator.Validator(root)
            checker.check_subagents()
            self.assertTrue(
                any("harness-managed" in f for f in checker.findings),
                checker.findings,
            )

    def test_validator_mirrors_reserved_storm_target_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "profiles").mkdir()
            (root / "profiles" / "x.json").write_text("{}")
            digest = hashlib.sha256(b"{}").hexdigest()
            manifest = {"assets": [{
                "source": "profiles/x.json",
                "target": ".polytoken/storm/evil.json",
                "kind": "profile",
                "merge": "managed-file",
                "sha256": digest,
            }]}
            (root / "manifest.json").write_text(json.dumps(manifest))
            checker = validator.Validator(root)
            checker.check_manifest()
            self.assertTrue(
                any("reserved" in f for f in checker.findings),
                checker.findings,
            )


class ModelReferenceTests(unittest.TestCase):
    """Fresh-review fix: MODEL_QUALIFIED_RE must accept valid
    ``provider/model(high)`` effort suffixes (no literal backslash) and
    reject malformed or injected references."""

    VALID = [
        "anthropic/claude-opus-4.6(high)",
        "openai/gpt-5.2(xhigh)",
        "google/gemini-3.1-pro(medium)",
        "openai/gpt-5.2:exact(mini)",
        "provider/model",
        "a/b(full)",
        "a-b.c_d/e-f.g:h(nano)",
    ]
    INVALID = [
        "provider/model(high",            # unbalanced open paren
        "provider/modelhigh)",            # unbalanced close paren
        "provider/model(high))",          # extra close paren
        "provider/model(HIGH)",           # effort names are lowercase
        "provider/model()",               # empty suffix
        "provider/model (high)",          # embedded whitespace
        "provider/model(high) ",          # trailing whitespace
        "provider/model(high);rm -rf /",  # shell injection
        "provider/model(high)$(whoami)",  # command substitution
        "provider/model(high)extra",      # trailing junk
        "provider/model(superhigh)",      # unknown effort name
        "provider/model\\(high)",         # literal backslash (old bug shape)
        "provider/model\n(high)",         # embedded newline
        "/provider/model(high)",          # leading slash
        "provider/(high)",                # empty model segment
        "not a model!!",
    ]

    def test_render_team_accepts_valid_qualified_references(self):
        for ref in self.VALID:
            self.assertTrue(render_team.MODEL_QUALIFIED_RE.fullmatch(ref), ref)

    def test_render_team_rejects_malformed_or_injected_references(self):
        for ref in self.INVALID:
            self.assertFalse(render_team.MODEL_QUALIFIED_RE.fullmatch(ref), ref)

    def test_render_team_and_validator_regexes_agree(self):
        for ref in self.VALID + self.INVALID:
            self.assertEqual(
                bool(render_team.MODEL_QUALIFIED_RE.fullmatch(ref)),
                bool(validator.MODEL_QUALIFIED_RE.match(ref)),
                ref,
            )


class ProfileTests(unittest.TestCase):
    """AC.8: built-in profiles render a complete valid team."""

    def test_builtin_profiles_exist_and_cover_every_role(self):
        for name in ("quality", "balanced", "economy", "inherit"):
            profile = json.loads((ASSETS / "profiles" / f"{name}.json").read_text())
            self.assertEqual(profile["name"], name)
            self.assertEqual(set(profile["roles"]), validator.ALL_ROLES)

    def test_profile_model_references_are_valid_and_fallback_free(self):
        for path in (ASSETS / "profiles").glob("*.json"):
            profile = json.loads(path.read_text())
            for role, entry in profile["roles"].items():
                self.assertNotIn("fallback_models", entry)
                model = entry.get("model")
                if model is not None:
                    self.assertTrue(
                        validator.MODEL_ALIAS_RE.match(model)
                        or validator.MODEL_QUALIFIED_RE.match(model),
                        f"{path.stem}/{role}: bad model reference {model!r}",
                    )

    def test_inherit_profile_pins_nothing(self):
        profile = json.loads((ASSETS / "profiles/inherit.json").read_text())
        for entry in profile["roles"].values():
            self.assertNotIn("model", entry)


class HookSafetyTests(unittest.TestCase):
    """AC.10: bounded, default-off, fail-toward-stop continuation."""

    def run_hook(self, mode="stop", env_extra=None, project=None):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "POLYTOKEN_SESSION_ID": "test-session",
            "TMPDIR": tempfile.gettempdir(),
        }
        if project:
            env["POLYTOKEN_PROJECT_DIR"] = str(project)
        env.update(env_extra or {})
        return subprocess.run(
            ["bash", str(HOOK_SCRIPT), mode],
            input="{}", capture_output=True, text=True, env=env, timeout=10,
        )

    def enable(self, project: Path) -> None:
        marker = project / ".polytoken/hooks/storm-continue-on-idle.enabled"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()

    def assert_stop(self, result):
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), '{"outcome":"stop"}')

    def test_continuation_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_hook(env_extra={
                "POLYTOKEN_GOAL_ACTIVE": "true", "POLYTOKEN_FACET_NAME": "execute",
            }, project=Path(tmp))
            self.assert_stop(result)

    def test_continuation_requires_active_goal_and_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.enable(project)
            for env in (
                {"POLYTOKEN_GOAL_ACTIVE": "false", "POLYTOKEN_FACET_NAME": "execute"},
                {"POLYTOKEN_GOAL_ACTIVE": "true", "POLYTOKEN_FACET_NAME": "plan"},
                {},
            ):
                self.assert_stop(self.run_hook(env_extra=env, project=project))

    def test_continuation_is_one_shot_per_user_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.enable(project)
            env = {"POLYTOKEN_GOAL_ACTIVE": "true", "POLYTOKEN_FACET_NAME": "execute",
                   "POLYTOKEN_SESSION_ID": "one-shot-test"}
            guard = Path(tempfile.gettempdir()) / "storm-continue-on-idle/one-shot-test.fired"
            guard.unlink(missing_ok=True)
            first = self.run_hook(env_extra=env, project=project)
            self.assertEqual(first.returncode, 0)
            self.assertIn('"outcome":"continue"', first.stdout)
            self.assertEqual(first.stdout.count('"outcome"'), 1)
            self.assert_stop(self.run_hook(env_extra=env, project=project))
            reset = self.run_hook(mode="pre_user_prompt", env_extra=env, project=project)
            self.assertEqual(reset.returncode, 0)
            self.assertEqual(reset.stdout, "")
            again = self.run_hook(env_extra=env, project=project)
            self.assertIn('"outcome":"continue"', again.stdout)
            guard.unlink(missing_ok=True)

    def test_uncertain_or_malformed_state_stops_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.enable(project)
            env = {"POLYTOKEN_GOAL_ACTIVE": "true", "POLYTOKEN_FACET_NAME": "execute",
                   "POLYTOKEN_SESSION_ID": "../evil/../../escape"}
            result = self.run_hook(env_extra=env, project=project)
            self.assertEqual(result.returncode, 0)
            self.assertIn('"outcome":"stop"', result.stdout)

    def test_kill_switch_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.enable(project)
            self.assert_stop(self.run_hook(env_extra={
                "POLYTOKEN_GOAL_ACTIVE": "true", "POLYTOKEN_FACET_NAME": "execute",
                "STORM_CONTINUE_ON_IDLE": "off",
            }, project=project))

    def test_hook_fragment_uses_known_events_and_unique_names(self):
        entries = json.loads((ASSETS / "hooks/hooks.fragment.json").read_text())
        names = [entry["name"] for entry in entries]
        self.assertEqual(len(names), len(set(names)))
        for entry in entries:
            self.assertTrue(entry["name"].startswith("storm-"))
            self.assertIn(entry["event"], validator.HOOK_EVENTS)
            self.assertIn("storm-continue-on-idle.sh", entry["handler"]["bash"])


class RenderTeamTests(unittest.TestCase):
    """AC.8: atomic profile activation."""

    def setUp(self):
        self.sandbox = Path(tempfile.mkdtemp())
        self.target = self.sandbox / ".polytoken/subagents"
        self.target.mkdir(parents=True)
        for template in (ASSETS / "subagents").glob("*.md"):
            shutil.copy2(template, self.target / template.name)

    def tearDown(self):
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def run_render(self, *args):
        return subprocess.run(
            [sys.executable, str(RENDER_TEAM), *args],
            capture_output=True, text=True,
        )

    def activate(self, profile):
        return self.run_render(
            "--profile", str(ASSETS / "profiles" / f"{profile}.json"),
            "--templates", str(ASSETS / "subagents"),
            "--target", str(self.target),
        )

    def test_each_builtin_profile_renders_complete_valid_team(self):
        for profile in ("quality", "balanced", "economy", "inherit"):
            result = self.activate(profile)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for role in validator.ALL_ROLES:
                self.assertTrue((self.target / f"{role}.md").exists())

    def test_model_injection_and_inherit(self):
        self.assertEqual(self.activate("quality").returncode, 0)
        self.assertIn("model: default_model:full",
                      (self.target / "storm-oracle.md").read_text())
        self.assertEqual(self.activate("inherit").returncode, 0)
        self.assertNotIn("model:", (self.target / "storm-oracle.md").read_text())

    def test_activation_preserves_unmanaged_assets(self):
        (self.target / "my-own.md").write_text("user-authored\n")
        self.assertEqual(self.activate("balanced").returncode, 0)
        self.assertEqual((self.target / "my-own.md").read_text(), "user-authored\n")

    def test_first_activation_rollback_removes_added_roles(self):
        for path in self.target.glob("storm-*.md"):
            path.unlink()
        self.assertEqual(self.activate("balanced").returncode, 0)
        self.assertTrue((self.target / "storm-oracle.md").exists())
        result = self.run_render("--rollback", "--target", str(self.target))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.target / "storm-oracle.md").exists())

    def test_rollback_restores_previous_team(self):
        pristine = (self.target / "storm-oracle.md").read_text()
        self.assertEqual(self.activate("balanced").returncode, 0)
        self.assertIn("model:", (self.target / "storm-oracle.md").read_text())
        result = self.run_render("--rollback", "--target", str(self.target))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.target / "storm-oracle.md").read_text(), pristine)

    def test_invalid_profile_aborts_without_touching_existing_set(self):
        bad = self.sandbox / "bad.json"
        roles = {role: {} for role in validator.ALL_ROLES}
        roles["storm-oracle"] = {"model": "not a model!!"}
        bad.write_text(json.dumps({"name": "bad", "roles": roles}))
        before = (self.target / "storm-oracle.md").read_text()
        result = self.run_render(
            "--profile", str(bad),
            "--templates", str(ASSETS / "subagents"),
            "--target", str(self.target),
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual((self.target / "storm-oracle.md").read_text(), before)

    def custom_profile(self, name: str, oracle_model: str) -> Path:
        roles = {role: {} for role in validator.ALL_ROLES}
        roles["storm-oracle"] = {"model": oracle_model}
        path = self.sandbox / f"{name}.json"
        path.write_text(json.dumps({"name": name, "roles": roles}))
        return path

    def render_custom(self, profile: Path):
        return self.run_render(
            "--profile", str(profile),
            "--templates", str(ASSETS / "subagents"),
            "--target", str(self.target),
        )

    def test_activation_accepts_qualified_model_with_effort_suffix(self):
        profile = self.custom_profile(
            "effort", "anthropic/claude-opus-4.6(high)")
        result = self.render_custom(profile)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("model: anthropic/claude-opus-4.6(high)",
                      (self.target / "storm-oracle.md").read_text())

    def test_activation_rejects_malformed_effort_suffix(self):
        profile = self.custom_profile(
            "bad-effort", "anthropic/claude-opus-4.6(high")
        before = (self.target / "storm-oracle.md").read_text()
        result = self.render_custom(profile)
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid model reference", result.stdout)
        self.assertEqual((self.target / "storm-oracle.md").read_text(), before)

    def test_activation_backup_carries_kind_marker(self):
        self.assertEqual(self.activate("balanced").returncode, 0)
        root = self.sandbox / ".polytoken/storm/team-backups"
        backups = list(root.iterdir())
        self.assertTrue(backups, "activation must record a team backup")
        record = json.loads((backups[0] / "backup.json").read_text())
        self.assertEqual(record["kind"], "storm-team")
        self.assertIsInstance(record["roles"], list)

    def test_team_rollback_ignores_foreign_backup_records(self):
        self.assertEqual(self.activate("balanced").returncode, 0)
        rendered = (self.target / "storm-oracle.md").read_text()
        # A second activation makes the balanced set the rollback target.
        self.assertEqual(self.activate("economy").returncode, 0)
        storm = self.sandbox / ".polytoken/storm"
        self.assertTrue((storm / "team-backups").is_dir(),
                        "team backups live apart from manager backups")
        # A foreign (asset-manager-shaped) record with the newest mtime must
        # be skipped even if it lands in the team backups root.
        stray = storm / "team-backups/99999999-999999-foreign"
        stray.mkdir()
        (stray / "backup.json").write_text(json.dumps({
            "kind": "manage-polytoken-assets",
            "entries": [{"target": ".polytoken/hooks.json", "existed": False}],
        }))
        oracle = self.target / "storm-oracle.md"
        oracle.write_text(oracle.read_text() + "corrupt\n")
        result = self.run_render("--rollback", "--target", str(self.target))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.target / "storm-oracle.md").read_text(), rendered)

    def check(self):
        return self.run_render("--check", "--target", str(self.target))

    def test_check_clean_after_activation(self):
        self.assertEqual(self.activate("balanced").returncode, 0)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("active profile: balanced", result.stdout)

    def test_check_without_activation_reports_absence(self):
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no active profile", result.stdout)

    def test_check_reports_drifted_role(self):
        self.assertEqual(self.activate("balanced").returncode, 0)
        oracle = self.target / "storm-oracle.md"
        oracle.write_text(oracle.read_text() + "local edit\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("storm-oracle", result.stdout)
        self.assertIn("drift", result.stdout)

    def test_check_reports_invalid_model_reference(self):
        self.assertEqual(self.activate("balanced").returncode, 0)
        active = self.sandbox / ".polytoken/storm/active-profile.json"
        record = json.loads(active.read_text())
        record["roles"]["storm-oracle"] = {"model": "not a model!!"}
        active.write_text(json.dumps(record, indent=2) + "\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid model reference", result.stdout)

    def test_check_is_read_only(self):
        self.assertEqual(self.activate("balanced").returncode, 0)
        oracle = self.target / "storm-oracle.md"
        oracle.write_text(oracle.read_text() + "local edit\n")
        before = {p.name: p.read_bytes() for p in self.target.glob("*.md")}
        self.assertEqual(self.check().returncode, 1)
        after = {p.name: p.read_bytes() for p in self.target.glob("*.md")}
        self.assertEqual(before, after)


class RenderTeamConfinementTests(unittest.TestCase):
    """Fresh-review fix: target confinement. Activation, check, and rollback
    must refuse a target (or target parent) whose symlinks escape the
    consuming project/.polytoken boundary, before any read or write."""

    def setUp(self):
        self.sandbox = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.sandbox, True)
        self.target = self.sandbox / ".polytoken/subagents"
        self.target.mkdir(parents=True)
        for template in (ASSETS / "subagents").glob("*.md"):
            shutil.copy2(template, self.target / template.name)
        self.outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.outside, True)

    def run_render(self, *args):
        return subprocess.run(
            [sys.executable, str(RENDER_TEAM), *args],
            capture_output=True, text=True,
        )

    def activate(self, profile="balanced"):
        return self.run_render(
            "--profile", str(ASSETS / "profiles" / f"{profile}.json"),
            "--templates", str(ASSETS / "subagents"),
            "--target", str(self.target),
        )

    def replace_target_with_symlink(self):
        moved = self.sandbox / "real-subagents"
        self.target.rename(moved)
        self.target.symlink_to(self.outside, target_is_directory=True)

    def test_activate_rejects_symlinked_target(self):
        self.replace_target_with_symlink()
        result = self.activate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink escape", result.stdout + result.stderr)
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_activate_rejects_symlinked_polytoken_root(self):
        poly = self.sandbox / ".polytoken"
        moved = self.sandbox / "real-polytoken"
        poly.rename(moved)
        poly.symlink_to(self.outside, target_is_directory=True)
        result = self.activate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink escape", result.stdout + result.stderr)
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_rollback_rejects_symlinked_target(self):
        self.assertEqual(self.activate().returncode, 0)
        self.replace_target_with_symlink()
        result = self.run_render("--rollback", "--target", str(self.target))
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink escape", result.stdout + result.stderr)
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_check_rejects_symlinked_target(self):
        self.assertEqual(self.activate().returncode, 0)
        self.replace_target_with_symlink()
        result = self.run_render("--check", "--target", str(self.target))
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink escape", result.stdout + result.stderr)


class SecurityTests(unittest.TestCase):
    """AC.13: no credentials in distributed assets."""

    def test_distributed_assets_contain_no_secret_patterns(self):
        findings = []
        for base in ("subagents", "profiles", "hooks", "scripts"):
            for path in (ASSETS / base).rglob("*"):
                if not path.is_file():
                    continue
                text = path.read_text(errors="replace")
                for pattern in validator.SECRET_PATTERNS:
                    if pattern.search(text):
                        findings.append(f"{path}: {pattern.pattern}")
        self.assertEqual(findings, [])

    def test_hook_script_contains_no_network_or_tracker_calls(self):
        script = HOOK_SCRIPT.read_text()
        for forbidden in (
            "curl", "wget", "mcp__linear", "linear-cli", "http://", "https://"
        ):
            self.assertNotIn(forbidden, script)


if __name__ == "__main__":
    unittest.main()
