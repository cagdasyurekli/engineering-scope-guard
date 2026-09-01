#!/usr/bin/env python3
"""Build the private all-gates manifest required before successor freeze."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from engineering_scope_guard.pilot_contract import canonical_bytes, digest


SCHEMA_NAME = "engineering-scope-guard.launch-surface-final-readiness"
GATES = (
    "low_contentless_launch",
    "medium_contentless_launch",
    "treatment_clean_profiles",
    "runtime_identity_pinned",
    "runtime_sentinel_stable",
    "qualified_pool",
    "evaluator_source_pinned",
    "azure_evaluator_operational",
    "campaign_clock_operational",
    "subject_quota_sufficient",
    "canonical_repository_healthy",
    "scientific_integrity_clear",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _self_hash(value: dict[str, Any], field: str) -> bool:
    return value.get(field) == digest(
        {key: item for key, item in value.items() if key != field}
    )


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    _require(isinstance(value, dict), f"{path.name} is not an object")
    return value


def build(
    *, preflight: dict[str, Any], runtime: dict[str, Any],
    launch_contract: dict[str, Any], stability: dict[str, Any],
    quota: dict[str, Any], azure_pool: dict[str, Any],
    azure_readiness: dict[str, Any], campaign_clock: dict[str, Any],
    azure_occupancy: dict[str, Any], canonical_health: dict[str, Any],
) -> dict[str, Any]:
    """Validate the external evidence and bind every prospective gate."""

    _require(
        preflight.get("ready_for_external_gates") is True
        and _self_hash(preflight, "preflight_sha256"),
        "successor preflight is not valid",
    )
    _require(_self_hash(runtime, "receipt_sha256"), "runtime receipt drifted")
    _require(_self_hash(launch_contract, "contract_sha256"), "launch contract drifted")
    _require(_self_hash(stability, "state_sha256"), "stability state drifted")
    _require(
        quota.get("schema_name")
        == "engineering-scope-guard.launch-surface-subject-quota-gate"
        and quota.get("status") == "pass"
        and quota.get("operational_headroom_percent", -1)
        >= quota.get("minimum_operational_headroom_percent", 101)
        and quota.get("planned_subject_cells") == 40
        and quota.get("maximum_subject_attempts") == 48
        and quota.get("codex_binary_sha256") == runtime.get("codex_binary_sha256")
        and _self_hash(quota, "quota_gate_sha256"),
        "subject quota gate is not sufficient",
    )
    _require(
        azure_pool.get("schema_name")
        == "engineering-scope-guard.azure-evaluator-pool"
        and azure_pool.get("status") == "ready"
        and _self_hash(azure_pool, "pool_receipt_sha256"),
        "Azure evaluator pool is not ready",
    )
    _require(
        azure_readiness.get("schema_name")
        == "engineering-scope-guard.azure-evaluator-receipt"
        and azure_readiness.get("status") == "pass"
        and azure_readiness.get("azure_exit_code") == 0
        and azure_readiness.get("azure_retry_count") == 0
        and azure_readiness.get("azure_requeue_count") == 0
        and azure_readiness.get("evaluator_revision")
        == azure_pool.get("evaluator_revision")
        and azure_readiness.get("repolaunch_revision")
        == azure_pool.get("repolaunch_revision")
        and azure_readiness.get("worker_image_identity")
        == azure_pool.get("worker_image_identity")
        and _self_hash(azure_readiness, "azure_evaluator_receipt_sha256"),
        "Azure evaluator readiness canary did not pass cleanly",
    )
    _require(
        campaign_clock.get("schema_name")
        == "engineering-scope-guard.campaign-clock"
        and campaign_clock.get("hard_max_duration_ns", 0) > 0
        and campaign_clock.get("accumulated_previous_ns", -1) >= 0
        and isinstance(campaign_clock.get("completed_segments"), list)
        and isinstance(campaign_clock.get("current_segment"), dict)
        and _self_hash(campaign_clock, "receipt_sha256"),
        "independent campaign clock is not valid",
    )
    _require(
        azure_occupancy.get("schema_name")
        == "engineering-scope-guard.azure-evaluator-occupancy"
        and azure_occupancy.get("status") == "pass"
        and azure_occupancy.get("conflicting_pools") == []
        and azure_occupancy.get("conflicting_jobs") == []
        and azure_occupancy.get("conflicting_active_nodes") == 0
        and azure_occupancy.get("own_pool_id") == azure_pool.get("pool_id")
        and _self_hash(azure_occupancy, "occupancy_receipt_sha256"),
        "Azure account still has conflicting compute",
    )
    _require(
        canonical_health.get("schema_name")
        == "engineering-scope-guard.canonical-repository-health"
        and canonical_health.get("status") == "pass"
        and canonical_health.get("repository")
        == "cagdasyurekli/engineering-scope-guard"
        and canonical_health.get("default_branch") == "main"
        and canonical_health.get("canonical_commit")
        == "a62c7a74637c7ce9cfb9d7b3414de36ac56c27e9"
        and canonical_health.get("repository_public") is True
        and canonical_health.get("main_ruleset_active") is True
        and canonical_health.get("ci_passed") is True
        and canonical_health.get("codeql_passed") is True
        and canonical_health.get("open_codeql_alerts") == 0
        and _self_hash(canonical_health, "canonical_health_sha256"),
        "canonical repository health gate failed",
    )
    launches = stability.get("launches")
    _require(isinstance(launches, list), "stability launches are absent")
    passing = {
        effort: [
            item for item in launches
            if item.get("effort") == effort and item.get("status") == "pass"
        ]
        for effort in ("low", "medium")
    }
    _require(
        all(len(items) == 1 for items in passing.values())
        and len(launches) <= 4
        and preflight.get("qualified_independent_clusters", 0) >= 10
        and preflight.get("prior_subject_invocation_starts") == 0
        and preflight.get("selection_was_outcome_blind") is True,
        "scientific-integrity prerequisites are not intact",
    )
    evidence = {
        "low_contentless_launch": stability["state_sha256"],
        "medium_contentless_launch": stability["state_sha256"],
        "treatment_clean_profiles": launch_contract["treatment_diff_sha256"],
        "runtime_identity_pinned": runtime["receipt_sha256"],
        "runtime_sentinel_stable": preflight["runtime_sentinel_identity_sha256"],
        "qualified_pool": preflight["population_selection_sha256"],
        "evaluator_source_pinned": preflight["evaluator_identity_sha256"],
        "azure_evaluator_operational": azure_readiness[
            "azure_evaluator_receipt_sha256"
        ],
        "campaign_clock_operational": campaign_clock["receipt_sha256"],
        "subject_quota_sufficient": quota["quota_gate_sha256"],
        "canonical_repository_healthy": canonical_health[
            "canonical_health_sha256"
        ],
        "scientific_integrity_clear": digest(
            {
                "preflight_sha256": preflight["preflight_sha256"],
                "occupancy_receipt_sha256": azure_occupancy[
                    "occupancy_receipt_sha256"
                ],
                "unresolved_defects": [],
            }
        ),
    }
    _require(tuple(evidence) == GATES, "final readiness gate order drifted")
    body = {
        "schema_name": SCHEMA_NAME,
        "schema_version": 1,
        "status": "pass",
        "gates": {
            name: {"status": "pass", "evidence_sha256": evidence[name]}
            for name in GATES
        },
        "bindings": {
            "preflight_sha256": preflight["preflight_sha256"],
            "runtime_receipt_sha256": runtime["receipt_sha256"],
            "launch_surface_contract_sha256": launch_contract["contract_sha256"],
            "stability_state_sha256": stability["state_sha256"],
            "quota_gate_sha256": quota["quota_gate_sha256"],
            "azure_pool_receipt_sha256": azure_pool["pool_receipt_sha256"],
            "azure_readiness_receipt_sha256": azure_readiness[
                "azure_evaluator_receipt_sha256"
            ],
            "campaign_clock_receipt_sha256": campaign_clock["receipt_sha256"],
            "azure_occupancy_receipt_sha256": azure_occupancy[
                "occupancy_receipt_sha256"
            ],
            "canonical_health_sha256": canonical_health[
                "canonical_health_sha256"
            ],
        },
        "unresolved_scientific_integrity_defects": [],
        "cell_1_authorized": True,
    }
    return {**body, "final_readiness_sha256": digest(body)}


def validate(value: dict[str, Any]) -> None:
    _require(
        value.get("schema_name") == SCHEMA_NAME
        and value.get("schema_version") == 1
        and value.get("status") == "pass"
        and value.get("cell_1_authorized") is True
        and value.get("unresolved_scientific_integrity_defects") == []
        and isinstance(value.get("gates"), dict)
        and set(value["gates"]) == set(GATES)
        and all(
            value["gates"][name].get("status") == "pass"
            and isinstance(value["gates"][name].get("evidence_sha256"), str)
            and len(value["gates"][name]["evidence_sha256"]) == 64
            for name in GATES
        )
        and _self_hash(value, "final_readiness_sha256"),
        "final readiness manifest is invalid",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "preflight", "runtime", "launch_contract", "stability", "quota",
        "azure_pool", "azure_readiness", "campaign_clock", "azure_occupancy",
        "canonical_health",
    ):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = {
        name: _read(getattr(args, name))
        for name in (
            "preflight", "runtime", "launch_contract", "stability", "quota",
            "azure_pool", "azure_readiness", "campaign_clock", "azure_occupancy",
            "canonical_health",
        )
    }
    result = build(**values)
    validate(result)
    _require(".local" in args.output.parts, "final readiness must remain below .local")
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_bytes(canonical_bytes(result))
    args.output.chmod(0o600)
    print(json.dumps({"status": "pass", "final_readiness_sha256": result["final_readiness_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
