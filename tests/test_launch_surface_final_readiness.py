from __future__ import annotations

from copy import deepcopy
import unittest

from engineering_scope_guard.pilot_contract import digest
from scripts import launch_surface_final_readiness as readiness


def _seal(body: dict, field: str) -> dict:
    return {**body, field: digest(body)}


class LaunchSurfaceFinalReadinessTests(unittest.TestCase):
    def inputs(self) -> dict:
        runtime = _seal(
            {
                "codex_binary_sha256": "1" * 64,
                "model": "gpt-5.6-sol",
            },
            "receipt_sha256",
        )
        launch = _seal(
            {"treatment_diff_sha256": "2" * 64}, "contract_sha256"
        )
        stability = _seal(
            {
                "launches": [
                    {"effort": "low", "status": "pass"},
                    {"effort": "medium", "status": "pass"},
                ]
            },
            "state_sha256",
        )
        preflight = _seal(
            {
                "ready_for_external_gates": True,
                "qualified_independent_clusters": 16,
                "prior_subject_invocation_starts": 0,
                "selection_was_outcome_blind": True,
                "runtime_sentinel_identity_sha256": "3" * 64,
                "population_selection_sha256": "4" * 64,
                "evaluator_identity_sha256": "5" * 64,
            },
            "preflight_sha256",
        )
        quota = _seal(
            {
                "schema_name": "engineering-scope-guard.launch-surface-subject-quota-gate",
                "status": "pass",
                "operational_headroom_percent": 79,
                "minimum_operational_headroom_percent": 75,
                "planned_subject_cells": 40,
                "maximum_subject_attempts": 48,
                "codex_binary_sha256": "1" * 64,
            },
            "quota_gate_sha256",
        )
        pool = _seal(
            {
                "schema_name": "engineering-scope-guard.azure-evaluator-pool",
                "status": "ready",
                "pool_id": "esg-rr002-evaluator-pool",
                "evaluator_revision": "eval-rev",
                "repolaunch_revision": "launch-rev",
                "worker_image_identity": "image",
            },
            "pool_receipt_sha256",
        )
        azure = _seal(
            {
                "schema_name": "engineering-scope-guard.azure-evaluator-receipt",
                "status": "pass",
                "azure_exit_code": 0,
                "azure_retry_count": 0,
                "azure_requeue_count": 0,
                "evaluator_revision": "eval-rev",
                "repolaunch_revision": "launch-rev",
                "worker_image_identity": "image",
            },
            "azure_evaluator_receipt_sha256",
        )
        clock = _seal(
            {
                "schema_name": "engineering-scope-guard.campaign-clock",
                "hard_max_duration_ns": 10,
                "accumulated_previous_ns": 0,
                "completed_segments": [],
                "current_segment": {},
            },
            "receipt_sha256",
        )
        occupancy = _seal(
            {
                "schema_name": "engineering-scope-guard.azure-evaluator-occupancy",
                "status": "pass",
                "conflicting_pools": [],
                "conflicting_jobs": [],
                "conflicting_active_nodes": 0,
                "own_pool_id": "esg-rr002-evaluator-pool",
            },
            "occupancy_receipt_sha256",
        )
        health = _seal(
            {
                "schema_name": "engineering-scope-guard.canonical-repository-health",
                "status": "pass",
                "repository": "cagdasyurekli/engineering-scope-guard",
                "default_branch": "main",
                "canonical_commit": "a62c7a74637c7ce9cfb9d7b3414de36ac56c27e9",
                "repository_public": True,
                "main_ruleset_active": True,
                "ci_passed": True,
                "codeql_passed": True,
                "open_codeql_alerts": 0,
            },
            "canonical_health_sha256",
        )
        return {
            "preflight": preflight,
            "runtime": runtime,
            "launch_contract": launch,
            "stability": stability,
            "quota": quota,
            "azure_pool": pool,
            "azure_readiness": azure,
            "campaign_clock": clock,
            "azure_occupancy": occupancy,
            "canonical_health": health,
        }

    def test_all_twelve_gates_are_bound_and_self_hashed(self) -> None:
        manifest = readiness.build(**self.inputs())
        readiness.validate(manifest)
        self.assertEqual(set(manifest["gates"]), set(readiness.GATES))
        self.assertEqual(len(manifest["gates"]), 12)
        self.assertTrue(manifest["cell_1_authorized"])

    def test_failed_or_drifted_external_evidence_is_rejected(self) -> None:
        values = self.inputs()
        values["azure_readiness"]["azure_retry_count"] = 1
        with self.assertRaisesRegex(ValueError, "Azure evaluator readiness"):
            readiness.build(**values)

        values = self.inputs()
        values["quota"] = deepcopy(values["quota"])
        values["quota"]["operational_headroom_percent"] = 20
        with self.assertRaisesRegex(ValueError, "quota"):
            readiness.build(**values)


if __name__ == "__main__":
    unittest.main()
