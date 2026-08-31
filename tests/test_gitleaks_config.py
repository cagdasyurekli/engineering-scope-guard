from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".gitleaks.toml"


class GitleaksConfigTests(unittest.TestCase):
    def test_frozen_receipt_allowlist_is_narrow(self) -> None:
        value = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(value["extend"], {"useDefault": True})
        self.assertEqual(len(value["allowlists"]), 2)

        allowlist = value["allowlists"][0]
        self.assertEqual(allowlist["targetRules"], ["generic-api-key"])
        self.assertEqual(allowlist["condition"], "AND")
        self.assertEqual(allowlist["regexTarget"], "line")

        line_pattern = re.compile(allowlist["regexes"][0])
        path_pattern = re.compile(allowlist["paths"][0])
        digest = "a" * 64
        self.assertIsNotNone(
            line_pattern.fullmatch(f'    "confirmation_token_sha256": "{digest}",')
        )
        self.assertIsNone(line_pattern.fullmatch(f'    "api_key": "{digest}",'))
        self.assertIsNotNone(
            path_pattern.search("experiment/pilot_v3_qualification.json")
        )
        self.assertIsNone(path_pattern.search("experiment/not_allowlisted.json"))

        revision_allowlist = value["allowlists"][1]
        self.assertEqual(
            revision_allowlist["targetRules"], ["sourcegraph-access-token"]
        )
        self.assertEqual(revision_allowlist["condition"], "AND")
        self.assertEqual(revision_allowlist["regexTarget"], "line")

        revision_pattern = re.compile(revision_allowlist["regexes"][0])
        revision_path_pattern = re.compile(revision_allowlist["paths"][0])
        revision = "b" * 40
        for key in ("dataset_revision", "evaluator_revision", "repolaunch_revision"):
            self.assertIsNotNone(
                revision_pattern.fullmatch(f'    "{key}": "{revision}",')
            )
        self.assertIsNone(
            revision_pattern.fullmatch(f'    "sourcegraph_token": "{revision}",')
        )
        self.assertIsNotNone(
            revision_path_pattern.search("experiment/pilot_host_qualification.json")
        )
        self.assertIsNone(
            revision_path_pattern.search("experiment/not_allowlisted.json")
        )


if __name__ == "__main__":
    unittest.main()
