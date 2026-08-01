"""Deterministic contract, alias-equivalence, and state-transition tests."""

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "skills/storm-contract/workflow-contract.json"
VALIDATOR_PATH = ROOT / "skills/storm-contract/validate_transcript.py"
FIXTURES = ROOT / "tests/fixtures/transcripts"
CONFORMANCE_DOC = (ROOT / "docs/workflow-conformance.md").read_text()
MODULE = (ROOT / "skills/module.yaml").read_text()
HELP = (ROOT / "skills/module-help.csv").read_text()
CONTRACT = json.loads(CONTRACT_PATH.read_text())


def load_validator():
    spec = importlib.util.spec_from_file_location("storm_validate_transcript", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


def load_fixture(path: Path):
    raw = json.loads(path.read_text())
    events, policy, max_rounds = VALIDATOR._normalize_transcript(raw)
    return events, policy, max_rounds


class ContractStructureTests(unittest.TestCase):
    """The JSON contract encodes the canonical authority and transition rules."""

    def test_contract_encodes_canonical_authority_and_transitions(self):
        authorities = CONTRACT["authorities"]
        self.assertEqual("bmad", authorities["pre_publication"]["owner"])
        self.assertEqual("linear", authorities["post_publication"]["owner"])
        self.assertEqual("storm-linear.publish", authorities["handoff_point"])
        self.assertIn("phase decides", authorities["phase_decides_rule"])
        self.assertEqual("forbidden", CONTRACT["artifact_lifecycle"]["parallel_authority"])

        chain = CONTRACT["execution_chain"]
        self.assertEqual(
            [
                "plan_facet",
                "write_plan",
                "plan_reviewed",
                "handoff_plan_approved",
                "goal_activated",
                "execute_facet",
                "read_goal_verified",
                "storm-linear.open",
                "open_verified",
                "mutation",
            ],
            chain,
        )

        by_event = {}
        for entry in CONTRACT["transitions"]:
            by_event.setdefault(entry["event"], []).append(entry)
        self.assertEqual(["implementing"], by_event["mutation"][0]["from"])
        self.assertEqual(["goal_verified"], by_event["issue_opened"][0]["from"])
        self.assertEqual(["executing"], by_event["goal_verified"][0]["from"])
        self.assertEqual(["goal_activated"], by_event["execute_entered"][0]["from"])
        self.assertEqual(["plan_reviewed"], by_event["handoff_approved"][0]["from"])
        self.assertEqual(["done"], by_event["sprint_reconciled"][0]["from"])
        self.assertEqual(["close_ready"], by_event["issue_closed"][0]["from"])
        self.assertEqual(["published"], by_event["sprint_ready_updated"][0]["from"])

    def test_child_ticket_rules_are_machinable(self):
        rules = CONTRACT["child_story_rules"]
        self.assertIn("reconciles nothing", rules["child_close"])
        self.assertIn("never closes", rules["child_close"])
        by_event = {e["event"]: e for e in CONTRACT["transitions"] if e["to"] != "self"}
        self.assertEqual("child_target", by_event["child_closed"]["guard"])
        self.assertEqual("story_target", by_event["issue_closed"]["guard"])

    def test_review_loop_uses_configured_round_cap(self):
        self.assertEqual(
            "review_loop_max_rounds", CONTRACT["review_policy"]["round_cap_setting"]
        )
        self.assertTrue(CONTRACT["review_policy"]["fresh_pass_required_after_fix"])
        self.assertIn("review_loop_max_rounds:", MODULE)
        self.assertIn("review_loop_max_rounds", CONFORMANCE_DOC)
        guard = CONTRACT["guards"]["review_round_cap"]
        self.assertIn("review_loop_max_rounds", guard)
        self.assertIn("review_halted_non_converged", guard)

    def test_commit_policy_defaults_and_allowed_values(self):
        policy = CONTRACT["settings"]["completion_commit_policy"]
        self.assertEqual("require-explicit", policy["default"])
        self.assertEqual(
            ["require-explicit", "allow-without-storm-commit"], policy["allowed"]
        )
        self.assertIn("explicit operator authority", policy["rule"])
        self.assertIn("completion_commit_policy:", MODULE)
        self.assertIn("allow-without-storm-commit", MODULE)

    def test_enforcement_level_is_honest_about_directive_control(self):
        enforcement = CONTRACT["enforcement"]
        self.assertEqual("directive", enforcement["level"])
        self.assertIn("does not provide a physical sandbox", enforcement["statement"])
        self.assertIn("shell_exec", enforcement["statement"])
        for scenario in ("smoke_plan_handoff_goal_open_gate", "smoke_role_tool_contracts"):
            self.assertIn(scenario, enforcement["smoke_scenarios"])
            self.assertIn(scenario, CONFORMANCE_DOC)


class AliasEquivalenceTests(unittest.TestCase):
    """Aliases resolve to canonical operations and carry no independent lifecycle."""

    def test_slash_aliases_resolve_to_canonical_operations(self):
        operations = CONTRACT["operations"]
        for name, alias in CONTRACT["aliases"].items():
            for operation in alias["canonical_operations"]:
                self.assertIn(operation, operations, f"{name} -> unknown {operation}")
            if alias["status"] == "retired":
                self.assertEqual([], alias["canonical_operations"])

    def test_aliases_contain_no_independent_lifecycle(self):
        aliases = CONTRACT["aliases"]
        self.assertIn("never", aliases["/create-story"]["rule"])
        self.assertIn("never", aliases["/implement"]["rule"])
        self.assertEqual(
            ["storm-linear.slice"], aliases["/to-tickets"]["canonical_operations"]
        )
        self.assertNotIn(
            "storm-linear.publish", aliases["/implement"]["canonical_operations"]
        )
        for name in ("/to-spec", "/to-tickets", "/tdd", "/code-review"):
            self.assertNotIn(
                "storm-linear.close",
                aliases[name]["canonical_operations"],
                f"{name} must not close independently",
            )
        self.assertEqual(
            ["storm-linear.publish"], aliases["/to-spec"]["canonical_operations"]
        )

    def test_missing_aliases_are_not_advertised(self):
        for retired in ("/wayfinder", "story-execute", "story-plan"):
            self.assertEqual("retired", CONTRACT["aliases"][retired]["status"])
            self.assertNotIn(retired.strip("/"), HELP)

    def test_docs_record_approved_divergence_ledger(self):
        for number in range(1, 13):
            self.assertIn(f"D{number} ", CONFORMANCE_DOC)
        for phrase in (
            "review_loop_max_rounds",
            "completion_commit_policy",
            "require-explicit",
            "handoff_plan",
            "storm-linear slice",
            "phase-decides",
        ):
            self.assertIn(phrase, CONFORMANCE_DOC)

    def test_docs_reference_contract_version(self):
        self.assertIn(CONTRACT["contract_version"], CONFORMANCE_DOC)


class TranscriptFixtureTests(unittest.TestCase):
    """Scenario fixtures validate against the contract through the real validator."""

    def test_valid_fixtures_conform(self):
        valid = sorted(FIXTURES.glob("valid_*.json"))
        self.assertGreaterEqual(len(valid), 5)
        for path in valid:
            events, policy, max_rounds = load_fixture(path)
            errors = VALIDATOR.validate_transcript(
                events, CONTRACT, policy=policy, max_rounds=max_rounds
            )
            self.assertEqual([], errors, f"{path.name}: {errors}")

    def test_invalid_fixtures_are_rejected(self):
        invalid = sorted(FIXTURES.glob("invalid_*.json"))
        self.assertGreaterEqual(len(invalid), 8)
        for path in invalid:
            events, policy, max_rounds = load_fixture(path)
            errors = VALIDATOR.validate_transcript(
                events, CONTRACT, policy=policy, max_rounds=max_rounds
            )
            self.assertTrue(errors, f"{path.name} should be rejected")

    def test_rejected_handoff_leaves_todo_and_blocks_mutation(self):
        events, policy, max_rounds = load_fixture(
            FIXTURES / "invalid_rejected_handoff_mutation.json"
        )
        errors = VALIDATOR.validate_transcript(
            events, CONTRACT, policy=policy, max_rounds=max_rounds
        )
        self.assertIn("halted_pre_open", errors[0])
        self.assertIn("mutation", errors[0])

    def test_missing_goal_or_failed_open_blocks_mutation(self):
        for name in ("invalid_missing_goal_open.json", "invalid_pre_open_mutation.json"):
            events, policy, max_rounds = load_fixture(FIXTURES / name)
            errors = VALIDATOR.validate_transcript(
                events, CONTRACT, policy=policy, max_rounds=max_rounds
            )
            self.assertTrue(errors, name)

    def test_child_ticket_cannot_close_or_reconcile_parent(self):
        events, _, _ = load_fixture(FIXTURES / "invalid_child_closes_parent.json")
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertIn("story target", errors[0])
        events, _, _ = load_fixture(FIXTURES / "invalid_child_reconciles_parent.json")
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertIn("sprint_reconciled", errors[0])

    def test_commit_requires_explicit_authority(self):
        events, _, _ = load_fixture(FIXTURES / "invalid_commit_without_authority.json")
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertIn("commit_authorized", errors[0])

    def test_commit_policy_controls_close(self):
        events, _, _ = load_fixture(
            FIXTURES / "invalid_require_explicit_close_without_authority.json"
        )
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertIn("require-explicit", errors[0])
        events, policy, _ = load_fixture(FIXTURES / "valid_allow_without_storm_commit_close.json")
        self.assertEqual(
            [], VALIDATOR.validate_transcript(events, CONTRACT, policy=policy)
        )

    def test_authority_without_completed_commit_rejected_at_close(self):
        events, _, _ = load_fixture(
            FIXTURES / "invalid_authority_without_commit_completed.json"
        )
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertTrue(errors, "authority without a completed commit must be rejected")
        self.assertIn("require-explicit", errors[0])
        self.assertIn("completed commit", errors[0])

    def test_review_cap_error_names_the_setting(self):
        events, _, _ = load_fixture(FIXTURES / "invalid_review_cap_exceeded.json")
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertIn("review_loop_max_rounds", errors[0])

    def test_validator_cli_exit_codes(self):
        valid = FIXTURES / "valid_full_story.json"
        invalid = FIXTURES / "invalid_commit_without_authority.json"
        ok = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), str(valid)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, ok.returncode, ok.stdout + ok.stderr)
        self.assertIn('"valid": true', ok.stdout)
        bad = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), str(invalid)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, bad.returncode, bad.stdout + bad.stderr)
        self.assertIn("commit_authorized", bad.stdout)


