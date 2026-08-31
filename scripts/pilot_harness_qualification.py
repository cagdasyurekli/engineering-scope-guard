#!/usr/bin/env python3
"""Audit Pilot harness qualification without launching any experimental cell."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import (
    BATCH_STOP_FAILURES,
    EXPERIMENTAL_OUTCOMES,
    RERUNNABLE_INFRASTRUCTURE,
    read_object,
    validate_contract,
)

SCHEMA = "engineering-scope-guard.pilot-harness-qualification"
DECISION = "GO TO EXPLORATORY PILOT"


def audit(path: Path, root: Path) -> dict[str, Any]:
    receipt = read_object(path)
    contract_path = root / receipt["contract"]["path"]
    contract = read_object(contract_path)
    validate_contract(contract, root)
    previous = read_object(root / "experiment/pilot_execution_readiness.json")
    cells = contract["schedule"]["cells"]
    paired = all(
        cells[index]["requested_task_slot"] == cells[index + 1]["requested_task_slot"]
        and cells[index]["repetition"] == cells[index + 1]["repetition"]
        and {cells[index]["arm"], cells[index + 1]["arm"]} == {"baseline", "short"}
        for index in range(0, len(cells), 2)
    )
    slot_budget = contract["final_pool"]["task_slot_replacement_budget"]
    rerun_budget = contract["trajectory_infrastructure_rerun_budget"]
    taxonomy_sets = (
        set(contract["failure_taxonomy"]["experimental_outcomes"]),
        set(contract["failure_taxonomy"]["same_cell_infrastructure_rerun"]),
        set(contract["failure_taxonomy"]["stop_batch"]),
    )
    checks = {
        "identity": receipt.get("schema_name") == SCHEMA and receipt.get("status") == "complete",
        "terminal_decision": receipt.get("decision") == DECISION,
        "previous_decision_preserved": (
            previous.get("decision") == "REDESIGN REQUIRED"
            and previous.get("pilot_authorized") is False
            and {item["id"] for item in previous["blockers"]}
            == {"batch_harness_enforcement", "v1_run_order_binding", "replacement_budget_units"}
        ),
        "zero_execution": (
            receipt.get("pilot_cells_executed") == 0
            and receipt.get("policy_comparisons_executed") == 0
            and contract["pilot_policy_comparison_runs"] == 0
            and contract["qualification"]["pilot_cells_executed"] == 0
        ),
        "contract_bound": (
            receipt["contract"]["contract_sha256"] == contract["contract_sha256"]
            and receipt["contract"]["final_pool_sha256"] == contract["final_pool"]["final_pool_sha256"]
            and receipt["contract"]["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
        ),
        "final_pool": len(contract["final_pool"]["slots"]) == 12,
        "schedule": len(cells) == 48 and paired and contract["schedule"]["manual_edits_permitted"] is False,
        "distinct_budget_names": set(receipt["budgets"]) == {
            "task_slot_replacement", "trajectory_infrastructure_rerun"
        },
        "task_slot_budget": (
            slot_budget["allowance"] == 8 and slot_budget["consumed"] == 4
            and slot_budget["remaining"] == 4
            and slot_budget["remaining_authority_after_finalization"] == 0
            and slot_budget["finalized_before_schedule"] is True
        ),
        "trajectory_rerun_budget": (
            rerun_budget["allowance"] == 8 and rerun_budget["initial_consumed"] == 0
            and rerun_budget["maximum_attempts_per_cell"] == 2
            and rerun_budget["task_or_arm_change_permitted"] is False
        ),
        "taxonomy_exact_and_disjoint": (
            taxonomy_sets == (EXPERIMENTAL_OUTCOMES, RERUNNABLE_INFRASTRUCTURE, BATCH_STOP_FAILURES)
            and not (taxonomy_sets[0] & taxonomy_sets[1] or taxonomy_sets[0] & taxonomy_sets[2]
                     or taxonomy_sets[1] & taxonomy_sets[2])
        ),
        "corrective_contract": (
            contract["trajectory"]["initial_round"] == 0
            and contract["trajectory"]["maximum_corrective_rounds"] == 1
            and contract["subject"]["configuration_change_during_trajectory_permitted"] is False
        ),
        "isolation_limits_honest": (
            contract["isolation"]["provider_unknowns_are_limitations"] is True
            and "provider-side cache isolation guarantee" in contract["isolation"]["unavailable"]
        ),
        "qualification_canaries": all(receipt["qualification"][name] is True for name in (
            "fixtures_or_no_op_only", "contract_mismatch_rejected", "arm_contamination_rejected",
            "state_root_reuse_rejected", "schedule_byte_reproducible",
            "pool_change_changes_commitment", "budget_units_mechanically_distinct",
            "failed_attempt_history_preserved", "failure_taxonomy_frozen",
        )),
        "no_contract_ambiguity": receipt["qualification"]["unresolved_treatment_or_admissibility_ambiguity"] is False,
        "pilot_goal_inactive": (
            receipt["pilot_goal_active"] is False
            and receipt["proposed_pilot_goal"]["status"] == "proposed-not-active"
            and receipt["proposed_pilot_goal"]["execute_now"] is False
        ),
    }
    failed = [name for name, value in checks.items() if not value]
    if failed:
        raise ExperimentConfigurationError("Pilot harness qualification failed: " + ", ".join(failed))
    return {
        "schema_name": SCHEMA + "-audit",
        "schema_version": 1,
        "status": "pass",
        "decision": DECISION,
        "checks": checks,
        "pilot_cells_executed": 0,
        "policy_comparisons_executed": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=Path("experiment/pilot_harness_qualification.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(audit(args.receipt, args.root.resolve()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
