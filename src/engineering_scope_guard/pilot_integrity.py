"""Execution-integrity helpers for the frozen Pilot runner.

This module handles credential isolation, provider-error recognition,
pre-subject repository baselines, and read-only resume assessment. It never
launches a Pilot subject or evaluator and never mutates the Pilot ledger.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError
from .pilot_contract import classify_receipt
from .pilot_runner import next_legal_action

AUTH_FILE = "auth.json"
PROVIDER_ERROR_CODES = {
    "api_connection_error",
    "authentication_error",
    "invalid_api_key",
    "rate_limit_exceeded",
    "service_unavailable",
    "server_error",
    "unauthorized",
}
_AUTH_STATUS = re.compile(
    r"(?:unexpected\s+)?(?:status\s+)?(?:401\s+Unauthorized|403\s+Forbidden)\b",
    re.IGNORECASE,
)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError(f"cannot read isolated credential metadata: {error}") from error
    if not isinstance(value, dict):
        raise ExperimentConfigurationError("isolated credential metadata is not an object")
    return value


def inspect_file_auth(source_codex_home: Path) -> dict[str, Any]:
    """Validate file-backed Codex authentication without exposing secrets."""

    auth_path = source_codex_home / AUTH_FILE
    try:
        mode = stat.S_IMODE(auth_path.stat().st_mode)
    except OSError as error:
        raise ExperimentConfigurationError("source Codex auth.json is absent") from error
    if mode & 0o077:
        raise ExperimentConfigurationError("source Codex auth.json permissions are not restrictive")
    value = _read_object(auth_path)
    login_method = value.get("auth_mode")
    if login_method not in {"chatgpt", "api"}:
        raise ExperimentConfigurationError("source Codex auth.json has an unsupported login method")
    if login_method == "chatgpt" and not isinstance(value.get("tokens"), dict):
        raise ExperimentConfigurationError("source ChatGPT auth.json lacks token material")
    return {
        "storage": "file",
        "login_method": login_method,
        "source_permissions": f"{mode:04o}",
        "credential_artifact": AUTH_FILE,
    }


def provision_file_auth(source_codex_home: Path, target_codex_home: Path) -> dict[str, Any]:
    """Copy only file-backed auth into one isolated Codex home."""

    metadata = inspect_file_auth(source_codex_home)
    target_codex_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    target_codex_home.chmod(0o700)
    target = target_codex_home / AUTH_FILE
    if target.exists():
        raise ExperimentConfigurationError("isolated Codex auth.json already exists")
    source = source_codex_home / AUTH_FILE
    try:
        with source.open("rb") as input_handle, target.open("xb") as output_handle:
            os.chmod(target, 0o600)
            shutil.copyfileobj(input_handle, output_handle)
            output_handle.flush()
            os.fsync(output_handle.fileno())
    except OSError as error:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise ExperimentConfigurationError("cannot provision isolated Codex authentication") from error
    if stat.S_IMODE(target.stat().st_mode) != 0o600:
        raise ExperimentConfigurationError("isolated Codex auth.json permissions are not restrictive")
    return {**metadata, "target_permissions": "0600", "copied_artifacts": [AUTH_FILE]}


def remove_file_auth(target_codex_home: Path) -> None:
    """Remove trajectory-local credential material and fail if it remains."""

    target = target_codex_home / AUTH_FILE
    try:
        target.unlink(missing_ok=True)
    except OSError as error:
        raise ExperimentConfigurationError("cannot remove isolated Codex authentication") from error
    if target.exists():
        raise ExperimentConfigurationError("isolated Codex authentication remains after cleanup")


def classify_provider_event(event: dict[str, Any]) -> bool:
    """Recognize bounded provider failures only in Codex error event contexts."""

    if event.get("type") not in {"error", "turn.failed"}:
        return False
    error = event.get("error")
    if isinstance(error, dict) and error.get("code") in PROVIDER_ERROR_CODES:
        return True
    messages = []
    if isinstance(event.get("message"), str):
        messages.append(event["message"])
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        messages.append(error["message"])
    return any(_AUTH_STATUS.search(message) is not None for message in messages)


def parse_provider_trace(content: bytes) -> dict[str, Any]:
    """Return content-free provider/session metadata from Codex JSONL bytes."""

    session_present = False
    provider_failure = False
    terminal_event = None
    recognized_events = 0
    for raw_line in content.splitlines():
        try:
            event = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if not isinstance(event_type, str):
            continue
        recognized_events += 1
        if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
            session_present = True
        if event_type in {"turn.completed", "turn.failed"}:
            terminal_event = event_type
        provider_failure = provider_failure or classify_provider_event(event)
    return {
        "recognized_events": recognized_events,
        "session_present": session_present,
        "provider_infrastructure_failure": provider_failure,
        "terminal_event": terminal_event,
    }


def _git(
    repository: Path,
    arguments: list[str],
    *,
    environment: dict[str, str] | None = None,
    binary: bool = False,
) -> bytes | str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=not binary,
        check=False,
    )
    if completed.returncode != 0:
        raise ExperimentConfigurationError(f"repository baseline command failed: git {arguments[0]}")
    return completed.stdout


def repository_state(repository: Path) -> dict[str, Any]:
    """Capture exact content-free Git status categories before subject work."""

    head = str(_git(repository, ["rev-parse", "HEAD"])).strip()
    raw = _git(
        repository,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=matching"],
        binary=True,
    )
    assert isinstance(raw, bytes)
    entries = raw.split(b"\0")
    categories: dict[str, list[str]] = {
        "staged": [],
        "tracked_worktree": [],
        "untracked": [],
        "ignored": [],
    }
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4 or entry[2:3] != b" ":
            raise ExperimentConfigurationError("repository status entry is malformed")
        code = entry[:2].decode("ascii", errors="strict")
        path = entry[3:].decode("utf-8", errors="surrogateescape")
        if code == "??":
            categories["untracked"].append(path)
        elif code == "!!":
            categories["ignored"].append(path)
        else:
            if code[0] != " ":
                categories["staged"].append(path)
            if code[1] != " ":
                categories["tracked_worktree"].append(path)
            if code[0] in {"R", "C"} and index < len(entries):
                index += 1
    return {"head": head, **{name: sorted(paths) for name, paths in categories.items()}}


def _index_environment(index_path: Path) -> dict[str, str]:
    return {**os.environ, "GIT_INDEX_FILE": str(index_path)}


def capture_repository_baseline(repository: Path, derived_root: Path) -> dict[str, Any]:
    """Create a Git tree for the exact materialized pre-subject state."""

    derived_root.mkdir(parents=True, exist_ok=True)
    index_path = derived_root / "pre-subject.index"
    if index_path.exists():
        raise ExperimentConfigurationError("pre-subject baseline index already exists")
    environment = _index_environment(index_path)
    _git(repository, ["read-tree", "HEAD"], environment=environment)
    _git(repository, ["add", "-A", "--"], environment=environment)
    tree = str(_git(repository, ["write-tree"], environment=environment)).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise ExperimentConfigurationError("pre-subject baseline tree is malformed")
    return {"tree": tree, "state": repository_state(repository)}


def subject_patch_from_baseline(
    repository: Path, derived_root: Path, baseline: dict[str, Any]
) -> bytes:
    """Extract only changes after the captured materialized baseline."""

    tree = baseline.get("tree")
    if not isinstance(tree, str) or not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise ExperimentConfigurationError("pre-subject baseline tree is unavailable")
    index_path = derived_root / "subject.index"
    index_path.unlink(missing_ok=True)
    environment = _index_environment(index_path)
    _git(repository, ["read-tree", tree], environment=environment)
    _git(repository, ["add", "-A", "--"], environment=environment)
    output = _git(
        repository,
        ["diff", "--cached", "--binary", tree, "--"],
        environment=environment,
        binary=True,
    )
    assert isinstance(output, bytes)
    return output


def assess_ledger_resume(contract: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe the frozen next transition without appending a ledger event."""

    action = next_legal_action(contract, events)
    kind = action["action"]
    attempt_finishes = [
        event["payload"] for event in events if event.get("event_type") == "attempt_finished"
    ]
    prior = attempt_finishes[-1] if attempt_finishes else None
    prior_classification = classify_receipt(contract, prior) if prior is not None else None
    reruns_consumed = sum(
        event.get("event_type") == "infrastructure_rerun_authorized" for event in events
    )
    legal_resume = kind in {"launch", "authorize_infrastructure_rerun"}
    return {
        "next_legal_action": kind,
        "legal_resume": legal_resume,
        "prior_attempt_termination": None if prior is None else prior.get("termination"),
        "prior_attempt_is_rerunnable": bool(
            prior_classification and prior_classification["same_cell_rerun_permitted"]
        ),
        "reruns_consumed": reruns_consumed,
        "future_retry_budget_units": 1 if kind == "authorize_infrastructure_rerun" else 0,
        "hypothetical_provider_retry_budget_units": 1,
        "terminal_ledger_requires_new_design": kind == "batch_stopped",
    }
