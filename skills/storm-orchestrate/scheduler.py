#!/usr/bin/env python3
"""Deterministic scheduling gates for the storm-orchestrate coordinator.

This standard-library module owns the mechanical gates that must not depend
on prompt compliance: parsing lane records, computing the dependency-ready
frontier, rejecting overlapping writer ownership, classifying native job
terminal states, and deciding whether every required result is reconciled
before finalization. Judgment, task routing, and specialist prompts stay in
the model; this module only answers "is this dispatch/finalization allowed?".

Lane record convention (stored in the native todo description; the native
todo status/dependencies and native job status remain the live state — there
is no second task database). One marker, one field set — SKILL.md, the docs,
and this parser all use exactly this convention:

    storm-lane: 7
    specialist: storm-fixer
    objective: Implement hex-grid neighbor lookup
    ownership: source/core/hex/Grid.cs, source/core/hex/
    dependencies: 2, 3
    edits: allowed
    state: pending
    validation: dotnet build; gdUnit4 core suite
    result: neighbor lookup returns the six adjacent hexes in cube coordinates

Field rules:

- ``edits`` is ``allowed`` or ``read-only``.
- ``state`` is one of ``pending``, ``working``, ``completed``, ``failed``,
  ``cancelled``, ``timed-out``, ``rejected-fit``, ``reconciled``,
  ``dispositioned``.
- ``result`` carries the expected result summary before dispatch and the
  terminal result summary once the lane is terminal.
- ``partial_changes`` lists files a failed/cancelled/timed-out writer touched
  before stopping; ``partial_inspected: true`` is required before a
  replacement writer may start on the same ownership.
- ``disposition`` records the explicit reroute/replace/operator decision and
  is required when — and only when — the state is ``dispositioned``.

Native todo statuses map onto lane states (pending->pending,
in_progress->working, done->completed, blocked->pending); a native
dependency list overrides the record's ``dependencies`` when supplied.

CLI (standard library only; exit 0 = gate passes, 1 = gate fails,
2 = malformed input or record error):

    python3 scheduler.py frontier lanes.json
    python3 scheduler.py conflicts lanes.json
    python3 scheduler.py finalize lanes.json [--required 1,2,3]

``lanes.json`` is a JSON array of lane entries:

    [{"todo_id": 1, "description": "storm-lane: 1\nspecialist: ...",
      "native_status": "in_progress", "native_dependencies": [2]}]

``native_status`` and ``native_dependencies`` are optional; when present they
override the record fields, exactly as in ``parse_lane``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

LANE_MARKER = "storm-lane:"

LANE_STATES = (
    "pending",
    "working",
    "completed",
    "failed",
    "cancelled",
    "timed-out",
    "rejected-fit",
    "reconciled",
    "dispositioned",
)
TERMINAL_STATES = frozenset(
    {
        "completed",
        "failed",
        "cancelled",
        "timed-out",
        "rejected-fit",
        "reconciled",
        "dispositioned",
    }
)
SUCCESS_STATES = frozenset({"completed", "reconciled"})
FAILURE_STATES = frozenset({"failed", "cancelled", "timed-out", "rejected-fit"})

NATIVE_JOB_STATE_MAP = {
    "reserved": "pending",
    "running": "working",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
}
NATIVE_TODO_STATE_MAP = {
    "pending": "pending",
    "in_progress": "working",
    "done": "completed",
    "blocked": "pending",
}

LIST_FIELDS = ("ownership", "dependencies", "partial_changes")
KNOWN_FIELDS = frozenset(
    {
        "specialist",
        "objective",
        "ownership",
        "dependencies",
        "edits",
        "state",
        "validation",
        "result",
        "partial_changes",
        "partial_inspected",
        "disposition",
    }
)


class LaneRecordError(ValueError):
    """A lane record is malformed; the coordinator must fix the record, not guess."""


@dataclass(frozen=True)
class Lane:
    todo_id: int
    specialist: str
    objective: str
    ownership: tuple[str, ...] = ()
    dependencies: tuple[int, ...] = ()
    edits_allowed: bool = False
    state: str = "pending"
    validation: str = ""
    result: str = ""
    partial_changes: tuple[str, ...] = ()
    partial_inspected: bool = False
    disposition: str = ""

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def successful(self) -> bool:
        return self.state in SUCCESS_STATES

    @property
    def is_writer(self) -> bool:
        return self.edits_allowed


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.ok


def classify_native_job_state(status: str, reason: str | None = None) -> str:
    """Map a native Polytoken job status onto a lane state.

    ``failed`` with a timeout/deadline reason classifies as ``timed-out``.
    Unknown statuses raise rather than guess: an unrecognized terminal signal
    must stop scheduling, not silently downgrade.
    """
    normalized = status.strip().lower()
    if normalized not in NATIVE_JOB_STATE_MAP:
        raise LaneRecordError(f"unknown native job status: {status!r}")
    mapped = NATIVE_JOB_STATE_MAP[normalized]
    if mapped == "failed" and reason:
        lowered = reason.lower()
        if "timed out" in lowered or "timeout" in lowered or "deadline" in lowered:
            return "timed-out"
    return mapped


def lane_state_from_todo_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in NATIVE_TODO_STATE_MAP:
        raise LaneRecordError(f"unknown native todo status: {status!r}")
    return NATIVE_TODO_STATE_MAP[normalized]


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_lane_fields(description: str) -> dict:
    """Parse the ``storm-lane`` block out of a native todo description."""
    fields: dict = {}
    in_block = False
    for raw_line in description.splitlines():
        line = raw_line.strip()
        if line.startswith(LANE_MARKER):
            in_block = True
            continue
        if not in_block:
            continue
        if not line:
            break
        if ":" not in line:
            raise LaneRecordError(f"malformed lane record line: {raw_line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        if key not in KNOWN_FIELDS:
            raise LaneRecordError(f"unknown lane record field: {key!r}")
        fields[key] = value.strip()
    if not in_block:
        raise LaneRecordError("missing 'storm-lane:' marker in description")
    return fields


def parse_lane(
    todo_id: int,
    description: str,
    native_status: str | None = None,
    native_dependencies: list[int] | tuple[int, ...] | None = None,
) -> Lane:
    """Build a Lane from a native todo id, its description, and live native state."""
    fields = parse_lane_fields(description)
    for required in ("specialist", "objective"):
        if not fields.get(required):
            raise LaneRecordError(f"lane record missing required field: {required}")

    edits = fields.get("edits", "read-only").strip().lower()
    if edits not in ("allowed", "read-only"):
        raise LaneRecordError(f"edits must be 'allowed' or 'read-only', got {edits!r}")

    if native_status is not None:
        state = lane_state_from_todo_status(native_status)
    else:
        state = fields.get("state", "pending").strip().lower()
        if state not in LANE_STATES:
            raise LaneRecordError(f"unknown lane state: {state!r}")

    if native_dependencies is not None:
        dependencies = tuple(int(dep) for dep in native_dependencies)
    else:
        raw_deps = _split_list(fields.get("dependencies", ""))
        try:
            dependencies = tuple(int(dep) for dep in raw_deps)
        except ValueError as exc:
            raise LaneRecordError(f"dependencies must be todo ids: {raw_deps!r}") from exc

    if todo_id in dependencies:
        raise LaneRecordError(f"lane {todo_id} depends on itself")

    disposition = fields.get("disposition", "")
    if state == "dispositioned" and not disposition:
        raise LaneRecordError(
            f"lane {todo_id} is dispositioned but records no disposition reason"
        )
    if disposition and state != "dispositioned":
        raise LaneRecordError(
            f"lane {todo_id} records a disposition but is in state {state!r}; "
            "a disposition is only valid on a dispositioned lane"
        )

    partial_inspected = fields.get("partial_inspected", "").strip().lower() == "true"

    return Lane(
        todo_id=todo_id,
        specialist=fields["specialist"],
        objective=fields["objective"],
        ownership=tuple(_split_list(fields.get("ownership", ""))),
        dependencies=dependencies,
        edits_allowed=(edits == "allowed"),
        state=state,
        validation=fields.get("validation", ""),
        result=fields.get("result", ""),
        partial_changes=tuple(_split_list(fields.get("partial_changes", ""))),
        partial_inspected=partial_inspected,
        disposition=disposition,
    )


def find_dependency_cycles(lanes: list[Lane]) -> list[tuple[int, ...]]:
    """Dependency cycles in the lane graph, each returned as the cycle path
    (e.g. ``(2, 3, 2)``). A cyclic graph has no valid frontier — the cyclic
    lanes could never dispatch — so this is a record error, not a gate."""
    by_id = {lane.todo_id: lane for lane in lanes}
    cycles: list[tuple[int, ...]] = []
    reported: set[frozenset] = set()
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {todo_id: WHITE for todo_id in by_id}

    def visit(todo_id: int, stack: list[int]) -> None:
        color[todo_id] = GRAY
        stack.append(todo_id)
        for dep in by_id[todo_id].dependencies:
            if dep not in by_id:
                continue  # unknown deps are reported by the frontier itself
            if color[dep] == GRAY:
                cycle = tuple(stack[stack.index(dep):] + [dep])
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    cycles.append(cycle)
            elif color[dep] == WHITE:
                visit(dep, stack)
        stack.pop()
        color[todo_id] = BLACK

    for todo_id in by_id:
        if color[todo_id] == WHITE:
            visit(todo_id, [])
    return cycles


def dependency_frontier(lanes: list[Lane]) -> list[Lane]:
    """Pending lanes whose dependencies are all in a success terminal state.

    A lane whose dependency failed, was cancelled, timed out, or rejected the
    task is NOT on the frontier — it is blocked and needs an explicit
    coordinator decision, never an automatic retry. A cyclic dependency graph
    has no valid frontier at all, so cycles raise rather than silently
    starving the cyclic lanes.
    """
    cycles = find_dependency_cycles(lanes)
    if cycles:
        rendered = [" -> ".join(str(i) for i in cycle) for cycle in cycles]
        raise LaneRecordError(f"dependency cycle(s) detected: {rendered}")
    by_id = {lane.todo_id: lane for lane in lanes}
    frontier = []
    for lane in lanes:
        if lane.state != "pending":
            continue
        missing = [dep for dep in lane.dependencies if dep not in by_id]
        if missing:
            raise LaneRecordError(
                f"lane {lane.todo_id} depends on unknown todos {missing}"
            )
        if all(by_id[dep].successful for dep in lane.dependencies):
            frontier.append(lane)
    return frontier


def blocked_by_failure(lanes: list[Lane]) -> list[tuple[int, int, str]]:
    """(lane, dependency, dependency state) triples that can never dispatch
    until the coordinator reroutes or replaces the failed dependency. A
    dependency in a failure state needs a disposition; a dependency already
    dispositioned needs its dependent's edges re-pointed at the replacement —
    neither unblocks on its own."""
    by_id = {lane.todo_id: lane for lane in lanes}
    blocked = []
    for lane in lanes:
        if lane.state != "pending":
            continue
        for dep in lane.dependencies:
            dependency = by_id.get(dep)
            if dependency is not None and (
                dependency.state in FAILURE_STATES
                or dependency.state == "dispositioned"
            ):
                blocked.append((lane.todo_id, dep, dependency.state))
    return blocked


def ownership_overlaps(first: str, second: str) -> bool:
    """True when two ownership entries name the same file or one folder
    contains the other entry. Entries are repository-relative paths; a
    trailing slash marks a folder."""
    a = first.rstrip("/")
    b = second.rstrip("/")
    if a == b:
        return True
    return a.startswith(b + "/") or b.startswith(a + "/")


def find_writer_conflicts(lanes: list[Lane]) -> list[tuple[int, int, str, str]]:
    """Overlapping ownership among non-terminal writer lanes.

    Two writers may never hold overlapping file/folder ownership at the same
    time; overlapping folder ownership is prohibited unless the plan
    serializes the lanes through dependencies (serialized lanes are not both
    non-terminal, so they do not appear here).
    """
    conflicts = []
    writers = [lane for lane in lanes if lane.is_writer and not lane.terminal]
    for index, first in enumerate(writers):
        for second in writers[index + 1 :]:
            for own_first in first.ownership:
                for own_second in second.ownership:
                    if ownership_overlaps(own_first, own_second):
                        conflicts.append(
                            (first.todo_id, second.todo_id, own_first, own_second)
                        )
    return conflicts


def mark_reconciled(lane: Lane, result: str | None = None) -> Lane:
    """Consume a completed lane's result. Only terminal-success lanes can be
    reconciled; specialist output is evidence, not authority, until the
    coordinator reconciles it."""
    if lane.state != "completed":
        raise LaneRecordError(
            f"lane {lane.todo_id} in state {lane.state!r} cannot be reconciled"
        )
    updates = {"state": "reconciled"}
    if result is not None:
        updates["result"] = result
    return replace(lane, **updates)


def mark_partial_inspected(lane: Lane) -> Lane:
    """Record that a stopped writer's partial filesystem changes were
    inspected. Cancellation is not rollback; a replacement writer may start
    only after this inspection."""
    if lane.state not in ("failed", "cancelled", "timed-out"):
        raise LaneRecordError(
            f"lane {lane.todo_id} in state {lane.state!r} has no partial work to inspect"
        )
    return replace(lane, partial_inspected=True)


def mark_dispositioned(lane: Lane, reason: str) -> Lane:
    """Record the explicit coordinator/operator decision for a failed lane.

    A failure-state lane blocks finalization until it is dispositioned:
    rerouted, replaced, or explicitly accepted by the operator. The reason is
    mandatory and is recorded on the lane; a stopped writer's partial changes
    must be inspected first. Dispositioning is a decision record, not a
    retry — it never changes the lane's outcome, and dependents stay blocked
    until their edges are re-pointed."""
    if lane.state not in FAILURE_STATES:
        raise LaneRecordError(
            f"lane {lane.todo_id} in state {lane.state!r} cannot be dispositioned; "
            "only failed, cancelled, timed-out, or rejected-fit lanes need a disposition"
        )
    if not reason.strip():
        raise LaneRecordError(
            f"lane {lane.todo_id} disposition requires a non-empty reason"
        )
    if lane.partial_changes and not lane.partial_inspected:
        raise LaneRecordError(
            f"lane {lane.todo_id} left partial changes {list(lane.partial_changes)} "
            "that must be inspected before the lane is dispositioned"
        )
    return replace(lane, state="dispositioned", disposition=reason.strip())


def replacement_writer_allowed(lane: Lane) -> GateResult:
    """Whether a replacement writer may start for a stopped writer lane."""
    if lane.state not in ("failed", "cancelled", "timed-out"):
        return GateResult(
            False, (f"lane {lane.todo_id} is not a stopped writer ({lane.state})",)
        )
    if lane.partial_changes and not lane.partial_inspected:
        return GateResult(
            False,
            (
                f"lane {lane.todo_id} left partial changes {list(lane.partial_changes)} "
                "that must be inspected before a replacement writer starts",
            ),
        )
    return GateResult(True, ())


def reconciliation_pending(lanes: list[Lane]) -> list[Lane]:
    """Terminal-success lanes whose results have not been consumed yet."""
    return [lane for lane in lanes if lane.state == "completed"]


def finalization_gate(
    lanes: list[Lane], required_ids: list[int] | tuple[int, ...] | None = None
) -> GateResult:
    """Whether the coordinator may finalize (final response / close).

    Blocked until: every lane is terminal, every required lane's result is
    reconciled, every failure-state lane has been explicitly dispositioned
    (via ``mark_dispositioned``, which records the reason), no stopped writer
    has uninspected partial changes, no writer conflicts remain, and the
    dependency graph is acyclic.
    """
    reasons: list[str] = []
    by_id = {lane.todo_id: lane for lane in lanes}

    for cycle in find_dependency_cycles(lanes):
        rendered = " -> ".join(str(i) for i in cycle)
        reasons.append(f"dependency cycle among lanes: {rendered}")

    required = list(required_ids) if required_ids is not None else list(by_id)
    missing = [todo_id for todo_id in required if todo_id not in by_id]
    for todo_id in missing:
        reasons.append(f"required lane {todo_id} is missing from the board")

    for lane in lanes:
        if not lane.terminal:
            reasons.append(f"lane {lane.todo_id} is still {lane.state}")
        elif lane.state in FAILURE_STATES:
            reasons.append(
                f"lane {lane.todo_id} ended {lane.state} and needs an explicit "
                "disposition (reroute, replacement, or operator decision)"
            )
        if lane.state in ("failed", "cancelled", "timed-out") and (
            lane.partial_changes and not lane.partial_inspected
        ):
            reasons.append(
                f"lane {lane.todo_id} has uninspected partial changes "
                f"{list(lane.partial_changes)}"
            )

    for todo_id in required:
        lane = by_id.get(todo_id)
        if lane is None:
            continue
        if lane.state == "completed":
            reasons.append(
                f"required lane {todo_id} result is not reconciled yet"
            )

    for first, second, own_first, own_second in find_writer_conflicts(lanes):
        reasons.append(
            f"writer conflict between lanes {first} and {second}: "
            f"{own_first} overlaps {own_second}"
        )

    return GateResult(not reasons, tuple(reasons))


# --- CLI -----------------------------------------------------------------


def load_lanes(path: str) -> list[Lane]:
    """Load lanes from a JSON file: an array of ``{"todo_id", "description",
    "native_status"?, "native_dependencies"?}`` entries parsed through the
    real ``parse_lane``. Malformed input raises ``LaneRecordError``."""
    try:
        raw = json.loads(Path(path).read_text())
    except OSError as exc:
        raise LaneRecordError(f"cannot read lanes file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LaneRecordError(f"lanes file {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise LaneRecordError("lanes file must contain a JSON array of lane entries")
    lanes = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise LaneRecordError(f"lane entry[{index}] must be an object")
        try:
            todo_id = int(entry["todo_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LaneRecordError(
                f"lane entry[{index}] needs an integer 'todo_id'"
            ) from exc
        description = entry.get("description")
        if not isinstance(description, str):
            raise LaneRecordError(f"lane entry[{index}] needs a string 'description'")
        native_dependencies = entry.get("native_dependencies")
        if native_dependencies is not None:
            if not isinstance(native_dependencies, list):
                raise LaneRecordError(
                    f"lane entry[{index}] 'native_dependencies' must be a list"
                )
            try:
                native_dependencies = [int(dep) for dep in native_dependencies]
            except (TypeError, ValueError) as exc:
                raise LaneRecordError(
                    f"lane entry[{index}] 'native_dependencies' must be todo ids"
                ) from exc
        lanes.append(
            parse_lane(
                todo_id,
                description,
                native_status=entry.get("native_status"),
                native_dependencies=native_dependencies,
            )
        )
    ids = [lane.todo_id for lane in lanes]
    if len(ids) != len(set(ids)):
        raise LaneRecordError("lanes file contains duplicate todo_id values")
    return lanes


def main(argv: list[str]) -> int:
    args = list(argv)
    required: list[int] | None = None
    positional: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--required":
            index += 1
            if index >= len(args):
                print(__doc__)
                return 2
            try:
                required = [int(part) for part in args[index].split(",") if part.strip()]
            except ValueError:
                print(json.dumps({"error": "--required takes comma-separated todo ids"}))
                return 2
        elif arg.startswith("-"):
            print(json.dumps({"error": f"unknown option {arg!r}"}))
            return 2
        else:
            positional.append(arg)
        index += 1

    if len(positional) != 2 or positional[0] not in ("frontier", "conflicts", "finalize"):
        print(__doc__)
        return 2
    command, lanes_path = positional

    try:
        lanes = load_lanes(lanes_path)
    except LaneRecordError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2

    try:
        if command == "frontier":
            frontier = dependency_frontier(lanes)
            blocked = blocked_by_failure(lanes)
            report = {
                "frontier": [lane.todo_id for lane in frontier],
                "blocked": [
                    {"lane": lane_id, "dependency": dep, "dependency_state": state}
                    for lane_id, dep, state in blocked
                ],
            }
            print(json.dumps(report, indent=2))
            return 0

        if command == "conflicts":
            conflicts = find_writer_conflicts(lanes)
            report = {
                "ok": not conflicts,
                "conflicts": [
                    {
                        "first": first,
                        "second": second,
                        "ownership_first": own_first,
                        "ownership_second": own_second,
                    }
                    for first, second, own_first, own_second in conflicts
                ],
            }
            print(json.dumps(report, indent=2))
            return 0 if not conflicts else 1

        gate = finalization_gate(lanes, required_ids=required)
        print(json.dumps({"ok": gate.ok, "reasons": list(gate.reasons)}, indent=2))
        return 0 if gate.ok else 1
    except LaneRecordError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
