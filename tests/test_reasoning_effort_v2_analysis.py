from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import canonical_bytes, digest
from engineering_scope_guard.reasoning_effort_v2 import (
    ANALYSIS_ENVELOPE_SCHEMA,
    build_contract,
    build_private_pool,
    subject_command_identity,
)
from engineering_scope_guard.reasoning_effort_v2_analysis import (
    AnalysisInputError,
    INTEGER_WORK_FIELDS,
    _unbiased_bootstrap_indices,
    analyze_reasoning_effort_v2,
)


def private_tasks(count: int, *, offset: int = 0) -> list[dict[str, str]]:
    return [
        {
            "task_id": f"never-emit-task-{number}",
            "repository": f"never-emit-owner/repo-{number}",
            "task_snapshot_sha256": f"{number % 16:x}" * 64,
            "resolved_image": f"never-emit-image-{number}@sha256:{number:064x}",
        }
        for number in range(offset + 1, offset + count + 1)
    ]


def frozen_contract(
    primary_count: int = 10,
    alternate_count: int = 1,
    *,
    canary_starts: int = 0,
) -> tuple[dict, dict]:
    pool = build_private_pool(
        private_tasks(primary_count),
        private_tasks(alternate_count, offset=primary_count),
    )
    return (
        build_contract(
            pool,
            model="fixture-model",
            codex_version="fixture-version",
            runtime_identity="fixture-runtime",
            source_identity="fixture-source",
            qualification_receipt_sha256="b" * 64,
            evaluator_identity="fixture-evaluator",
            image_pool_identity="c" * 64,
            tool_configuration_identity="fixture-tools",
            maximum_contentless_canary_subject_invocation_starts=canary_starts,
        ),
        pool,
    )


def analysis_records(contract: dict, *, direction: str = "tie") -> list[dict]:
    records = []
    for cell in contract["schedule"]["cells"]:
        accepted = (
            cell["arm"] == direction
            if direction in {"low", "medium"}
            else cell["repetition"] == 1
        )
        records.append(
            {
                "cell_id": cell["cell_id"],
                "termination": (
                    "accepted_completed" if accepted else "evaluator_test_failure"
                ),
                "timed_out": False,
                "evaluator_anomalies": [],
                "input_tokens": 100 if cell["arm"] == "low" else 120,
                "cached_input_tokens": 10,
                "cache_write_input_tokens": 5,
                "output_tokens": 20,
                "reasoning_output_tokens": 4,
                "turns": 1,
                "tool_actions": 2,
                "search_actions": 1,
                "correction_turns": 1 if cell["repetition"] == 2 else 0,
                "wall_seconds": 2.0,
            }
        )
    return records


def seal_artifact(body: dict) -> dict:
    return {**body, "receipt_sha256": digest(body)}


def artifact_byte_sha256(artifact: dict) -> str:
    return hashlib.sha256(canonical_bytes(artifact)).hexdigest()