class SliceTransitionTests(unittest.TestCase):
    """slice_completed is a self-transition: it never substitutes for
    sprint_ready_updated."""

    def _events(self, *names):
        return [{"event": name} for name in names]

    def test_slice_completed_is_a_self_transition(self):
        by_event = {}
        for entry in CONTRACT["transitions"]:
            by_event.setdefault(entry["event"], []).append(entry)
        entries = by_event["slice_completed"]
        self.assertEqual(1, len(entries))
        self.assertEqual("self", entries[0]["to"])
        self.assertEqual(["published", "ready_for_dev"], entries[0]["from"])

    def test_slice_from_published_does_not_skip_sprint_ready_updated(self):
        events = self._events(
            "scope_resolved",
            "grill_confirmed",
            "publish_succeeded",
            "slice_completed",
            "plan_created",
        )
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("plan_created", errors[0])
        self.assertIn("published", errors[0])

    def test_slice_then_sprint_ready_update_is_valid(self):
        events = self._events(
            "scope_resolved",
            "grill_confirmed",
            "publish_succeeded",
            "slice_completed",
            "sprint_ready_updated",
            "plan_created",
        )
        self.assertEqual([], VALIDATOR.validate_transcript(events, CONTRACT))


if __name__ == "__main__":
    unittest.main()
