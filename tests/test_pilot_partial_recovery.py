from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engineering_scope_guard.pilot_contract import build_contract, read_ledger
from engineering_scope_guard.pilot_partial_recovery import (
    assess_recovery_evidence,
    build_partial_recovery_preview,
)
from engineering_scope_guard.pilot_runner import (
    append_runner_event,
    build_launch_request,
    initialize_ledger,
)
from engineering_scope_guard.pilot_successor import (
    build_successor_authorization,
    initialize_successor_ledger,
    next_successor_legal_action,
)

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


class PilotPartialRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = build_contract(ROOT)

    def _preserved_partial(self, root: Path, *, report: bool = False) -> dict[str, Path]:
        contract_path = root / "experiment/pilot_execution_contract.json"
        authorization_path = root / "experiment/pilot_successor_batch_authorization.json"
        integrity_path = root / "experiment/pilot_execution_integrity_qualification.json"
        predecessor = root / ".local/pilot-runner/pilot-ledger.jsonl"
        successor = root / ".local/pilot-successor-runner/pilot-successor-ledger.jsonl"
        write_json(contract_path, self.contract)
        initialize_ledger(self.contract, predecessor)
        old_request = build_launch_request(
            self.contract, self.contract["schedule"]["cells"][0], root / "old-state", 1
        )
        append_runner_event(predecessor, "attempt_started", old_request)
        old_receipt = {
            **old_request,
            "started_at": "2026-08-28T00:00:00+00:00",
            "ended_at": "2026-08-28T00:00:01+00:00",
            "termination": "malformed_incomplete_measurement",
            "evaluator_result": {"resolved": None, "rounds": 0},
            "usage": {},
            "usage_complete": False,
            "admissible_under_contract": False,
            "deviations": [],
        }
        append_runner_event(predecessor, "attempt_finished", old_receipt)
        append_runner_event(
            predecessor,
            "batch_stopped",
            {"cell_id": old_request["cell_id"], "termination": old_receipt["termination"]},
        )
        integrity = {
            "contract_sha256": self.contract["contract_sha256"],
            "repairs_qualified": True,
            "provider_parser": {
                "observed_message_only_401_classified_as_provider_infrastructure": True
            },
            "materialization": {"status": "pass"},
            "ledger": {
                "terminal_event_sha256": read_ledger(predecessor)[-1]["event_sha256"],
                "unchanged": True,
            },
            "experimental_activity": {
                "pilot_subject_invocations": 0,
                "pilot_evaluator_invocations": 0,
                "policy_comparisons": 0,
            },
        }
        write_json(integrity_path, integrity)
        authorization = build_successor_authorization(
            self.contract, read_ledger(predecessor), integrity
        )
        write_json(authorization_path, authorization)
        events = initialize_successor_ledger(self.contract, authorization, successor)
        action = next_successor_legal_action(self.contract, authorization, events)
        state = root / ".local/pilot-successor-runner"
        request = build_launch_request(self.contract, action["cell"], state, 2)
        request["attempt_started_at"] = "2026-08-28T00:00:02+00:00"
        append_runner_event(successor, "attempt_started", request)
        roots = {name: Path(value) for name, value in request["isolation_roots"].items()}
        roots["raw"].mkdir(parents=True)
        roots["derived"].mkdir(parents=True)
        trace = roots["raw"] / "codex-round-0.jsonl"
        trace.write_text(
            "\n".join(
                (
                    json.dumps({"type": "thread.started", "thread_id": "sanitized-session"}),
                    json.dumps(
                        {
                            "type": "turn.completed",
                            "usage": {
                                "input_tokens": 10,
                                "cached_input_tokens": 2,
                                "output_tokens": 4,
                                "reasoning_output_tokens": 1,
                            },
                        }
                    ),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (roots["derived"] / "pre-subject.index").write_bytes(b"baseline")
        (roots["derived"] / "subject.index").write_bytes(b"subject")
        (roots["derived"] / "prediction.patch").write_bytes(b"")
        write_json(
            roots["derived"] / "prediction.json",
            {request["actual_task_id"]: {"model_patch": ""}},
        )
        output = roots["raw"] / "evaluator-round-0"
        output.mkdir()
        (output / "command.stdout").write_bytes(b"sanitized")
        (output / "command.stderr").write_bytes(b"")
        write_json(
            output / "results.json",
            {
                "submitted_ids": [request["actual_task_id"]],
                "empty_patch_ids": [request["actual_task_id"]],
            },
        )
        if report:
            write_json(
                output / request["actual_task_id"] / "report.json",
                {"resolved": True, "FAIL_TO_PASS": {}, "PASS_TO_PASS": {}},
            )
        return {
            "contract_path": contract_path,
            "authorization_path": authorization_path,
            "integrity_path": integrity_path,
            "predecessor_path": predecessor,
            "successor_ledger_path": successor,
        }

    def test_recovery_evidence_requires_complete_fields_and_legal_transition(self) -> None:
        complete = assess_recovery_evidence(
            {"timing": True, "usage": True, "evaluator": True},
            valid_finalization_transition=True,
        )
        self.assertEqual(complete, {"recoverable": True, "legal": True, "missing_or_ambiguous": []})
        missing = assess_recovery_evidence(
            {"timing": True, "usage": True, "evaluator": False},
            valid_finalization_transition=True,
        )
        self.assertFalse(missing["recoverable"])
        self.assertFalse(missing["legal"])
        self.assertEqual(missing["missing_or_ambiguous"], ["evaluator"])

    def test_real_shape_preview_fails_closed_without_execution_or_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._preserved_partial(root)
            before = paths["successor_ledger_path"].read_bytes()
            with patch.object(
                subprocess,
                "Popen",
                side_effect=AssertionError("recovery preview launched a process"),
            ):
                preview = build_partial_recovery_preview(
                    root, **paths, contract_source_root=ROOT
                )
            self.assertEqual(preview["decision"], "STOP PILOT")
            self.assertFalse(preview["recovery"]["recoverable"])
            self.assertFalse(preview["evaluator"]["structured_result_complete"])
            self.assertTrue(preview["subject"]["usage_complete"])
            self.assertEqual(preview["subject"]["usage"]["total_tokens"], 14)
            self.assertEqual(preview["expected_state"]["ledger_events_to_append"], [])
            self.assertEqual(preview["expected_state"]["additional_reruns_consumed"], 0)
            self.assertFalse(preview["rerun"]["legal"])
            self.assertEqual(preview["experimental_activity"]["receipts_created"], 0)
            self.assertEqual(
                preview["experimental_activity"]["valid_completed_cells"], 0
            )
            self.assertEqual(preview["experimental_activity"]["policy_comparisons"], 0)
            self.assertEqual(paths["successor_ledger_path"].read_bytes(), before)

    def test_complete_evaluator_artifacts_are_recognized_but_do_not_fill_timing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._preserved_partial(root, report=True)
            preview = build_partial_recovery_preview(
                root, **paths, contract_source_root=ROOT
            )
            self.assertTrue(preview["evaluator"]["structured_result_complete"])
            self.assertIn("receipt_started_at", preview["missing_or_ambiguous"])
            self.assertIn("receipt_ended_at", preview["missing_or_ambiguous"])
            self.assertFalse(preview["recovery"]["recoverable"])


if __name__ == "__main__":
    unittest.main()
