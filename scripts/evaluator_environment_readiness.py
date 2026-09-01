#!/usr/bin/env python3
"""Build the private 15-gate readiness receipt without freezing subjects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engineering_scope_guard.campaign_clock import _validate_receipt as validate_clock
from engineering_scope_guard.evaluator_environment import digest, validate_receipt
from engineering_scope_guard.evaluator_environment_readiness import (
    GATE_NAMES,
    build_readiness,
)
from engineering_scope_guard.evaluator_stable_qualification import (
    validate_receipt as validate_qualification,
)
from engineering_scope_guard.launch_surface import validate_launch_contract
from engineering_scope_guard.pilot_contract import canonical_bytes
from engineering_scope_guard.runtime_lock import sentinel
try:
    from scripts.evaluator_environment_lock import write_private
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from evaluator_environment_lock import write_private


def _read(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"private readiness input is not an object: {path}")
    return value


def _self_hash(value: dict, field: str) -> bool:
    body = {key: item for key, item in value.items() if key != field}
    return value.get(field) == digest(body)


def _gate(passed: bool, evidence: object) -> dict[str, str]:
    return {"status": "pass" if passed else "fail", "evidence_sha256": digest(evidence)}


def build(args: argparse.Namespace) -> dict:
    canonical = _read(args.canonical_health)
    qualification = _read(args.qualification)
    first = _read(args.environment_receipt)
    second = _read(args.second_environment_receipt)
    gold = _read(args.gold_receipt)
    clock = _read(args.campaign_clock)
    runtime = _read(args.runtime_receipt)
    launch = _read(args.launch_contract)
    quota = _read(args.quota)
    azure = _read(args.azure_state)

    validate_qualification(qualification)
    validate_receipt(first)
    validate_receipt(second)
    validate_clock(clock)
    runtime_check = sentinel(runtime)
    validate_launch_contract(launch)

    selection = qualification["selection"]
    task_count = len(selection["primary"]) + len(selection["alternates"])
    images = first["e2_images"]
    python_layer = first["e3_packages"]["python"]
    common_environment = first["global_environment_sha256"] == second["global_environment_sha256"]
    gates = {
        "public_canonical_healthy": _gate(
            canonical.get("status") == "pass"
            and _self_hash(canonical, "canonical_health_sha256"),
            canonical,
        ),
        "qualified_pool_valid": _gate(
            qualification.get("status") == "stable_pool_ready"
            and len(selection["primary"]) >= 10
            and qualification["subject_accounting"]["subject_invocation_starts"] == 0,
            {"state_sha256": qualification["state_sha256"], "task_count": task_count},
        ),
        "evaluator_source_pinned": _gate(
            bool(first["e1_source"]["revision"])
            and len(first["e1_source"]["tree_sha256"]) == 64
            and len(first["e1_source"]["lock_config_sha256"]) == 64,
            first["e1_source"],
        ),
        "evaluator_images_pinned": _gate(
            len(images) == task_count + 1
            and all("@sha256:" in image["resolved_ref"] for image in images),
            images,
        ),
        "evaluator_packages_pinned": _gate(
            len(python_layer["packages"]) > 0
            and len(first["e3_packages"]["system_packages"]) > 0,
            first["e3_packages"],
        ),
        "fresh_worker_reproducible": _gate(
            common_environment
            and first["task_environment_sha256s"] == second["task_environment_sha256s"],
            {
                "first": first["receipt_sha256"],
                "second": second["receipt_sha256"],
                "global": first["global_environment_sha256"],
            },
        ),
        "gold_preflight_successful": _gate(
            gold.get("status") == "pass"
            and gold.get("global_environment_sha256") == first["global_environment_sha256"]
            and gold.get("remaining_container_count") == 0,
            gold,
        ),
        "monotonic_campaign_clock_successful": _gate(True, clock),
        "runtime_identity_pinned": _gate(runtime_check.get("status") == "pass", runtime_check),
        "low_launch_profile_valid": _gate(
            launch["profiles"]["low"]["reasoning_effort"] == "low", launch["profiles"]["low"]
        ),
        "medium_launch_profile_valid": _gate(
            launch["profiles"]["medium"]["reasoning_effort"] == "medium",
            launch["profiles"]["medium"],
        ),
        "within_task_evaluator_identity_equal": _gate(
            common_environment and len(first["task_environment_sha256s"]) == task_count,
            first["task_environment_sha256s"],
        ),
        "sufficient_subject_quota": _gate(
            quota.get("status") == "pass"
            and quota.get("operational_headroom_percent", -1)
            >= quota.get("minimum_operational_headroom_percent", 101),
            quota,
        ),
        "no_azure_reserve_contention": _gate(
            azure.get("status") == "available"
            and azure.get("experiment_owned_active_compute") == 0,
            azure,
        ),
        "no_unresolved_scientific_integrity_defect": _gate(
            not args.scientific_defect, sorted(args.scientific_defect)
        ),
    }
    assert tuple(gates) == GATE_NAMES
    return build_readiness(gates)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-health", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--environment-receipt", type=Path, required=True)
    parser.add_argument("--second-environment-receipt", type=Path, required=True)
    parser.add_argument("--gold-receipt", type=Path, required=True)
    parser.add_argument("--campaign-clock", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--launch-contract", type=Path, required=True)
    parser.add_argument("--quota", type=Path, required=True)
    parser.add_argument("--azure-state", type=Path, required=True)
    parser.add_argument("--scientific-defect", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = build(args)
    write_private(args.output, canonical_bytes(receipt))
    print(json.dumps({
        "status": receipt["status"],
        "subject_freeze_authorized": receipt["subject_freeze_authorized"],
        "failed_gates": receipt["failed_gates"],
        "readiness_sha256": receipt["readiness_sha256"],
    }, sort_keys=True))
    return 0 if receipt["subject_freeze_authorized"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