def terminal_envelope(
    contract: dict,
    *,
    direction: str = "tie",
    activate_last: bool = False,
    invalid: bool = False,
    canary_starts: int | None = None,
) -> dict:
    projection = contract["source"]["private_pool"]
    primary = {
        item["population_slot"]: item["task_commitment_sha256"]
        for item in projection["primary_slot_commitments"]
    }
    alternate = projection["alternate_order_commitments"][0][
        "task_commitment_sha256"
    ]
    slots = []
    for slot in range(1, projection["primary_count"] + 1):
        activated = activate_last and slot == projection["primary_count"]
        commitment = alternate if activated else primary[slot]
        slots.append(
            {
                "population_slot": slot,
                "task_commitment_sha256": commitment,
                "repository_commitment_sha256": commitment,
                "alternate_activated": activated,
                "alternate_ordinal": 1 if activated else None,
            }
        )
    assignment_by_slot = {item["population_slot"]: item for item in slots}
    records = []
    for number, record in enumerate(analysis_records(contract, direction=direction), start=1):
        cell = next(
            item
            for item in contract["schedule"]["cells"]
            if item["cell_id"] == record["cell_id"]
        )
        records.append(
            {
                **record,
                "attempt": 1,
                "effective_task_commitment_sha256": assignment_by_slot[
                    cell["population_slot"]
                ]["task_commitment_sha256"],
            }
        )
    if invalid:
        records = records[:4]
    receipt_projections = []
    for record in records:
        command_sha256 = subject_command_identity(contract, record["cell_id"])
        common = {
            "schema_version": 1,
            "contract_sha256": contract["contract_sha256"],
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "cell_id": record["cell_id"],
            "attempt": record["attempt"],
            "effective_task_commitment_sha256": record[
                "effective_task_commitment_sha256"
            ],
        }
        execution = seal_artifact(
            {
                **common,
                "schema_name": "engineering-scope-guard.reasoning-effort-v2-execution-artifact",
                "subject_invocation_started": True,
                "command_sha256": command_sha256,
                "status": "returned",
                "timed_out": False,
                "subject_exit_code": 0,
                "ownership_token_sha256": "1" * 64,
                "process_identity_sha256": "2" * 64,
                "container_identity_sha256": "3" * 64,
                "subject_stdout_sha256": "4" * 64,
                "subject_stderr_sha256": "5" * 64,
                "prediction_sha256": "6" * 64,
                "patch_sha256": "7" * 64,
                "cleanup_receipt_sha256": None,
            }
        )
        evaluator = seal_artifact(
            {
                **common,
                "schema_name": "engineering-scope-guard.reasoning-effort-v2-evaluator-artifact",
                "evaluator_identity": contract["source"]["evaluator_identity"],
                "invocation_started": record["termination"] != "trajectory_timeout",
                "evaluator_command_sha256": (
                    None if record["termination"] == "trajectory_timeout" else "c" * 64
                ),
                "ownership_token_sha256": (
                    None if record["termination"] == "trajectory_timeout" else "d" * 64
                ),
                "process_identity_sha256": (
                    None if record["termination"] == "trajectory_timeout" else "e" * 64
                ),
                "container_identity_sha256": (
                    None if record["termination"] == "trajectory_timeout" else "f" * 64
                ),
                "disposition": (
                    "accepted"
                    if record["termination"] == "accepted_completed"
                    else "not_run"
                    if record["termination"] == "trajectory_timeout"
                    else "test_failure"
                ),
                "anomaly_codes": list(record["evaluator_anomalies"]),
                "evaluator_stdout_sha256": (
                    None if record["termination"] == "trajectory_timeout" else "8" * 64
                ),
                "evaluator_stderr_sha256": (
                    None if record["termination"] == "trajectory_timeout" else "9" * 64
                ),
                "report_sha256": (
                    None if record["termination"] == "trajectory_timeout" else "a" * 64
                ),
                "results_sha256": (
                    None if record["termination"] == "trajectory_timeout" else "b" * 64
                ),
            }
        )
        measurement = seal_artifact(
            {
                **common,
                "schema_name": "engineering-scope-guard.reasoning-effort-v2-measurement-artifact",
                "record_completeness": "complete",
                **{
                    field: record[field]
                    for field in (*INTEGER_WORK_FIELDS, "wall_seconds")
                },
            }
        )
        record["evaluator_receipt_sha256"] = artifact_byte_sha256(evaluator)
        receipt_body = {
            "schema_name": "engineering-scope-guard.reasoning-effort-v2-terminal-receipt",
            "schema_version": 1,
            "contract_sha256": contract["contract_sha256"],
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "cell_id": record["cell_id"],
            "attempt": record["attempt"],
            "effective_task_commitment_sha256": record[
                "effective_task_commitment_sha256"
            ],
            "subject_invocation_started": True,
            "command_sha256": command_sha256,
            "classification": record["termination"],
            "execution_receipt_sha256": artifact_byte_sha256(execution),
            "evaluator_receipt_sha256": record["evaluator_receipt_sha256"],
            "measurement_receipt_sha256": artifact_byte_sha256(measurement),
            "execution_artifact": execution,
            "evaluator_artifact": evaluator,
            "measurement_artifact": measurement,
            "analysis_record": {
                key: value
                for key, value in record.items()
                if key
                not in {
                    "attempt",
                    "effective_task_commitment_sha256",
                    "evaluator_receipt_sha256",
                }
            },
        }
        receipt = {
            **receipt_body,
            "terminal_receipt_sha256": digest(receipt_body),
        }
        record["terminal_receipt_sha256"] = receipt["terminal_receipt_sha256"]
        receipt_projections.append(receipt)
    actual_canary_starts = (
        contract["attempt_accounting"][
            "maximum_contentless_canary_subject_invocation_starts"
        ]
        if canary_starts is None
        else canary_starts
    )
    experiment_starts = sum(
        receipt["subject_invocation_started"] is True
        for receipt in receipt_projections
    )
    body = {
        "schema_name": ANALYSIS_ENVELOPE_SCHEMA,
        "schema_version": 1,
        "contract_sha256": contract["contract_sha256"],
        "private_pool_sha256": projection["private_pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "live_seal_sha256": "d" * 64,
        "ledger_binding": {
            "schema_name": "engineering-scope-guard.reasoning-effort-v2-ledger",
            "schema_version": 1,
            "event_count": 100,
            "head_event_sha256": "e" * 64,
        },
        "receipt_set_sha256": digest(
            [
                {
                    "cell_id": record["cell_id"],
                    "attempt": record["attempt"],
                    "terminal_receipt_sha256": record["terminal_receipt_sha256"],
                    "evaluator_receipt_sha256": record["evaluator_receipt_sha256"],
                }
                for record in receipt_projections
            ]
        ),
        "qualification_receipt_sha256": contract["source"][
            "qualification_receipt_sha256"
        ],
        "evaluator_identity": contract["source"]["evaluator_identity"],
        "image_pool_identity": contract["source"]["image_pool_identity"],
        "repository_commitment_source": (
            "task_commitment_sha256_under_frozen_global_repository_uniqueness"
        ),
        "protocol_valid": not invalid,
        "batch_stop_classification": "harness_failure" if invalid else None,
        "stage_1_audit_sha256": "f" * 64,
        "terminal_status": "invalid_terminated" if invalid else "complete",
        "subject_start_accounting": {
            "canary_subject_invocation_starts": actual_canary_starts,
            "experiment_subject_invocation_starts": experiment_starts,
            "total_subject_invocation_starts": (
                actual_canary_starts + experiment_starts
            ),
        },
        "effective_assignments": slots,
        "receipt_projections": receipt_projections,
        "records": records,
    }
    return {**body, "envelope_sha256": digest(body)}


def reseal(envelope: dict) -> dict:
    changed = deepcopy(envelope)
    changed["envelope_sha256"] = digest(
        {key: value for key, value in changed.items() if key != "envelope_sha256"}
    )
    return changed


def reseal_record_projection(envelope: dict, index: int) -> dict:
    """Keep one synthetic record and its full receipt projection exactly bound."""

    changed = deepcopy(envelope)
    record = changed["records"][index]
    receipt = changed["receipt_projections"][index]
    receipt["analysis_record"] = {
        key: value
        for key, value in record.items()
        if key
        not in {
            "attempt",
            "effective_task_commitment_sha256",
            "terminal_receipt_sha256",
            "evaluator_receipt_sha256",
        }
    }
    receipt["classification"] = record["termination"]
    execution = receipt["execution_artifact"]
    evaluator = receipt["evaluator_artifact"]
    measurement = receipt["measurement_artifact"]
    if record["termination"] == "trajectory_timeout":
        execution["status"] = "trajectory_timeout"
        execution["timed_out"] = True
        execution["prediction_sha256"] = None
        execution["patch_sha256"] = None
        evaluator["disposition"] = "not_run"
        evaluator["invocation_started"] = False
        for field in (
            "evaluator_command_sha256", "ownership_token_sha256",
            "process_identity_sha256", "container_identity_sha256",
            "evaluator_stdout_sha256", "evaluator_stderr_sha256",
            "report_sha256", "results_sha256",
        ):
            evaluator[field] = None
    else:
        execution["status"] = "returned"
        execution["timed_out"] = False
        execution["prediction_sha256"] = "6" * 64
        execution["patch_sha256"] = "7" * 64
        evaluator["invocation_started"] = True
        evaluator["evaluator_command_sha256"] = "c" * 64
        evaluator["ownership_token_sha256"] = "d" * 64
        evaluator["process_identity_sha256"] = "e" * 64
        evaluator["container_identity_sha256"] = "f" * 64
        evaluator["evaluator_stdout_sha256"] = "8" * 64
        evaluator["evaluator_stderr_sha256"] = "9" * 64
        evaluator["report_sha256"] = "a" * 64
        evaluator["results_sha256"] = "b" * 64
        evaluator["disposition"] = (
            "accepted"
            if record["termination"] == "accepted_completed"
            else "test_failure"
        )
    evaluator["anomaly_codes"] = list(record["evaluator_anomalies"])
    for field in (*INTEGER_WORK_FIELDS, "wall_seconds"):
        measurement[field] = record[field]
    measurement["record_completeness"] = (
        "absent"
        if all(record[field] is None for field in (*INTEGER_WORK_FIELDS, "wall_seconds"))
        else "complete"
    )
    for artifact in (execution, evaluator, measurement):
        artifact["receipt_sha256"] = digest(
            {key: value for key, value in artifact.items() if key != "receipt_sha256"}
        )
    receipt["execution_receipt_sha256"] = artifact_byte_sha256(execution)
    receipt["evaluator_receipt_sha256"] = artifact_byte_sha256(evaluator)
    receipt["measurement_receipt_sha256"] = artifact_byte_sha256(measurement)
    record["evaluator_receipt_sha256"] = receipt["evaluator_receipt_sha256"]
    receipt["terminal_receipt_sha256"] = digest(
        {
            key: value
            for key, value in receipt.items()
            if key != "terminal_receipt_sha256"
        }
    )
    record["terminal_receipt_sha256"] = receipt["terminal_receipt_sha256"]
    changed["receipt_set_sha256"] = digest(
        [
            {
                "cell_id": item["cell_id"],
                "attempt": item["attempt"],
                "terminal_receipt_sha256": item["terminal_receipt_sha256"],
                "evaluator_receipt_sha256": item["evaluator_receipt_sha256"],
            }
            for item in changed["receipt_projections"]
        ]
    )
    return reseal(changed)


def reseal_receipt(receipt: dict) -> dict:
    changed = deepcopy(receipt)
    for artifact, binding in (
        (changed["execution_artifact"], "execution_receipt_sha256"),
        (changed["evaluator_artifact"], "evaluator_receipt_sha256"),
        (changed["measurement_artifact"], "measurement_receipt_sha256"),
    ):
        artifact["receipt_sha256"] = digest(
            {key: value for key, value in artifact.items() if key != "receipt_sha256"}
        )
        changed[binding] = artifact_byte_sha256(artifact)
    changed["terminal_receipt_sha256"] = digest(
        {
            key: value
            for key, value in changed.items()
            if key != "terminal_receipt_sha256"
        }
    )
    return changed


def with_full_work_retry(envelope: dict, index: int = 0) -> dict:
    """Add full-work attempt 1 infrastructure evidence before final attempt 2."""

    changed = deepcopy(envelope)
    original = changed["receipt_projections"][index]
    final_receipt = deepcopy(original)
    final_receipt["attempt"] = 2
    for artifact in (
        final_receipt["execution_artifact"],
        final_receipt["evaluator_artifact"],
        final_receipt["measurement_artifact"],
    ):
        artifact["attempt"] = 2
    final_receipt = reseal_receipt(final_receipt)

    failed = deepcopy(original)
    failed["classification"] = "provider_api_infrastructure_failure"
    failed["analysis_record"]["termination"] = failed["classification"]
    failed["analysis_record"]["timed_out"] = False
    failed["analysis_record"]["evaluator_anomalies"] = []
    failed["execution_artifact"].update(
        {
            "status": failed["classification"],
            "timed_out": False,
            "prediction_sha256": None,
            "patch_sha256": None,
        }
    )
    failed["evaluator_artifact"].update(
        {
            "invocation_started": False,
            "evaluator_command_sha256": None,
            "ownership_token_sha256": None,
            "process_identity_sha256": None,
            "container_identity_sha256": None,
            "disposition": "not_run",
            "anomaly_codes": [],
            "evaluator_stdout_sha256": None,
            "evaluator_stderr_sha256": None,
            "report_sha256": None,
            "results_sha256": None,
        }
    )
    retry_work = {
        "input_tokens": 30,
        "cached_input_tokens": 5,
        "cache_write_input_tokens": 0,
        "output_tokens": 7,
        "reasoning_output_tokens": 2,
        "turns": 1,
        "tool_actions": 2,
        "search_actions": 1,
        "correction_turns": 1,
        "wall_seconds": 1.5,
    }
    failed["analysis_record"].update(retry_work)
    failed["measurement_artifact"].update(retry_work)
    failed = reseal_receipt(failed)

    changed["receipt_projections"][index : index + 1] = [failed, final_receipt]
    final_record = changed["records"][index]
    final_record["attempt"] = 2
    final_record["terminal_receipt_sha256"] = final_receipt[
        "terminal_receipt_sha256"
    ]
    final_record["evaluator_receipt_sha256"] = final_receipt[
        "evaluator_receipt_sha256"
    ]
    changed["receipt_set_sha256"] = digest(
        [
            {
                "cell_id": item["cell_id"],
                "attempt": item["attempt"],
                "terminal_receipt_sha256": item["terminal_receipt_sha256"],
                "evaluator_receipt_sha256": item["evaluator_receipt_sha256"],
            }
            for item in changed["receipt_projections"]
        ]
    )
    accounting = changed["subject_start_accounting"]
    accounting["experiment_subject_invocation_starts"] += 1
    accounting["total_subject_invocation_starts"] += 1
    return reseal(changed)


def reseal_receipt_artifacts_without_semantic_reconciliation(
    envelope: dict, index: int
) -> dict:
    """Reseal a synthetic projection while preserving a deliberate semantic lie."""

    changed = deepcopy(envelope)
    receipt = changed["receipt_projections"][index]
    record = changed["records"][index]
    for artifact, byte_field in (
        (receipt["execution_artifact"], "execution_receipt_sha256"),
        (receipt["evaluator_artifact"], "evaluator_receipt_sha256"),
        (receipt["measurement_artifact"], "measurement_receipt_sha256"),
    ):
        artifact["receipt_sha256"] = digest(
            {key: value for key, value in artifact.items() if key != "receipt_sha256"}
        )
        receipt[byte_field] = artifact_byte_sha256(artifact)
    record["evaluator_receipt_sha256"] = receipt["evaluator_receipt_sha256"]
    receipt["terminal_receipt_sha256"] = digest(
        {
            key: value
            for key, value in receipt.items()
            if key != "terminal_receipt_sha256"
        }
    )
    record["terminal_receipt_sha256"] = receipt["terminal_receipt_sha256"]
    changed["receipt_set_sha256"] = digest(
        [
            {
                "cell_id": item["cell_id"],
                "attempt": item["attempt"],
                "terminal_receipt_sha256": item["terminal_receipt_sha256"],
                "evaluator_receipt_sha256": item["evaluator_receipt_sha256"],
            }
            for item in changed["receipt_projections"]
        ]
    )
    return reseal(changed)


class ReasoningEffortV2AnalysisTests(unittest.TestCase):
    def test_real_contract_terminal_envelope_integration_is_dynamic(self) -> None:
        for count in (10, 11, 12):
            with self.subTest(count=count):
                contract, _ = frozen_contract(count)
                envelope = terminal_envelope(contract)
                first = analyze_reasoning_effort_v2(contract, envelope)
                second = analyze_reasoning_effort_v2(contract, envelope)
                self.assertEqual(first, second)
                self.assertEqual(first["analysis_population"]["frozen_cells"], 4 * count)
                self.assertEqual(
                    first["acceptance"]["paired_repository_clusters"][
                        "independent_repository_clusters"
                    ],
                    count,
                )
                self.assertEqual(first["analysis_sha256"], digest(
                    {key: value for key, value in first.items() if key != "analysis_sha256"}
                ))

    def test_only_exact_core_validated_envelope_is_accepted(self) -> None:
        contract, _ = frozen_contract()
        original = terminal_envelope(contract)
        for mutation in ("extra", "contract", "ledger", "receipt", "protocol"):
            changed = deepcopy(original)
            if mutation == "extra":
                changed["private_task_id"] = "leak"
            elif mutation == "contract":
                changed["contract_sha256"] = "0" * 64
            elif mutation == "ledger":
                changed["ledger_binding"]["head_event_sha256"] = "not-a-hash"
            elif mutation == "receipt":
                changed["receipt_set_sha256"] = "not-a-hash"
            else:
                changed["protocol_valid"] = False
            changed = reseal(changed)
            with self.subTest(mutation=mutation), self.assertRaises(
                ExperimentConfigurationError
            ):
                analyze_reasoning_effort_v2(contract, changed)

    def test_subject_start_accounting_is_exact_receipt_bound_and_capped(self) -> None:
        contract, _ = frozen_contract(canary_starts=1)
        original = terminal_envelope(contract, canary_starts=1)
        self.assertEqual(
            original["subject_start_accounting"],
            {
                "canary_subject_invocation_starts": 1,
                "experiment_subject_invocation_starts": 40,
                "total_subject_invocation_starts": 41,
            },
        )
        mutations = []
        for field, value in (
            ("canary_subject_invocation_starts", 0),
            ("experiment_subject_invocation_starts", 39),
            ("total_subject_invocation_starts", 42),
        ):
            changed = deepcopy(original)
            changed["subject_start_accounting"][field] = value
            mutations.append(reseal(changed))
        receipt_mismatch = deepcopy(original)
        receipt_mismatch["subject_start_accounting"][
            "experiment_subject_invocation_starts"
        ] = 39
        receipt_mismatch["subject_start_accounting"][
            "total_subject_invocation_starts"
        ] = 40
        mutations.append(reseal(receipt_mismatch))
        over_cap = deepcopy(original)
        over_cap["subject_start_accounting"] = {
            "canary_subject_invocation_starts": 1,
            "experiment_subject_invocation_starts": 56,
            "total_subject_invocation_starts": 57,
        }
        mutations.append(reseal(over_cap))
        extra_field = deepcopy(original)
        extra_field["subject_start_accounting"]["caller_claimed_starts"] = 41
        mutations.append(reseal(extra_field))
        for changed in mutations:
            with self.subTest(accounting=changed["subject_start_accounting"]):
                with self.assertRaises(ExperimentConfigurationError):
                    analyze_reasoning_effort_v2(contract, changed)

        zero_canary_contract, _ = frozen_contract(canary_starts=0)
        forbidden_canary = terminal_envelope(
            zero_canary_contract, canary_starts=1
        )
        with self.assertRaises(ExperimentConfigurationError):
            analyze_reasoning_effort_v2(zero_canary_contract, forbidden_canary)

    def test_resealed_receipts_cannot_lie_about_command_or_evaluator_outcome(self) -> None:
        contract, _ = frozen_contract()
        original = terminal_envelope(contract)

        forged_command = deepcopy(original)
        forged_command["receipt_projections"][0]["command_sha256"] = "0" * 64
        forged_command["receipt_projections"][0]["execution_artifact"][
            "command_sha256"
        ] = "0" * 64

        forged_outcome = deepcopy(original)
        forged_outcome["receipt_projections"][0]["evaluator_artifact"][
            "disposition"
        ] = "test_failure"

        for changed in (forged_command, forged_outcome):
            with self.assertRaises(ExperimentConfigurationError):
                analyze_reasoning_effort_v2(
                    contract,
                    reseal_receipt_artifacts_without_semantic_reconciliation(
                        changed, 0
                    ),
                )

    def test_record_receipt_assignment_and_extra_fields_fail_closed(self) -> None:
        contract, _ = frozen_contract()
        original = terminal_envelope(contract)
        mutations = []
        for field, value in (
            ("effective_task_commitment_sha256", "0" * 64),
            ("terminal_receipt_sha256", "invalid"),
            ("evaluator_receipt_sha256", "invalid"),
        ):
            changed = deepcopy(original)
            changed["records"][0][field] = value
            mutations.append(reseal(changed))
        changed = deepcopy(original)
        changed["records"][0]["task_id"] = "private-leak"
        mutations.append(reseal(changed))
        for envelope in mutations:
            with self.assertRaises(ExperimentConfigurationError):
                analyze_reasoning_effort_v2(contract, envelope)

    def test_taxonomy_timeout_numeric_and_complete_work_rules(self) -> None:
        contract, _ = frozen_contract()
        original = terminal_envelope(contract)
        mutations = []
        for field, value in (
            ("termination", "invented_outcome"),
            ("timed_out", True),
            ("turns", 1.5),
            ("wall_seconds", 2),
            ("output_tokens", None),
            ("cached_input_tokens", 200),
        ):
            changed = deepcopy(original)
            changed["records"][0][field] = value
            mutations.append(reseal(changed))
        for envelope in mutations:
            with self.assertRaises((AnalysisInputError, ExperimentConfigurationError)):
                analyze_reasoning_effort_v2(contract, envelope)

        absent = deepcopy(original)
        for field in (*INTEGER_WORK_FIELDS, "wall_seconds"):
            absent["records"][0][field] = None
        result = analyze_reasoning_effort_v2(
            contract, reseal_record_projection(absent, 0)
        )
        self.assertEqual(
            result["work"]["input_tokens"]["by_arm"]["low"]["unconditional"][
                "complete_work_cells"
            ],
            19,
        )

    def test_protocol_validity_and_batch_stop_are_envelope_derived(self) -> None:
        contract, _ = frozen_contract()
        invalid = terminal_envelope(contract, invalid=True)
        result = analyze_reasoning_effort_v2(contract, invalid)
        self.assertEqual(
            result["scientific_disposition"]["label"],
            "EXPERIMENT INVALID / TERMINATED",
        )
        self.assertFalse(result["terminal_integrity"]["protocol_valid"])
        self.assertEqual(
            result["terminal_integrity"]["batch_stop_classification"],
            "harness_failure",
        )

    def test_frozen_disposition_policy_and_work_denominators(self) -> None:
        contract, _ = frozen_contract()
        medium = analyze_reasoning_effort_v2(
            contract, terminal_envelope(contract, direction="medium")
        )
        low = analyze_reasoning_effort_v2(
            contract, terminal_envelope(contract, direction="low")
        )
        self.assertEqual(medium["scientific_disposition"]["label"], "MEDIUM FAVORED")
        self.assertEqual(low["scientific_disposition"]["label"], "LOW FAVORED")
        low_work = low["work"]["fresh_input_tokens"]["by_arm"]["medium"]
        self.assertEqual(low_work["unconditional"]["complete_work_cells"], 20)
        self.assertEqual(
            low_work["accepted_conditional"][
                "accepted_admissible_cells_with_complete_work"
            ],
            0,
        )
        self.assertIsNone(low_work["accepted_conditional"]["per_accepted_outcome"])

    def test_public_safe_falsification_and_alternate_sensitivity(self) -> None:
        contract, _ = frozen_contract()
        envelope = terminal_envelope(contract, activate_last=True)
        envelope["records"][0]["termination"] = "trajectory_timeout"
        envelope["records"][0]["timed_out"] = True
        envelope["records"][1]["evaluator_anomalies"] = ["schema_warning"]
        envelope = reseal_record_projection(envelope, 0)
        envelope = reseal_record_projection(envelope, 1)
        result = analyze_reasoning_effort_v2(contract, envelope)
        self.assertEqual(len(result["falsification"]["leave_one_slot_out"]), 10)
        self.assertTrue(result["acceptance"]["discordant_repetitions"])
        self.assertIsNotNone(result["falsification"]["timeout_extreme_case_bounds"])
        self.assertIn("with", result["falsification"]["cache_presence_strata"])
        self.assertIn("with", result["falsification"]["correction_turn_presence_strata"])
        self.assertEqual(
            result["falsification"]["alternate_use_sensitivity"][
                "activated_slot_count"
            ],
            1,
        )

    def test_all_receipts_retain_failed_attempt_work_without_identities(self) -> None:
        contract, pool = frozen_contract()
        envelope = with_full_work_retry(terminal_envelope(contract))
        result = analyze_reasoning_effort_v2(contract, envelope)
        trajectory = result["attempt_trajectory"]
        self.assertEqual(
            set(trajectory),
            {
                "attempt_counts_by_arm",
                "attempt_1_to_attempt_2_transitions",
                "work",
                "diagnostics_by_arm",
            },
        )
        arm = contract["schedule"]["cells"][0]["arm"]
        counts = trajectory["attempt_counts_by_arm"][arm]
        self.assertEqual(
            set(counts),
            {"attempts", "attempt_1", "attempt_2", "classification_counts"},
        )
        self.assertEqual(counts["attempts"], 21)
        self.assertEqual(counts["attempt_2"], 1)
        transition = next(
            item
            for item in trajectory["attempt_1_to_attempt_2_transitions"]
            if item["attempt_1_classification"]
            == "provider_api_infrastructure_failure"
        )
        self.assertEqual(transition["attempt_1_attempts"], 1)
        self.assertEqual(transition["attempt_2_activated"], 1)
        self.assertEqual(transition["attempt_2_outcomes"], {"accepted_completed": 1})
        self.assertEqual(
            set(transition),
            {
                "attempt_1_classification",
                "attempt_1_attempts",
                "attempt_2_activated",
                "attempt_2_outcomes",
            },
        )

        input_work = trajectory["work"]["input_tokens"]["by_arm"][arm]
        self.assertEqual(
            set(input_work),
            {
                "all_attempts",
                "discarded_or_infrastructure_invalid",
                "final_record_only",
                "final_record_vs_all_attempts",
                "accepted_conditional_trajectory",
            },
        )
        self.assertEqual(
            input_work["discarded_or_infrastructure_invalid"]["total"], 30.0
        )
        self.assertEqual(
            input_work["final_record_vs_all_attempts"][
                "incremental_retry_or_discarded_work"
            ],
            30.0,
        )
        accepted_final = result["work"]["input_tokens"]["by_arm"][arm][
            "accepted_conditional"
        ]
        accepted_trajectory = input_work["accepted_conditional_trajectory"]
        self.assertEqual(
            accepted_trajectory["total"], accepted_final["total"] + 30.0
        )
        self.assertEqual(
            accepted_trajectory["complete_work_attempts_in_denominator"],
            accepted_trajectory[
                "accepted_final_outcomes_with_complete_trajectory_work"
            ]
            + 1,
        )
        diagnostics = trajectory["diagnostics_by_arm"][arm]
        self.assertEqual(
            set(diagnostics),
            {
                "timeout_attempts",
                "attempt_2_timeout_attempts",
                "complete_work_attempts",
                "cache_present_complete_work_attempts",
                "correction_present_complete_work_attempts",
                "retry_complete_work_attempts",
                "attempt_2_cache_present_complete_work_attempts",
                "attempt_2_correction_present_complete_work_attempts",
            },
        )
        self.assertEqual(diagnostics["retry_complete_work_attempts"], 1)
        self.assertEqual(
            diagnostics["attempt_2_cache_present_complete_work_attempts"], 1
        )
        self.assertEqual(
            diagnostics["attempt_2_correction_present_complete_work_attempts"],
            0,
        )
        usefulness = result["esg_rr_002_usefulness"]
        self.assertEqual(
            set(usefulness),
            {
                "primary_acceptance_point_estimate",
                "primary_acceptance_interval",
                "retry_inclusive_work_result",
                "retry_inclusive_falsification_result",
            },
        )
        self.assertEqual(
            usefulness["retry_inclusive_work_result"]["sha256"],
            digest(
                {
                    "final_record_work": result["work"],
                    "all_attempt_work": trajectory["work"],
                }
            ),
        )
        self.assertTrue(result["prior_evidence_comparison"][
            "gate_policy_matches_prior_evidence"
        ])

        encoded = json.dumps(result, sort_keys=True)
        for task in [*pool["primaries"], *pool["alternates"]]:
            self.assertNotIn(task["task_id"], encoded)
            self.assertNotIn(task["repository"], encoded)
            self.assertNotIn(task["resolved_image"], encoded)
        for forbidden in (
            "cell_id",
            "population_slot",
            "task_commitment_sha256",
            "repository_commitment_sha256",
            "effort-v2-slot",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_output_and_input_commitment_do_not_echo_private_identities(self) -> None:
        contract, pool = frozen_contract()
        envelope = terminal_envelope(contract)
        result = analyze_reasoning_effort_v2(contract, envelope)
        encoded = json.dumps(result, sort_keys=True)
        for task in [*pool["primaries"], *pool["alternates"]]:
            self.assertNotIn(task["task_id"], encoded)
            self.assertNotIn(task["repository"], encoded)
            self.assertNotIn(task["resolved_image"], encoded)
        self.assertEqual(result["records_sha256"], digest(envelope["records"]))
        self.assertNotIn("task_id", encoded)
        for forbidden in (
            "cell_id",
            "population_slot",
            "task_commitment_sha256",
            "repository_commitment_sha256",
            "effort-v2-slot",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_sha256_bootstrap_reference_uses_unbiased_rejection_sampling(self) -> None:
        self.assertEqual(
            _unbiased_bootstrap_indices(
                seed="reference-seed", sample=0, draws=12, population_size=10
            ),
            (8, 8, 9, 8, 7, 9, 2, 8, 2, 9, 3, 1),
        )
        self.assertEqual(
            _unbiased_bootstrap_indices(
                seed="rejection-seed", sample=3, draws=20, population_size=129
            ),
            (108, 94, 54, 69, 33, 71, 100, 38, 99, 115, 33, 77, 6, 87, 110, 91, 86, 15, 125, 16),
        )

    def test_envelope_is_not_mutated(self) -> None:
        contract, _ = frozen_contract()
        envelope = terminal_envelope(contract)
        before = deepcopy(envelope)
        analyze_reasoning_effort_v2(contract, envelope)
        self.assertEqual(envelope, before)


if __name__ == "__main__":
    unittest.main()
