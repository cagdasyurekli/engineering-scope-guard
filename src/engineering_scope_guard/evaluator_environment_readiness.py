"""Canonical 15-gate readiness state for the environment-locked successor."""

from __future__ import annotations

from typing import Any, Mapping

from .evaluator_environment import digest


GATE_NAMES = (
    "public_canonical_healthy",
    "qualified_pool_valid",
    "evaluator_source_pinned",
    "evaluator_images_pinned",
    "evaluator_packages_pinned",
    "fresh_worker_reproducible",
    "gold_preflight_successful",
    "monotonic_campaign_clock_successful",
    "runtime_identity_pinned",
    "low_launch_profile_valid",
    "medium_launch_profile_valid",
    "within_task_evaluator_identity_equal",
    "sufficient_subject_quota",
    "no_azure_reserve_contention",
    "no_unresolved_scientific_integrity_defect",
)


def build_readiness(gates: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """Seal the exact readiness matrix without granting live authority itself."""

    if set(gates) != set(GATE_NAMES):
        raise ValueError("readiness gate set drifted")
    normalized = {}
    for name in GATE_NAMES:
        gate = gates[name]
        if set(gate) != {"status", "evidence_sha256"}:
            raise ValueError(f"readiness gate fields drifted: {name}")
        if gate["status"] not in {"pass", "fail"}:
            raise ValueError(f"readiness gate status is invalid: {name}")
        evidence = gate["evidence_sha256"]
        if not isinstance(evidence, str) or len(evidence) != 64:
            raise ValueError(f"readiness gate evidence is invalid: {name}")
        normalized[name] = dict(gate)
    failed = [name for name in GATE_NAMES if normalized[name]["status"] == "fail"]
    body = {
        "schema_name": "engineering-scope-guard.evaluator-environment-readiness",
        "schema_version": 1,
        "status": "pass" if not failed else "blocked",
        "subject_freeze_authorized": not failed,
        "gates": normalized,
        "failed_gates": failed,
    }
    return {**body, "readiness_sha256": digest(body)}


def validate_readiness(receipt: Mapping[str, Any]) -> None:
    """Reject a readiness receipt whose gate matrix or authority bit drifted."""

    expected = {
        "schema_name",
        "schema_version",
        "status",
        "subject_freeze_authorized",
        "gates",
        "failed_gates",
        "readiness_sha256",
    }
    if set(receipt) != expected:
        raise ValueError("readiness receipt fields drifted")
    rebuilt = build_readiness(receipt["gates"])
    if dict(receipt) != rebuilt:
        raise ValueError("readiness receipt identity drifted")
