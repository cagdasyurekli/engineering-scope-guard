from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import (
    append_ledger_event,
    build_contract,
    read_ledger,
)
from engineering_scope_guard.pilot_integrity import (
    assess_ledger_resume,
    capture_repository_baseline,
    classify_provider_event,
    inspect_file_auth,
    parse_provider_trace,
    provision_file_auth,
    remove_file_auth,
    repository_state,
    subject_patch_from_baseline,
)
from engineering_scope_guard.pilot_runner import (
    append_runner_event,
    build_launch_request,
    initialize_ledger,
)
from scripts.pilot_runner import LiveBackend, run_auth_canary

ROOT = Path(__file__).resolve().parents[1]
def git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


class PilotIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = build_contract(ROOT)

    def test_missing_or_unsafe_file_auth_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "source"
            home.mkdir()
            with self.assertRaisesRegex(ExperimentConfigurationError, "auth.json"):
                inspect_file_auth(home)
            auth = home / "auth.json"
            auth.write_text('{"auth_mode":"chatgpt","tokens":{}}\n')
            auth.chmod(0o644)
            with self.assertRaisesRegex(ExperimentConfigurationError, "permissions"):
                inspect_file_auth(home)

    def test_file_auth_bridge_copies_only_auth_and_removes_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "auth.json").write_text(
                '{"auth_mode":"chatgpt","tokens":{}}\n'
            )
            (source / "auth.json").chmod(0o600)
            (source / "history.jsonl").write_text("private history\n")
            (source / "state.sqlite").write_bytes(b"state")

            metadata = provision_file_auth(source, target)

            self.assertEqual(metadata["storage"], "file")
            self.assertEqual(metadata["login_method"], "chatgpt")
            self.assertEqual(metadata["copied_artifacts"], ["auth.json"])
            self.assertEqual({path.name for path in target.iterdir()}, {"auth.json"})
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            self.assertEqual((target / "auth.json").stat().st_mode & 0o777, 0o600)
            self.assertNotIn("tokens", json.dumps(metadata))

            remove_file_auth(target)
            self.assertFalse((target / "auth.json").exists())

    def test_live_auth_canary_is_fresh_and_persists_only_sanitized_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            (source / "auth.json").write_text(
                json.dumps({"auth_mode": "chatgpt", "tokens": {}})
            )
            (source / "auth.json").chmod(0o600)
            contract = {
                "subject": {"model": "fixture-model", "reasoning_effort": "medium"}
            }
            backend = SimpleNamespace(
                source_codex_home=source,
                codex_binary="codex",
                contract=contract,
                _environment=lambda home: {"CODEX_HOME": str(home)},
            )

            def runner(*_args, **kwargs):
                self.assertTrue(Path(kwargs["env"]["CODEX_HOME"]).is_dir())
                trace = b"\n".join(
                    (
                        b'{"type":"thread.started","thread_id":"not-persisted"}',
                        b'{"type":"item.completed","item":{"type":"agent_message","text":"private response text"}}',
                        b'{"type":"turn.completed","usage":{"input_tokens":3,"cached_input_tokens":0,"output_tokens":1,"reasoning_output_tokens":0}}',
                    )
                ) + b"\n"
                return 0, False, trace, b""

            result = run_auth_canary(backend, 1, runner=runner)

            serialized = json.dumps(result)
            self.assertEqual(result["status"], "pass")
            self.assertTrue(result["credential_material_removed"])
            self.assertNotIn("tokens", result["auth_bridge"])
            self.assertNotIn("private response text", serialized)
            self.assertNotIn("not-persisted", serialized)

    def test_live_environment_does_not_inherit_api_key_credentials(self) -> None:
        isolated_home = Path("/content-free/isolated-codex-home")
        backend = SimpleNamespace(evaluator_root=ROOT)
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "must-not-cross", "CODEX_API_KEY": "must-not-cross"},
        ):
            environment = LiveBackend._environment(backend, isolated_home)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("CODEX_API_KEY", environment)
        self.assertEqual(environment["CODEX_HOME"], str(isolated_home))

    def test_provider_error_classification_is_context_bounded(self) -> None:
        cases = (
            ({"type": "error", "error": {"code": "api_connection_error"}}, True),
            ({"type": "error", "error": {"code": "authentication_error"}}, True),
            ({"type": "error", "message": "status 401 Unauthorized"}, True),
            (
                {"type": "turn.failed", "error": {"message": "403 Forbidden: invalid token"}},
                True,
            ),
            ({"type": "error", "message": "unrecognized transport shape"}, False),
            (
                {"type": "item.completed", "item": {"type": "agent_message", "text": "401"}},
                False,
            ),
            ({"type": "turn.failed", "error": {"message": "model could not solve task"}}, False),
        )
        for event, expected in cases:
            with self.subTest(event=event):
                self.assertEqual(classify_provider_event(event), expected)

    def test_observed_401_schema_and_partial_usage_are_provider_failures(self) -> None:
        observed_schema = b"\n".join(
            (
                b'{"type":"thread.started","thread_id":"content-free"}',
                b'{"type":"turn.started"}',
                b'{"type":"error","message":"unexpected status 401 Unauthorized"}',
                b'{"type":"turn.failed","error":{"message":"unexpected status 401 Unauthorized"}}',
            )
        ) + b"\n"
        details = parse_provider_trace(observed_schema)
        self.assertTrue(details["provider_infrastructure_failure"])
        self.assertEqual(details["terminal_event"], "turn.failed")
        partial = b"\n".join(
            (
                b'{"type":"thread.started","thread_id":"sanitized"}',
                b'{"type":"turn.completed","usage":{"input_tokens":3,"cached_input_tokens":0,"output_tokens":1,"reasoning_output_tokens":0}}',
                b'{"type":"error","message":"unexpected status 401 Unauthorized"}',
            )
        ) + b"\n"
        self.assertTrue(parse_provider_trace(partial)["provider_infrastructure_failure"])

    def test_repository_baseline_excludes_pre_subject_dirt_from_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            derived = root / "derived"
            repository.mkdir()
            derived.mkdir()
            git(repository, "init", "-q")
            git(repository, "config", "user.email", "fixture@example.invalid")
            git(repository, "config", "user.name", "Fixture")
            (repository / "tracked.txt").write_text("clean head\n")
            git(repository, "add", "tracked.txt")
            git(repository, "commit", "-qm", "base")

            (repository / "tracked.txt").write_text("image baseline\n")
            (repository / "image-residue.txt").write_text("pre-subject\n")
            (repository / ".gitignore").write_text("image-ignored.txt\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-qm", "ignore fixture residue")
            (repository / "image-ignored.txt").write_text("ignored pre-subject\n")
            state = repository_state(repository)
            self.assertEqual(state["tracked_worktree"], ["tracked.txt"])
            self.assertEqual(state["untracked"], ["image-residue.txt"])
            self.assertEqual(state["ignored"], ["image-ignored.txt"])

            baseline = capture_repository_baseline(repository, derived)
            self.assertEqual(subject_patch_from_baseline(repository, derived, baseline), b"")

            (repository / "tracked.txt").write_text("image baseline\nsubject change\n")
            (repository / "subject-new.txt").write_text("new subject file\n")
            patch = subject_patch_from_baseline(repository, derived, baseline)
            self.assertIn(b"+subject change", patch)
            self.assertIn(b"subject-new.txt", patch)
            self.assertNotIn(b"-clean head", patch)
            self.assertNotIn(b"+image baseline", patch)
            self.assertNotIn(b"image-residue.txt", patch)

    def test_terminal_failed_attempt_is_immutable_and_has_no_legal_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "pilot-ledger.jsonl"
            initialize_ledger(self.contract, ledger)
            request = build_launch_request(
                self.contract,
                self.contract["schedule"]["cells"][0],
                Path(directory) / "state",
                1,
            )
            append_runner_event(ledger, "attempt_started", request)
            receipt = {
                **request,
                "started_at": "2026-08-28T00:00:00+00:00",
                "ended_at": "2026-08-28T00:00:01+00:00",
                "termination": "malformed_incomplete_measurement",
                "evaluator_result": {"resolved": None},
                "usage": {},
                "usage_complete": False,
                "admissible_under_contract": False,
                "deviations": [],
            }
            append_runner_event(ledger, "attempt_finished", receipt)
            append_runner_event(
                ledger,
                "batch_stopped",
                {"cell_id": request["cell_id"], "termination": receipt["termination"]},
            )
            before = ledger.read_bytes()
            assessment = assess_ledger_resume(self.contract, read_ledger(ledger))
            self.assertFalse(assessment["legal_resume"])
            self.assertEqual(assessment["next_legal_action"], "batch_stopped")
            self.assertFalse(assessment["prior_attempt_is_rerunnable"])
            self.assertEqual(assessment["hypothetical_provider_retry_budget_units"], 1)
            self.assertEqual(ledger.read_bytes(), before)

    def test_provider_attempt_authorizes_same_cell_rerun_without_mutating_during_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "pilot-ledger.jsonl"
            initialize_ledger(self.contract, ledger)
            request = build_launch_request(
                self.contract,
                self.contract["schedule"]["cells"][0],
                Path(directory) / "state",
                1,
            )
            append_ledger_event(ledger, "attempt_started", request)
            receipt = {
                **request,
                "started_at": "2026-08-28T00:00:00+00:00",
                "ended_at": "2026-08-28T00:00:01+00:00",
                "termination": "provider_api_infrastructure_failure",
                "evaluator_result": {"resolved": None},
                "usage": {},
                "usage_complete": False,
                "admissible_under_contract": False,
                "deviations": [],
            }
            append_ledger_event(ledger, "attempt_finished", receipt)
            before = ledger.read_bytes()
            assessment = assess_ledger_resume(self.contract, read_ledger(ledger))
            self.assertTrue(assessment["legal_resume"])
            self.assertEqual(assessment["next_legal_action"], "authorize_infrastructure_rerun")
            self.assertTrue(assessment["prior_attempt_is_rerunnable"])
            self.assertEqual(assessment["future_retry_budget_units"], 1)
            self.assertEqual(ledger.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
