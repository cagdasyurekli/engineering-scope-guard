from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from scripts.esg_rr_001_audit import _task_vectors, audit

ROOT = Path(__file__).resolve().parents[1]


class Esgrr001AuditTests(unittest.TestCase):
    def test_public_identity_and_core_analysis_audit_passes(self) -> None:
        result = audit(ROOT, "all")
        self.assertEqual(result["version"], "0.6")
        self.assertEqual(result["level_1"]["status"], "pass")
        level_two = result["level_2"]
        self.assertEqual(level_two["population"]["complete_task_clusters"], 7)
        self.assertEqual(
            level_two["paired_acceptance"][
                "short_minus_baseline_percentage_points"
            ],
            -14.2857,
        )
        self.assertEqual(
            level_two["paired_work"]["input_tokens"]["short_over_baseline_ratio"],
            1.222743,
        )
        self.assertEqual(
            level_two["paired_work"]["wall_seconds"]["short_over_baseline_ratio"],
            1.326281,
        )
        self.assertEqual(
            level_two["discordance"],
            {
                "baseline_only_accepted": 3,
                "both_accepted": 3,
                "both_failed": 7,
                "short_only_accepted": 1,
            },
        )

    def test_population_drift_fails_closed(self) -> None:
        diagnostic = json.loads(
            (ROOT / "experiment/pilot_v3_c_short_mechanism_diagnostic.json").read_text()
        )
        changed = copy.deepcopy(diagnostic)
        changed["tasks"].pop()
        with self.assertRaisesRegex(ExperimentConfigurationError, "exactly seven"):
            _task_vectors(changed, "acceptance")

    def test_report_has_required_claim_boundaries_and_valid_local_links(self) -> None:
        paths = (
            ROOT / "docs/reports/ESG-RR-001.md",
            ROOT / "README.md",
            ROOT / "docs/CLAIMS_CHANGELOG.md",
        )
        report = paths[0].read_text(encoding="utf-8")
        for heading in (
            "## Abstract",
            "## Exact treatment",
            "### Acceptance first",
            "## Post-hoc mechanism evidence",
            "## Evidence against the adverse narrative and alternatives",
            "## Reproducibility and public artifact manifest",
            "## Conflict disclosure and mitigations",
            "## Corrections and versioning",
            "## Citation",
        ):
            self.assertIn(heading, report)
        for claim_id in range(1, 8):
            self.assertIn(f"ESG-RR-001-C0{claim_id}", report)
        self.assertIn("Version 0.6 republication", report)
        self.assertIn("Version 0.2 correction", report)
        self.assertNotIn("immutable tag `esg-rr-001-v0.1`", report)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths).lower()
        for forbidden in (
            "minimality prompts make coding agents worse",
            "scope guard saves tokens",
            "coding agents waste x% of their tokens",
            "we proved overengineering can be prevented",
            "our tool detects wasted work",
            "no quality loss",
            "quality preserved",
            "c-short caused extra search",
            "the final scope review improved quality",
            "ai agents should never use large context",
            "native tools solve observability",
            "the project proved no product is needed",
        ):
            self.assertNotIn(forbidden, combined)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                relative = target.split("#", 1)[0]
                self.assertTrue(
                    (path.parent / relative).resolve().exists(),
                    f"broken local link in {path}: {target}",
                )


if __name__ == "__main__":
    unittest.main()
