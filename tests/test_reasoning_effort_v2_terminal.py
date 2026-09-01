from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engineering_scope_guard.pilot_contract import digest
from engineering_scope_guard.evaluator_stable_qualification import seal_receipt
from engineering_scope_guard.reasoning_effort_v2 import build_contract, build_private_pool
from engineering_scope_guard.reasoning_effort_v2_analysis import (
    analyze_reasoning_effort_v2,
)
from engineering_scope_guard.reasoning_effort_v2_terminal import (
    ANALYSIS_PATH,
    CONTRACT_PATH,
    EXPERIMENT_PATHS,
    INTEGRITY_STOP_DISPOSITION,
    INSUFFICIENT_DISPOSITION,
    QUALIFICATION_SUMMARY_PATH,
    TERMINAL_ENVELOPE_PATH,
    TERMINAL_REPORT_PATH,
    TERMINAL_RESULT_PATH,
    TerminalPackageError,
    _derive_esg_gate,
    _public_safety_scan,
    build_terminal_package,
    canonical_artifact_bytes,
    validate_terminal_result,
    verify_terminal_package,
    write_terminal_package,
)
from scripts import reasoning_effort_v2_terminal as terminal_cli

# Reuse provider-free fixtures that are already independently tested by their
# owning modules.  The terminal tests build new contracts bound to their own
# qualification receipt; no tracked or private live artifact is read.
from tests.test_evaluator_stable_qualification import (
    fail_candidate,
    pass_candidate,
    receipt as qualification_receipt,
)
from tests.test_reasoning_effort_v2_analysis import (
    private_tasks,
    terminal_envelope,
    with_full_work_retry,
)


def insufficient_receipt() -> dict:
    value = qualification_receipt()
    for _ in range(9):
        pass_candidate(value)
    for _ in range(39):
        fail_candidate(value)
    return value


def ready_receipt() -> dict:
    value = qualification_receipt()
    for _ in range(16):
        pass_candidate(value)
    value["runtime_observation"]["model_catalog_fetched_at"] = (  # type: ignore[index]
        "2026-08-30T16:56:25.169118Z"
    )
    value["runtime_observation"]["model_catalog_sha256"] = "a" * 64  # type: ignore[index]
    seal_receipt(value)
    return value


def integrity_stop_receipt(qualification: dict) -> dict:
    expected = qualification["runtime_observation"]
    observed = deepcopy(expected)
    observed["model_catalog_fetched_at"] = "2026-08-31T11:57:25.817632Z"
    observed["model_catalog_sha256"] = "b" * 64
    body = {
        "schema_name": (
            "engineering-scope-guard.reasoning-effort-v2-pre-freeze-terminal"
        ),
        "schema_version": 1,
        "status": "terminal",
        "classification": "runtime_identity_mismatch_before_contract_freeze",
        "qualification_state_sha256": qualification["state_sha256"],
        "storage_authority_sha256": "a" * 64,
        "expected_runtime_sha256": digest(expected),
        "observed_runtime_sha256": digest(observed),
        "expected_model_catalog_sha256": expected["model_catalog_sha256"],
        "observed_model_catalog_sha256": observed["model_catalog_sha256"],
        "changed_fields": ["model_catalog_fetched_at", "model_catalog_sha256"],
        "subject_invocation_starts": 0,
        "contract_frozen": False,
        "provider_calls_performed": False,
        "evaluator_invocations_performed": False,
        "task_material_accessed": False,
    }
    return {**body, "receipt_sha256": digest(body)}


def experiment_evidence(
    *, invalid: bool = False, canary_allowance: int = 0, primary_count: int = 12,
    maximum_subject_starts: int = 56,
) -> tuple[dict, dict, dict, dict]:
    receipt = ready_receipt()
    pool = build_private_pool(
        private_tasks(primary_count), private_tasks(4, offset=primary_count)
    )
    runtime = receipt["runtime_observation"]
    contract = build_contract(
        pool,
        model=runtime["model"],
        codex_version=runtime["codex_version"],
        runtime_identity="fixture-runtime-identity",
        source_identity="fixture-source-identity",
        qualification_receipt_sha256=receipt["state_sha256"],
        evaluator_identity="fixture-evaluator-identity",
        image_pool_identity="c" * 64,
        tool_configuration_identity="fixture-tool-identity",
        maximum_contentless_canary_subject_invocation_starts=canary_allowance,
        maximum_subject_invocation_starts=maximum_subject_starts,
    )
    envelope = terminal_envelope(contract, invalid=invalid)
    analysis = analyze_reasoning_effort_v2(contract, envelope)
    return receipt, contract, envelope, analysis


