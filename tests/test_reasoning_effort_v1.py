from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import digest
from engineering_scope_guard.reasoning_effort_v1 import (
    CELL_COUNT,
    USAGE_MEASUREMENT_SCOPE,
    append_event,
    authorize_attempt_2,
    build_contract,
    generate_schedule,
    read_attempt_ledger,
    read_events,
    record_attempt_start,
    record_cell_completed,
    validate_attempt_ledger,
    validate_contract,
    validate_frozen_identity,
    validate_usage,
)


def fixture_tasks() -> list[dict[str, str]]:
    return [
        {
            "task_id": f"task-{number}",
            "repository": f"owner/repo-{number}",
            "task_snapshot_sha256": f"{number:x}" * 64,
        }
        for number in range(1, 9)
    ]


def fixture_contract(qualification: int = 0) -> dict:
    return build_contract(
        fixture_tasks(),
        model="gpt-5.6-sol",
        codex_version="0.151.0",
        runtime_identity="runtime-sha256:fixture",
        source_revision="source-fixture",
        evaluator_revision="evaluator-fixture",
        qualification_subject_executions=qualification,
        dataset_identity="SWE-bench-Live/MultiLang",
        evaluator_identity="SWE-bench-Live official evaluator",
        repolaunch_revision="repolaunch-fixture",
        image_pool_identity="image-pool-fixture",
    )


