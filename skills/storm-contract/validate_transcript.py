#!/usr/bin/env python3
"""Deterministic transcript validator for the Storm canonical workflow contract.

Loads ``workflow-contract.json`` (in this directory) and validates an event
transcript against its states, transitions, and guards. This is a contract
conformance check only: it proves a recorded event sequence obeys the
canonical lifecycle. It does not prove live Polytoken tool behavior — that is
what the disposable smoke scenarios in docs/workflow-conformance.md are for.

Transcript format (JSON):

    {
      "policy": "require-explicit",        // optional; completion_commit_policy
      "max_rounds": 3,                     // optional; review_loop_max_rounds
      "events": [
        {"event": "scope_resolved"},
        {"event": "issue_opened", "target": "story"},
        ...
      ]
    }

A bare JSON array of events is also accepted. CLI usage:

    python3 validate_transcript.py transcript.json [--policy P] [--max-rounds N]

Exit code 0 with a JSON report when valid; exit code 1 with the failure list
when invalid; exit code 2 on malformed input.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CONTRACT_PATH = Path(__file__).resolve().parent / "workflow-contract.json"
VALID_POLICIES = ("require-explicit", "allow-without-storm-commit")


class TranscriptError(Exception):
    """Malformed transcript or contract input (distinct from a contract violation)."""


def load_contract(path: Path | None = None) -> dict:
    source = path or CONTRACT_PATH
    try:
        return json.loads(source.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise TranscriptError(f"cannot load contract {source}: {exc}") from exc


def _normalize_transcript(raw) -> tuple[list[dict], str | None, int | None]:
    if isinstance(raw, list):
        return raw, None, None
    if isinstance(raw, dict):
        events = raw.get("events")
        if not isinstance(events, list):
            raise TranscriptError("transcript object must contain an 'events' list")
        policy = raw.get("policy")
        max_rounds = raw.get("max_rounds")
        if max_rounds is not None and (not isinstance(max_rounds, int) or max_rounds < 1):
            raise TranscriptError("max_rounds must be a positive integer")
        return events, policy, max_rounds
    raise TranscriptError("transcript must be a JSON array or object")


def validate_transcript(
    events,
    contract: dict,
    policy: str | None = None,
    max_rounds: int | None = None,
) -> list[str]:
    """Validate an event sequence against the contract. Returns a list of
    violations; an empty list means the transcript conforms."""
    if policy is None:
        policy = contract["settings"]["completion_commit_policy"]["default"]
    if policy not in VALID_POLICIES:
        raise TranscriptError(f"unknown completion_commit_policy: {policy!r}")
    if max_rounds is None:
        max_rounds = int(contract["settings"]["review_loop_max_rounds"]["default"])
    if max_rounds < 1:
        raise TranscriptError("max_rounds must be a positive integer")

    transitions = {}
    for entry in contract["transitions"]:
        transitions.setdefault(entry["event"], []).append(entry)

    state = contract["states"]["initial"]
    opened_target = None
    commit_authorized = False
    commit_completed = False
    fix_count = 0
    errors: list[str] = []

    for index, record in enumerate(events):
        label = f"event[{index}]"
        if not isinstance(record, dict) or "event" not in record:
            errors.append(f"{label}: each event must be an object with an 'event' key")
            return errors
        name = record["event"]
        candidates = transitions.get(name)
        if candidates is None:
            errors.append(f"{label}: unknown event {name!r}")
            return errors
        entry = next((c for c in candidates if state in c["from"]), None)
        if entry is None:
            errors.append(
                f"{label}: event {name!r} is not allowed from state {state!r}"
            )
            return errors

        guard = entry.get("guard")
        if guard == "review_round_cap" and fix_count + 2 > max_rounds:
            errors.append(
                f"{label}: fix_applied would exceed review_loop_max_rounds "
                f"({max_rounds}); only review_halted_non_converged may follow"
            )
            return errors
        if guard == "commit_authorized_seen" and not commit_authorized:
            errors.append(
                f"{label}: commit_completed without a prior commit_authorized event"
            )
            return errors
        if guard == "close_policy" and policy == "require-explicit" and not commit_completed:
            errors.append(
                f"{label}: completion_commented under require-explicit without "
                "a completed commit; commit authority alone is insufficient — "
                "the issue must stay In Progress"
            )
            return errors
        if guard == "story_target" and opened_target != "story":
            errors.append(
                f"{label}: issue_closed requires an opened story target "
                f"(opened target is {opened_target!r})"
            )
            return errors
        if guard == "child_target" and opened_target != "child":
            errors.append(
                f"{label}: child_closed requires an opened child-ticket target "
                f"(opened target is {opened_target!r})"
            )
            return errors

        if name == "issue_opened":
            target = record.get("target")
            allowed = entry.get("fields", {}).get("target", [])
            if target not in allowed:
                errors.append(
                    f"{label}: issue_opened requires target in {allowed}, got {target!r}"
                )
                return errors
            opened_target = target
        if name == "commit_authorized":
            commit_authorized = True
        if name == "commit_completed":
            commit_completed = True
        if name == "fix_applied":
            fix_count += 1

        state = state if entry["to"] == "self" else entry["to"]

    return errors


def main(argv: list[str]) -> int:
    args = list(argv)
    policy = None
    max_rounds = None
    positional = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--policy":
            index += 1
            policy = args[index]
        elif arg == "--max-rounds":
            index += 1
            max_rounds = int(args[index])
        else:
            positional.append(arg)
        index += 1
    if len(positional) != 1:
        print(__doc__)
        return 2
    try:
        raw = json.loads(Path(positional[0]).read_text())
        events, embedded_policy, embedded_rounds = _normalize_transcript(raw)
        contract = load_contract()
        errors = validate_transcript(
            events,
            contract,
            policy=policy if policy is not None else embedded_policy,
            max_rounds=max_rounds if max_rounds is not None else embedded_rounds,
        )
    except TranscriptError as exc:
        print(json.dumps({"valid": False, "input_error": str(exc)}))
        return 2
    report = {"valid": not errors, "errors": errors}
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
