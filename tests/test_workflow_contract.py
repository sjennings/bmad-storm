"""Deterministic contract, alias-equivalence, and state-transition tests."""

import importlib.util
import json
import subprocess
import sys
import tomllib
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
OVERRIDES = ROOT / "skills/storm-setup/assets/overrides"
BUILD_OVERRIDE = OVERRIDES / "bmad-build.toml"
STORM_BUILD_SKILL = ROOT / "skills/storm-build/SKILL.md"


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
        self.assertEqual("2.0.0", CONTRACT["contract_version"])
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

    def test_direct_build_is_unconditionally_unwrapped(self):
        self.assertTrue(BUILD_OVERRIDE.exists())
        self.assertEqual(
            1,
            len(list(OVERRIDES.glob("bmad-build.toml"))),
            "Build must have exactly one Storm override",
        )
        for legacy in ("bmad-create-story.toml", "bmad-dev-story.toml", "bmad-quick-dev.toml"):
            self.assertFalse((OVERRIDES / legacy).exists(), legacy)

        build = tomllib.loads(BUILD_OVERRIDE.read_text())
        workflow = build["workflow"]
        self.assertEqual(["persistent_facts"], list(workflow))
        self.assertEqual(1, len(workflow["persistent_facts"]))
        fact = workflow["persistent_facts"][0]
        for text in (
            "upstream canonical workflow",
            "intentionally unwrapped by Storm",
            "bmad-create-story",
            "bmad-dev-story",
            "bmad-quick-dev",
            "no Storm tracker or sprint lifecycle side effects",
            "storm-build author",
            "storm-build implement",
            "storm-build validate",
        ):
            self.assertIn(text, fact)
        self.assertNotIn("activation_steps_append", build["workflow"])
        self.assertNotIn("on_complete", build["workflow"])

    def test_storm_build_owns_explicit_modes_and_planner_cardinality(self):
        self.assertTrue(STORM_BUILD_SKILL.exists())
        wrapper = STORM_BUILD_SKILL.read_text()
        for syntax in (
            "storm-build author <story-key>",
            "storm-build implement <story-key-or-issue>",
            "storm-build validate <scope>",
        ):
            self.assertIn(syntax, wrapper)
        self.assertIn("zero", wrapper)
        self.assertIn("exactly one adaptive", wrapper)
        self.assertIn("If the target is the story issue", wrapper)
        self.assertIn("do not call sprint planning", wrapper.lower())
        self.assertIn("must not publish, open, or close", " ".join(wrapper.split()))
        self.assertEqual("storm-build", CONTRACT["route_selection"]["canonical_workflow"])
        self.assertEqual("storm-build", CONTRACT["route_selection"]["planner_call_owner"])
        self.assertEqual(
            {"author": 1, "story_implementation": 1, "child_implementation": 0, "validation_review": 0},
            CONTRACT["route_selection"]["planner_call_cardinality"],
        )

    def test_sprint_planning_owns_projection_and_retrospective_is_advisory(self):
        planning = tomllib.loads((OVERRIDES / "bmad-sprint-planning.toml").read_text())["workflow"]
        planning_text = str(planning)
        for text in (
            "sole owner",
            "readiness",
            "status",
            "validate",
            "repair",
            "upstream deterministic",
            "--autonomous",
            "only when the installed sprint-planning skill documents that flag",
            "headless",
            "fallback",
            "warn",
            "legacy-compatible",
            "bmad-sprint-status",
            "bmad-check-implementation-readiness",
        ):
            self.assertIn(text, planning_text)

        retrospective = tomllib.loads((OVERRIDES / "bmad-retrospective.toml").read_text())["workflow"]
        retrospective_text = str(retrospective)
        for text in (
            "evidence-based",
            "off by default",
            "headless",
            "duplication",
            "pattern divergence",
            "god-class growth",
            "specification drift",
            "proposal-only",
            "bmad-correct-course",
            "storm-harness-improvement",
            "Never directly change",
        ):
            self.assertIn(text, retrospective_text)

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

    def test_completed_commit_is_mandatory_and_not_configurable(self):
        self.assertNotIn("completion_commit_policy", CONTRACT["settings"])
        self.assertNotIn("completion_commit_policy:", MODULE)
        self.assertNotIn("allow-without-storm-commit", MODULE)
        close = CONTRACT["operations"]["storm-linear.close"]
        self.assertIn("godot_shutdown_clean", close["preconditions"])
        self.assertIn("commit_completed", close["preconditions"])
        self.assertIn("RID", CONTRACT["guards"]["godot_shutdown_clean_seen"])
        self.assertIn("ObjectDB", CONTRACT["guards"]["godot_shutdown_clean_seen"])
        self.assertIn("resources still in use", CONTRACT["guards"]["godot_shutdown_clean_seen"])
        completion_guard = CONTRACT["guards"]["completion_evidence_current"]
        self.assertIn("godot_shutdown_clean", completion_guard)
        self.assertIn("completed commit", completion_guard)

    def test_enforcement_level_is_honest_about_directive_control(self):
        enforcement = CONTRACT["enforcement"]
        self.assertEqual("directive", enforcement["level"])
        self.assertIn("does not provide a physical sandbox", enforcement["statement"])
        self.assertIn("shell_exec", enforcement["statement"])
        for scenario in (
            "smoke_storm_build_wrapper_boundary",
            "smoke_plan_handoff_goal_open_gate",
            "smoke_role_tool_contracts",
        ):
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

    def test_v7_legacy_operations_warn_and_forward_to_unwrapped_build(self):
        operations = CONTRACT["operations"]
        self.assertEqual("canonical", operations["storm-build"]["kind"])
        self.assertEqual(
            ["author", "implement", "validate"], operations["storm-build"]["modes"]
        )
        self.assertEqual("upstream-canonical", operations["bmad-build"]["kind"])
        self.assertFalse(operations["bmad-build"]["storm_wrapped"])
        self.assertTrue(operations["bmad-code-review"]["standalone"])
        self.assertEqual("storm-build validate", operations["bmad-code-review"]["preferred_entry"])
        self.assertIn("explicit payload", operations["storm-grilling"]["handoff"])
        self.assertIn("do not write a story/spec artifact", operations["storm-grilling"]["handoff"])
        for name, route in (
            ("bmad-create-story", "upstream authoring"),
            ("bmad-dev-story", "upstream implementation"),
            ("bmad-quick-dev", "upstream intent resolution"),
        ):
            shim = operations[name]
            self.assertEqual("deprecation-shim", shim["kind"])
            self.assertTrue(shim["warning"])
            self.assertEqual("bmad-build", shim["routes_to"])
            self.assertEqual(route, shim["route"])
            self.assertIn("forward original input", " ".join(shim["effects"]))

        self.assertEqual(["storm-build"], CONTRACT["aliases"]["/create-story"]["canonical_operations"])
        self.assertEqual(["authoring"], [CONTRACT["aliases"]["/create-story"]["route"]])
        self.assertEqual(["storm-build"], CONTRACT["aliases"]["/implement"]["canonical_operations"])
        self.assertEqual("implementation", CONTRACT["aliases"]["/implement"]["route"])

        self.assertEqual("bmad-sprint-planning", operations["bmad-sprint-status"]["routes_to"])
        self.assertTrue(operations["bmad-sprint-status"]["warning"])
        self.assertEqual(
            "retired", operations["bmad-check-implementation-readiness"]["status"]
        )
        self.assertEqual(
            "bmad-sprint-planning",
            operations["bmad-check-implementation-readiness"]["routes_to"],
        )

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
        self.assertEqual("retired", aliases["/to-spec"]["status"])
        self.assertEqual([], aliases["/to-spec"]["canonical_operations"])
        self.assertIn("storm-build author", aliases["/to-spec"]["rule"])

    def test_sprint_status_ownership_and_partial_outcomes_are_explicit(self):
        planning = CONTRACT["operations"]["bmad-sprint-planning"]
        self.assertEqual("bmad-sprint-planning", CONTRACT["authorities"]["sprint_planning"]["owner"])
        self.assertEqual(
            {"readiness", "status", "validate", "repair"},
            set(planning["intents"]),
        )
        self.assertEqual("upstream deterministic script", planning["implementation"])
        self.assertEqual("fallback-only with warning", planning["inference"])
        for operation in ("storm-linear.publish", "storm-linear.close"):
            self.assertFalse(CONTRACT["operations"][operation]["writes_sprint_status"])
            self.assertFalse(CONTRACT["operations"][operation]["invokes_planner"])
        self.assertFalse(CONTRACT["operations"]["storm-reconcile"]["writes_sprint_status"])
        self.assertEqual(
            ["operator handoff: bmad-sprint-planning repair intent"],
            CONTRACT["operations"]["storm-reconcile"]["requests"],
        )
        self.assertFalse(CONTRACT["operations"]["storm-reconcile"]["invokes_planner"])
        self.assertEqual("advisory", CONTRACT["operations"]["bmad-retrospective"]["kind"])
        self.assertEqual(
            ["bmad-correct-course", "storm-harness-improvement"],
            CONTRACT["operations"]["bmad-retrospective"]["follow_up"],
        )
        self.assertEqual(
            "published but blocked before implementation",
            CONTRACT["partial_outcomes"]["publication_success_planning_failure"]["result"],
        )
        self.assertEqual(
            "Linear Done with sprint reconciliation repair required",
            CONTRACT["partial_outcomes"]["linear_done_planning_failure"]["result"],
        )

    def test_legacy_override_files_are_not_shipped_as_templates(self):
        for legacy in ("bmad-create-story.toml", "bmad-dev-story.toml", "bmad-quick-dev.toml"):
            self.assertFalse((OVERRIDES / legacy).exists())
        setup = (ROOT / "skills/storm-setup/SKILL.md").read_text()
        self.assertIn("manual merge", setup)
        self.assertIn("Never auto-delete, auto-merge", setup)
        self.assertIn("direct-Build boundary", setup)
        self.assertIn("storm-build", setup)

    def test_missing_aliases_are_not_advertised(self):
        for retired in ("/wayfinder", "story-execute", "story-plan"):
            self.assertEqual("retired", CONTRACT["aliases"][retired]["status"])
            self.assertNotIn(retired.strip("/"), HELP)

    def test_docs_record_approved_divergence_ledger(self):
        for number in range(1, 13):
            self.assertIn(f"D{number} ", CONFORMANCE_DOC)
        for phrase in (
            "review_loop_max_rounds",
            "completed commit",
            "handoff_plan",
            "storm-linear slice",
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

    def test_partial_planner_failure_fixtures_keep_completed_linear_outcome(self):
        publication_events, _, _ = load_fixture(
            FIXTURES / "valid_publication_planner_failure.json"
        )
        self.assertEqual("publish_succeeded", publication_events[-2]["event"])
        self.assertEqual("planner_readiness_failed", publication_events[-1]["event"])
        self.assertEqual([], VALIDATOR.validate_transcript(publication_events, CONTRACT))

        done_events, _, _ = load_fixture(FIXTURES / "valid_done_reconciliation_failure.json")
        self.assertEqual("issue_closed", done_events[-2]["event"])
        self.assertEqual("planner_reconciliation_failed", done_events[-1]["event"])
        self.assertEqual([], VALIDATOR.validate_transcript(done_events, CONTRACT))

    def test_invalid_fixtures_are_rejected(self):
        invalid = sorted(FIXTURES.glob("invalid_*.json"))
        self.assertGreaterEqual(len(invalid), 8)
        for path in invalid:
            try:
                events, policy, max_rounds = load_fixture(path)
            except VALIDATOR.TranscriptError:
                continue
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

    def test_godot_shutdown_leaks_block_commit_and_close(self):
        events, _, _ = load_fixture(FIXTURES / "valid_full_story.json")
        events = [event for event in events if event["event"] != "godot_shutdown_clean"]
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("godot_shutdown_clean", errors[0])
        self.assertIn("In Progress", errors[0])

    def test_fix_after_clean_shutdown_requires_fresh_shutdown_evidence(self):
        events, _, _ = load_fixture(FIXTURES / "valid_full_story.json")
        commit_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "commit_authorized"
        )
        events[commit_index:commit_index] = [
            {"event": "fix_applied"},
            {"event": "native_review_passed"},
            {"event": "cross_review_passed"},
        ]
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("godot_shutdown_clean", errors[0])
        self.assertIn("In Progress", errors[0])

    def test_later_godot_run_requires_its_own_clean_shutdown(self):
        events, _, _ = load_fixture(FIXTURES / "valid_full_story.json")
        commit_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "commit_authorized"
        )
        events.insert(commit_index, {"event": "godot_run_started"})
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("godot_shutdown_clean", errors[0])
        self.assertIn("In Progress", errors[0])

    def test_fix_after_completed_commit_requires_a_fresh_commit(self):
        events, _, _ = load_fixture(FIXTURES / "valid_full_story.json")
        completion_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "completion_commented"
        )
        events[completion_index:completion_index] = [
            {"event": "fix_applied"},
            {"event": "native_review_passed"},
            {"event": "cross_review_passed"},
            {"event": "godot_run_started"},
            {"event": "godot_shutdown_clean"},
        ]
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("completed commit", errors[0])
        self.assertIn("In Progress", errors[0])

    def test_godot_run_after_completed_commit_requires_fresh_shutdown(self):
        events, _, _ = load_fixture(FIXTURES / "valid_full_story.json")
        completion_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "completion_commented"
        )
        events.insert(completion_index, {"event": "godot_run_started"})
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("godot_shutdown_clean", errors[0])
        self.assertIn("In Progress", errors[0])

    def test_godot_shutdown_evidence_requires_one_to_one_start_pairing(self):
        events, _, _ = load_fixture(FIXTURES / "valid_full_story.json")
        without_start = [event for event in events if event["event"] != "godot_run_started"]
        errors = VALIDATOR.validate_transcript(without_start, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("without a matching godot_run_started", errors[0])

        start_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "godot_run_started"
        )
        duplicate_start = list(events)
        duplicate_start.insert(start_index, {"event": "godot_run_started"})
        errors = VALIDATOR.validate_transcript(duplicate_start, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("already outstanding", errors[0])

        clean_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "godot_shutdown_clean"
        )
        duplicate_clean = list(events)
        duplicate_clean.insert(clean_index, {"event": "godot_shutdown_clean"})
        errors = VALIDATOR.validate_transcript(duplicate_clean, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("without a matching godot_run_started", errors[0])

    def test_godot_run_pair_is_valid_during_implementation(self):
        events, _, _ = load_fixture(FIXTURES / "valid_full_story.json")
        mutation_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "mutation"
        )
        events[mutation_index + 1:mutation_index + 1] = [
            {"event": "godot_run_started"},
            {"event": "godot_shutdown_clean"},
        ]
        self.assertEqual([], VALIDATOR.validate_transcript(events, CONTRACT))

    def test_commit_authorization_is_single_use(self):
        events, _, _ = load_fixture(FIXTURES / "valid_full_story.json")
        commit_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "commit_completed"
        )
        events.insert(commit_index + 1, {"event": "commit_completed"})
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("without a prior commit_authorized", errors[0])

        events, _, _ = load_fixture(FIXTURES / "valid_full_story.json")
        authority_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "commit_authorized"
        )
        events.insert(authority_index, {"event": "commit_authorized"})
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertTrue(errors)
        self.assertIn("existing authorization", errors[0])

    def test_commit_requires_explicit_authority(self):
        events, _, _ = load_fixture(FIXTURES / "invalid_commit_without_authority.json")
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertIn("commit_authorized", errors[0])

    def test_close_without_completed_commit_is_always_rejected(self):
        events, _, _ = load_fixture(
            FIXTURES / "invalid_require_explicit_close_without_authority.json"
        )
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertIn("completed commit", errors[0])

        events, _, _ = load_fixture(
            FIXTURES / "invalid_authority_without_commit_completed.json"
        )
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertIn("completed commit", errors[0])

    def test_removed_commit_policy_override_is_rejected(self):
        raw = json.loads(
            (FIXTURES / "invalid_removed_commit_policy_override.json").read_text()
        )
        with self.assertRaises(VALIDATOR.TranscriptError):
            VALIDATOR._normalize_transcript(raw)

    def test_authority_without_completed_commit_rejected_at_close(self):
        events, _, _ = load_fixture(
            FIXTURES / "invalid_authority_without_commit_completed.json"
        )
        errors = VALIDATOR.validate_transcript(events, CONTRACT)
        self.assertTrue(errors, "authority without a completed commit must be rejected")
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
