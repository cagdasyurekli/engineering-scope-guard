"""Capped contentless launches for a prospectively pinned runtime identity."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from .launch_surface import rendered_command, validate_treatment_pair
from .runtime_lock import RuntimeIdentityError, canonical_bytes, digest, sentinel


PROMPT = "Return exactly RUNTIME_STABILITY_OK. Do not use tools.\n"
Runner = Callable[[Sequence[str], bytes, Path], subprocess.CompletedProcess[bytes]]


def run_contentless_launch(
    receipt: dict[str, Any], *, state_path: Path, effort: str,
    runner: Runner | None = None, repair_from_receipt: dict[str, Any] | None = None,
    launch_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if effort not in {"low", "medium"}:
        raise RuntimeIdentityError("contentless launch effort must be low or medium")
    if ".local" not in state_path.parts:
        raise RuntimeIdentityError("runtime soak state must remain below .local")
    identity = sentinel(receipt)
    state = _read_state(state_path, receipt, repair_from_receipt)
    if len(state["launches"]) >= 4:
        raise RuntimeIdentityError("contentless runtime launch maximum is exhausted")
    prior_for_effort = [item for item in state["launches"] if item["effort"] == effort]
    if any(item.get("status") == "pass" for item in prior_for_effort):
        raise RuntimeIdentityError("contentless runtime effort already passed")
    if len(prior_for_effort) >= 2:
        raise RuntimeIdentityError("contentless runtime effort retry maximum is exhausted")
    command = [receipt["invocation_path"], *[
        item.replace("<EFFORT>", effort) for item in receipt["command_template"]
    ]]
    profile_sha256 = None
    launch_contract_sha256 = None
    if launch_contract is not None:
        profiles = launch_contract.get("profiles", {})
        validate_treatment_pair(profiles.get("low", {}), profiles.get("medium", {}))
        if rendered_command(profiles[effort]) != command:
            raise RuntimeIdentityError("structured launch profile differs from runtime command")
        profile_sha256 = digest(profiles[effort])
        launch_contract_sha256 = launch_contract.get("contract_sha256")
        if (
            launch_contract.get("profile_sha256s", {}).get(effort) != profile_sha256
            or not isinstance(launch_contract_sha256, str)
        ):
            raise RuntimeIdentityError("structured launch profile hash drifted")
    ordinal = len(state["launches"]) + 1
    reservation = {
        "ordinal": ordinal,
        "effort": effort,
        "status": "reserved",
        "reserved_at": datetime.now(UTC).isoformat(),
        "runtime_receipt_sha256": receipt["receipt_sha256"],
        "sentinel_identity_sha256": identity["observed_identity_sha256"],
        "launch_profile_sha256": profile_sha256,
        "launch_surface_contract_sha256": launch_contract_sha256,
    }
    state["launches"].append(reservation)
    _write_state(state_path, state)

    execute = runner or _run
    try:
        with tempfile.TemporaryDirectory(dir=state_path.parent) as directory:
            completed = execute(command, PROMPT.encode(), Path(directory))
    except BaseException as error:
        reservation.update({
            "status": "failed_before_return",
            "failure_class": type(error).__name__,
            "completed_at": datetime.now(UTC).isoformat(),
        })
        _write_state(state_path, state)
        raise

    raw_path = state_path.parent / f"contentless-launch-{ordinal}.jsonl"
    stderr_path = state_path.parent / f"contentless-launch-{ordinal}.stderr"
    _write_private_bytes(raw_path, completed.stdout)
    _write_private_bytes(stderr_path, completed.stderr)
    events, item_types = _parse_events(completed.stdout)
    prohibited = sorted(item_types - {"agent_message", "reasoning"})
    passed = completed.returncode == 0 and "turn.completed" in events and not prohibited
    reservation.update({
        "status": "pass" if passed else "failed",
        "completed_at": datetime.now(UTC).isoformat(),
        "return_code": completed.returncode,
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "event_types": sorted(events),
        "item_types": sorted(item_types),
        "prohibited_item_types": prohibited,
        "raw_path": raw_path.name,
        "stderr_path": stderr_path.name,
    })
    _write_state(state_path, state)
    if not passed:
        raise RuntimeIdentityError("contentless runtime launch failed its closed-surface check")
    return {
        "status": "pass",
        "ordinal": ordinal,
        "effort": effort,
        "runtime_receipt_sha256": receipt["receipt_sha256"],
        "launch_profile_sha256": profile_sha256,
        "launch_surface_contract_sha256": launch_contract_sha256,
        "soak_state_sha256": state["state_sha256"],
    }


def _run(command: Sequence[str], prompt: bytes, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, input=prompt, cwd=cwd, capture_output=True, check=False)


def _parse_events(raw: bytes) -> tuple[set[str], set[str]]:
    events: set[str] = set()
    items: set[str] = set()
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RuntimeIdentityError("contentless launch emitted malformed JSONL") from error
        event_type = value.get("type")
        if isinstance(event_type, str):
            events.add(event_type)
        item_type = (value.get("item") or {}).get("type")
        if isinstance(item_type, str):
            items.add(item_type)
    return events, items


def _read_state(
    path: Path, receipt: dict[str, Any], repair_from_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    runtime_sha256 = receipt["receipt_sha256"]
    try:
        state = json.loads(path.read_text())
    except FileNotFoundError:
        return {
            "schema_name": "engineering-scope-guard.runtime-stability-soak",
            "schema_version": 2,
            "runtime_receipt_sha256s": [runtime_sha256],
            "active_runtime_receipt_sha256": runtime_sha256,
            "launches": [],
        }
    expected = state.get("state_sha256")
    body = dict(state)
    body.pop("state_sha256", None)
    if expected != digest(body):
        raise RuntimeIdentityError("runtime soak state drifted")
    if state.get("schema_name") != "engineering-scope-guard.runtime-stability-soak":
        raise RuntimeIdentityError("runtime soak state is malformed")
    if state.get("schema_version") == 1:
        state = _migrate_v1(state)
    if state.get("schema_version") != 2 or not isinstance(state.get("launches"), list):
        raise RuntimeIdentityError("runtime soak state is malformed")
    if state.get("active_runtime_receipt_sha256") != runtime_sha256:
        _authorize_pre_success_repin(state, receipt, repair_from_receipt)
    return state


def _migrate_v1(state: dict[str, Any]) -> dict[str, Any]:
    prior = state.pop("runtime_receipt_sha256", None)
    state.pop("state_sha256", None)
    if not isinstance(prior, str):
        raise RuntimeIdentityError("runtime soak v1 state is malformed")
    state["schema_version"] = 2
    state["runtime_receipt_sha256s"] = [prior]
    state["active_runtime_receipt_sha256"] = prior
    return state


def _authorize_pre_success_repin(
    state: dict[str, Any], receipt: dict[str, Any], prior: dict[str, Any] | None,
) -> None:
    if prior is None:
        raise RuntimeIdentityError("runtime soak receipt changed without a repair receipt")
    if prior.get("receipt_sha256") != state.get("active_runtime_receipt_sha256"):
        raise RuntimeIdentityError("runtime soak repair predecessor does not match")
    if any(item.get("status") == "pass" for item in state["launches"]):
        raise RuntimeIdentityError("runtime cannot be repinned after a passing launch")
    if len(state.get("runtime_receipt_sha256s", [])) != 1:
        raise RuntimeIdentityError("pre-success runtime repin maximum is exhausted")
    state["runtime_receipt_sha256s"].append(receipt["receipt_sha256"])
    state["active_runtime_receipt_sha256"] = receipt["receipt_sha256"]


def _write_state(path: Path, state: dict[str, Any]) -> None:
    state.pop("state_sha256", None)
    state["state_sha256"] = digest(state)
    _write_private_bytes(path, canonical_bytes(state))


def _write_private_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)
