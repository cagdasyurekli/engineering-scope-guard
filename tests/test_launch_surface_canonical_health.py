from __future__ import annotations

from copy import deepcopy
import unittest

from scripts import launch_surface_canonical_health as health


class CanonicalHealthTests(unittest.TestCase):
    def responses(self) -> dict[str, object]:
        return {
            f"repos/{health.REPOSITORY}": {"private": False, "default_branch": "main"},
            f"repos/{health.REPOSITORY}/commits/main": {"sha": health.EXPECTED_COMMIT},
            f"repos/{health.REPOSITORY}/commits/{health.EXPECTED_COMMIT}/check-runs": {
                "check_runs": [
                    {"name": name, "status": "completed", "conclusion": "success"}
                    for name in health.REQUIRED_CHECKS
                ]
            },
            f"repos/{health.REPOSITORY}/rulesets": [
                {"name": "Protect main", "enforcement": "active"}
            ],
            f"repos/{health.REPOSITORY}/code-scanning/alerts?state=open&per_page=100": [],
            f"repos/{health.REPOSITORY}/releases/tags/esg-rr-001-v0.6": {
                "tag_name": "esg-rr-001-v0.6", "immutable": True
            },
        }

    def test_build_passes_only_with_exact_canonical_health(self) -> None:
        responses = self.responses()
        receipt = health.build(responses.__getitem__)
        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(receipt["open_codeql_alerts"], 0)

    def test_missing_required_check_fails_closed(self) -> None:
        responses = deepcopy(self.responses())
        endpoint = f"repos/{health.REPOSITORY}/commits/{health.EXPECTED_COMMIT}/check-runs"
        responses[endpoint]["check_runs"].pop()
        receipt = health.build(responses.__getitem__)
        self.assertEqual(receipt["status"], "fail")


if __name__ == "__main__":
    unittest.main()