class ReasoningEffortV1Test(unittest.TestCase):
    def test_schedule_is_deterministic_repository_distinct_and_counterbalanced(self) -> None:
        schedule = generate_schedule(fixture_tasks())
        self.assertEqual(schedule, generate_schedule(list(reversed(fixture_tasks()))))
        self.assertEqual(len(schedule["cells"]), CELL_COUNT)
        self.assertEqual(len({task["repository"] for task in schedule["tasks"]}), 8)
        for task in schedule["tasks"]:
            cells = [cell for cell in schedule["cells"] if cell["task_slot"] == task["slot"]]
            by_repetition = {
                repetition: [cell["arm"] for cell in cells if cell["repetition"] == repetition]
                for repetition in (1, 2)
            }
            self.assertEqual(by_repetition[1], list(reversed(by_repetition[2])))
            self.assertEqual(
                {(cell["arm"], cell["repetition"]) for cell in cells},
                {("low", 1), ("medium", 1), ("low", 2), ("medium", 2)},
            )

    def test_contract_freezes_one_model_runtime_and_only_effort_varies(self) -> None:
        contract = fixture_contract(qualification=4)
        validate_contract(contract)
        self.assertFalse(contract["live_execution_authorized"])
        self.assertEqual(contract["subject"]["only_variable"], "reasoning_effort")
        self.assertEqual(set(contract["subject"]["arms"]), {"low", "medium"})
        self.assertEqual(contract["analysis_unit"]["unit"], "task/repository")
        self.assertEqual(
            contract["attempt_accounting"]["maximum_subject_executions_including_qualification"],
            64,
        )
        self.assertEqual(contract["trajectory"]["subject_invocations_per_cell"], 1)
        self.assertEqual(contract["trajectory"]["subject_timeout_seconds"], 900)
        self.assertEqual(contract["trajectory"]["evaluator_timeout_seconds"], 1800)
        self.assertEqual(
            contract["staging"]["stage_1_cell_ids"],
            [cell["cell_id"] for cell in contract["schedule"]["cells"][:4]],
        )
        self.assertEqual(
            contract["source"]["pool_sha256"], contract["schedule"]["pool_sha256"]
        )
        self.assertEqual(
            contract["analysis"]["uncertainty"]["method"],
            "deterministic task-cluster bootstrap",
        )
        self.assertTrue(contract["claim_boundaries"]["exploratory_only"])
        self.assertFalse(contract["stop_rules"]["confirmatory_experiment_permitted"])
        taxonomy = contract["failure_taxonomy"]
        classes = [
            set(taxonomy["experimental_outcomes"]),
            set(taxonomy["retryable_infrastructure"]),
            set(taxonomy["mandatory_batch_stop"]),
        ]
        self.assertFalse(
            classes[0] & classes[1] | classes[0] & classes[2] | classes[1] & classes[2]
        )

        with self.assertRaisesRegex(ExperimentConfigurationError, "pool identity"):
            build_contract(
                fixture_tasks(),
                model="gpt-5.6-sol",
                codex_version="0.151.0",
                runtime_identity="runtime-sha256:fixture",
                source_revision="source-fixture",
                evaluator_revision="evaluator-fixture",
                expected_pool_sha256="0" * 64,
            )

    def test_contract_and_schedule_identity_reject_tampering(self) -> None:
        contract = fixture_contract()
        validate_frozen_identity(
            contract,
            expected_contract_sha256=contract["contract_sha256"],
            expected_schedule_sha256=contract["schedule"]["schedule_sha256"],
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "was replaced"):
            validate_frozen_identity(
                contract,
                expected_contract_sha256="0" * 64,
                expected_schedule_sha256=contract["schedule"]["schedule_sha256"],
            )
        changed_contract = deepcopy(contract)
        changed_contract["subject"]["model"] = "different"
        with self.assertRaisesRegex(ExperimentConfigurationError, "contract identity"):
            validate_contract(changed_contract)

        changed_schedule = deepcopy(contract)
        changed_schedule["schedule"]["cells"][0]["arm"] = "medium"
        with self.assertRaisesRegex(ExperimentConfigurationError, "contract identity"):
            validate_contract(changed_schedule)

        resealed = deepcopy(contract)
        resealed["trajectory"]["subject_timeout_seconds"] = 901
        resealed["contract_sha256"] = digest(
            {key: value for key, value in resealed.items() if key != "contract_sha256"}
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "scientific fields"):
            validate_contract(resealed)

    def test_task_pool_rejects_repository_reuse(self) -> None:
        tasks = fixture_tasks()
        tasks[-1]["repository"] = tasks[0]["repository"]
        with self.assertRaisesRegex(ExperimentConfigurationError, "repositories must be distinct"):
            generate_schedule(tasks)

    def test_hash_chained_jsonl_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            append_event(path, "note", {"value": 1})
            append_event(path, "note", {"value": 2})
            events = read_events(path)
            self.assertEqual(
                events[1]["previous_event_sha256"], events[0]["event_sha256"]
            )
            lines = path.read_text(encoding="utf-8").splitlines()
            changed = json.loads(lines[0])
            changed["payload"]["value"] = 99
            lines[0] = json.dumps(changed, sort_keys=True, separators=(",", ":"))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ExperimentConfigurationError, "digest mismatch"):
                read_events(path)

    def test_attempt_2_requires_authorization_and_completed_cell_never_repeats(
        self,
    ) -> None:
        contract = fixture_contract()
        cell_id = contract["schedule"]["cells"][0]["cell_id"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            record_attempt_start(path, contract, cell_id, 1)
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "lacks explicit authorization"
            ):
                record_attempt_start(path, contract, cell_id, 2)
            authorize_attempt_2(
                path, contract, cell_id, "qualified infrastructure invalidity"
            )
            record_attempt_start(path, contract, cell_id, 2)
            record_cell_completed(path, contract, cell_id, 2)
            with self.assertRaisesRegex(ExperimentConfigurationError, "completed cell"):
                record_attempt_start(path, contract, cell_id, 3)
            self.assertEqual(read_attempt_ledger(path, contract), read_events(path))

    def test_global_subject_cap_includes_qualification(self) -> None:
        contract = fixture_contract(qualification=4)
        events = []
        for index, cell in enumerate(contract["schedule"]["cells"]):
            events.append(
                {
                    "event_type": "attempt_started",
                    "payload": {"cell_id": cell["cell_id"], "attempt": 1},
                }
            )
            events.append(
                {
                    "event_type": "subject_invocation_started",
                    "payload": {
                        "cell_id": cell["cell_id"],
                        "attempt": 1,
                        "prompt_sha256": "1" * 64,
                        "command_sha256": "2" * 64,
                        "codex_executable_sha256": "3" * 64,
                    },
                }
            )
            if index < 28:
                events.append(
                    {
                        "event_type": "attempt_2_authorized",
                        "payload": {
                            "cell_id": cell["cell_id"],
                            "next_attempt": 2,
                            "reason": "fixture",
                            "classification": "official_evaluator_error",
                        },
                    }
                )
                events.append(
                    {
                        "event_type": "attempt_started",
                        "payload": {"cell_id": cell["cell_id"], "attempt": 2},
                    }
                )
                events.append(
                    {
                        "event_type": "subject_invocation_started",
                        "payload": {
                            "cell_id": cell["cell_id"],
                            "attempt": 2,
                            "prompt_sha256": "1" * 64,
                            "command_sha256": "2" * 64,
                            "codex_executable_sha256": "3" * 64,
                        },
                    }
                )
        validate_attempt_ledger(contract, events)
        final_cell = contract["schedule"]["cells"][-1]["cell_id"]
        events.append(
            {
                "event_type": "attempt_2_authorized",
                "payload": {
                    "cell_id": final_cell,
                    "next_attempt": 2,
                    "reason": "fixture",
                    "classification": "official_evaluator_incomplete",
                },
            }
        )
        events.append(
            {
                "event_type": "attempt_started",
                "payload": {"cell_id": final_cell, "attempt": 2},
            }
        )
        events.append(
            {
                "event_type": "subject_invocation_started",
                "payload": {
                    "cell_id": final_cell,
                    "attempt": 2,
                    "prompt_sha256": "1" * 64,
                    "command_sha256": "2" * 64,
                    "codex_executable_sha256": "3" * 64,
                },
            }
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "cap exceeded"):
            validate_attempt_ledger(contract, events)

    def test_usage_requires_current_fields_and_unambiguous_final_scope(self) -> None:
        usage = {
            "input_tokens": 100,
            "cached_input_tokens": 30,
            "cache_write_input_tokens": 20,
            "output_tokens": 15,
            "reasoning_output_tokens": 5,
        }
        self.assertEqual(
            validate_usage(usage, measurement_scope=USAGE_MEASUREMENT_SCOPE),
            {
                "provider_reported": usage,
                "derived": {"calculated_fresh_input_tokens": 50},
            },
        )
        for field in tuple(usage):
            incomplete = dict(usage)
            incomplete.pop(field)
            with self.assertRaises(ExperimentConfigurationError):
                validate_usage(incomplete, measurement_scope=USAGE_MEASUREMENT_SCOPE)
        negative = dict(usage, cache_write_input_tokens=-1)
        with self.assertRaisesRegex(ExperimentConfigurationError, "non-negative"):
            validate_usage(negative, measurement_scope=USAGE_MEASUREMENT_SCOPE)
        provider_total = dict(usage, total_tokens=115)
        with self.assertRaisesRegex(ExperimentConfigurationError, "unexpected"):
            validate_usage(provider_total, measurement_scope=USAGE_MEASUREMENT_SCOPE)
        with self.assertRaisesRegex(ExperimentConfigurationError, "ambiguous"):
            validate_usage(usage, measurement_scope="intermediate_cumulative")


if __name__ == "__main__":
    unittest.main()
