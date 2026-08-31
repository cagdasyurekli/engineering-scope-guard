import json
from pathlib import Path
import tempfile
import unittest

from engineering_scope_guard.campaign_clock import (
    CampaignClock,
    CampaignReceiptError,
    CampaignTimeout,
    wait_for_campaign,
)


class FakeClock:
    def __init__(self, nanoseconds: int = 0) -> None:
        self.nanoseconds = nanoseconds
        self.wall_value = "2026-08-31T00:00:00+00:00"

    def monotonic_ns(self) -> int:
        return self.nanoseconds

    def wall(self) -> str:
        return self.wall_value

    def advance(self, seconds: float) -> None:
        self.nanoseconds += int(seconds * 1_000_000_000)


class CampaignClockTests(unittest.TestCase):
    def _campaign(self, root: Path, clock: FakeClock, limit: float = 60) -> CampaignClock:
        return CampaignClock.create(
            root / "campaign.json",
            campaign_uuid="00000000-0000-4000-8000-000000000001",
            immutable_config_sha256="a" * 64,
            hard_max_duration_seconds=limit,
            monotonic_ns=clock.monotonic_ns,
            wall_clock=clock.wall,
        )

    def test_normal_task_completion(self) -> None:
        clock = FakeClock()
        responses = iter([
            [{"id": "t", "state": "active"}],
            [{"id": "t", "state": "completed"}],
        ])
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._campaign(Path(directory), clock)
            result = wait_for_campaign(
                ["job"], campaign, lambda _: next(responses), poll_seconds=1,
                sleep=clock.advance,
            )
        self.assertEqual(result["job"][0]["state"], "completed")
        self.assertEqual(campaign.elapsed_ns, 1_000_000_000)

    def test_start_time_changes_do_not_reset_deadline(self) -> None:
        clock = FakeClock()
        starts = iter(["2026-08-31T00:00:00Z", "2026-08-31T00:10:00Z"])
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._campaign(Path(directory), clock, limit=3)
            with self.assertRaises(CampaignTimeout):
                wait_for_campaign(
                    ["job"], campaign,
                    lambda _: [{"id": "t", "state": "active", "executionInfo": {"startTime": next(starts)}}],
                    poll_seconds=2, sleep=clock.advance,
                )
        self.assertEqual(campaign.elapsed_ns, 4_000_000_000)

    def test_requeue_does_not_reset_elapsed_time(self) -> None:
        clock = FakeClock()
        responses = iter([
            [{"id": "t", "state": "active", "executionInfo": {"startTime": "one"}}],
            [{"id": "t", "state": "active", "executionInfo": {"startTime": "two"}}],
            [{"id": "t", "state": "completed", "executionInfo": {"startTime": "two"}}],
        ])
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._campaign(Path(directory), clock)
            wait_for_campaign(["job"], campaign, lambda _: next(responses), poll_seconds=2, sleep=clock.advance)
        self.assertEqual(campaign.elapsed_ns, 4_000_000_000)

    def test_unchanged_retry_counter_is_diagnostic_only(self) -> None:
        clock = FakeClock()
        responses = iter([
            [{"id": "t", "state": "active", "executionInfo": {"retryCount": 0}}],
            [{"id": "t", "state": "completed", "executionInfo": {"retryCount": 0}}],
        ])
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._campaign(Path(directory), clock)
            result = wait_for_campaign(["job"], campaign, lambda _: next(responses), poll_seconds=3, sleep=clock.advance)
        self.assertEqual(result["job"][0]["azure_retry_count"], 0)
        self.assertEqual(campaign.elapsed_ns, 3_000_000_000)

    def test_restart_starts_new_monotonic_segment(self) -> None:
        first, second = FakeClock(10), FakeClock(900)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._campaign(root, first)
            first.advance(4)
            campaign.checkpoint({})
            resumed = CampaignClock.resume(
                root / "campaign.json", campaign_uuid=campaign.receipt["campaign_uuid"],
                immutable_config_sha256="a" * 64, monotonic_ns=second.monotonic_ns,
                wall_clock=second.wall,
            )
        self.assertEqual(resumed.receipt["accumulated_previous_ns"], 4_000_000_000)

    def test_persisted_elapsed_resumes_across_unrelated_origins(self) -> None:
        first, second = FakeClock(50), FakeClock(5)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._campaign(root, first)
            first.advance(3)
            campaign.checkpoint({})
            resumed = CampaignClock.resume(
                root / "campaign.json", campaign_uuid=campaign.receipt["campaign_uuid"],
                immutable_config_sha256="a" * 64, monotonic_ns=second.monotonic_ns,
                wall_clock=second.wall,
            )
            second.advance(2)
        self.assertEqual(resumed.elapsed_ns, 5_000_000_000)

    def test_timeout_crossing_after_restart_is_authoritative(self) -> None:
        first, second = FakeClock(), FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._campaign(root, first, limit=5)
            first.advance(4)
            campaign.checkpoint({})
            resumed = CampaignClock.resume(
                root / "campaign.json", campaign_uuid=campaign.receipt["campaign_uuid"],
                immutable_config_sha256="a" * 64, monotonic_ns=second.monotonic_ns,
                wall_clock=second.wall,
            )
            second.advance(1)
            with self.assertRaises(CampaignTimeout):
                resumed.require_within_limit()

    def test_multiple_jobs_complete_under_one_clock(self) -> None:
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._campaign(Path(directory), clock)
            result = wait_for_campaign(
                ["a", "b"], campaign,
                lambda job: [{"id": job, "state": "completed"}], poll_seconds=0,
            )
        self.assertEqual(set(result), {"a", "b"})

    def test_interrupted_worker_persists_partial_state(self) -> None:
        clock = FakeClock()

        def reader(job: str):
            if job == "b":
                raise KeyboardInterrupt
            clock.advance(2)
            return [{"id": "t", "state": "active"}]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._campaign(root, clock)
            with self.assertRaises(KeyboardInterrupt):
                wait_for_campaign(["a", "b"], campaign, reader, poll_seconds=0)
            saved = json.loads((root / "campaign.json").read_text())
        self.assertEqual(saved["task_states"]["a"][0]["state"], "active")
        self.assertEqual(saved["current_segment"]["checkpoint_elapsed_ns"], 2_000_000_000)

    def test_wall_clock_disagreement_cannot_change_elapsed_time(self) -> None:
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._campaign(Path(directory), clock)
            clock.wall_value = "2020-01-01T00:00:00+00:00"
            clock.advance(7)
            campaign.checkpoint({})
            clock.wall_value = "2035-01-01T00:00:00+00:00"
        self.assertEqual(campaign.elapsed_ns, 7_000_000_000)

    def test_receipt_tamper_and_identity_drift_fail_closed(self) -> None:
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._campaign(root, clock)
            with self.assertRaisesRegex(CampaignReceiptError, "config hash"):
                CampaignClock.resume(
                    root / "campaign.json", campaign_uuid=campaign.receipt["campaign_uuid"],
                    immutable_config_sha256="b" * 64, monotonic_ns=clock.monotonic_ns,
                    wall_clock=clock.wall,
                )
            saved = json.loads((root / "campaign.json").read_text())
            saved["hard_max_duration_ns"] += 1
            (root / "campaign.json").write_text(json.dumps(saved))
            with self.assertRaisesRegex(CampaignReceiptError, "hash drifted"):
                CampaignClock.resume(
                    root / "campaign.json", campaign_uuid=campaign.receipt["campaign_uuid"],
                    immutable_config_sha256="a" * 64, monotonic_ns=clock.monotonic_ns,
                    wall_clock=clock.wall,
                )


if __name__ == "__main__":
    unittest.main()
