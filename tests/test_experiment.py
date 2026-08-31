import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import (
    ARMS,
    PILOT_ARMS,
    ExperimentConfigurationError,
    capture_run_record,
    prepare_cells,
    prepare_pilot_readiness_cells,
    run_isolation_canary,
    run_pilot_readiness_isolation_canary,
)


ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "experiment" / "arms"
SOURCE = ROOT / "tests" / "fixtures" / "demo_before"
TRACE = ROOT / "tests" / "fixtures" / "traces" / "codex-0.150.1-exec.jsonl"


def tree_fingerprint(root: Path) -> str:
    values: list[bytes] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            values.extend((b"link", relative, path.readlink().as_posix().encode()))
        elif path.is_file():
            values.extend((b"file", relative, path.read_bytes()))
        elif path.is_dir():
            values.extend((b"dir", relative))
    return hashlib.sha256(b"\0".join(values)).hexdigest()


class ExperimentIsolationTests(unittest.TestCase):
    def test_prepare_creates_exactly_three_byte_identical_isolated_cells(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            before = tree_fingerprint(SOURCE)
            manifest = prepare_cells(SOURCE, state, POLICIES)

            self.assertEqual(manifest["arms"], list(ARMS))
            self.assertEqual([cell["arm"] for cell in manifest["cells"]], list(ARMS))
            self.assertEqual(
                {cell["repository_fingerprint"] for cell in manifest["cells"]},
                {manifest["source_repository_fingerprint"]},
            )
            self.assertIsNone(manifest["cells"][0]["intervention"])
            self.assertFalse((state / "cells" / "baseline" / "intervention.txt").exists())
            self.assertEqual(
                (state / "cells" / "short" / "intervention.txt").read_bytes(),
                (POLICIES / "short.txt").read_bytes(),
            )
            self.assertEqual(tree_fingerprint(SOURCE), before)

    def test_prepare_rejects_state_inside_source(self):
        with self.assertRaisesRegex(
            ExperimentConfigurationError, "outside the source repository"
        ):
            prepare_cells(SOURCE, SOURCE / "experiment-state", POLICIES)

    def test_prepare_pilot_readiness_uses_only_baseline_and_surviving_short_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            manifest = prepare_pilot_readiness_cells(SOURCE, state, POLICIES)

            self.assertEqual(manifest["arms"], list(PILOT_ARMS))
            self.assertEqual(
                [cell["arm"] for cell in manifest["cells"]], list(PILOT_ARMS)
            )
            self.assertFalse((state / "cells" / "full").exists())
            self.assertFalse((state / "cells" / "baseline" / "intervention.txt").exists())
            self.assertEqual(
                (state / "cells" / "short" / "intervention.txt").read_bytes(),
                (POLICIES / "short.txt").read_bytes(),
            )

    def test_canary_is_deterministic_and_proves_separation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = run_isolation_canary(SOURCE, root / "first", POLICIES)
            second = run_isolation_canary(SOURCE, root / "second", POLICIES)

            self.assertEqual(first, second)
            self.assertEqual(first["status"], "pass")
            self.assertTrue(first["byte_identical_repository_starts"])
            self.assertTrue(first["separate_codex_state"])
            self.assertTrue(first["separate_raw_and_derived_output"])
            self.assertTrue(first["isolated_process_envelopes"])
            self.assertTrue(first["no_cross_arm_intervention_contamination"])
            self.assertEqual(
                (root / "first" / "canary.json").read_bytes(),
                (root / "second" / "canary.json").read_bytes(),
            )

    def test_pilot_readiness_canary_is_deterministic_and_excludes_full_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = run_pilot_readiness_isolation_canary(
                SOURCE, root / "first", POLICIES
            )
            second = run_pilot_readiness_isolation_canary(
                SOURCE, root / "second", POLICIES
            )

            self.assertEqual(first, second)
            self.assertEqual(first["arms"], list(PILOT_ARMS))
            self.assertEqual(first["status"], "pass")
            self.assertFalse((root / "first" / "cells" / "full").exists())
            self.assertEqual(
                (root / "first" / "canary.json").read_bytes(),
                (root / "second" / "canary.json").read_bytes(),
            )

    def test_arm_policy_assets_match_current_candidate_document(self):
        candidate = (ROOT / "docs" / "CANDIDATE_POLICY.md").read_text(encoding="utf-8")
        short = (POLICIES / "short.txt").read_text(encoding="utf-8").strip()
        full = (POLICIES / "full.txt").read_text(encoding="utf-8").strip()
        self.assertIn(f"> {short}", candidate)
        for paragraph in full.split("\n\n"):
            self.assertIn("> " + paragraph.replace("\n", "\n> "), candidate)


class ExperimentCaptureTests(unittest.TestCase):
    def write_json(self, root: Path, name: str, value: object) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def write_v0_events(self, root: Path) -> Path:
        path = root / "events.jsonl"
        path.write_text(
            json.dumps(
                {
                    "schema_name": "engineering-scope-guard.event",
                    "schema_version": 1,
                    "event": "structural_delta",
                    "files": {"counts": {"added": 0, "deleted": 0, "modified": 0}},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_capture_records_usage_turns_verification_billing_and_v0(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution = self.write_json(
                root,
                "execution.json",
                {
                    "schema_version": 1,
                    "task_id": "development-01",
                    "run_id": "seed-01",
                    "arm": "full",
                    "wall_time_ms": 1234,
                    "timed_out": False,
                    "process_exit_code": 0,
                },
            )
            verification = self.write_json(
                root,
                "verification.json",
                {
                    "schema_version": 1,
                    "results": [{"name": "unit", "kind": "test", "exit_code": 0}],
                },
            )
            billing = self.write_json(
                root,
                "billing.json",
                {
                    "schema_version": 1,
                    "currency": "USD",
                    "components": {"input": "0.01", "output": "0.02"},
                },
            )
            output = root / "record.json"
            record = capture_run_record(
                TRACE,
                execution,
                verification,
                self.write_v0_events(root),
                output,
                billing,
            )
            repeated_output = root / "record-repeated.json"
            repeated = capture_run_record(
                TRACE,
                execution,
                verification,
                root / "events.jsonl",
                repeated_output,
                billing,
            )

            self.assertEqual(record["identity"]["arm"], "full")
            self.assertEqual(
                record["turns"],
                {"started": 1, "completed": 1, "failed": 0, "balanced": True},
            )
            self.assertEqual(
                record["usage"]["components"],
                {
                    "cached_input_tokens": 0,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 0,
                },
            )
            self.assertEqual(record["billing"]["status"], "available")
            self.assertTrue(record["verification"]["all_passed"])
            self.assertEqual(record["v0_events"][0]["event"], "structural_delta")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), record)
            self.assertEqual(repeated, record)
            self.assertEqual(repeated_output.read_bytes(), output.read_bytes())

    def test_capture_preserves_timeout_and_unavailable_billing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution = self.write_json(
                root,
                "execution.json",
                {
                    "schema_version": 1,
                    "task_id": "development-01",
                    "run_id": "seed-02",
                    "arm": "baseline",
                    "wall_time_ms": 60000,
                    "timed_out": True,
                    "process_exit_code": None,
                },
            )
            verification = self.write_json(
                root,
                "verification.json",
                {"schema_version": 1, "results": []},
            )
            record = capture_run_record(
                TRACE,
                execution,
                verification,
                self.write_v0_events(root),
                root / "record.json",
            )
            self.assertTrue(record["execution"]["timed_out"])
            self.assertEqual(record["billing"]["status"], "unavailable")
            self.assertFalse(record["verification"]["all_passed"])

    def test_capture_rejects_timeout_with_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution = self.write_json(
                root,
                "execution.json",
                {
                    "schema_version": 1,
                    "task_id": "development-01",
                    "run_id": "seed-02",
                    "arm": "baseline",
                    "wall_time_ms": 1,
                    "timed_out": True,
                    "process_exit_code": 124,
                },
            )
            verification = self.write_json(
                root,
                "verification.json",
                {"schema_version": 1, "results": []},
            )
            with self.assertRaisesRegex(ExperimentConfigurationError, "must not have"):
                capture_run_record(
                    TRACE,
                    execution,
                    verification,
                    self.write_v0_events(root),
                    root / "record.json",
                )


if __name__ == "__main__":
    unittest.main()
