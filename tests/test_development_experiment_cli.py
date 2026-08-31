import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "development_experiment.py"
TRACE = ROOT / "tests" / "fixtures" / "traces" / "codex-0.150.1-exec.jsonl"


class DevelopmentExperimentCliTests(unittest.TestCase):
    def test_prepare_keeps_non_sensitive_json_stdout_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(ROOT / "src")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "prepare",
                    "--source",
                    str(ROOT / "tests" / "fixtures" / "demo_before"),
                    "--state-dir",
                    str(Path(temporary) / "state"),
                    "--policies-dir",
                    str(ROOT / "experiment" / "arms"),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stderr, "")
            receipt = json.loads(completed.stdout)
            self.assertEqual(
                receipt["schema_name"], "engineering-scope-guard.development-cells"
            )
            self.assertEqual(receipt["arms"], ["baseline", "short", "full"])

    def test_record_writes_private_billing_data_without_copying_it_to_stdout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution = root / "execution.json"
            execution.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "task_id": "development-01",
                        "run_id": "seed-01",
                        "arm": "short",
                        "wall_time_ms": 123,
                        "timed_out": False,
                        "process_exit_code": 0,
                    }
                ),
                encoding="utf-8",
            )
            verification = root / "verification.json"
            verification.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "results": [{"name": "unit", "kind": "test", "exit_code": 0}],
                    }
                ),
                encoding="utf-8",
            )
            events = root / "events.jsonl"
            events.write_text(
                json.dumps(
                    {
                        "schema_name": "engineering-scope-guard.event",
                        "schema_version": 1,
                        "event": "structural_delta",
                        "private_extension": {"secret": "PRIVATE-EVENT"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            billing = root / "billing.json"
            billing.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "currency": "PRIVATE-CURRENCY",
                        "components": {"private-provider-charge": "12.34"},
                    }
                ),
                encoding="utf-8",
            )
            output = root / "record.json"

            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(ROOT / "src")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "record",
                    "--trace",
                    str(TRACE),
                    "--execution",
                    str(execution),
                    "--verification",
                    str(verification),
                    "--v0-events",
                    str(events),
                    "--billing",
                    str(billing),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(completed.stderr, "")
            record = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(record["billing"]["currency"], "PRIVATE-CURRENCY")
            self.assertEqual(
                record["billing"]["components"]["private-provider-charge"], "12.34"
            )
            self.assertEqual(
                record["v0_events"][0]["private_extension"]["secret"], "PRIVATE-EVENT"
            )


if __name__ == "__main__":
    unittest.main()
