"""Subprocess tests for the storm-orchestrate scheduler CLI.

These run the actual ``skills/storm-orchestrate/scheduler.py`` entry point
documented in ``skills/storm-orchestrate/SKILL.md`` — frontier, conflicts,
and finalize over a JSON lanes file — with no duplicate reference logic.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = ROOT / "skills/storm-orchestrate/scheduler.py"
SKILL_PATH = ROOT / "skills/storm-orchestrate/SKILL.md"


def documented_example_description() -> str:
    """The concrete lane record documented in SKILL.md (single source)."""
    blocks = [
        block
        for block in SKILL_PATH.read_text().split("```")
        if "storm-lane: 7" in block
    ]
    assert len(blocks) == 1, "SKILL.md must carry exactly one concrete example"
    return blocks[0].strip()


def record(
    todo_id,
    specialist="storm-fixer",
    objective="Do the thing",
    ownership="",
    dependencies="",
    edits="allowed",
    state="pending",
    validation="dotnet build",
    result="",
    partial_changes="",
    partial_inspected="",
    disposition="",
):
    fields = {
        "specialist": specialist,
        "objective": objective,
        "ownership": ownership,
        "dependencies": dependencies,
        "edits": edits,
        "state": state,
        "validation": validation,
        "result": result,
        "partial_changes": partial_changes,
        "partial_inspected": partial_inspected,
        "disposition": disposition,
    }
    lines = [f"storm-lane: {todo_id}"]
    lines.extend(f"{key}: {value}" for key, value in fields.items() if value != "")
    return "\n".join(lines)


class SchedulerCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lanes_path = Path(self.tmp.name) / "lanes.json"

    def write_lanes(self, entries):
        self.lanes_path.write_text(json.dumps(entries))
        return self.lanes_path

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCHEDULER_PATH), *args],
            capture_output=True,
            text=True,
        )

    def test_frontier_reports_dispatchable_and_blocked_lanes(self):
        path = self.write_lanes([
            {"todo_id": 1, "description": record(1, state="failed")},
            {"todo_id": 2, "description": record(2, dependencies="1")},
            {"todo_id": 3, "description": record(3, edits="read-only", specialist="storm-explorer")},
        ])
        proc = self.run_cli("frontier", str(path))
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual([3], report["frontier"])
        self.assertEqual(
            [{"lane": 2, "dependency": 1, "dependency_state": "failed"}],
            report["blocked"],
        )

    def test_frontier_rejects_cycle_with_exit_2(self):
        path = self.write_lanes([
            {"todo_id": 1, "description": record(1, dependencies="2")},
            {"todo_id": 2, "description": record(2, dependencies="1")},
        ])
        proc = self.run_cli("frontier", str(path))
        self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("cycle", json.loads(proc.stdout)["error"])

    def test_conflicts_exit_1_with_overlap_and_0_without(self):
        overlapping = self.write_lanes([
            {"todo_id": 1, "description": record(1, ownership="source/core/hex/")},
            {"todo_id": 2, "description": record(2, ownership="source/core/hex/Grid.cs")},
        ])
        proc = self.run_cli("conflicts", str(overlapping))
        self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertFalse(report["ok"])
        self.assertEqual(1, len(report["conflicts"]))

        disjoint = self.write_lanes([
            {"todo_id": 1, "description": record(1, ownership="source/core/hex/")},
            {"todo_id": 2, "description": record(2, ownership="source/ui/Hud.cs")},
        ])
        proc = self.run_cli("conflicts", str(disjoint))
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual({"ok": True, "conflicts": []}, json.loads(proc.stdout))

    def test_finalize_blocks_then_passes_after_reconciliation(self):
        pending_result = self.write_lanes([
            {"todo_id": 1, "description": record(1, state="completed")},
        ])
        proc = self.run_cli("finalize", str(pending_result))
        self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
        self.assertTrue(any("not reconciled" in r for r in json.loads(proc.stdout)["reasons"]))

        reconciled = self.write_lanes([
            {"todo_id": 1, "description": record(1, state="reconciled")},
        ])
        proc = self.run_cli("finalize", str(reconciled))
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual({"ok": True, "reasons": []}, json.loads(proc.stdout))

    def test_finalize_honors_required_and_dispositioned_lanes(self):
        path = self.write_lanes([
            {"todo_id": 1, "description": record(1, state="reconciled")},
            {
                "todo_id": 2,
                "description": record(
                    2, state="dispositioned", disposition="rerouted to lane 3"
                ),
            },
            {"todo_id": 3, "description": record(3, state="reconciled")},
        ])
        proc = self.run_cli("finalize", str(path))
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

        proc = self.run_cli("finalize", str(path), "--required", "1,99")
        self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
        self.assertTrue(any("missing" in r for r in json.loads(proc.stdout)["reasons"]))

    def test_malformed_input_and_unknown_command_exit_2(self):
        self.lanes_path.write_text("not json")
        proc = self.run_cli("frontier", str(self.lanes_path))
        self.assertEqual(2, proc.returncode)
        self.assertIn("error", json.loads(proc.stdout))

        proc = self.run_cli("frobnicate", str(self.lanes_path))
        self.assertEqual(2, proc.returncode)

        proc = self.run_cli("frontier", str(self.lanes_path), "--bogus")
        self.assertEqual(2, proc.returncode)

    def test_native_overrides_and_duplicate_ids(self):
        path = self.write_lanes([
            {
                "todo_id": 1,
                "description": record(1, dependencies="9"),
                "native_status": "in_progress",
                "native_dependencies": [],
            },
        ])
        proc = self.run_cli("frontier", str(path))
        # native overrides mean no unknown-dependency error and nothing pending
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual({"frontier": [], "blocked": []}, json.loads(proc.stdout))

        duplicate = self.write_lanes([
            {"todo_id": 1, "description": record(1)},
            {"todo_id": 1, "description": record(1)},
        ])
        proc = self.run_cli("frontier", str(duplicate))
        self.assertEqual(2, proc.returncode)
        self.assertIn("duplicate", json.loads(proc.stdout)["error"])

    def test_documented_example_record_flows_through_cli(self):
        """The exact example record from SKILL.md parses and schedules via CLI."""
        description = documented_example_description()
        path = self.write_lanes([
            {"todo_id": 2, "description": record(2, state="reconciled")},
            {"todo_id": 3, "description": record(3, state="reconciled")},
            {"todo_id": 7, "description": description},
        ])
        proc = self.run_cli("frontier", str(path))
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn(7, json.loads(proc.stdout)["frontier"])


if __name__ == "__main__":
    unittest.main()
