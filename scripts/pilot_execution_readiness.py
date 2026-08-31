#!/usr/bin/env python3
"""Audit the evidence-only Pilot execution-readiness decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "engineering-scope-guard.pilot-execution-readiness"
DECISION = "REDESIGN REQUIRED"
EXPECTED_BLOCKERS = {
    "batch_harness_enforcement",
    "v1_run_order_binding",
    "replacement_budget_units",
}


class ReadinessDecisionError(RuntimeError):
    """Raised when the readiness decision contradicts durable evidence."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReadinessDecisionError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ReadinessDecisionError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ReadinessDecisionError(f"cannot hash {path}: {error}") from error


def audit(decision_path: Path, root: Path) -> dict[str, Any]:
    """Verify the reconciled decision without running a Pilot or provider call."""

    root = root.resolve()
    decision = _read(decision_path)
    prior = _read(root / "experiment/pilot_readiness.json")
    external = _read(root / "experiment/external_input_readiness.json")
    partition = _read(root / "experiment/external_task_partition.json")
    runtime = _read(root / "experiment/evaluator_runtime_readiness.json")
    host = _read(root / "experiment/pilot_host_qualification.json")
    blockers = {item.get("id") for item in decision.get("blockers", [])}
    gate_status = {
        item.get("id"): item.get("status") for item in decision.get("gate_matrix", [])
    }

    checks = {
        "identity": (
            decision.get("schema_name") == SCHEMA
            and decision.get("schema_version") == 1
            and decision.get("status") == "complete"
        ),
        "decision_boundary": (
            decision.get("decision") == DECISION
            and decision.get("pilot_authorized") is False
            and decision.get("pilot_policy_comparison_runs") == 0
        ),
        "arms_and_policy_bytes": (
            decision["arms"]["ids"] == ["baseline", "short"]
            and [arm["id"] for arm in prior["arms"]] == ["baseline", "short"]
            and decision["arms"]["short_policy_sha256"]
            == _sha256(root / "experiment/arms/short.txt")
            == prior["arms"][1]["policy_sha256"]
            and decision["arms"]["d_v0_1_excluded"] is True
            and decision["arms"]["policy_bytes_changed"] is False
        ),
        "source_and_partition": (
            decision["task_source"]["revision"] == partition["source"]["revision"]
            == external["selected_source"]["revision"]
            and decision["task_source"]["eligible_tasks"]
            == partition["eligibility"]["eligible_distinct_tasks"] == 634
            and decision["partition"]["allocation_sha256"]
            == partition["partition"]["allocation_sha256"]
            and decision["partition"]["original_pilot_tasks"]
            == partition["partition"]["pilot_count"] == 12
        ),
        "qualified_final_pool": (
            host["status"] == "complete"
            and host["pilot_authorized"] is False
            and host["codex_runs"] == 0
            and host["policy_arm_runs"] == 0
            and decision["partition"]["final_qualified_pool_tasks"]
            == host["summary"]["final_pool_size"] == 12
            and host["summary"]["recorded_gold_attempts"] == 48
            and decision["partition"]["qualification_task_replacements"]
            == host["replacement_rule"]["consumed"] == 4
        ),
        "effective_reserve": (
            decision["partition"]["effective_reserve_tasks"]
            == host["summary"]["effective_confirmatory_reserve"][
                "effective_confirmatory_reserve_count"
            ] == 499
            and decision["partition"]["effective_reserve_ids_sha256"]
            == host["summary"]["effective_confirmatory_reserve"][
                "effective_confirmatory_reserve_ids_sha256"
            ]
            and decision["partition"]["reserve_ids_or_bodies_emitted"] is False
            and decision["partition"]["confirmatory_task_bodies_inspected"] is False
        ),
        "evaluator_and_fixed_subject": (
            decision["host_and_evaluator"]["evaluator_revision"]
            == host["source"]["evaluator_revision"]
            == runtime["source"]["evaluator_revision"]
            and decision["host_and_evaluator"]["final_pool_all_pass_three_of_three"]
            is True
            and decision["fixed_subject"]["live_single_condition_trajectory_complete"]
            == runtime["fixed_subject"]["replacement"]["trajectory_complete"]
            is True
            and decision["fixed_subject"]["codex_version"]
            == runtime["fixed_subject"]["codex_version"] == "0.150.1"
            and decision["fixed_subject"]["model"]
            == runtime["fixed_subject"]["model"] == "gpt-5.6-terra"
        ),
        "usage_and_billing_limits": (
            decision["usage_and_billing"]["cache_write_tokens"] == "unavailable"
            and decision["usage_and_billing"]["provider_billed_amount_and_currency"]
            == "unavailable"
            and runtime["fixed_subject"]["usage"]["provider_billed_cost"]
            == "unavailable"
            and set(decision["usage_and_billing"]["observed_provider_fields"])
            == set(external["usage_and_billing"]["codex_exec_provider_reported_fields"])
        ),
        "reviewer_and_margin_limits": (
            decision["review_and_claims"][
                "confirmed_independent_experienced_reviewers"
            ] == external["review"]["independent_experienced_reviewers"] == 0
            and decision["methodological_parameters"]["pilot_requires_mcid"] is False
            and decision["methodological_parameters"][
                "pilot_requires_non_inferiority_margin"
            ] is False
            and decision["methodological_parameters"]["arbitrary_values_inherited"]
            is False
        ),
        "planned_budget_preserved": (
            decision["budgets"]["planned_subject_trajectories"]
            == prior["run_budget"]["planned_agent_runs"] == 48
            and decision["budgets"]["pilot_run_level_infrastructure_reserve_recorded"]
            == prior["run_budget"]["infrastructure_only_replacement_runs"] == 8
            and decision["budgets"]["recorded_absolute_subject_trajectory_ceiling"]
            == prior["run_budget"]["total_agent_run_ceiling"] == 56
            and decision["budgets"]["units_reconciled"] is False
        ),
        "blockers_are_exact": (
            blockers == EXPECTED_BLOCKERS
            and {name for name, status in gate_status.items() if status == "blocker"}
            == EXPECTED_BLOCKERS
        ),
        "audited_source_bytes": all(
            _sha256(root / path) == digest
            for path, digest in decision["audited_source_sha256"].items()
        ),
        "next_goal_not_active": (
            decision["proposed_next_goal"]["name"]
            == "Pilot Harness and Reserve Contract Qualification"
            and decision["proposed_next_goal"]["status"] == "proposed-not-active"
            and decision["proposed_next_goal"]["execute_now"] is False
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ReadinessDecisionError(
            "Pilot execution-readiness checks failed: " + ", ".join(failed)
        )
    return {
        "schema_name": SCHEMA + "-audit",
        "schema_version": 1,
        "status": "pass",
        "checks": checks,
        "decision": DECISION,
        "pilot_authorized": False,
        "pilot_policy_comparison_runs": 0,
        "blockers": sorted(blockers),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--decision",
        type=Path,
        default=Path("experiment/pilot_execution_readiness.json"),
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(audit(args.decision, args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
