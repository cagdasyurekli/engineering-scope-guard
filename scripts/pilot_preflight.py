#!/usr/bin/env python3
"""Audit the durable blocked Pilot preflight receipt without running a cell."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import read_object, validate_contract


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ExperimentConfigurationError(f"cannot hash {path}: {error}") from error


def audit(receipt_path: Path, root: Path) -> dict[str, Any]:
    receipt = read_object(receipt_path)
    contract_path = root / receipt["contract"]["path"]
    contract = read_object(contract_path)
    validate_contract(contract, root)

    expected_checks = {
        "codex_subject_canary": True,
        "confirmatory_reserve_emitted": False,
        "contract_audit": True,
        "contract_tracked_from_main": True,
        "docker_architecture_resources_and_images": True,
        "evaluator_and_source_revisions": True,
        "fresh_isolation_canary": True,
        "head_equal_origin_main": True,
        "no_experimental_byte_drift": True,
        "pilot_ledger_absent": True,
        "pilot_state_roots_absent": True,
        "working_tree_clean_before_preflight": True,
    }
    checks = {
        "schema": (
            receipt.get("schema_name") == "engineering-scope-guard.pilot-preflight"
            and receipt.get("schema_version") == 1
        ),
        "provenance": (
            receipt.get("base_commit")
            == "c71df19b4a90d0ae408c09fa3c1518e5f0e7aef0"
            and receipt.get("recorded_at") == "2026-08-28"
            and isinstance(receipt.get("stop", {}).get("discrepancy"), str)
            and bool(receipt["stop"]["discrepancy"].strip())
        ),
        "blocked_before_cell_one": (
            receipt.get("status") == "blocked"
            and receipt.get("preflight_passed") is False
            and receipt.get("preflight_restarted_from_beginning") is True
            and receipt.get("stop", {}).get("class") == "harness_failure"
            and receipt.get("stop", {}).get("frozen_action") == "stop_batch"
            and receipt.get("stop", {}).get("stopped_before_cell") == 1
            and "harness_failure" in contract["failure_taxonomy"]["stop_batch"]
        ),
        "zero_execution": (
            receipt.get("pilot_cells_executed") == 0
            and receipt.get("policy_comparisons_executed") == 0
            and contract["pilot_policy_comparison_runs"] == 0
        ),
        "parameters_unchanged": receipt.get("experimental_parameters_changed") is False,
        "preflight_checks": receipt.get("checks") == expected_checks,
        "contract_commitments": (
            receipt["contract"].get("version") == contract["contract_version"]
            and receipt["contract"].get("contract_sha256") == contract["contract_sha256"]
            and receipt["contract"].get("final_pool_sha256")
            == contract["final_pool"]["final_pool_sha256"]
            and receipt["contract"].get("schedule_sha256")
            == contract["schedule"]["schedule_sha256"]
            and receipt["contract"].get("short_policy_sha256")
            == contract["arms"]["short_policy_sha256"]
            and receipt["contract"].get("contract_file_sha256") == _sha256(contract_path)
        ),
        "evidence_source_bytes": all(
            _sha256(root / path) == expected
            for path, expected in receipt.get("evidence_source_sha256", {}).items()
        ) and len(receipt.get("evidence_source_sha256", {})) == 3,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ExperimentConfigurationError(
            "blocked Pilot preflight receipt mismatch: " + ", ".join(failed)
        )
    return {
        "schema_name": "engineering-scope-guard.pilot-preflight-audit",
        "status": "pass",
        "conclusion": "blocked",
        "stop_class": "harness_failure",
        "pilot_cells_executed": 0,
        "policy_comparisons_executed": 0,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt", type=Path, default=Path("experiment/pilot_preflight.json")
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        result = audit(args.receipt, args.root.resolve())
    except (ExperimentConfigurationError, KeyError, OSError, ValueError) as error:
        print(f"pilot_preflight: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
