"""Static contract tests for the explicit Storm Build wrapper."""

from pathlib import Path
import re
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = (ROOT / "skills/storm-build/SKILL.md").read_text()
GRILLING = (ROOT / "skills/storm-grilling/SKILL.md").read_text()
DIRECT_OVERRIDE = ROOT / "skills/storm-setup/assets/overrides/bmad-build.toml"
LINEAR = (ROOT / "skills/storm-linear/SKILL.md").read_text()
RECONCILE = (ROOT / "skills/storm-reconcile/SKILL.md").read_text()
SETUP = (ROOT / "skills/storm-setup/SKILL.md").read_text()
MODULE = (ROOT / "skills/module.yaml").read_text()
TRACKER = (ROOT / "skills/storm-linear/reference/issue-tracker.md").read_text()
POLYTOKEN_VALIDATOR = (
    ROOT / "skills/storm-setup/assets/polytoken/scripts/validate_polytoken_assets.py"
).read_text()
CODE_REVIEW = (ROOT / "skills/storm-setup/assets/overrides/bmad-code-review.toml").read_text()
HELP = (ROOT / "skills/module-help.csv").read_text()


def section(title: str, next_title: str | None = None) -> str:
    start = WRAPPER.index(title)
    end = WRAPPER.index(next_title, start) if next_title else len(WRAPPER)
    return WRAPPER[start:end]


