from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sanitize_pilot_host_qualification.py"
SPEC = importlib.util.spec_from_file_location("sanitize_pilot_host", SCRIPT)
assert SPEC and SPEC.loader
sanitizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sanitizer)


class SanitizePilotHostQualificationTests(unittest.TestCase):
    def test_run_projection_removes_raw_material_and_local_references(self) -> None:
        value = {
            "status": "complete",
            "procedure": {"dataset_snapshot_path": "/Users/person/private/data"},
            "tasks": [
                {
                    "runs": [
                        {
                            "outcome": "PASS",
                            "classification": "official-gold-success",
                            "report": "file:///Users/person/private/report.json",
                            "raw_output_dir": ".local/private-output",
                            "official_image": {"id": "sha256:fixture"},
                        }
                    ]
                }
            ],
        }

        result = sanitizer.sanitize(value)

        run = result["tasks"][0]["runs"][0]
        self.assertEqual(
            run,
            {
                "outcome": "PASS",
                "classification": "official-gold-success",
                "official_image": {"id": "sha256:fixture"},
            },
        )
        self.assertEqual(
            result["procedure"]["dataset_snapshot_path"],
            "<redacted-local-reference>",
        )
        self.assertNotIn("raw_output_dir", result["tasks"][0]["runs"][0])
        self.assertFalse(result["public_sanitization"]["scientific_outcomes_changed"])

    def test_repository_receipt_is_the_canonical_public_projection(self) -> None:
        receipt = ROOT / "experiment" / "pilot_host_qualification.json"
        self.assertEqual(receipt.read_bytes(), sanitizer.sanitized_bytes(receipt))
        lowered = receipt.read_bytes().lower()
        for forbidden in (b"/users/", b"file://", b"/.codex/", b"/.local/"):
            self.assertNotIn(forbidden, lowered)
        value = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertNotIn(
            "raw_output_dir",
            {
                key
                for task in value["tasks"]
                for run in task["runs"]
                for key in run
            },
        )


if __name__ == "__main__":
    unittest.main()
