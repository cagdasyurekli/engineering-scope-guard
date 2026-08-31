from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import digest
from engineering_scope_guard.reasoning_effort_v2 import (
    ALTERNATE_ACTIVATION_CLASSES,
    ARMS,
    MANDATORY_BATCH_STOP,
    RETRYABLE_INFRASTRUCTURE,
    build_contract,
    build_harness_source_closure,
    build_prior_evidence_identity,
    build_private_pool,
    generate_schedule,
    public_pool_projection,
    replay_attempt_state,
    subject_command_identity,
    validate_attempt_events,
    validate_attempt_number,
    validate_contract,
    validate_frozen_identity,
    validate_harness_source_closure,
    validate_prior_evidence_identity,
    validate_private_pool,
    validate_private_pool_binding,
)

SHA = "a" * 64


def tasks(count: int, *, offset: int = 0) -> list[dict[str, str]]:
    return [
        {
            "task_id": f"private-task-{number}",
            "repository": f"private-owner/repository-{number}",
            "task_snapshot_sha256": f"{number % 16:x}" * 64,
            "resolved_image": f"private/image-{number}@sha256:{number:064x}",
        }
        for number in range(offset + 1, offset + count + 1)
    ]


def pool(primary_count: int = 12, alternate_count: int = 4) -> dict:
    return build_private_pool(
        tasks(primary_count), tasks(alternate_count, offset=primary_count)
    )


def contract(primary_count: int = 12, alternate_count: int = 4, canary: int = 0) -> dict:
    return build_contract(
        pool(primary_count, alternate_count),
        model="gpt-5.6-sol",
        codex_version="fixture",
        runtime_identity="runtime-fixture",
        source_identity="source-fixture",
        qualification_receipt_sha256="b" * 64,
        evaluator_identity="evaluator-fixture",
        image_pool_identity="c" * 64,
        tool_configuration_identity="tools-fixture",
        maximum_contentless_canary_subject_invocation_starts=canary,
    )


def reseal(value: dict) -> dict:
    result = deepcopy(value)
    result["contract_sha256"] = digest(
        {key: item for key, item in result.items() if key != "contract_sha256"}
    )
    return result


def attempt_start(cell: dict, attempt: int, commitment: str) -> dict:
    return {
        "event_type": "attempt_started",
        "payload": {
            "cell_id": cell["cell_id"],
            "attempt": attempt,
            "effective_task_commitment_sha256": commitment,
        },
    }


def subject_start(contract: dict, cell: dict, attempt: int, commitment: str) -> dict:
    return {
        "event_type": "subject_invocation_started",
        "payload": {
            "cell_id": cell["cell_id"],
            "attempt": attempt,
            "effective_task_commitment_sha256": commitment,
            "command_sha256": subject_command_identity(contract, cell["cell_id"]),
            "ownership_token_sha256": "e" * 64,
            "process_identity_sha256": "f" * 64,
        },
    }


def finish(
    cell: dict,
    attempt: int,
    commitment: str,
    classification: str,
    *,
    subject_started: bool,
    evidence: str = SHA,
) -> dict:
    return {
        "event_type": "attempt_finished",
        "payload": {
            "cell_id": cell["cell_id"],
            "attempt": attempt,
            "classification": classification,
            "evidence_sha256": evidence,
            "effective_task_commitment_sha256": commitment,
            "subject_invocation_started": subject_started,
        },
    }


def complete(cell: dict, attempt: int, commitment: str, *, evidence: str = SHA) -> dict:
    return {
        "event_type": "cell_completed",
        "payload": {
            "cell_id": cell["cell_id"],
            "attempt": attempt,
            "classification": "accepted_completed",
            "evidence_sha256": evidence,
            "effective_task_commitment_sha256": commitment,
        },
    }


def primary_commitments(value: dict) -> dict[int, str]:
    return {
        item["population_slot"]: item["task_commitment_sha256"]
        for item in value["source"]["private_pool"]["primary_slot_commitments"]
    }