class StormBuildWrapperTests(unittest.TestCase):
    def test_explicit_syntax_and_fail_closed_mode_contract(self):
        syntax = section("## Syntax and fail-closed parsing", "## Adaptive sprint-planning call")
        self.assertEqual(
            [
                "storm-build author <story-key>",
                "storm-build implement <story-key-or-issue>",
                "storm-build validate <scope>",
            ],
            re.findall(r"^storm-build (?:author|implement|validate) <[^>]+>$", syntax, re.MULTILINE),
        )
        self.assertIn("Require exactly one mode and a non-empty target", syntax)
        self.assertIn("Missing, unknown, or malformed", syntax)
        self.assertIn("zero", syntax)
        self.assertIn(
            "wrapper's mode and target are the authoritative run context",
            " ".join(WRAPPER.split()),
        )

    def test_author_route_orders_grill_build_artifact_publish_and_one_planner(self):
        author = " ".join(section("## `storm-build author", "## `storm-build implement").split())
        markers = (
            "Invoke `storm-grilling` in `full` mode **before invoking `bmad-build`**",
            "Capture the returned **Seams & test points** handoff payload",
            "Invoke `bmad-build` with an explicit authoring request",
            "and the captured Seams & test points payload",
            "Verify the resulting story/spec artifact contains the captured",
            "After that artifact verification, offer `storm-spec-review`",
            "Invoke `storm-linear publish`",
            "call sprint planning exactly once",
        )
        positions = [author.index(marker) for marker in markers]
        self.assertEqual(sorted(positions), positions)
        self.assertIn("Seams & test points", author)
        self.assertIn("published but blocked before implementation", author)
        self.assertIn("If the payload is absent or altered, stop", author)
        self.assertLess(author.index("If the payload is absent or altered, stop"), author.index("Invoke `storm-linear publish`"))
        self.assertEqual(1, author.count("call sprint planning exactly once"))
        self.assertNotIn("write `sprint-status.yaml`", author)

    def test_grilling_returns_seams_to_wrapper_without_writing_build_artifacts(self):
        self.assertIn("return the agreed **Seams & test points** as an explicit handoff payload", GRILLING)
        self.assertIn("storm-build author` captures that payload", GRILLING)
        self.assertIn("does not write a story/spec artifact", GRILLING)
        self.assertNotIn("must carry that list into the story/spec artifact", GRILLING)

    def test_implementation_route_orders_gates_and_limits_planner_to_story(self):
        implementation = section("## `storm-build implement", "## `storm-build validate")
        normalized = " ".join(implementation.split())
        markers = (
            "explicit preflight grill",
            "plan -> review -> handoff_plan -> active goal -> execute -> read_goal",
            "Invoke `bmad-build` with an explicit implementation request",
            "After the Build/native review completes, invoke `storm-cross-review`",
            "exactly one task-scoped completion commit",
            "Only after the commit is complete invoke `storm-linear close`",
            "If the target is the story issue, call sprint planning exactly once",
        )
        positions = [normalized.index(marker) for marker in markers]
        self.assertEqual(sorted(positions), positions)
        self.assertIn(
            "If it is a child ticket, do not call sprint planning and never close or reconcile the parent",
            " ".join(implementation.split()),
        )
        self.assertIn(
            "linear done with reconciliation repair required",
            " ".join(implementation.lower().split()),
        )
        self.assertEqual(1, normalized.count("call sprint planning exactly once"))
        self.assertIn("it does not authorize push", normalized)
        self.assertIn("A failed commit leaves the target `In Progress`", normalized)

    def test_validate_route_has_no_tracker_or_planner_lifecycle(self):
        validate = section("## `storm-build validate", "## Authority and failure reporting")
        self.assertLess(
            validate.index("Invoke `bmad-build` with an explicit validation/review request"),
            validate.index("invoke `storm-cross-review`"),
        )
        self.assertIn("must not publish, open, or close", " ".join(validate.split()))
        self.assertIn("do not call sprint planning", " ".join(validate.lower().split()))
        self.assertNotIn("storm-linear publish", validate)
        self.assertNotIn("storm-linear open", validate)
        self.assertNotIn("storm-linear close", validate)

    def test_direct_build_override_has_no_lifecycle_hooks(self):
        override = tomllib.loads(DIRECT_OVERRIDE.read_text())["workflow"]
        self.assertEqual(["persistent_facts"], list(override))
        self.assertNotIn("activation_steps_append", override)
        self.assertNotIn("on_complete", override)
        fact = override["persistent_facts"][0]
        self.assertIn("intentionally unwrapped by Storm", fact)
        self.assertIn("direct callers receive no storm tracker or sprint lifecycle side effects", fact.lower())

    def test_planner_and_reconcile_ownership_are_not_duplicated(self):
        self.assertIn("never invokes sprint planning", LINEAR)
        self.assertIn("responsible for exactly one adaptive", LINEAR)
        self.assertIn("never directly edits `sprint-status.yaml`", RECONCILE)
        self.assertIn("never invokes `bmad-sprint-planning`", RECONCILE)
        self.assertIn("hands off the required planner repair intent", RECONCILE)
        self.assertIn("only when that installed skill explicitly advertises", WRAPPER)
        self.assertIn("do not retry with another guessed form", " ".join(WRAPPER.lower().split()))

    def test_setup_requires_targets_and_validates_wrapper_boundary(self):
        self.assertIn("missing `bmad-build`, `bmad-sprint-planning`, or `bmad-retrospective` target is a hard failure", SETUP)
        self.assertIn("direct-Build boundary", SETUP)
        self.assertIn("storm-build` skill advertises exactly `author`, `implement`, and `validate`", SETUP)
        self.assertIn("Do not claim that rendered `bmad-build` exposes route-specific gates", SETUP)
        self.assertIn("non-empty scalar", SETUP)

    def test_linear_transport_is_authenticated_cli_not_mcp(self):
        combined = "\n".join((SETUP, MODULE, TRACKER, POLYTOKEN_VALIDATOR))
        self.assertIn("linear-cli", SETUP)
        self.assertIn("linear-cli", MODULE)
        self.assertIn("linear-cli", TRACKER)
        self.assertNotIn("linear-server", combined)
        self.assertNotIn("LINEAR_MUTATION_TOOLS", POLYTOKEN_VALIDATOR)

    def test_tracker_cli_contract_is_noninteractive_and_write_verified(self):
        normalized = " ".join(TRACKER.split())
        self.assertIn("--output json --compact --no-cache --no-pager", TRACKER)
        self.assertIn("--data -", TRACKER)
        self.assertIn("issues comment", TRACKER)
        self.assertIn("issues update", TRACKER)
        self.assertIn("reread", normalized.lower())
        self.assertIn("LINEAR_API_KEY", TRACKER)
        self.assertIn("auth status", TRACKER)
        self.assertNotIn("save_comment", TRACKER)
        self.assertNotIn("save_issue", TRACKER)

    def test_review_surface_and_help_row_remain_standalone(self):
        self.assertIn("storm-cross-review", CODE_REVIEW)
        self.assertIn("on_complete", CODE_REVIEW)
        row = next(line for line in HELP.splitlines() if ",storm-build," in line)
        self.assertIn(",SBW,", row)
        self.assertIn("author <story-key>", row)
        self.assertIn("implement <story-key-or-issue>", row)
        self.assertIn("validate <scope>", row)


if __name__ == "__main__":
    unittest.main()
