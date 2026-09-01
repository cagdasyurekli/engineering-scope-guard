import tempfile
from pathlib import Path
import unittest

from scripts.launch_surface_quota_gate import build_receipt, write_private


class LaunchSurfaceQuotaGateTests(unittest.TestCase):
    def _response(self, used: int) -> dict:
        return {
            "rateLimitsByLimitId": {
                "codex": {
                    "limitId": "codex",
                    "planType": "pro",
                    "primary": {
                        "usedPercent": used,
                        "windowDurationMins": 10080,
                        "resetsAt": 123,
                    },
                    "rateLimitReachedType": None,
                    "spendControlReached": False,
                }
            }
        }

    def test_passes_only_with_at_least_seventy_five_percent_headroom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "codex"
            binary.write_bytes(b"runtime")
            self.assertEqual(build_receipt(binary, self._response(25))["status"], "pass")
            self.assertEqual(build_receipt(binary, self._response(26))["status"], "fail")

    def test_private_receipt_is_self_hashed_and_mode_0600(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / ".local"
            binary = Path(directory) / "codex"
            binary.write_bytes(b"runtime")
            receipt = build_receipt(binary, self._response(0))
            output = root / "quota.json"
            write_private(output, receipt)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(receipt["operational_headroom_percent"], 100)


if __name__ == "__main__":
    unittest.main()
