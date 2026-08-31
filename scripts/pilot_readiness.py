#!/usr/bin/env python3
"""Audit the metadata-only Exploratory Pilot readiness record."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
READINESS = ROOT / "experiment" / "pilot_readiness.json"


class PilotReadinessError(RuntimeError):
    """Raised when the readiness record contradicts its bounded design."""


def _readiness() -> dict[str, Any]:
    try:
        value = json.loads(READINESS.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PilotReadinessError(f"cannot read readiness record: {error}") from error
    if not isinstance(value, dict):
        raise PilotReadinessError("readiness record must be a JSON object")
    return value


def audit_readiness() -> dict[str, Any]:
    """Verify current NO-GO facts without reading any future task body."""

    value = _readiness()
    if (
        value.get("schema_name") != "engineering-scope-guard.pilot-readiness"
        or value.get("schema_version") != 1
        or value.get("conclusion") != "NO-GO"
        or value.get("pilot_authorized") is not False
    ):
        raise PilotReadinessError("readiness identity or conclusion is invalid")

    arms = value.get("arms")
    if not isinstance(arms, list) or [arm.get("id") for arm in arms] != ["baseline", "short"]:
        raise PilotReadinessError("readiness arms must be exactly baseline and short")
    if arms[0].get("policy_path") is not None or arms[0].get("policy_sha256") is not None:
        raise PilotReadinessError("baseline must have no intervention asset")
    short_path = ROOT / str(arms[1].get("policy_path"))
    try:
        short_hash = hashlib.sha256(short_path.read_bytes()).hexdigest()
    except OSError as error:
        raise PilotReadinessError(f"cannot read short policy: {error}") from error
    if short_hash != arms[1].get("policy_sha256"):
        raise PilotReadinessError("short policy hash differs from the readiness record")

    supply = value.get("task_supply")
    if not isinstance(supply, dict):
        raise PilotReadinessError("task supply record is missing")
    if (
        supply.get("catalog_status") != "absent"
        or supply.get("custodian_status") != "unconfirmed"
        or supply.get("confirmed_distinct_eligible_tasks") != 0
        or supply.get("task_bodies_inspected") is not False
        or supply.get("confirmatory_task_bodies_inspected") is not False
    ):
        raise PilotReadinessError("current task-supply NO-GO facts changed")
    strata = supply.get("strata")
    per_stratum = supply.get("pilot_tasks_per_stratum")
    if (
        not isinstance(strata, list)
        or len(strata) != 4
        or len(set(strata)) != 4
        or per_stratum != 3
        or supply.get("minimum_required_distinct_pilot_tasks") != len(strata) * per_stratum
        or supply.get("minimum_required_opaque_inventory")
        != 2 * len(strata) * per_stratum
    ):
        raise PilotReadinessError("task strata or opaque inventory arithmetic is invalid")

    budget = value.get("run_budget")
    if not isinstance(budget, dict):
        raise PilotReadinessError("run budget is missing")
    planned = (
        budget.get("distinct_pilot_tasks", 0)
        * budget.get("arms", 0)
        * budget.get("repetitions_per_task_arm", 0)
    )
    if (
        budget.get("status") != "contingent-not-authorized"
        or planned != budget.get("planned_agent_runs")
        or planned + budget.get("infrastructure_only_replacement_runs", -1)
        != budget.get("total_agent_run_ceiling")
        or planned * budget.get("maximum_turns_per_run", 0)
        != budget.get("maximum_planned_agent_turns")
    ):
        raise PilotReadinessError("run budget arithmetic or authorization is invalid")

    reviewers = value.get("reviewers")
    if (
        not isinstance(reviewers, dict)
        or reviewers.get("confirmed_independent_experienced_reviewers") != 0
        or reviewers.get("llm_judge_equivalent_to_human_review") is not False
    ):
        raise PilotReadinessError("reviewer capacity or LLM-judge boundary changed")

    retention = value.get("version_and_retention")
    if (
        not isinstance(retention, dict)
        or retention.get("retain_all_attempts_failures_and_deviations") is not True
        or retention.get("confirmatory_freeze_started") is not False
    ):
        raise PilotReadinessError("run-retention or confirmatory-freeze boundary changed")

    gates = value.get("gate_status")
    if not isinstance(gates, dict) or gates.get("adequate_task_supply") != "fail":
        raise PilotReadinessError("NO-GO must retain the failed task-supply gate")
    if gates.get("local_process_envelope_isolation") != "pass":
        raise PilotReadinessError("local canary status is not recorded as pass")

    return {
        "schema_name": "engineering-scope-guard.pilot-readiness-audit",
        "schema_version": 1,
        "status": "pass",
        "conclusion": "NO-GO",
        "pilot_authorized": False,
        "arms": ["baseline", "short"],
        "confirmed_distinct_eligible_tasks": 0,
        "minimum_required_opaque_inventory": supply["minimum_required_opaque_inventory"],
        "planned_agent_runs_if_gates_pass": planned,
        "total_agent_run_ceiling_if_gates_pass": budget["total_agent_run_ceiling"],
    }


def main() -> int:
    try:
        result = audit_readiness()
    except PilotReadinessError as error:
        print(f"pilot_readiness: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
