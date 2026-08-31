"""Durable campaign timing independent of remote task timestamps."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from .runtime_lock import digest


MonotonicNs = Callable[[], int]
WallClock = Callable[[], str]
StatusReader = Callable[[str], Sequence[dict[str, Any]]]


class CampaignTimeout(RuntimeError):
    """The independent elapsed-time budget has been exhausted."""


class CampaignReceiptError(RuntimeError):
    """The campaign receipt is malformed or its frozen identity drifted."""


@dataclass
class CampaignClock:
    """Persist elapsed time as independent process-local monotonic segments."""

    receipt_path: Path
    receipt: dict[str, Any]
    monotonic_ns: MonotonicNs = time.monotonic_ns
    wall_clock: WallClock = lambda: datetime.now(UTC).isoformat()
    _segment_origin_ns: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _validate_receipt(self.receipt)
        self._segment_origin_ns = self.monotonic_ns()

    @classmethod
    def create(
        cls,
        receipt_path: Path,
        *,
        campaign_uuid: str,
        immutable_config_sha256: str,
        hard_max_duration_seconds: float,
        monotonic_ns: MonotonicNs = time.monotonic_ns,
        wall_clock: WallClock = lambda: datetime.now(UTC).isoformat(),
    ) -> CampaignClock:
        _validate_uuid(campaign_uuid)
        _validate_sha256(immutable_config_sha256)
        if hard_max_duration_seconds <= 0:
            raise ValueError("hard_max_duration_seconds must be positive")
        if receipt_path.exists():
            raise CampaignReceiptError("campaign receipt already exists")
        now = wall_clock()
        receipt = {
            "schema_name": "engineering-scope-guard.campaign-clock",
            "schema_version": 1,
            "campaign_uuid": campaign_uuid,
            "immutable_config_sha256": immutable_config_sha256,
            "wall_clock_created_at": now,
            "hard_max_duration_ns": int(hard_max_duration_seconds * 1_000_000_000),
            "accumulated_previous_ns": 0,
            "completed_segments": [],
            "current_segment": _new_segment(now),
            "task_states": {},
            "last_checkpoint_wall_clock": now,
        }
        _seal(receipt)
        _write_atomic(receipt_path, receipt)
        return cls(receipt_path, receipt, monotonic_ns, wall_clock)

    @classmethod
    def resume(
        cls,
        receipt_path: Path,
        *,
        campaign_uuid: str,
        immutable_config_sha256: str,
        monotonic_ns: MonotonicNs = time.monotonic_ns,
        wall_clock: WallClock = lambda: datetime.now(UTC).isoformat(),
    ) -> CampaignClock:
        try:
            receipt = json.loads(receipt_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise CampaignReceiptError("campaign receipt is missing or malformed") from error
        _validate_receipt(receipt)
        if receipt["campaign_uuid"] != campaign_uuid:
            raise CampaignReceiptError("campaign UUID drifted")
        if receipt["immutable_config_sha256"] != immutable_config_sha256:
            raise CampaignReceiptError("campaign config hash drifted")
        prior = receipt["current_segment"]
        receipt["completed_segments"].append({
            **prior,
            "wall_clock_closed_at": wall_clock(),
        })
        receipt["accumulated_previous_ns"] += prior["checkpoint_elapsed_ns"]
        receipt["current_segment"] = _new_segment(wall_clock())
        receipt["last_checkpoint_wall_clock"] = wall_clock()
        _seal(receipt)
        _write_atomic(receipt_path, receipt)
        return cls(receipt_path, receipt, monotonic_ns, wall_clock)

    @property
    def elapsed_ns(self) -> int:
        current = self.monotonic_ns() - self._segment_origin_ns
        if current < 0:
            raise CampaignReceiptError("monotonic clock moved backwards")
        return self.receipt["accumulated_previous_ns"] + current

    @property
    def expired(self) -> bool:
        return self.elapsed_ns >= self.receipt["hard_max_duration_ns"]

    def checkpoint(self, task_states: dict[str, Any]) -> None:
        current = self.monotonic_ns() - self._segment_origin_ns
        if current < self.receipt["current_segment"]["checkpoint_elapsed_ns"]:
            raise CampaignReceiptError("monotonic segment elapsed time regressed")
        self.receipt["current_segment"]["checkpoint_elapsed_ns"] = current
        self.receipt["task_states"] = task_states
        self.receipt["last_checkpoint_wall_clock"] = self.wall_clock()
        _seal(self.receipt)
        _write_atomic(self.receipt_path, self.receipt)

    def require_within_limit(self) -> None:
        if self.expired:
            raise CampaignTimeout("campaign exceeded its independent elapsed-time limit")


def wait_for_campaign(
    job_ids: Sequence[str],
    campaign: CampaignClock,
    status_reader: StatusReader,
    *,
    poll_seconds: float = 10,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, list[dict[str, Any]]]:
    """Poll jobs while remote timestamps and retries remain diagnostic only."""
    if not job_ids or len(set(job_ids)) != len(job_ids):
        raise ValueError("job_ids must be non-empty and unique")
    if poll_seconds < 0:
        raise ValueError("poll_seconds must not be negative")
    task_states: dict[str, list[dict[str, Any]]] = {}
    while True:
        campaign.checkpoint(task_states)
        campaign.require_within_limit()
        try:
            for job_id in job_ids:
                task_states[job_id] = [_task_state(item) for item in status_reader(job_id)]
        except BaseException:
            campaign.checkpoint(task_states)
            raise
        campaign.checkpoint(task_states)
        campaign.require_within_limit()
        if all(
            task_states.get(job_id)
            and all(task.get("state") == "completed" for task in task_states[job_id])
            for job_id in job_ids
        ):
            return task_states
        try:
            sleep(poll_seconds)
        except BaseException:
            campaign.checkpoint(task_states)
            raise


def _new_segment(now: str) -> dict[str, Any]:
    return {
        "segment_id": str(uuid.uuid4()),
        "wall_clock_started_at": now,
        "checkpoint_elapsed_ns": 0,
    }


def _task_state(value: dict[str, Any]) -> dict[str, Any]:
    execution = value.get("executionInfo") or {}
    failure = execution.get("failureInfo") or {}
    return {
        "task_id": value.get("id"),
        "state": value.get("state"),
        "azure_start_time": execution.get("startTime"),
        "azure_end_time": execution.get("endTime"),
        "azure_retry_count": execution.get("retryCount"),
        "azure_failure_code": failure.get("code"),
    }


def _validate_uuid(value: Any) -> None:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise ValueError("campaign_uuid must be a canonical UUID") from error
    if str(parsed) != value:
        raise ValueError("campaign_uuid must be a canonical UUID")


def _validate_sha256(value: Any) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("immutable_config_sha256 must be a lowercase SHA-256 digest")


def _seal(receipt: dict[str, Any]) -> None:
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = digest(receipt)


def _validate_receipt(receipt: dict[str, Any]) -> None:
    expected = receipt.get("receipt_sha256")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if expected != digest(body):
        raise CampaignReceiptError("campaign receipt hash drifted")
    if receipt.get("schema_name") != "engineering-scope-guard.campaign-clock" or receipt.get("schema_version") != 1:
        raise CampaignReceiptError("campaign receipt schema drifted")
    try:
        _validate_uuid(receipt["campaign_uuid"])
        _validate_sha256(receipt["immutable_config_sha256"])
    except (KeyError, ValueError) as error:
        raise CampaignReceiptError(str(error)) from error
    for field_name in ("hard_max_duration_ns", "accumulated_previous_ns"):
        value = receipt.get(field_name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise CampaignReceiptError(f"{field_name} is invalid")
    if receipt["hard_max_duration_ns"] <= 0:
        raise CampaignReceiptError("hard_max_duration_ns must be positive")
    segments = receipt.get("completed_segments")
    current = receipt.get("current_segment")
    if not isinstance(segments, list) or not isinstance(current, dict):
        raise CampaignReceiptError("campaign segment state is malformed")
    segment_ids: list[str] = []
    for segment in [*segments, current]:
        if not isinstance(segment, dict):
            raise CampaignReceiptError("campaign segment is malformed")
        try:
            _validate_uuid(segment["segment_id"])
        except (KeyError, ValueError) as error:
            raise CampaignReceiptError("campaign segment identity is invalid") from error
        elapsed = segment.get("checkpoint_elapsed_ns")
        if not isinstance(elapsed, int) or isinstance(elapsed, bool) or elapsed < 0:
            raise CampaignReceiptError("campaign segment elapsed time is invalid")
        segment_ids.append(segment["segment_id"])
    if len(segment_ids) != len(set(segment_ids)):
        raise CampaignReceiptError("campaign segment identity was reused")
    if receipt["accumulated_previous_ns"] != sum(
        segment["checkpoint_elapsed_ns"] for segment in segments
    ):
        raise CampaignReceiptError("campaign accumulated elapsed time drifted")
    if not isinstance(receipt.get("task_states"), dict):
        raise CampaignReceiptError("campaign task states are malformed")


def _write_atomic(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
        temporary = Path(handle.name)
    os.replace(temporary, path)
