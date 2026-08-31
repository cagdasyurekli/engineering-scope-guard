#!/usr/bin/env python3
"""Produce the public-safe effort-v1 analysis from a validated private ledger."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import canonical_bytes
from engineering_scope_guard.reasoning_effort_v1 import (
    EXPERIMENTAL_OUTCOMES,
    read_attempt_ledger,
    validate_attempt_ledger,
    validate_contract,
)
from engineering_scope_guard.reasoning_effort_v1_analysis import (
    PROVIDER_USAGE_FIELDS,
    RAW_WORK_FIELDS,
    analyze,
)
from scripts.reasoning_effort_v1_runner import runner_status


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"expected JSON object: {path}")
    return value


def records_from_ledger(
    events: Sequence[dict[str, Any]], schedule: dict[str, Any]
) -> list[dict[str, Any]]:
    """Extract only terminal experimental outcomes bound to frozen cells."""

    cells = schedule.get("cells")
    if not isinstance(cells, list):
        raise ExperimentConfigurationError("frozen schedule cells are absent")
    frozen = {
        cell["cell_id"]: cell
        for cell in cells
        if isinstance(cell, dict) and isinstance(cell.get("cell_id"), str)
    }
    if len(frozen) != len(cells):
        raise ExperimentConfigurationError("frozen cell identifiers are malformed")

    finished: dict[tuple[str, int], dict[str, Any]] = {}
    completed: list[tuple[str, int]] = []
    for event in events:
        event_type = event.get("event_type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise ExperimentConfigurationError("ledger event payload is malformed")
        if event_type == "attempt_finished":
            key = (payload.get("cell_id"), payload.get("attempt"))
            if not isinstance(key[0], str) or key[1] not in (1, 2) or key in finished:
                raise ExperimentConfigurationError("attempt-finished identity is malformed")
            finished[key] = payload
        elif event_type == "cell_completed":
            key = (payload.get("cell_id"), payload.get("attempt"))
            if not isinstance(key[0], str) or key[1] not in (1, 2) or key in completed:
                raise ExperimentConfigurationError("cell-completed identity is malformed")
            completed.append(key)

    records: dict[str, dict[str, Any]] = {}
    for key in completed:
        cell_id, _attempt = key
        cell = frozen.get(cell_id)
        receipt = finished.get(key)
        if cell is None or receipt is None:
            raise ExperimentConfigurationError("completed cell lacks frozen receipt evidence")
        classification = receipt.get("classification")
        expected_identity = {
            "task_id": cell["task_id"],
            "repository": cell["repository"],
            "arm": cell["arm"],
            "repetition": cell["repetition"],
        }
        if any(receipt.get(field) != value for field, value in expected_identity.items()):
            raise ExperimentConfigurationError("receipt identity differs from frozen cell")
        if (
            classification not in EXPERIMENTAL_OUTCOMES
            or receipt.get("termination") != classification
            or receipt.get("admissible") is not True
            or receipt.get("accepted") != (classification == "accepted_completed")
        ):
            raise ExperimentConfigurationError("completed receipt is not a frozen experimental outcome")
        if cell_id in records:
            raise ExperimentConfigurationError("frozen cell completed more than once")
        record = {
            **expected_identity,
            "admissible": True,
            "accepted": receipt["accepted"],
            "termination": classification,
        }
        presence = [field in receipt and receipt[field] is not None for field in RAW_WORK_FIELDS]
        if any(presence):
            if not all(presence):
                raise ExperimentConfigurationError("receipt has a partial work-measurement bundle")
            for field in PROVIDER_USAGE_FIELDS:
                record[field] = receipt[field]
            for field in (
                "subject_wall_seconds",
                "subject_turns",
                "command_count",
                "search_count",
                "item_counts",
            ):
                record[field] = receipt[field]
        records[cell_id] = record

    return [records[cell["cell_id"]] for cell in cells if cell["cell_id"] in records]


def build_analysis(
    contract: dict[str, Any], events: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    validate_contract(contract)
    validate_attempt_ledger(contract, list(events))
    execution_status = runner_status(contract, list(events))
    terminal_action = execution_status["next_action"]["action"]
    if terminal_action not in {"complete", "stopped"}:
        raise ExperimentConfigurationError("analysis requires a terminal experiment ledger")
    records = records_from_ledger(events, contract["schedule"])
    result = analyze(records, contract["schedule"])
    result["contract_sha256"] = contract["contract_sha256"]
    result["schedule_sha256"] = contract["schedule"]["schedule_sha256"]
    result["ledger_terminal_event_sha256"] = (
        events[-1]["event_sha256"] if events else None
    )
    result["execution_terminal_status"] = execution_status
    result["harness_attempts"] = sum(
        event.get("event_type") == "attempt_started" for event in events
    )
    result["conservative_subject_invocation_starts"] = sum(
        event.get("event_type") == "subject_invocation_started" for event in events
    )
    result["confirmed_returned_subject_invocations"] = sum(
        event.get("event_type") == "subject_invocation_returned" for event in events
    )
    result["ambiguous_subject_invocation_starts"] = (
        result["conservative_subject_invocation_starts"]
        - result["confirmed_returned_subject_invocations"]
    )
    result["qualification_subject_invocations"] = contract["attempt_accounting"][
        "qualification_subject_executions"
    ]
    result["conservative_invocation_starts_including_qualification"] = (
        result["conservative_subject_invocation_starts"]
        + result["qualification_subject_invocations"]
    )
    result["experimental_outcomes"] = len(records)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("experiment/reasoning_effort_v1_contract.json"),
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path(".local/reasoning-effort-v1/ledger.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiment/reasoning_effort_v1_analysis.json"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    contract_path = args.contract if args.contract.is_absolute() else root / args.contract
    ledger_path = args.ledger if args.ledger.is_absolute() else root / args.ledger
    output_path = args.output if args.output.is_absolute() else root / args.output
    try:
        contract = _read_object(contract_path)
        events = read_attempt_ledger(ledger_path, contract)
        result = build_analysis(contract, events)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(canonical_bytes(result))
        print(
            json.dumps(
                {
                    "status": "terminal-analysis-complete",
                    "harness_attempts": result["harness_attempts"],
                    "conservative_subject_invocation_starts": result[
                        "conservative_subject_invocation_starts"
                    ],
                    "confirmed_returned_subject_invocations": result[
                        "confirmed_returned_subject_invocations"
                    ],
                    "experimental_outcomes": result["experimental_outcomes"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (ExperimentConfigurationError, OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