def parsed(package: dict[Path, bytes], path: Path) -> dict:
    return json.loads(package[path])


class ReasoningEffortV2TerminalTests(unittest.TestCase):
    def test_insufficient_package_is_exact_private_safe_and_deterministic(self) -> None:
        receipt = insufficient_receipt()
        first = build_terminal_package(
            terminal_path="insufficient_population",
            qualification_receipt=receipt,
        )
        second = build_terminal_package(
            terminal_path="insufficient_population",
            qualification_receipt=deepcopy(receipt),
        )
        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {QUALIFICATION_SUMMARY_PATH, TERMINAL_RESULT_PATH, TERMINAL_REPORT_PATH},
        )
        result = parsed(first, TERMINAL_RESULT_PATH)
        validate_terminal_result(result)
        self.assertEqual(result["terminal_disposition"], INSUFFICIENT_DISPOSITION)
        self.assertFalse(result["experiment"]["started"])
        self.assertEqual(
            result["experiment"]["subject_start_accounting"],
            {
                "canary_subject_invocation_starts": 0,
                "experiment_subject_invocation_starts": 0,
                "total_subject_invocation_starts": 0,
            },
        )
        self.assertIsNone(result["primary_outcome"])
        self.assertFalse(
            result["esg_rr_002_candidate_gate"]["candidate_justified"]
        )
        self.assertEqual(
            result["esg_rr_002_candidate_gate"]["decision"], "not_applicable"
        )
        report = first[TERMINAL_REPORT_PATH].decode()
        for heading in (
            "## Evaluator qualification",
            "## Experiment",
            "## Primary outcome",
            "## Work",
            "## Falsification",
            "## Decision",
            "## Repository",
            "## Next boundary",
        ):
            self.assertIn(heading, report)
        self.assertIn("Attempted candidates: 48", report)
        self.assertIn("No subject experiment started", report)
        rendered = b"\n".join(first.values()).decode()
        self.assertNotIn("private-python", rendered)
        self.assertNotIn("private/repo", rendered)
        self.assertNotIn("private/image", rendered)
        self.assertNotIn(".local/", rendered)

    def test_insufficient_rejects_in_progress_and_any_experiment_artifact(self) -> None:
        in_progress = qualification_receipt()
        with self.assertRaisesRegex(TerminalPackageError, "in-progress"):
            build_terminal_package(
                terminal_path="insufficient_population",
                qualification_receipt=in_progress,
            )
        receipt, contract, envelope, analysis = experiment_evidence()
        with self.assertRaisesRegex(TerminalPackageError, "forbids"):
            build_terminal_package(
                terminal_path="insufficient_population",
                qualification_receipt=insufficient_receipt(),
                contract=contract,
                terminal_envelope=envelope,
                analysis=analysis,
            )
        with self.assertRaisesRegex(TerminalPackageError, "in-progress"):
            build_terminal_package(
                terminal_path="experiment_terminal",
                qualification_receipt=in_progress,
                contract=contract,
                terminal_envelope=envelope,
                analysis=analysis,
            )
        self.assertEqual(receipt["status"], "stable_pool_ready")

    def test_pre_subject_integrity_stop_is_common_only_and_claim_safe(self) -> None:
        receipt = ready_receipt()
        stop = integrity_stop_receipt(receipt)
        package = build_terminal_package(
            terminal_path="pre_subject_integrity_stop",
            qualification_receipt=receipt,
            integrity_stop=stop,
        )
        self.assertEqual(
            set(package),
            {QUALIFICATION_SUMMARY_PATH, TERMINAL_RESULT_PATH, TERMINAL_REPORT_PATH},
        )
        result = parsed(package, TERMINAL_RESULT_PATH)
        validate_terminal_result(result)
        self.assertEqual(result["terminal_disposition"], INTEGRITY_STOP_DISPOSITION)
        self.assertEqual(result["qualification"]["qualified_independent_clusters"], 16)
        self.assertFalse(result["experiment"]["started"])
        self.assertEqual(result["experiment"]["frozen_cells"], 0)
        self.assertEqual(result["experiment"]["evaluator_invocation_starts"], 0)
        self.assertEqual(
            result["integrity_stop"]["private_stop_receipt_sha256"],
            stop["receipt_sha256"],
        )
        self.assertIsNone(result["primary_outcome"])
        self.assertIsNone(result["work_sha256"])
        self.assertIsNone(result["falsification_sha256"])
        self.assertEqual(
            result["esg_rr_002_candidate_gate"]["decision"], "not_applicable"
        )
        report = package[TERMINAL_REPORT_PATH].decode()
        self.assertIn("stable qualification gate passed", report)
        self.assertIn("not a frozen experimental population", report)
        self.assertIn("No LOW-versus-MEDIUM outcome exists", report)

    def test_pre_subject_integrity_stop_rejects_missing_or_tampered_receipt(self) -> None:
        receipt = ready_receipt()
        with self.assertRaisesRegex(TerminalPackageError, "requires only"):
            build_terminal_package(
                terminal_path="pre_subject_integrity_stop",
                qualification_receipt=receipt,
            )
        stop = integrity_stop_receipt(receipt)
        stop["observed_model_catalog_sha256"] = stop[
            "expected_model_catalog_sha256"
        ]
        with self.assertRaisesRegex(TerminalPackageError, "incomplete"):
            build_terminal_package(
                terminal_path="pre_subject_integrity_stop",
                qualification_receipt=receipt,
                integrity_stop=stop,
            )

    def test_experiment_package_derives_counts_analysis_and_esg_gate(self) -> None:
        receipt, contract, envelope, analysis = experiment_evidence()
        package = build_terminal_package(
            terminal_path="experiment_terminal",
            qualification_receipt=receipt,
            contract=contract,
            terminal_envelope=envelope,
            analysis=analysis,
            repository_workflow_authorized=True,
            next_boundary="authorize_second_experiment",
        )
        self.assertEqual(
            set(package),
            {
                QUALIFICATION_SUMMARY_PATH,
                TERMINAL_RESULT_PATH,
                TERMINAL_REPORT_PATH,
                CONTRACT_PATH,
                TERMINAL_ENVELOPE_PATH,
                ANALYSIS_PATH,
            },
        )
        result = parsed(package, TERMINAL_RESULT_PATH)
        validate_terminal_result(result)
        self.assertEqual(result["experiment"]["frozen_cells"], 48)
        self.assertEqual(result["experiment"]["attempt_records"], 48)
        self.assertEqual(
            result["experiment"]["subject_start_accounting"],
            {
                "canary_subject_invocation_starts": 0,
                "experiment_subject_invocation_starts": 48,
                "total_subject_invocation_starts": 48,
            },
        )
        self.assertEqual(result["experiment"]["evaluator_invocation_starts"], 48)
        self.assertEqual(result["experiment"]["missing_cells"], 0)
        self.assertEqual(result["experiment"]["alternates_activated"], 0)
        self.assertEqual(
            result["scientific_disposition"],
            analysis["scientific_disposition"]["label"],
        )
        self.assertEqual(
            result["work_sha256"],
            analysis["esg_rr_002_usefulness"]["retry_inclusive_work_result"][
                "sha256"
            ],
        )
        self.assertEqual(
            result["falsification_sha256"],
            analysis["esg_rr_002_usefulness"][
                "retry_inclusive_falsification_result"
            ]["sha256"],
        )
        self.assertTrue(
            result["esg_rr_002_candidate_gate"]["candidate_justified"]
        )
        self.assertEqual(
            result["esg_rr_002_candidate_gate"]["policy_sha256"],
            contract["esg_rr_002_gate_policy"]["policy_sha256"],
        )
        self.assertEqual(
            set(result["esg_rr_002_candidate_gate"]["criteria"]),
            {
                "methodological_integrity",
                "sufficient_admissible_data",
                "independence_adequate",
                "uncertainty_informative",
                "evaluator_valid",
                "usefulness_threshold_met",
                "disposition_permitted",
                "significance_or_equivalence_test_not_used",
                "materially_adds_to_existing_evidence",
            },
        )
        self.assertEqual(package[CONTRACT_PATH], canonical_artifact_bytes(contract))
        self.assertEqual(
            package[TERMINAL_ENVELOPE_PATH], canonical_artifact_bytes(envelope)
        )
        self.assertEqual(package[ANALYSIS_PATH], canonical_artifact_bytes(analysis))

    def test_experiment_accepts_frozen_subset_of_qualified_population(self) -> None:
        receipt, contract, envelope, analysis = experiment_evidence(
            primary_count=10, maximum_subject_starts=48
        )
        package = build_terminal_package(
            terminal_path="experiment_terminal",
            qualification_receipt=receipt,
            contract=contract,
            terminal_envelope=envelope,
            analysis=analysis,
            repository_workflow_authorized=True,
            next_boundary="authorize_second_experiment",
        )
        result = parsed(package, TERMINAL_RESULT_PATH)
        self.assertEqual(result["qualification"]["qualified_independent_clusters"], 16)
        self.assertEqual(result["experiment"]["frozen_cells"], 40)
        self.assertEqual(result["experiment"]["subject_invocation_start_cap"], 48)
        self.assertTrue(result["claim_boundaries"]["pull_request_authorized"])
        self.assertEqual(result["next_boundary"], "authorize_second_experiment")

    def test_experiment_uses_actual_envelope_canary_count(self) -> None:
        receipt, contract, envelope, analysis = experiment_evidence(canary_allowance=1)
        package = build_terminal_package(
            terminal_path="experiment_terminal",
            qualification_receipt=receipt,
            contract=contract,
            terminal_envelope=envelope,
            analysis=analysis,
        )
        result = parsed(package, TERMINAL_RESULT_PATH)
        experiment = result["experiment"]
        self.assertEqual(
            experiment["subject_start_accounting"],
            {
                "canary_subject_invocation_starts": 1,
                "experiment_subject_invocation_starts": 48,
                "total_subject_invocation_starts": 49,
            },
        )
        self.assertIn(
            "Actual contentless-canary subject invocation starts: 1",
            package[TERMINAL_REPORT_PATH].decode(),
        )

    def test_experiment_package_binds_retry_inclusive_work_and_diagnostics(self) -> None:
        receipt, contract, envelope, _ = experiment_evidence()
        envelope = with_full_work_retry(envelope)
        analysis = analyze_reasoning_effort_v2(contract, envelope)
        package = build_terminal_package(
            terminal_path="experiment_terminal",
            qualification_receipt=receipt,
            contract=contract,
            terminal_envelope=envelope,
            analysis=analysis,
        )
        result = parsed(package, TERMINAL_RESULT_PATH)
        self.assertEqual(result["experiment"]["attempt_records"], 49)
        self.assertEqual(
            result["experiment"]["subject_start_accounting"][
                "experiment_subject_invocation_starts"
            ],
            49,
        )
        self.assertIn(
            "All-attempt work, discarded or infrastructure-invalid work, retry",
            package[TERMINAL_REPORT_PATH].decode(),
        )

    def test_invalid_experiment_is_not_an_esg_rr_002_candidate(self) -> None:
        receipt, contract, envelope, analysis = experiment_evidence(invalid=True)
        package = build_terminal_package(
            terminal_path="experiment_terminal",
            qualification_receipt=receipt,
            contract=contract,
            terminal_envelope=envelope,
            analysis=analysis,
        )
        result = parsed(package, TERMINAL_RESULT_PATH)
        self.assertEqual(
            result["scientific_disposition"], "EXPERIMENT INVALID / TERMINATED"
        )
        self.assertFalse(
            result["esg_rr_002_candidate_gate"]["candidate_justified"]
        )
        self.assertFalse(
            result["esg_rr_002_candidate_gate"]["criteria"][
                "disposition_permitted"
            ]
        )
        self.assertEqual(
            result["experiment"]["subject_start_accounting"],
            {
                "canary_subject_invocation_starts": 0,
                "experiment_subject_invocation_starts": 4,
                "total_subject_invocation_starts": 4,
            },
        )

    def test_esg_gate_uses_supplied_contract_policy_without_hidden_thresholds(self) -> None:
        _, contract, _, analysis = experiment_evidence()
        policy = deepcopy(contract["esg_rr_002_gate_policy"])
        policy["minimum_independent_admissible_clusters"] = 13
        policy["policy_sha256"] = digest(
            {key: value for key, value in policy.items() if key != "policy_sha256"}
        )
        gate = _derive_esg_gate(analysis, policy)
        self.assertEqual(gate["policy_sha256"], policy["policy_sha256"])
        self.assertFalse(gate["criteria"]["sufficient_admissible_data"])
        self.assertFalse(gate["criteria"]["independence_adequate"])
        self.assertFalse(gate["criteria"]["materially_adds_to_existing_evidence"])
        self.assertFalse(gate["candidate_justified"])

    def test_esg_gate_recomputes_usefulness_and_prior_evidence_comparison(self) -> None:
        _, contract, _, analysis = experiment_evidence()
        policy = contract["esg_rr_002_gate_policy"]
        self.assertEqual(
            set(analysis["esg_rr_002_usefulness"]), set(policy["usefulness_requires"])
        )
        self.assertTrue(_derive_esg_gate(analysis, policy)["candidate_justified"])

        forged_usefulness = deepcopy(analysis)
        forged_usefulness["esg_rr_002_usefulness"][
            "retry_inclusive_work_result"
        ]["sha256"] = "0" * 64
        forged_gate = _derive_esg_gate(forged_usefulness, policy)
        self.assertFalse(forged_gate["criteria"]["usefulness_threshold_met"])
        self.assertFalse(forged_gate["candidate_justified"])

        forged_prior = deepcopy(analysis)
        forged_prior["prior_evidence_comparison"]["prior_evidence_gap"] = "drift"
        prior_gate = _derive_esg_gate(forged_prior, policy)
        self.assertFalse(
            prior_gate["criteria"]["materially_adds_to_existing_evidence"]
        )
        self.assertFalse(prior_gate["candidate_justified"])

    def test_analysis_and_qualification_binding_mismatches_fail_closed(self) -> None:
        receipt, contract, envelope, analysis = experiment_evidence()
        forged_analysis = deepcopy(analysis)
        forged_analysis["scientific_disposition"]["label"] = "LOW FAVORED"
        forged_analysis["analysis_sha256"] = digest(
            {key: value for key, value in forged_analysis.items() if key != "analysis_sha256"}
        )
        with self.assertRaisesRegex(TerminalPackageError, "does not regenerate"):
            build_terminal_package(
                terminal_path="experiment_terminal",
                qualification_receipt=receipt,
                contract=contract,
                terminal_envelope=envelope,
                analysis=forged_analysis,
            )
        other = ready_receipt()
        other["state_sha256"] = "0" * 64
        with self.assertRaisesRegex(TerminalPackageError, "qualification receipt is invalid"):
            build_terminal_package(
                terminal_path="experiment_terminal",
                qualification_receipt=other,
                contract=contract,
                terminal_envelope=envelope,
                analysis=analysis,
            )

    def test_write_verify_readback_and_drift_detection_for_both_paths(self) -> None:
        packages = [
            build_terminal_package(
                terminal_path="insufficient_population",
                qualification_receipt=insufficient_receipt(),
            )
        ]
        receipt, contract, envelope, analysis = experiment_evidence()
        packages.append(
            build_terminal_package(
                terminal_path="experiment_terminal",
                qualification_receipt=receipt,
                contract=contract,
                terminal_envelope=envelope,
                analysis=analysis,
            )
        )
        for package in packages:
            with self.subTest(count=len(package)), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                write_terminal_package(root, package)
                verify_terminal_package(root, package)
                target = root / TERMINAL_RESULT_PATH
                target.write_bytes(target.read_bytes() + b" ")
                with self.assertRaisesRegex(TerminalPackageError, "bytes drifted"):
                    verify_terminal_package(root, package)

    def test_insufficient_write_refuses_preexisting_experiment_artifact(self) -> None:
        package = build_terminal_package(
            terminal_path="insufficient_population",
            qualification_receipt=insufficient_receipt(),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / CONTRACT_PATH
            path.parent.mkdir(parents=True)
            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(TerminalPackageError, "pre-existing"):
                write_terminal_package(root, package)

    def test_insufficient_verify_rejects_broken_experiment_symlink(self) -> None:
        package = build_terminal_package(
            terminal_path="insufficient_population",
            qualification_receipt=insufficient_receipt(),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_terminal_package(root, package)
            path = root / CONTRACT_PATH
            path.symlink_to(root / "missing-contract.json")
            self.assertFalse(path.exists())
            self.assertTrue(path.is_symlink())
            with self.assertRaisesRegex(
                TerminalPackageError, "contains experiment artifacts"
            ):
                verify_terminal_package(root, package)

    def test_write_rejects_extra_paths_and_symlink_escape(self) -> None:
        package = build_terminal_package(
            terminal_path="insufficient_population",
            qualification_receipt=insufficient_receipt(),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            extra = {**package, Path("extra.json"): b"{}\n"}
            with self.assertRaisesRegex(TerminalPackageError, "file set drifted"):
                write_terminal_package(root, extra)
            root.mkdir()
            outside = Path(directory) / "outside"
            outside.mkdir()
            (root / "experiment").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(TerminalPackageError, "escapes root"):
                write_terminal_package(root, package)
            self.assertEqual(list(outside.iterdir()), [])

    def test_canonical_json_rejects_nonfinite_numbers(self) -> None:
        with self.assertRaises(ValueError):
            canonical_artifact_bytes({"value": float("nan")})

    def test_public_safety_rejects_identifiers_paths_output_and_credentials(self) -> None:
        unsafe = (
            {"task_id": "x"},
            {"task": "x"},
            {"task_text": "x"},
            {"repo": "owner/name"},
            {"repository_url": "https://example.invalid/private"},
            {"image": "private-image"},
            {"image_ref": "private-image"},
            {"resolved_image": "image"},
            {"body": "private body"},
            {"body_text": "private body"},
            {"prompt": "private prompt"},
            {"prompt_payload": "private prompt"},
            {"patch": "private patch"},
            {"patch_diff": "private patch"},
            {"stdout": "content"},
            {"raw_trace": "content"},
            {"provider_output": "content"},
            {"path": "/Users/private/result"},
            {"path": ".local"},
            {"path": "private/.local/result"},
            {"path": "C:\\private\\result"},
            {"path": "file:///private/result"},
            {"path": "~/private/result"},
            {"path": "safe/../private/result"},
            {"credentials": "secret"},
            {"service_password": "secret"},
            {"client_secret": "secret"},
        )
        for value in unsafe:
            with self.subTest(value=value), self.assertRaises(TerminalPackageError):
                _public_safety_scan(value)
        _public_safety_scan(
            {
                "task_commitment_sha256": "a" * 64,
                "repository_commitment_sha256": "b" * 64,
                "subject_stdout_sha256": "c" * 64,
                "patch_sha256": "d" * 64,
                "ownership_token_sha256": "e" * 64,
                "image_pool_identity": "fixture-image-identity",
                "primary_task_count": 12,
                "path": "config.local.toml",
                "host": "worker.localhost",
            }
        )

    def test_report_numbers_are_bound_to_terminal_result_and_analysis(self) -> None:
        receipt, contract, envelope, analysis = experiment_evidence()
        package = build_terminal_package(
            terminal_path="experiment_terminal",
            qualification_receipt=receipt,
            contract=contract,
            terminal_envelope=envelope,
            analysis=analysis,
        )
        result = parsed(package, TERMINAL_RESULT_PATH)
        report = package[TERMINAL_REPORT_PATH].decode()
        low = result["primary_outcome"]["low"]
        medium = result["primary_outcome"]["medium"]
        self.assertIn(
            f"LOW acceptance: {low['accepted']}/{low['admissible_cells']}", report
        )
        self.assertIn(
            f"MEDIUM acceptance: {medium['accepted']}/{medium['admissible_cells']}",
            report,
        )
        self.assertIn(result["scientific_disposition"], report)
        self.assertIn(result["terminal_result_sha256"], report)
        self.assertIn("Exactly one action requires user authorization", report)
        self.assertIn(
            "authorize_private_canonical_branch_push", report
        )
        self.assertFalse(result["claim_boundaries"]["pull_request_authorized"])
        self.assertFalse(result["claim_boundaries"]["merge_authorized"])

    def test_cli_build_and_verify_round_trip_without_providers(self) -> None:
        receipt = insufficient_receipt()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt_path = root / "qualification.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            arguments = [
                "reasoning_effort_v2_terminal.py",
                "build",
                "--terminal-path",
                "insufficient_population",
                "--qualification-receipt",
                str(receipt_path),
                "--output-root",
                str(root),
            ]
            with patch("sys.argv", arguments):
                self.assertEqual(terminal_cli.main(), 0)
            arguments[1] = "verify"
            with patch("sys.argv", arguments):
                self.assertEqual(terminal_cli.main(), 0)
            self.assertTrue((root / TERMINAL_RESULT_PATH).is_file())
            self.assertFalse(any((root / path).exists() for path in EXPERIMENT_PATHS))


if __name__ == "__main__":
    unittest.main()
