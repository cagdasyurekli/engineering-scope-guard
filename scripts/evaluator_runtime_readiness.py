#!/usr/bin/env python3
"""Audit local evaluator-runtime readiness evidence without running Docker or Pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class ReadinessError(RuntimeError):
    """Raised when runtime-readiness evidence contradicts frozen artifacts."""


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReadinessError(f"expected JSON object: {path}")
    return value


def audit(readiness_path: Path, root: Path) -> dict[str, Any]:
    readiness = _read(readiness_path)
    if readiness.get("schema_name") != "engineering-scope-guard.evaluator-runtime-readiness":
        raise ReadinessError("unsupported readiness schema")
    partition = _read(root / "experiment/external_task_partition.json")
    external = _read(root / "experiment/external_input_readiness.json")
    canary = readiness["amd64_canary"]
    gold = readiness["gold_evaluator"]
    subject = readiness["fixed_subject"]
    usage = subject["usage"]
    budget = readiness["pilot_budget"]
    checks = {
        "source_identity": (
            readiness["source"]["dataset_revision"] == partition["source"]["revision"]
            == external["selected_source"]["revision"]
            and readiness["source"]["evaluator_revision"]
            == external["selected_source"]["evaluator_revision"]
        ),
        "allocated_task_unchanged": (
            readiness["source"]["instance_id"]
            == partition["partition"]["smoke_candidate"]["instance_id"]
        ),
        "amd64_canary": (
            canary["requested_platform"] == "linux/amd64"
            and canary["reported_architecture"] == "x86_64"
            and canary["cold_exit_code"] == 0
            and canary["warm_exit_codes"] == [0, 0, 0]
        ),
        "rosetta_configured": (
            readiness["docker"]["virtualization_backend"]
            == "apple-virtualization-framework"
            and readiness["docker"]["rosetta_exposed_to_vm"] is True
            and readiness["docker"]["rosetta_binfmt_registered"] is True
        ),
        "gold_reproducible": (
            len(gold["runs"]) == 3
            and all(run["exit_code"] == 0 and run["resolved"] is True for run in gold["runs"])
            and gold["reproducible"] is True
        ),
        "fixed_subject_receipt_complete": (
            subject["replacement"]["trajectory_complete"] is True
            and subject["replacement"]["turns"] == 2
            and subject["infrastructure_replacements_consumed"] == 1
        ),
        "usage_arithmetic": (
            usage["calculated_fresh_input_tokens"]
            == usage["input_tokens"] - usage["cached_input_tokens"]
            and usage["provider_billed_cost"] == "unavailable"
        ),
        "frozen_budget_preserved": (
            budget["frozen_tasks"] == partition["partition"]["pilot_count"] == 12
            and budget["planned_subject_runs"]
            == external["contingent_budget"]["planned_subject_runs"] == 48
            and budget["gold_preflights"]
            == external["contingent_budget"]["gold_evaluator_preflights"] == 36
        ),
        "pilot_not_authorized": (
            readiness["pilot_authorized"] is False
            and budget["operationally_feasible"] is False
        ),
        "bounded_conclusion": readiness["bounded_conclusion"] == "REDESIGN REQUIRED",
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise ReadinessError(f"runtime readiness checks failed: {failed}")
    return {
        "schema_name": "engineering-scope-guard.evaluator-runtime-readiness-audit",
        "schema_version": 1,
        "status": "pass",
        "checks": checks,
        "gold_runs": len(gold["runs"]),
        "subject_turns": subject["replacement"]["turns"],
        "measured_gold_valid_tasks": budget["measured_gold_valid_tasks"],
        "pilot_authorized": readiness["pilot_authorized"],
        "bounded_conclusion": readiness["bounded_conclusion"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--readiness",
        type=Path,
        default=Path("experiment/evaluator_runtime_readiness.json"),
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(audit(args.readiness, args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
