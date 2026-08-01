"""Deterministic tests for the storm-orchestrate scheduler gates.

These tests import and exercise the actual module at
skills/storm-orchestrate/scheduler.py — not a reference duplicate.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = ROOT / "skills/storm-orchestrate/scheduler.py"


def load_scheduler():
    spec = importlib.util.spec_from_file_location("storm_scheduler", SCHEDULER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve cls.__module__ here
    spec.loader.exec_module(module)
    return module


SCHED = load_scheduler()


def lane_description(**overrides) -> str:
    fields = {
        "specialist": "storm-fixer",
        "objective": "Implement the thing",
        "ownership": "source/core/hex/Grid.cs",
        "dependencies": "",
        "edits": "allowed",
        "state": "pending",
        "validation": "dotnet build",
        "result": "",
        "partial_changes": "",
        "partial_inspected": "",
        "disposition": "",
    }
    fields.update(overrides)
    lines = ["storm-lane: 1"]
    lines.extend(f"{key}: {value}" for key, value in fields.items() if value != "")
    return "\n".join(lines)


def make_lane(todo_id, **overrides) -> "SCHED.Lane":
    native_status = overrides.pop("native_status", None)
    native_dependencies = overrides.pop("native_dependencies", None)
    return SCHED.parse_lane(
        todo_id,
        lane_description(**overrides),
        native_status=native_status,
        native_dependencies=native_dependencies,
    )


class LaneParsingTests(unittest.TestCase):
    def test_parse_lane_record_full_fields(self):
        lane = make_lane(
            7,
            specialist="storm-fixer",
            objective="Implement hex neighbors",
            ownership="source/core/hex/Grid.cs, source/core/hex/",
            dependencies="2, 3",
            edits="allowed",
            validation="dotnet build; gdUnit4 core",
        )
        self.assertEqual(7, lane.todo_id)
        self.assertEqual("storm-fixer", lane.specialist)
        self.assertEqual(
            ("source/core/hex/Grid.cs", "source/core/hex/"), lane.ownership
        )
        self.assertEqual((2, 3), lane.dependencies)
        self.assertTrue(lane.edits_allowed)
        self.assertEqual("pending", lane.state)
        self.assertFalse(lane.terminal)

    def test_parse_requires_marker_and_required_fields(self):
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.parse_lane(1, "no marker here")
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.parse_lane(1, "storm-lane: 1\nspecialist: storm-fixer")
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.parse_lane(1, "storm-lane: 1\nspecialist: x\nobjective: y\nbogus: z")
        with self.assertRaises(SCHED.LaneRecordError):
            make_lane(1, edits="sometimes")
        with self.assertRaises(SCHED.LaneRecordError):
            make_lane(1, dependencies="abc")

    def test_native_status_and_dependencies_override_record(self):
        lane = make_lane(
            1, native_status="in_progress", native_dependencies=[4, 5], dependencies="9"
        )
        self.assertEqual("working", lane.state)
        self.assertEqual((4, 5), lane.dependencies)
        self.assertEqual("completed", make_lane(2, native_status="done").state)
        self.assertEqual("pending", make_lane(3, native_status="blocked").state)
        with self.assertRaises(SCHED.LaneRecordError):
            make_lane(4, native_status="mystery")

    def test_native_job_terminal_state_classification(self):
        self.assertEqual("pending", SCHED.classify_native_job_state("reserved"))
        self.assertEqual("working", SCHED.classify_native_job_state("running"))
        self.assertEqual("completed", SCHED.classify_native_job_state("completed"))
        self.assertEqual("failed", SCHED.classify_native_job_state("failed"))
        self.assertEqual("cancelled", SCHED.classify_native_job_state("cancelled"))
        self.assertEqual(
            "timed-out",
            SCHED.classify_native_job_state("failed", reason="job timed out"),
        )
        self.assertEqual(
            "timed-out",
            SCHED.classify_native_job_state("failed", reason="deadline expired"),
        )
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.classify_native_job_state("exploded")


class FrontierTests(unittest.TestCase):
    def test_scheduler_dispatches_only_dependency_frontier(self):
        first = make_lane(1)
        second = make_lane(2, dependencies="1")
        third = make_lane(3, dependencies="2")
        parallel = make_lane(4, specialist="storm-explorer", edits="read-only")
        lanes = [first, second, third, parallel]
        self.assertEqual({1, 4}, {lane.todo_id for lane in SCHED.dependency_frontier(lanes)})

        lanes = [make_lane(1, state="reconciled"), second, third, parallel]
        self.assertEqual({2, 4}, {lane.todo_id for lane in SCHED.dependency_frontier(lanes)})

    def test_failed_dependency_blocks_frontier_and_is_reported(self):
        failed = make_lane(1, state="failed")
        dependent = make_lane(2, dependencies="1")
        lanes = [failed, dependent]
        self.assertEqual([], SCHED.dependency_frontier(lanes))
        self.assertEqual([(2, 1, "failed")], SCHED.blocked_by_failure(lanes))

    def test_unknown_dependency_is_an_error_not_a_dispatch(self):
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.dependency_frontier([make_lane(1, dependencies="99")])


class DependencyGraphTests(unittest.TestCase):
    def test_self_dependency_is_rejected_at_parse(self):
        with self.assertRaises(SCHED.LaneRecordError) as ctx:
            make_lane(3, dependencies="3")
        self.assertIn("depends on itself", str(ctx.exception))

    def test_dependency_cycle_raises_from_frontier(self):
        lanes = [
            make_lane(1, dependencies="2"),
            make_lane(2, dependencies="1"),
            make_lane(4, specialist="storm-explorer", edits="read-only"),
        ]
        with self.assertRaises(SCHED.LaneRecordError) as ctx:
            SCHED.dependency_frontier(lanes)
        self.assertIn("cycle", str(ctx.exception))

    def test_find_dependency_cycles_reports_the_cycle_path(self):
        lanes = [
            make_lane(1, dependencies="3"),
            make_lane(2, dependencies="1"),
            make_lane(3, dependencies="2"),
        ]
        cycles = SCHED.find_dependency_cycles(lanes)
        self.assertEqual(1, len(cycles))
        cycle = cycles[0]
        self.assertEqual(cycle[0], cycle[-1])
        self.assertEqual({1, 2, 3}, set(cycle))

        acyclic = [make_lane(1), make_lane(2, dependencies="1")]
        self.assertEqual([], SCHED.find_dependency_cycles(acyclic))

    def test_cycle_blocks_finalization_with_explicit_reason(self):
        lanes = [
            make_lane(1, dependencies="2", state="reconciled"),
            make_lane(2, dependencies="1", state="reconciled"),
        ]
        gate = SCHED.finalization_gate(lanes)
        self.assertFalse(gate.ok)
        self.assertTrue(any("cycle" in reason for reason in gate.reasons))


class WriterOwnershipTests(unittest.TestCase):
    def test_scheduler_rejects_overlapping_writer_ownership(self):
        first = make_lane(1, ownership="source/core/hex/Grid.cs")
        same_file = make_lane(2, ownership="source/core/hex/Grid.cs")
        folder = make_lane(3, ownership="source/core/hex/")
        parent_folder = make_lane(4, ownership="source/core/")
        disjoint = make_lane(5, ownership="source/ui/Hud.cs")

        conflicts = SCHED.find_writer_conflicts([first, same_file, folder, parent_folder, disjoint])
        pairs = {(a, b) for a, b, _, _ in conflicts}
        self.assertIn((1, 2), pairs)
        self.assertIn((1, 3), pairs)
        self.assertIn((1, 4), pairs)
        self.assertNotIn((1, 5), pairs)

    def test_read_only_and_terminal_lanes_do_not_conflict(self):
        writer = make_lane(1, ownership="source/core/hex/")
        reader = make_lane(2, ownership="source/core/hex/Grid.cs", edits="read-only")
        done_writer = make_lane(3, ownership="source/core/hex/", state="reconciled")
        self.assertEqual([], SCHED.find_writer_conflicts([writer, reader, done_writer]))

    def test_serialized_writers_do_not_conflict(self):
        first = make_lane(1, ownership="source/core/hex/", state="reconciled")
        second = make_lane(2, ownership="source/core/hex/", dependencies="1")
        self.assertEqual([], SCHED.find_writer_conflicts([first, second]))


class ReconciliationTests(unittest.TestCase):
    def test_reconcile_only_completed_lanes(self):
        completed = make_lane(1, state="completed")
        reconciled = SCHED.mark_reconciled(completed, result="shipped")
        self.assertEqual("reconciled", reconciled.state)
        self.assertEqual("shipped", reconciled.result)
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.mark_reconciled(make_lane(2, state="working"))
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.mark_reconciled(make_lane(3, state="failed"))

    def test_reconciliation_pending_lists_unconsumed_results(self):
        lanes = [
            make_lane(1, state="completed"),
            make_lane(2, state="reconciled"),
            make_lane(3, state="working"),
        ]
        self.assertEqual([1], [lane.todo_id for lane in SCHED.reconciliation_pending(lanes)])

    def test_replacement_writer_requires_partial_inspection(self):
        cancelled = make_lane(
            1, state="cancelled", partial_changes="source/core/hex/Grid.cs"
        )
        gate = SCHED.replacement_writer_allowed(cancelled)
        self.assertFalse(gate.ok)
        self.assertIn("partial changes", gate.reasons[0])
        inspected = SCHED.mark_partial_inspected(cancelled)
        self.assertTrue(SCHED.replacement_writer_allowed(inspected).ok)
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.mark_partial_inspected(make_lane(2, state="working"))
        self.assertFalse(
            SCHED.replacement_writer_allowed(make_lane(3, state="completed")).ok
        )

    def test_finalization_waits_for_reconciliation_and_verification(self):
        done = make_lane(1, state="reconciled")
        verify = make_lane(2, specialist="storm-oracle", edits="read-only", state="reconciled")
        self.assertTrue(SCHED.finalization_gate([done, verify]).ok)

        pending = make_lane(3)
        gate = SCHED.finalization_gate([done, verify, pending])
        self.assertFalse(gate.ok)
        self.assertTrue(any("still pending" in reason for reason in gate.reasons))

        unreconciled = make_lane(4, state="completed")
        gate = SCHED.finalization_gate([done, verify, unreconciled])
        self.assertFalse(gate.ok)
        self.assertTrue(any("not reconciled" in reason for reason in gate.reasons))

        failed = make_lane(5, state="timed-out")
        gate = SCHED.finalization_gate([done, verify, failed])
        self.assertFalse(gate.ok)
        self.assertTrue(any("timed-out" in reason for reason in gate.reasons))

        partial = make_lane(
            6, state="failed", partial_changes="source/core/hex/Grid.cs"
        )
        gate = SCHED.finalization_gate([done, verify, partial])
        self.assertFalse(gate.ok)
        self.assertTrue(any("uninspected partial" in reason for reason in gate.reasons))

        conflict_a = make_lane(7, ownership="source/core/")
        conflict_b = make_lane(8, ownership="source/core/hex/Grid.cs")
        gate = SCHED.finalization_gate([done, verify, conflict_a, conflict_b])
        self.assertFalse(gate.ok)
        self.assertTrue(any("writer conflict" in reason for reason in gate.reasons))

        gate = SCHED.finalization_gate([done], required_ids=[99])
        self.assertFalse(gate.ok)
        self.assertTrue(any("missing" in reason for reason in gate.reasons))

    def test_rejected_fit_lane_blocks_finalization_until_dispositioned(self):
        lane = make_lane(1, state="rejected-fit", result="not a fixer task")
        gate = SCHED.finalization_gate([lane])
        self.assertFalse(gate.ok)
        self.assertTrue(any("rejected-fit" in reason for reason in gate.reasons))


class DispositionTests(unittest.TestCase):
    def test_dispositioned_failure_lane_passes_finalization(self):
        failed = make_lane(1, state="failed")
        gate = SCHED.finalization_gate([failed])
        self.assertFalse(gate.ok)
        self.assertTrue(any("disposition" in reason for reason in gate.reasons))

        dispositioned = SCHED.mark_dispositioned(
            failed, "operator accepted: obsolete lane, work folded into lane 2"
        )
        self.assertEqual("dispositioned", dispositioned.state)
        self.assertTrue(dispositioned.terminal)
        self.assertFalse(dispositioned.successful)
        gate = SCHED.finalization_gate([dispositioned])
        self.assertTrue(gate.ok, gate.reasons)

    def test_mark_dispositioned_requires_failure_state_and_reason(self):
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.mark_dispositioned(make_lane(1, state="working"), "rerouted")
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.mark_dispositioned(make_lane(2, state="completed"), "rerouted")
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.mark_dispositioned(make_lane(3, state="reconciled"), "rerouted")
        with self.assertRaises(SCHED.LaneRecordError):
            SCHED.mark_dispositioned(make_lane(4, state="failed"), "   ")

    def test_disposition_requires_partial_inspection_first(self):
        cancelled = make_lane(
            1, state="cancelled", partial_changes="source/core/hex/Grid.cs"
        )
        with self.assertRaises(SCHED.LaneRecordError) as ctx:
            SCHED.mark_dispositioned(cancelled, "replaced by lane 5")
        self.assertIn("partial changes", str(ctx.exception))
        inspected = SCHED.mark_partial_inspected(cancelled)
        dispositioned = SCHED.mark_dispositioned(inspected, "replaced by lane 5")
        self.assertEqual("dispositioned", dispositioned.state)

    def test_parsed_dispositioned_record_requires_consistent_reason(self):
        lane = make_lane(
            1, state="dispositioned", disposition="rerouted to lane 5"
        )
        self.assertEqual("dispositioned", lane.state)
        self.assertEqual("rerouted to lane 5", lane.disposition)

        with self.assertRaises(SCHED.LaneRecordError):
            make_lane(2, state="dispositioned")
        with self.assertRaises(SCHED.LaneRecordError):
            make_lane(3, state="failed", disposition="rerouted to lane 5")

    def test_dependent_of_dispositioned_lane_stays_blocked(self):
        failed = make_lane(1, state="failed")
        dependent = make_lane(2, dependencies="1")
        dispositioned = SCHED.mark_dispositioned(failed, "replaced by lane 3")
        lanes = [dispositioned, dependent]
        self.assertEqual([], SCHED.dependency_frontier(lanes))
        self.assertEqual(
            [(2, 1, "dispositioned")], SCHED.blocked_by_failure(lanes)
        )


class DocumentedConventionTests(unittest.TestCase):
    """The lane-record example documented in SKILL.md must parse with the
    real parser — one marker, one field set, no documentation drift."""

    def test_documented_example_record_parses(self):
        skill_text = (ROOT / "skills/storm-orchestrate/SKILL.md").read_text()
        blocks = [
            block
            for block in skill_text.split("```")
            if "storm-lane: 7" in block
        ]
        self.assertEqual(1, len(blocks), "SKILL.md must carry exactly one concrete storm-lane example")
        lane = SCHED.parse_lane(7, blocks[0])
        self.assertEqual("storm-fixer", lane.specialist)
        self.assertEqual("Implement hex-grid neighbor lookup", lane.objective)
        self.assertEqual(
            ("source/core/hex/Grid.cs", "source/core/hex/"), lane.ownership
        )
        self.assertEqual((2, 3), lane.dependencies)
        self.assertTrue(lane.edits_allowed)
        self.assertEqual("pending", lane.state)

    def test_module_docstring_example_parses(self):
        doc = SCHED.__doc__
        marker_at = doc.index("storm-lane: 7")
        end_at = doc.index("\n\n", marker_at)
        example = doc[marker_at:end_at]
        lane = SCHED.parse_lane(7, example)
        self.assertEqual("storm-fixer", lane.specialist)
        self.assertEqual((2, 3), lane.dependencies)


if __name__ == "__main__":
    unittest.main()
