from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from engineering_scope_guard.evidence_conditioned_analysis import analyze
from engineering_scope_guard.evidence_conditioned_execution import (
    TREATMENT_PATH,
    build_contract,
    build_launch_request,
    execute_attempt_durably,
    initialize_ledger,
)
from engineering_scope_guard.pilot_runner import EvaluatorResult, SubjectResult
from engineering_scope_guard.pilot_v3 import append_event

ROOT = Path(__file__).resolve().parents[1]


class AnalysisFixtureBackend:
    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        roots = {name: Path(value) for name, value in request["isolation_roots"].items()}
        for path in roots.values():
            path.mkdir(parents=True, exist_ok=False)
        credential = Path(request["credential_copy_identity"])
        credential.write_text("fixture", encoding="utf-8")
        return {
            "started_at": "2026-08-29T00:00:00+00:00",
            "ended_at": "2026-08-29T00:01:00+00:00",
            "credential": credential,
            "raw": roots["raw"],
            "derived": roots["derived"],
        }

    def cleanup(self, prepared: dict[str, Any]) -> None:
        prepared["credential"].unlink(missing_ok=True)

    def _subject(self, prepared: dict[str, Any], phase: str) -> SubjectResult:
        trace = prepared["raw"] / f"{phase}.jsonl"
        trace.write_text("", encoding="utf-8")
        return SubjectResult(
            exit_code=0,
            timed_out=False,
            session_id="session-1",
            usage={
                "input_tokens": 10,
                "cached_input_tokens": 4,
                "output_tokens": 2,
                "reasoning_output_tokens": 1,
            },
            trace_reference=str(trace),
        )

    def run_ordinary(self, request: dict[str, Any], prepared: dict[str, Any]) -> SubjectResult:
        return self._subject(prepared, "ordinary")

    def run_treatment(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        treatment: bytes,
        session_id: str,
    ) -> SubjectResult:
        return self._subject(prepared, "treatment")

    def run_correction(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        feedback: tuple[str, ...],
        session_id: str,
    ) -> SubjectResult:
        return self._subject(prepared, "corrective")

    def create_prediction(
        self, request: dict[str, Any], prepared: dict[str, Any]
    ) -> dict[str, Any]:
        patch = prepared["derived"] / "prediction.patch"
        patch.write_text("", encoding="utf-8")
        return {"patch_sha256": hashlib.sha256(b"").hexdigest()}

    def evaluate(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        prediction: dict[str, Any],
        round_number: int,
    ) -> EvaluatorResult:
        return EvaluatorResult(
            exit_code=0,
            timed_out=False,
            resolved=True,
            failing_checks=(),
            report_reference="fixture-report.json",
            results_reference="fixture-results.json",
            report_sha256="a" * 64,
            results_sha256="b" * 64,
            official_disposition="success",
            feedback_status="not_applicable",
        )


class EvidenceConditionedAnalysisTests(unittest.TestCase):
    def build_fixture(self, state: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
        contract = build_contract(ROOT)
        ledger = state / "execution-ledger.jsonl"
        initialize_ledger(contract, ledger)
        backend = AnalysisFixtureBackend()
        treatment = (ROOT / TREATMENT_PATH).read_bytes()
        for cell in contract["schedule"]["cells"]:
            request = build_launch_request(contract, cell, state, 1)
            request["attempt_started_at"] = "2026-08-29T00:00:00+00:00"
            append_event(ledger, "attempt_started", request)
            execute_attempt_durably(contract, request, backend, ledger, treatment)
        annotations = {
            "schema_name": (
                "engineering-scope-guard.evidence-conditioned-final-scope-review-mechanism-annotations"
            ),
            "schema_version": 1,
            "contract_sha256": contract["contract_sha256"],
            "cells": {
                cell["cell_id"]: {
                    "necessary_correctness_suppression": False,
                    "evidence_supported_optional_removal_or_simplification": False,
                    "apparent_pre_activation_behavioral_effect": False,
                    "c_short_equivalent_behavior": False,
                    "broad_proof_of_minimality_search": False,
                    "evidence_references": [],
                }
                for cell in contract["schedule"]["cells"]
                if cell["arm"] == "treatment"
            },
        }
        return contract, ledger, annotations

    def test_terminal_analysis_preserves_frozen_order_cluster_unit_and_all_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            contract, ledger, annotations = self.build_fixture(Path(directory))
            result = analyze(ROOT, contract, ledger, annotations)
        self.assertEqual(
            result["reporting_order"][0], "execution_completeness_and_missingness"
        )
        self.assertEqual(result["reporting_order"][-1], "bounded_disposition")
        completeness = result["execution_completeness_and_missingness"]
        self.assertEqual(completeness["admissible_cells"], 32)
        self.assertEqual(completeness["complete_task_clusters"], 8)
        self.assertEqual(
            result["task_bootstrap_and_leave_one_task_out"]["ordered_bootstrap_resamples"],
            8**8,
        )
        self.assertFalse(
            result["task_bootstrap_and_leave_one_task_out"][
                "repetitions_are_independent_n"
            ]
        )
        self.assertEqual(len(result["retirement_gates"]), 11)
        fired = result["bounded_disposition"]["fired_gates"]
        self.assertIn("no_accepted_outcome_mechanism", fired)
        self.assertIn("wall_or_work_increase", fired)
        self.assertEqual(result["bounded_disposition"]["class"], "candidate_retired")
        self.assertFalse(result["bounded_disposition"]["confirmatory_claim"])

    def test_replicated_necessary_correctness_annotation_fires_gate_with_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            contract, ledger, annotations = self.build_fixture(Path(directory))
            first_task = next(
                cell["opaque_task_commitment"]
                for cell in contract["schedule"]["cells"]
                if cell["arm"] == "treatment"
            )
            for cell in contract["schedule"]["cells"]:
                if cell["arm"] == "treatment" and cell["opaque_task_commitment"] == first_task:
                    value = annotations["cells"][cell["cell_id"]]
                    value["necessary_correctness_suppression"] = True
                    value["evidence_references"] = ["terminal-review:fixture"]
            result = analyze(ROOT, contract, ledger, annotations)
        fired = result["bounded_disposition"]["fired_gates"]
        self.assertIn("necessary_correctness_suppression", fired)

    def test_annotations_reject_unknown_cells_and_unsupported_positive_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            contract, ledger, annotations = self.build_fixture(Path(directory))
            invalid = copy.deepcopy(annotations)
            invalid["cells"]["unknown"] = next(iter(invalid["cells"].values()))
            with self.assertRaisesRegex(Exception, "non-treatment"):
                analyze(ROOT, contract, ledger, invalid)
            invalid = copy.deepcopy(annotations)
            first = next(iter(invalid["cells"].values()))
            first["c_short_equivalent_behavior"] = True
            with self.assertRaisesRegex(Exception, "lacks evidence"):
                analyze(ROOT, contract, ledger, invalid)


if __name__ == "__main__":
    unittest.main()