def stage_1_pass(contract_value: dict) -> list[dict]:
    cell_ids = [cell["cell_id"] for cell in contract_value["schedule"]["cells"][:4]]
    receipt_set = "f" * 64
    audit = {
        "schema_version": 1,
        "status": "pass",
        "criteria": {
            "exact_four_retained_cells": True,
            "terminal_receipts_complete": True,
            "receipt_hashes_valid": True,
            "ledger_chain_valid": True,
            "no_batch_stop": True,
            "runtime_identity_stable": True,
            "source_identity_stable": True,
        },
        "completed_cell_count": 4,
        "completed_cell_ids": cell_ids,
        "receipt_set_sha256": receipt_set,
        "outcome_fields_inspected": False,
        "outcome_values_emitted": False,
    }
    return [
        {
            "event_type": "stage_1_boundary_reached",
            "payload": {
                "completed_cell_count": 4,
                "completed_cell_ids": cell_ids,
                "receipt_set_sha256": receipt_set,
            },
        },
        {
            "event_type": "stage_1_audit_passed",
            "payload": {"audit": audit, "audit_sha256": digest(audit)},
        },
    ]


class ReasoningEffortV2Tests(unittest.TestCase):
    def test_harness_closure_and_prior_evidence_reject_file_drift(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        closure = build_harness_source_closure(repository)
        prior = build_prior_evidence_identity(repository)
        self.assertTrue(any(
            item["path"] == "scripts/reasoning_effort_v1_runner.py"
            for item in closure["files"]
        ))
        self.assertTrue(any(
            item["path"] == "src/engineering_scope_guard/disk_safety.py"
            for item in closure["files"]
        ))
        self.assertTrue(any(
            item["path"] == "scripts/reasoning_effort_v2_canary.py"
            for item in closure["files"]
        ))
        self.assertEqual(
            next(
                item["argv"] for item in closure["entrypoints"]
                if item["name"] == "canary_launch"
            ),
            ["python3", "scripts/reasoning_effort_v2_canary.py", "launch"],
        )
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            for item in closure["files"]:
                target = copied / item["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repository / item["path"], target)
            validate_harness_source_closure(closure, root=copied)
            target = copied / closure["files"][0]["path"]
            target.write_bytes(target.read_bytes() + b"\n")
            with self.assertRaisesRegex(ExperimentConfigurationError, "drifted"):
                validate_harness_source_closure(closure, root=copied)
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            for item in prior["files"]:
                target = copied / item["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repository / item["path"], target)
            validate_prior_evidence_identity(prior, root=copied)
            target = copied / prior["files"][0]["path"]
            target.write_bytes(target.read_bytes() + b"\n")
            with self.assertRaisesRegex(ExperimentConfigurationError, "drifted"):
                validate_prior_evidence_identity(prior, root=copied)

    def test_dynamic_schedule_and_stage_1_balance(self) -> None:
        for count, cells in ((10, 40), (11, 44), (12, 48)):
            with self.subTest(count=count):
                frozen = pool(count, 0)
                schedule = generate_schedule(count, frozen["private_pool_sha256"])
                self.assertEqual(len(schedule["cells"]), cells)
                self.assertEqual(
                    {arm: sum(cell["arm"] == arm for cell in schedule["cells"][:4]) for arm in ARMS},
                    {"low": 2, "medium": 2},
                )
                for slot in range(1, count + 1):
                    slot_cells = [
                        cell for cell in schedule["cells"]
                        if cell["population_slot"] == slot
                    ]
                    self.assertEqual(
                        {(cell["arm"], cell["repetition"]) for cell in slot_cells},
                        {(arm, repetition) for arm in ARMS for repetition in (1, 2)},
                    )

    def test_private_pool_rejects_count_overlap_and_repository_reuse(self) -> None:
        for count in (9, 13):
            with self.subTest(count=count), self.assertRaises(ExperimentConfigurationError):
                build_private_pool(tasks(count), [])
        primaries = tasks(10)
        duplicate = tasks(1, offset=10)
        duplicate[0]["task_id"] = primaries[0]["task_id"]
        with self.assertRaisesRegex(ExperimentConfigurationError, "task identities"):
            build_private_pool(primaries, duplicate)
        duplicate = tasks(1, offset=10)
        duplicate[0]["repository"] = primaries[0]["repository"]
        with self.assertRaisesRegex(ExperimentConfigurationError, "globally unique"):
            build_private_pool(primaries, duplicate)
        with self.assertRaisesRegex(ExperimentConfigurationError, "at most four"):
            build_private_pool(primaries, tasks(5, offset=10))
        reserved = tasks(10)
        reserved[0]["population_slot"] = 99
        with self.assertRaisesRegex(ExperimentConfigurationError, "reserved envelope"):
            build_private_pool(reserved, [])

    def test_private_pool_and_public_projection_are_sealed_and_private(self) -> None:
        frozen_pool = pool()
        validate_private_pool(frozen_pool)
        frozen_contract = contract()
        validate_private_pool_binding(frozen_pool, frozen_contract)
        encoded = json.dumps(frozen_contract, sort_keys=True)
        for task in [*frozen_pool["primaries"], *frozen_pool["alternates"]]:
            self.assertNotIn(task["task_id"], encoded)
            self.assertNotIn(task["repository"], encoded)
            self.assertNotIn(task["resolved_image"], encoded)
        projection = public_pool_projection(frozen_pool)
        self.assertTrue(projection["repository_distinct_across_primary_and_alternates"])

    def test_contract_freezes_full_pre_cell_1_protocol_and_analysis_policy(self) -> None:
        frozen = contract(canary=1)
        validate_contract(frozen)
        self.assertEqual(frozen["status"], "frozen-provider-free-live-execution-not-authorized")
        self.assertFalse(frozen["live_execution_authorized"])
        self.assertEqual(frozen["treatment"]["only_variable"], "reasoning_effort")
        self.assertEqual(frozen["runtime"]["sandbox"], "workspace-write")
        self.assertEqual(frozen["runtime"]["tool_configuration_identity"], "tools-fixture")
        self.assertIn("qualification_receipt_sha256", frozen["source"])
        self.assertIn("image_pool_identity", frozen["source"])
        self.assertEqual(frozen["trajectory"]["subject_invocations_per_attempt"], 1)
        self.assertFalse(frozen["alternate_activation"]["subject_outcome_or_direction_may_trigger_activation"])
        self.assertTrue(frozen["attempt_accounting"]["never_started_mandatory_cells_retain_first_start_capacity"])
        self.assertEqual(
            set(frozen["analysis_policy"]),
            {"schema_version", "bootstrap", "termination_taxonomy", "work_policy", "disposition_policy"},
        )
        self.assertTrue(
            frozen["analysis_policy"]["work_policy"][
                "accepted_conditional_is_descriptive_post_outcome_subset"
            ]
        )
        gate = frozen["esg_rr_002_gate_policy"]
        self.assertEqual(gate["minimum_independent_admissible_clusters"], 10)
        self.assertEqual(gate["maximum_finite_primary_interval_width"], 0.50)
        self.assertFalse(gate["significance_or_equivalence_test"])
        self.assertEqual(
            gate["policy_sha256"],
            digest({key: value for key, value in gate.items() if key != "policy_sha256"}),
        )

    def test_contract_rejects_resealed_extra_or_mutated_canonical_fields(self) -> None:
        cases = []
        changed = deepcopy(contract())
        changed["extra"] = True
        cases.append(changed)
        changed = deepcopy(contract())
        changed["treatment"]["extra"] = True
        cases.append(changed)
        changed = deepcopy(contract())
        changed["runtime"]["sandbox"] = "danger-full-access"
        cases.append(changed)
        changed = deepcopy(contract())
        changed["source"]["extra"] = True
        cases.append(changed)
        changed = deepcopy(contract())
        changed["status"] = "authorized"
        cases.append(changed)
        changed = deepcopy(contract())
        changed["analysis_policy"]["bootstrap"]["resamples"] = 99
        cases.append(changed)
        changed = deepcopy(contract())
        changed["esg_rr_002_gate_policy"]["maximum_finite_primary_interval_width"] = 0.75
        changed["esg_rr_002_gate_policy"]["policy_sha256"] = digest({
            key: value for key, value in changed["esg_rr_002_gate_policy"].items()
            if key != "policy_sha256"
        })
        cases.append(changed)
        for index, candidate in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ExperimentConfigurationError):
                validate_contract(reseal(candidate))

    def test_source_bindings_and_private_pool_mutation_fail_closed(self) -> None:
        frozen = contract()
        validate_frozen_identity(
            frozen,
            expected_contract_sha256=frozen["contract_sha256"],
            expected_qualification_receipt_sha256="b" * 64,
            expected_evaluator_identity="evaluator-fixture",
            expected_image_pool_identity="c" * 64,
        )
        for field in ("qualification_receipt_sha256", "image_pool_identity"):
            changed = deepcopy(frozen)
            changed["source"][field] = "not-a-sha"
            with self.subTest(field=field), self.assertRaises(ExperimentConfigurationError):
                validate_contract(reseal(changed))
        replacement = contract()
        replacement["source"]["evaluator_identity"] = "different-evaluator"
        replacement = reseal(replacement)
        with self.assertRaisesRegex(ExperimentConfigurationError, "contract was replaced"):
            validate_frozen_identity(
                replacement,
                expected_contract_sha256=frozen["contract_sha256"],
                expected_qualification_receipt_sha256="b" * 64,
                expected_evaluator_identity="evaluator-fixture",
                expected_image_pool_identity="c" * 64,
            )
        changed_pool = deepcopy(pool())
        changed_pool["primaries"][0]["repository"] = "changed/repo"
        with self.assertRaisesRegex(ExperimentConfigurationError, "identity mismatch"):
            validate_private_pool(changed_pool)

    def test_canary_is_frozen_as_maximum_and_consumed_only_by_ledger(self) -> None:
        frozen = contract(canary=1)
        empty = replay_attempt_state(frozen, [])
        self.assertEqual(empty["canary_subject_invocation_starts"], 0)
        canary = {
            "event_type": "canary_subject_invocation_started",
            "payload": {"evidence_sha256": SHA},
        }
        state = replay_attempt_state(frozen, [canary])
        self.assertEqual(state["total_subject_invocation_starts"], 1)
        with self.assertRaisesRegex(ExperimentConfigurationError, "maximum exceeded"):
            validate_attempt_events(frozen, [canary, canary])
        with self.assertRaisesRegex(ExperimentConfigurationError, "maximum exceeded"):
            validate_attempt_events(contract(canary=0), [canary])

    def test_attempt_state_requires_terminal_attempt_1_and_frozen_retry_authority(self) -> None:
        frozen = contract(10, 0)
        cell = frozen["schedule"]["cells"][0]
        commitment = primary_commitments(frozen)[cell["population_slot"]]
        events = [attempt_start(cell, 1, commitment)]
        with self.assertRaisesRegex(ExperimentConfigurationError, "prior attempt"):
            validate_attempt_events(frozen, [*events, attempt_start(cell, 2, commitment)])
        events.extend(
            [
                subject_start(frozen, cell, 1, commitment),
                finish(
                    cell, 1, commitment, RETRYABLE_INFRASTRUCTURE[0],
                    subject_started=True,
                ),
            ]
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "lacks frozen"):
            validate_attempt_events(frozen, [*events, attempt_start(cell, 2, commitment)])
        authorization = {
            "event_type": "attempt_2_authorized",
            "payload": {
                "cell_id": cell["cell_id"],
                "prior_attempt": 1,
                "next_attempt": 2,
                "classification": RETRYABLE_INFRASTRUCTURE[0],
                "evidence_sha256": SHA,
                "effective_task_commitment_sha256": commitment,
            },
        }
        validate_attempt_events(
            frozen, [*events, authorization, attempt_start(cell, 2, commitment)]
        )
        changed = deepcopy(authorization)
        changed["payload"]["classification"] = RETRYABLE_INFRASTRUCTURE[1]
        with self.assertRaisesRegex(ExperimentConfigurationError, "matching"):
            validate_attempt_events(frozen, [*events, changed])
        with self.assertRaisesRegex(ExperimentConfigurationError, "attempt 3"):
            validate_attempt_number(3)

    def test_mandatory_batch_stop_is_terminal_and_preserves_the_current_cell(self) -> None:
        frozen = contract(10, 0)
        cell = frozen["schedule"]["cells"][0]
        commitment = primary_commitments(frozen)[cell["population_slot"]]
        events = [
            attempt_start(cell, 1, commitment),
            finish(
                cell,
                1,
                commitment,
                MANDATORY_BATCH_STOP[0],
                subject_started=False,
            ),
        ]
        state = replay_attempt_state(frozen, events)
        self.assertEqual(state["batch_stop_classification"], MANDATORY_BATCH_STOP[0])
        self.assertEqual(state["next_cell_id"], cell["cell_id"])
        self.assertEqual(state["completed_cells"], 0)
        with self.assertRaisesRegex(ExperimentConfigurationError, "terminal batch stop"):
            validate_attempt_events(frozen, [*events, attempt_start(cell, 2, commitment)])

    def test_attempt_2_infrastructure_exhaustion_stops_without_attempt_3(self) -> None:
        frozen = contract(10, 0)
        cell = frozen["schedule"]["cells"][0]
        commitment = primary_commitments(frozen)[cell["population_slot"]]
        events = [
            attempt_start(cell, 1, commitment),
            finish(cell, 1, commitment, RETRYABLE_INFRASTRUCTURE[0], subject_started=False),
            {
                "event_type": "attempt_2_authorized",
                "payload": {
                    "cell_id": cell["cell_id"], "prior_attempt": 1, "next_attempt": 2,
                    "classification": RETRYABLE_INFRASTRUCTURE[0],
                    "evidence_sha256": SHA,
                    "effective_task_commitment_sha256": commitment,
                },
            },
            attempt_start(cell, 2, commitment),
            finish(cell, 2, commitment, RETRYABLE_INFRASTRUCTURE[1], subject_started=False),
            {
                "event_type": "batch_stopped",
                "payload": {
                    "cell_id": cell["cell_id"], "attempt": 2,
                    "classification": "durable_evidence_incomplete",
                    "evidence_sha256": SHA,
                },
            },
        ]
        state = replay_attempt_state(frozen, events)
        self.assertEqual(state["batch_stop_classification"], "durable_evidence_incomplete")
        self.assertEqual(state["next_cell_id"], cell["cell_id"])
        with self.assertRaisesRegex(ExperimentConfigurationError, "terminal batch stop|attempt 3"):
            validate_attempt_events(frozen, [*events, attempt_start(cell, 3, commitment)])

    def test_execution_is_exact_frozen_schedule_prefix(self) -> None:
        frozen = contract(10, 0)
        first, second = frozen["schedule"]["cells"][:2]
        commitments = primary_commitments(frozen)
        second_commitment = commitments[second["population_slot"]]
        with self.assertRaisesRegex(ExperimentConfigurationError, "schedule order"):
            validate_attempt_events(frozen, [attempt_start(second, 1, second_commitment)])
        first_commitment = commitments[first["population_slot"]]
        events = [
            attempt_start(first, 1, first_commitment),
            subject_start(frozen, first, 1, first_commitment),
            finish(first, 1, first_commitment, "accepted_completed", subject_started=True),
            complete(first, 1, first_commitment),
            attempt_start(second, 1, second_commitment),
        ]
        validate_attempt_events(frozen, events)

    def test_capacity_reserves_every_never_started_mandatory_cell(self) -> None:
        frozen = contract(12, 0)
        commitments = primary_commitments(frozen)
        events = []
        # Complete each cell; the first eight consume their one permitted retry.
        for index, cell in enumerate(frozen["schedule"]["cells"]):
            commitment = commitments[cell["population_slot"]]
            if index < 8:
                events.extend(
                    [
                        attempt_start(cell, 1, commitment),
                        subject_start(frozen, cell, 1, commitment),
                        finish(
                            cell, 1, commitment, RETRYABLE_INFRASTRUCTURE[0],
                            subject_started=True,
                        ),
                        {
                            "event_type": "attempt_2_authorized",
                            "payload": {
                                "cell_id": cell["cell_id"],
                                "prior_attempt": 1,
                                "next_attempt": 2,
                                "classification": RETRYABLE_INFRASTRUCTURE[0],
                                "evidence_sha256": SHA,
                                "effective_task_commitment_sha256": commitment,
                            },
                        },
                        attempt_start(cell, 2, commitment),
                        subject_start(frozen, cell, 2, commitment),
                        finish(
                            cell, 2, commitment, "accepted_completed",
                            subject_started=True,
                        ),
                        complete(cell, 2, commitment),
                    ]
                )
            else:
                events.extend(
                    [
                        attempt_start(cell, 1, commitment),
                        subject_start(frozen, cell, 1, commitment),
                        finish(
                            cell, 1, commitment, "accepted_completed",
                            subject_started=True,
                        ),
                        complete(cell, 1, commitment),
                    ]
                )
            if index == 3:
                events.extend(stage_1_pass(frozen))
        state = replay_attempt_state(frozen, events)
        self.assertEqual(state["total_subject_invocation_starts"], 56)

        with_canary = contract(12, canary=1)
        first = with_canary["schedule"]["cells"][0]
        commitment = primary_commitments(with_canary)[first["population_slot"]]
        canary = {
            "event_type": "canary_subject_invocation_started",
            "payload": {"evidence_sha256": SHA},
        }
        # Eight retries would leave only 47 starts for 48 mandatory cells.
        partial = [canary]
        for index, cell in enumerate(with_canary["schedule"]["cells"][:8]):
            effective = primary_commitments(with_canary)[cell["population_slot"]]
            partial.extend(
                [
                    attempt_start(cell, 1, effective),
                    subject_start(frozen, cell, 1, effective),
                    finish(
                        cell, 1, effective, RETRYABLE_INFRASTRUCTURE[0],
                        subject_started=True,
                    ),
                    {
                        "event_type": "attempt_2_authorized",
                        "payload": {
                            "cell_id": cell["cell_id"], "prior_attempt": 1,
                            "next_attempt": 2, "classification": RETRYABLE_INFRASTRUCTURE[0],
                            "evidence_sha256": SHA,
                            "effective_task_commitment_sha256": effective,
                        },
                    },
                    attempt_start(cell, 2, effective),
                    subject_start(frozen, cell, 2, effective),
                    finish(
                        cell, 2, effective, "accepted_completed", subject_started=True,
                    ),
                    complete(cell, 2, effective),
                ]
            )
            if index == 3:
                partial.extend(stage_1_pass(with_canary))
        with self.assertRaisesRegex(ExperimentConfigurationError, "reserved"):
            validate_attempt_events(with_canary, partial)
        self.assertEqual(commitment, primary_commitments(with_canary)[first["population_slot"]])

    def test_pre_attempt_capacity_exhaustion_is_terminal_without_active_attempt(self) -> None:
        frozen = contract(12, 0, canary=1)
        commitments = primary_commitments(frozen)
        events = [{
            "event_type": "canary_subject_invocation_started",
            "payload": {"evidence_sha256": SHA},
        }]
        cells = frozen["schedule"]["cells"]
        for index, cell in enumerate(cells[:-1]):
            commitment = commitments[cell["population_slot"]]
            events.extend([
                attempt_start(cell, 1, commitment),
                subject_start(frozen, cell, 1, commitment),
                finish(
                    cell, 1, commitment,
                    RETRYABLE_INFRASTRUCTURE[0] if index < 7 else "accepted_completed",
                    subject_started=True,
                ),
            ])
            if index < 7:
                events.extend([
                    {
                        "event_type": "attempt_2_authorized",
                        "payload": {
                            "cell_id": cell["cell_id"], "prior_attempt": 1,
                            "next_attempt": 2,
                            "classification": RETRYABLE_INFRASTRUCTURE[0],
                            "evidence_sha256": SHA,
                            "effective_task_commitment_sha256": commitment,
                        },
                    },
                    attempt_start(cell, 2, commitment),
                    subject_start(frozen, cell, 2, commitment),
                    finish(cell, 2, commitment, "accepted_completed", subject_started=True),
                    complete(cell, 2, commitment),
                ])
            else:
                events.append(complete(cell, 1, commitment))
            if index == 3:
                events.extend(stage_1_pass(frozen))
        final = cells[-1]
        commitment = commitments[final["population_slot"]]
        events.extend([
            attempt_start(final, 1, commitment),
            subject_start(frozen, final, 1, commitment),
            finish(final, 1, commitment, RETRYABLE_INFRASTRUCTURE[0], subject_started=True),
            {
                "event_type": "attempt_2_authorized",
                "payload": {
                    "cell_id": final["cell_id"], "prior_attempt": 1, "next_attempt": 2,
                    "classification": RETRYABLE_INFRASTRUCTURE[0],
                    "evidence_sha256": SHA,
                    "effective_task_commitment_sha256": commitment,
                },
            },
            {
                "event_type": "capacity_exhausted",
                "payload": {
                    "cell_id": final["cell_id"], "requested_attempt": 2,
                    "classification": "durable_evidence_incomplete",
                    "canary_subject_invocation_starts": 1,
                    "experiment_subject_invocation_starts": 55,
                    "never_started_mandatory_cells": 0,
                    "projected_subject_invocation_starts_with_reservation": 57,
                    "maximum_subject_invocation_starts": 56,
                },
            },
        ])
        state = replay_attempt_state(frozen, events)
        self.assertEqual(state["total_subject_invocation_starts"], 56)
        self.assertEqual(state["batch_stop_classification"], "durable_evidence_incomplete")
        self.assertEqual(state["next_cell_id"], final["cell_id"])
        with self.assertRaises(ExperimentConfigurationError):
            validate_attempt_events(frozen, [*events, attempt_start(final, 2, commitment)])

    def test_alternate_activation_is_next_ordinal_evidence_bound_and_outcome_blind(self) -> None:
        frozen = contract(10, 2)
        cell = frozen["schedule"]["cells"][0]
        slot = cell["population_slot"]
        primary = primary_commitments(frozen)[slot]
        alternate = frozen["source"]["private_pool"]["alternate_order_commitments"][0][
            "task_commitment_sha256"
        ]
        events = [
            attempt_start(cell, 1, primary),
            finish(
                cell, 1, primary, ALTERNATE_ACTIVATION_CLASSES[0],
                subject_started=False,
            ),
        ]
        activation = {
            "event_type": "alternate_activated",
            "payload": {
                "cell_id": cell["cell_id"],
                "population_slot": slot,
                "trigger_attempt": 1,
                "classification": ALTERNATE_ACTIVATION_CLASSES[0],
                "evidence_sha256": SHA,
                "replaces_task_commitment_sha256": primary,
                "alternate_ordinal": 1,
                "alternate_task_commitment_sha256": alternate,
                "next_attempt": 2,
                "subject_outcome_used": False,
                "outcome_direction_inspected": False,
            },
        }
        state = replay_attempt_state(
            frozen, [*events, activation, attempt_start(cell, 2, alternate)]
        )
        self.assertEqual(state["used_alternate_ordinals"], [1])
        self.assertEqual(state["effective_task_commitment_by_slot"][slot], alternate)
        self.assertEqual(state["total_subject_invocation_starts"], 0)

        mutations = []
        changed = deepcopy(activation)
        changed["payload"]["alternate_ordinal"] = 2
        mutations.append(changed)
        changed = deepcopy(activation)
        changed["payload"]["evidence_sha256"] = "e" * 64
        mutations.append(changed)
        changed = deepcopy(activation)
        changed["payload"]["subject_outcome_used"] = True
        mutations.append(changed)
        for candidate in mutations:
            with self.subTest(candidate=candidate["payload"]), self.assertRaises(
                ExperimentConfigurationError
            ):
                validate_attempt_events(frozen, [*events, candidate])

        outcome_events = [
            attempt_start(cell, 1, primary),
            subject_start(frozen, cell, 1, primary),
            finish(cell, 1, primary, "evaluator_test_failure", subject_started=True),
        ]
        with self.assertRaises(ExperimentConfigurationError):
            validate_attempt_events(frozen, [*outcome_events, activation])

    def test_alternate_cannot_reuse_slot_or_reset_attempt_and_global_budgets(self) -> None:
        frozen = contract(10, 2)
        first = frozen["schedule"]["cells"][0]
        slot = first["population_slot"]
        primary = primary_commitments(frozen)[slot]
        alternate = frozen["source"]["private_pool"]["alternate_order_commitments"][0][
            "task_commitment_sha256"
        ]
        activation = {
            "event_type": "alternate_activated",
            "payload": {
                "cell_id": first["cell_id"], "population_slot": slot,
                "trigger_attempt": 1, "classification": ALTERNATE_ACTIVATION_CLASSES[0],
                "evidence_sha256": SHA, "replaces_task_commitment_sha256": primary,
                "alternate_ordinal": 1, "alternate_task_commitment_sha256": alternate,
                "next_attempt": 2, "subject_outcome_used": False,
                "outcome_direction_inspected": False,
            },
        }
        events = [
            attempt_start(first, 1, primary),
            finish(
                first, 1, primary, ALTERNATE_ACTIVATION_CLASSES[0],
                subject_started=False,
            ),
            activation,
            attempt_start(first, 2, alternate),
            subject_start(frozen, first, 2, alternate),
            finish(first, 2, alternate, "accepted_completed", subject_started=True),
            complete(first, 2, alternate),
        ]
        state = replay_attempt_state(frozen, events)
        self.assertEqual(state["experiment_subject_invocation_starts"], 1)
        # A later cell from the same slot uses only the already activated task;
        # another activation is forbidden because the slot has a completed cell.
        later = next(
            cell for cell in frozen["schedule"]["cells"][1:]
            if cell["population_slot"] == slot
        )
        reuse_events = [
            *events,
            attempt_start(later, 1, alternate),
            finish(
                later, 1, alternate, ALTERNATE_ACTIVATION_CLASSES[0],
                subject_started=False,
            ),
        ]
        next_alternate = frozen["source"]["private_pool"][
            "alternate_order_commitments"
        ][1]["task_commitment_sha256"]
        reused_slot_activation = {
            "event_type": "alternate_activated",
            "payload": {
                "cell_id": later["cell_id"], "population_slot": slot,
                "trigger_attempt": 1, "classification": ALTERNATE_ACTIVATION_CLASSES[0],
                "evidence_sha256": SHA,
                "replaces_task_commitment_sha256": alternate,
                "alternate_ordinal": 2,
                "alternate_task_commitment_sha256": next_alternate,
                "next_attempt": 2, "subject_outcome_used": False,
                "outcome_direction_inspected": False,
            },
        }
        with self.assertRaisesRegex(ExperimentConfigurationError, "outcome-blind"):
            validate_attempt_events(frozen, [*reuse_events, reused_slot_activation])

        # The already consumed alternate cannot be attached to another slot.
        second = frozen["schedule"]["cells"][1]
        self.assertEqual(second["population_slot"], slot)
        cross_slot = frozen["schedule"]["cells"][2]
        self.assertNotEqual(cross_slot["population_slot"], slot)
        cross_primary = primary_commitments(frozen)[cross_slot["population_slot"]]
        through_second = [
            *events,
            attempt_start(second, 1, alternate),
            subject_start(frozen, second, 1, alternate),
            finish(second, 1, alternate, "accepted_completed", subject_started=True),
            complete(second, 1, alternate),
            attempt_start(cross_slot, 1, cross_primary),
            finish(
                cross_slot,
                1,
                cross_primary,
                ALTERNATE_ACTIVATION_CLASSES[0],
                subject_started=False,
            ),
        ]
        reused_alternate = deepcopy(activation)
        reused_alternate["payload"].update(
            {
                "cell_id": cross_slot["cell_id"],
                "population_slot": cross_slot["population_slot"],
                "replaces_task_commitment_sha256": cross_primary,
            }
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "outcome-blind"):
            validate_attempt_events(frozen, [*through_second, reused_alternate])


if __name__ == "__main__":
    unittest.main()
