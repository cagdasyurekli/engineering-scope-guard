#!/usr/bin/env python3
"""Authoritative, dependency-injected execution boundary for effort-v2.

The module is inert when imported or executed: it contains no configured live
backend and never starts Codex, Docker, or the evaluator by itself.  A host
backend supplies raw subject/evaluator results, while this adapter owns the
frozen command, durable launch boundary, artifact derivation, and reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Iterator, Mapping, Protocol
import argparse
from contextlib import contextmanager

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.launch_surface import (
    LaunchSurfaceError,
    build_launch_profile,
    rendered_command,
    validate_launch_contract,
    validate_treatment_pair,
)
from engineering_scope_guard.disk_safety import (
    disk_safety_snapshot,
    public_disk_safety_receipt,
)
from engineering_scope_guard.pilot_contract import digest
from engineering_scope_guard.pilot_contract import read_object
from engineering_scope_guard.pilot_integrity import (
    capture_repository_baseline,
    provision_file_auth,
    remove_file_auth,
    subject_patch_from_baseline,
)
from engineering_scope_guard.pilot_runner import (
    official_evaluator_command,
    parse_official_evaluator_artifacts,
)
from engineering_scope_guard.reasoning_effort_v2 import (
    subject_command_arguments,
    subject_command_identity,
    validate_contract,
    validate_harness_source_closure,
    validate_prior_evidence_identity,
    validate_private_pool_binding,
)
from engineering_scope_guard.runtime_lock import (
    RuntimeIdentityError,
    sentinel,
    validate_runtime_receipt,
)

try:
    from scripts.reasoning_effort_v1_runner import (
        _environment as v1_environment,
        _validate_prompt_bytes,
        parse_subject_trace,
    )
    from scripts.pilot_runner import resolve_dataset_task
    from scripts import evaluator_stable_qualification as qualifier_live
    from scripts import reasoning_effort_v2_runner as durable
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from reasoning_effort_v1_runner import (
        _environment as v1_environment,
        _validate_prompt_bytes,
        parse_subject_trace,
    )
    from pilot_runner import resolve_dataset_task
    import evaluator_stable_qualification as qualifier_live
    import reasoning_effort_v2_runner as durable


@dataclass(frozen=True)
class AttemptRequest:
    """Frozen private request handed to exactly one host-backend attempt."""

    cell_id: str
    attempt: int
    task: dict[str, Any]
    command: tuple[str, ...]
    command_sha256: str
    effective_task_commitment_sha256: str
    ownership_token_sha256: str
    process_identity_sha256: str
    subject_timeout_seconds: int
    evaluator_timeout_seconds: int


@dataclass(frozen=True)
class SubjectInvocation:
    """Raw, terminal subject evidence returned after the process is stopped."""

    exit_code: int | None
    timed_out: bool
    stdout: bytes
    stderr: bytes
    wall_seconds: float


@dataclass(frozen=True)
class EvaluatorInvocation:
    """Raw, terminal official-evaluator evidence returned after it is stopped."""

    exit_code: int | None
    timed_out: bool
    report: dict[str, Any] | None
    results: dict[str, Any] | None
    wall_seconds: float
    stdout: bytes = b""
    stderr: bytes = b""
    prediction: bytes = b""
    patch: bytes = b""
    report_bytes: bytes | None = None
    results_bytes: bytes | None = None
    infrastructure_failure: bool = False


@dataclass(frozen=True)
class PreparedAttempt:
    """Gated launch state plus independently observed immutable identities."""

    state: Any
    attestation: dict[str, Any]


@dataclass
class GatedProcess:
    """A child blocked before ``execve(Codex)`` until the durable start exists."""

    process: subprocess.Popen[bytes]
    release_fd: int
    command_sha256: str
    ownership_token_sha256: str
    process_identity_sha256: str
    process_identity: dict[str, Any] | None = None
    released: bool = False
    process_identity_observer: Callable[..., dict[str, Any]] | None = None
    container_identity_sha256: str | None = None


_GATED_EXEC = """
import os, sys
gate = int(sys.argv[1])
nonce = sys.argv[2]
if os.environ.pop('ESG_EXECUTION_NONCE', None) != nonce:
    raise SystemExit(126)
if os.read(gate, 1) != b'1':
    raise SystemExit(125)
os.close(gate)
os.execvpe(sys.argv[3], sys.argv[3:], os.environ)
"""


def _file_identity(path: str) -> dict[str, Any]:
    resolved = Path(path).resolve(strict=True)
    metadata = resolved.stat()
    return {
        "resolved_path": str(resolved),
        "file_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "size": metadata.st_size,
        "mtime_ns": metadata.st_mtime_ns,
    }


_PROCESS_BIRTH_MARKERS: dict[int, str] = {}


def _process_start_time(pid: int) -> str:
    """Return an OS-owned process birth marker, never elapsed wall-clock time."""

    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.is_file():
        # The command name can contain spaces and parentheses.  Field 22 begins
        # nineteen fields after the final closing parenthesis.
        fields = stat_path.read_text(encoding="utf-8").rsplit(")", 1)[1].split()
        _require(len(fields) >= 20, "process start-time evidence is malformed")
        return f"procfs-jiffies:{fields[19]}"
    # Popen remains the authoritative handle on platforms without procfs.  The
    # per-spawn nonce supplies the non-PID identity; this marker avoids invoking
    # an ambient `ps` binary from the provider-free adapter boundary.
    return _PROCESS_BIRTH_MARKERS.setdefault(pid, f"spawn:{time.monotonic_ns()}:{secrets.token_hex(16)}")


def _process_identity(
    process: subprocess.Popen[bytes], *, target_executable: str,
    command_sha256: str, ownership_token_sha256: str, nonce_sha256: str,
) -> dict[str, Any]:
    return {
        "pid": process.pid,
        "start_time": _process_start_time(process.pid),
        "launcher_executable": _file_identity(sys.executable),
        "target_executable": _file_identity(target_executable),
        "command_sha256": command_sha256,
        "ownership_token_sha256": ownership_token_sha256,
        "nonce_sha256": nonce_sha256,
        "gated_before_exec": True,
    }


def verify_process_identity(
    gated: GatedProcess | dict[str, Any], *,
    observed_process_start_identity: str | None = None,
) -> bool:
    """Return true only while the original PID/birth/executable/nonce tuple lives."""

    if isinstance(gated, dict):
        expected = gated.get("process_start_identity", gated.get("start_time"))
        return (
            isinstance(expected, str)
            and isinstance(observed_process_start_identity, str)
            and expected == observed_process_start_identity
        )
    if gated.process_identity is None:
        return gated.process.poll() is None
    if gated.process.poll() is not None:
        return False
    try:
        observer = gated.process_identity_observer or _process_identity
        current = observer(
            gated.process,
            target_executable=gated.process_identity["target_executable"]["resolved_path"],
            command_sha256=gated.command_sha256,
            ownership_token_sha256=gated.ownership_token_sha256,
            nonce_sha256=gated.process_identity["nonce_sha256"],
        )
    except (ExperimentConfigurationError, FileNotFoundError, ProcessLookupError):
        return False
    return current == gated.process_identity


def abort_gated_process(gated: GatedProcess) -> None:
    """Stop only the process whose full immutable launch identity still matches."""

    if not verify_process_identity(gated):
        return
    if gated.release_fd >= 0:
        os.close(gated.release_fd)
        gated.release_fd = -1
    # Closing an unreleased gate normally exits 125.  A released invocation owns
    # a new session/process group and is terminated as one unit.
    if gated.released:
        try:
            os.killpg(gated.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        gated.process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        if verify_process_identity(gated):
            try:
                os.killpg(gated.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        gated.process.communicate()


def prepare_gated_process(
    command: tuple[str, ...], *, cwd: Path, env: dict[str, str],
    command_sha256: str, ownership_token_sha256: str,
    process_identity_observer: Callable[..., dict[str, Any]] | None = None,
) -> GatedProcess:
    """Spawn a process that cannot execute the subject until explicitly released."""

    _require(bool(command) and all(isinstance(item, str) for item in command), "gated command is malformed")
    resolved_executable = shutil.which(command[0], path=env.get("PATH", os.defpath))
    if resolved_executable is None:
        resolved_executable = command[0]
    nonce = secrets.token_hex(32)
    nonce_sha256 = hashlib.sha256(bytes.fromhex(nonce)).hexdigest()
    child_env = dict(env)
    child_env["ESG_EXECUTION_NONCE"] = nonce
    read_fd, write_fd = os.pipe()
    try:
        process = subprocess.Popen(
            [sys.executable, "-c", _GATED_EXEC, str(read_fd), nonce, *command],
            cwd=cwd,
            env=child_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            pass_fds=(read_fd,),
        )
    except BaseException:
        os.close(read_fd)
        os.close(write_fd)
        raise
    os.close(read_fd)
    try:
        observer = process_identity_observer or _process_identity
        identity = observer(
            process,
            target_executable=resolved_executable,
            command_sha256=command_sha256,
            ownership_token_sha256=ownership_token_sha256,
            nonce_sha256=nonce_sha256,
        )
        _PROCESS_BIRTH_MARKERS[process.pid] = identity["start_time"]
    except BaseException:
        # The launch is not returned to a caller until its ownership identity is
        # observed.  If observation fails, the still-gated child must not leak.
        try:
            os.close(write_fd)
        except OSError:
            pass
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
        raise
    return GatedProcess(
        process, write_fd, command_sha256, ownership_token_sha256,
        digest(identity), identity, False, process_identity_observer,
    )


def run_gated_process(
    gated: GatedProcess, *, stdin: bytes, timeout_seconds: int,
) -> SubjectInvocation:
    """Release exactly one gated subject, then TERM/KILL its process group on timeout."""

    _require(not gated.released, "gated subject was already released")
    _require(verify_process_identity(gated), "gated subject process identity changed before release")
    started = time.monotonic()
    try:
        os.write(gated.release_fd, b"1")
    finally:
        os.close(gated.release_fd)
        gated.release_fd = -1
        gated.released = True
    try:
        stdout, stderr = gated.process.communicate(stdin, timeout=timeout_seconds)
        return SubjectInvocation(
            exit_code=gated.process.returncode,
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
            wall_seconds=float(time.monotonic() - started),
        )
    except subprocess.TimeoutExpired:
        os.killpg(gated.process.pid, signal.SIGTERM)
        try:
            stdout, stderr = gated.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(gated.process.pid, signal.SIGKILL)
            stdout, stderr = gated.process.communicate()
        return SubjectInvocation(
            exit_code=None,
            timed_out=True,
            stdout=stdout,
            stderr=stderr,
            wall_seconds=float(time.monotonic() - started),
        )
    except BaseException:
        try:
            os.killpg(gated.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            gated.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(gated.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            gated.process.communicate()
        raise


class ExecutionBackend(Protocol):
    """Narrow live boundary; fake implementations make the adapter provider-free testable."""

    def prepare(self, request: AttemptRequest) -> PreparedAttempt:
        """Revalidate inputs and prepare a gated process that has not executed Codex."""

    def run_subject(self, request: AttemptRequest, prepared: Any) -> SubjectInvocation:
        """Run exactly ``request.command`` and return only after the process stops."""

    def evaluate(
        self, request: AttemptRequest, prepared: Any, subject: SubjectInvocation
    ) -> EvaluatorInvocation:
        """Create the patch/prediction and run the pinned official evaluator once."""

    def prepare_evaluator(
        self, request: AttemptRequest, prepared: Any, subject: SubjectInvocation,
    ) -> GatedProcess:
        """Prepare but do not release the exact official evaluator."""

    def run_evaluator(
        self, request: AttemptRequest, prepared: Any, gated: GatedProcess,
    ) -> EvaluatorInvocation:
        """Release exactly the durably-owned official evaluator."""

    def cleanup(self, request: AttemptRequest, prepared: Any) -> None:
        """Remove trajectory-local credential material without deleting evidence."""

    def prove_not_running(
        self, request: AttemptRequest, prepared: Any, phase: str,
    ) -> dict[str, Any]:
        """Return a self-hashed ownership receipt only after the exact process is dead."""


class PreLaunchFailure(Exception):
    """A classified failure proven before any subject invocation starts."""

    def __init__(self, classification: str, anomaly_code: str) -> None:
        super().__init__(classification)
        self.classification = classification
        self.anomaly_code = anomaly_code


class CleanupFailure(ExperimentConfigurationError):
    """Cleanup failed after retaining the Docker proof already obtained."""

    def __init__(self, message: str, docker_ownership: dict[str, Any] | None) -> None:
        super().__init__(message)
        self.docker_ownership = docker_ownership


@dataclass(frozen=True)
class LocalTaskPreparation:
    """Private task materialization returned by the injected task callback."""

    workspace: Path
    prompt: bytes
    environment: Mapping[str, str]
    attestation: Mapping[str, Any]
    context: Any = None


@dataclass(frozen=True)
class LocalEvaluatorPlan:
    """One injected official-evaluator command plus its result decoder."""

    command: tuple[str, ...]
    cwd: Path
    environment: Mapping[str, str]
    stdin: bytes
    decode: Callable[[SubjectInvocation], EvaluatorInvocation]
    prediction: bytes = b""
    patch: bytes = b""


@dataclass
class LocalPreparedAttempt:
    """Owned local resources for one attempt; never reusable for another cell."""

    request_binding_sha256: str
    attempt_root: Path
    task: LocalTaskPreparation
    subject: GatedProcess
    evaluator_plan: LocalEvaluatorPlan | None = None
    evaluator: GatedProcess | None = None
    evaluator_containers_before: set[str] | None = None
    evaluator_container_ids: set[str] | None = None
    evaluator_docker_event_since_ns: int | None = None
    evaluator_docker_event_until_ns: int | None = None
    evaluator_ownership_marker: str | None = None
    evaluator_injection_sha256: str | None = None
    evaluator_dataset_sha256: str | None = None
    source_row_identity_sha256: str | None = None
    evaluator_docker_lifecycle_events: list[dict[str, Any]] | None = None
    remote_evaluator_receipt_sha256: str | None = None
    cleaned: bool = False


def _docker_container_ids(image: str) -> set[str]:
    completed = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"ancestor={image}"],
        capture_output=True, text=True, check=False,
    )
    _require(completed.returncode == 0, "Docker container ownership observation failed")
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}


def _docker_lifecycle_events(
    image: str, since_ns: int, until_ns: int,
) -> list[dict[str, Any]]:
    completed = subprocess.run(
        [
            "docker", "events", "--since", str(since_ns / 1_000_000_000),
            "--until", str(until_ns / 1_000_000_000),
            "--filter", "type=container",
            "--filter", "event=create", "--filter", "event=destroy",
            "--filter", f"image={image}", "--format", "{{json .}}",
        ],
        capture_output=True, text=True, check=False,
    )
    _require(completed.returncode == 0, "Docker create-event ownership observation failed")
    events: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ExperimentConfigurationError("Docker create-event evidence is malformed") from error
        actor = event.get("Actor") if isinstance(event, dict) else None
        container_id = actor.get("ID") if isinstance(actor, dict) else None
        attributes = actor.get("Attributes") if isinstance(actor, dict) else None
        action = event.get("Action", event.get("status")) if isinstance(event, dict) else None
        time_nano = event.get("timeNano") if isinstance(event, dict) else None
        _require(
            isinstance(container_id, str) and bool(container_id)
            and isinstance(attributes, dict)
            and action in {"create", "destroy"}
            and type(time_nano) is int
            and since_ns <= time_nano <= until_ns,
            "Docker lifecycle event evidence is malformed or outside its window",
        )
        events.append({
            "action": action,
            "container_id": container_id,
            "time_nano": time_nano,
            "image": attributes.get("image"),
            "name": attributes.get("name"),
            "ownership_marker_sha256": attributes.get(
                "engineering-scope-guard.ownership"
            ),
        })
    return sorted(
        events,
        key=lambda item: (item["time_nano"], item["container_id"], item["action"]),
    )


def _docker_observations(container_ids: set[str]) -> list[dict[str, Any]]:
    if not container_ids:
        return []
    completed = subprocess.run(
        ["docker", "inspect", *sorted(container_ids)],
        capture_output=True, text=True, check=False,
    )
    _require(completed.returncode == 0, "owned Docker container inspection failed")
    try:
        values = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ExperimentConfigurationError("owned Docker container evidence is malformed") from error
    _require(isinstance(values, list) and len(values) == len(container_ids), "owned Docker container set is ambiguous")
    return sorted(
        [
            {
                "id": value.get("Id"), "name": value.get("Name"),
                "image": value.get("Image"),
                "labels": (value.get("Config") or {}).get("Labels") or {},
                "running": (value.get("State") or {}).get("Running"),
            }
            for value in values
        ],
        key=lambda item: str(item["id"]),
    )


def _stop_owned_docker_containers(container_ids: set[str]) -> list[dict[str, Any]]:
    observations = _docker_observations(container_ids)
    running = {str(item["id"]) for item in observations if item["running"] is True}
    if running:
        stopped = subprocess.run(
            ["docker", "stop", "--time", "5", *sorted(running)],
            capture_output=True, text=True, check=False,
        )
        _require(stopped.returncode == 0, "owned evaluator Docker containers could not be stopped")
        observations = _docker_observations(container_ids)
    _require(all(item["running"] is False for item in observations), "owned Docker container is still running")
    return observations


def _docker_ids_with_exact_ownership(image: str, ownership_marker: str) -> set[str]:
    observations = _docker_observations(_docker_container_ids(image))
    return {
        item["id"] for item in observations
        if isinstance(item.get("labels"), dict)
        and item["labels"].get("engineering-scope-guard.ownership") == ownership_marker
    }


def _terminal_evaluator_container_observations(
    image: str, owned_ids: set[str], lifecycle: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Stop only still-present owned IDs and project event-proven removals."""

    current_owned = owned_ids & _docker_container_ids(image)
    observations = _stop_owned_docker_containers(current_owned)
    observed_ids = {item["id"] for item in observations}
    for container_id in sorted(owned_ids - observed_ids):
        events = [event for event in lifecycle if event["container_id"] == container_id]
        created = [event for event in events if event["action"] == "create"]
        destroyed = [event for event in events if event["action"] == "destroy"]
        _require(
            len(created) == 1 and len(destroyed) == 1
            and destroyed[0]["time_nano"] >= created[0]["time_nano"],
            "removed evaluator container lacks an exact create/destroy lifecycle",
        )
        observations.append({
            "id": container_id,
            "name": created[0]["name"],
            "image": created[0]["image"],
            "labels": {
                "engineering-scope-guard.ownership": created[0][
                    "ownership_marker_sha256"
                ]
            },
            "running": False,
            "removed": True,
        })
    return sorted(observations, key=lambda item: item["id"])


def _request_binding(request: AttemptRequest) -> str:
    return digest(
        {
            "cell_id": request.cell_id,
            "attempt": request.attempt,
            "command": list(request.command),
            "command_sha256": request.command_sha256,
            "effective_task_commitment_sha256": request.effective_task_commitment_sha256,
            "ownership_token_sha256": request.ownership_token_sha256,
        }
    )


def _private_local_path(path: Path, *, beneath: Path | None = None) -> Path:
    _require(".local" in path.parts, "local execution path is not contained by .local")
    cursor = path
    while cursor.name != ".local":
        _require(not cursor.is_symlink(), "local execution path contains a symlink")
        cursor = cursor.parent
    _require(not cursor.is_symlink(), "local execution root is a symlink")
    resolved = path.resolve()
    if beneath is not None:
        try:
            resolved.relative_to(beneath.resolve())
        except ValueError as error:
            raise ExperimentConfigurationError("local execution path escapes its attempt root") from error
    return resolved


class LocalExecutionBackend:
    """Concrete local backend whose external behavior is entirely injected.

    It owns process gating, identity, timeout, cleanup, and no-duplicate
    semantics.  Callbacks own only task materialization, frozen command
    resolution, and official-evaluator command/result adaptation.
    """

    _BASE_ATTESTATION_KEYS = {
        "runtime_identity", "source_identity", "evaluator_identity", "image_pool_identity",
        "codex_version", "model", "reasoning_effort", "resolved_image",
        "credential_isolated", "fresh_worktree", "sandbox", "network_access",
        "user_config_loaded", "external_tools_enabled",
    }

    def __init__(
        self, *, contract: dict[str, Any], live_seal: dict[str, Any], work_root: Path,
        task_callback: Callable[[AttemptRequest, Path], LocalTaskPreparation],
        command_callback: Callable[[AttemptRequest, LocalTaskPreparation], tuple[str, ...]],
        evaluator_callback: Callable[
            [AttemptRequest, LocalTaskPreparation, SubjectInvocation], LocalEvaluatorPlan
        ],
        cleanup_callback: Callable[[AttemptRequest, LocalTaskPreparation], None] | None = None,
        partial_cleanup_callback: Callable[[AttemptRequest, Path], dict[str, Any]] | None = None,
        process_identity_observer: Callable[..., dict[str, Any]] | None = None,
        trusted_evaluator_root: Path | None = None,
        evaluator_mode: str = "local_docker",
    ) -> None:
        validate_contract(contract)
        self.contract = contract
        self.live_seal = live_seal
        self.work_root = _private_local_path(Path(work_root))
        self.work_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.work_root.chmod(0o700)
        self.task_callback = task_callback
        self.command_callback = command_callback
        self.evaluator_callback = evaluator_callback
        self.cleanup_callback = cleanup_callback
        self.partial_cleanup_callback = partial_cleanup_callback
        self._partial_cleanup_evidence: dict[str, dict[str, Any]] = {}
        self.process_identity_observer = process_identity_observer
        _require(
            evaluator_mode in {"local_docker", "azure_batch"},
            "unknown evaluator execution mode",
        )
        self._evaluator_mode = evaluator_mode
        self.trusted_evaluator_root = (
            None if trusted_evaluator_root is None else Path(trusted_evaluator_root).resolve(strict=True)
        )

    @property
    def evaluator_mode(self) -> str:
        """Default legacy test-constructed backends to the local evaluator."""

        return getattr(self, "_evaluator_mode", "local_docker")

    def _state(self, request: AttemptRequest, prepared: Any) -> LocalPreparedAttempt:
        _require(isinstance(prepared, LocalPreparedAttempt), "local prepared state is malformed")
        _require(not prepared.cleaned, "local prepared state was already cleaned")
        _require(prepared.request_binding_sha256 == _request_binding(request), "local prepared state belongs to another attempt")
        return prepared

    def prepare(self, request: AttemptRequest) -> PreparedAttempt:
        attempt_root = self.work_root / request.cell_id / f"attempt-{request.attempt}"
        _private_local_path(attempt_root, beneath=self.work_root)
        _require(not attempt_root.exists(), "local attempt workspace already exists")
        attempt_root.mkdir(parents=True, mode=0o700)
        cursor = attempt_root
        while True:
            cursor.chmod(0o700)
            if cursor == self.work_root:
                break
            cursor = cursor.parent
        try:
            task = self.task_callback(request, attempt_root)
        except BaseException:
            if self.partial_cleanup_callback is not None:
                self._partial_cleanup_evidence[_request_binding(request)] = (
                    self.partial_cleanup_callback(request, attempt_root)
                )
            raise
        try:
            _require(isinstance(task, LocalTaskPreparation), "task callback returned malformed preparation")
            workspace = _private_local_path(Path(task.workspace), beneath=attempt_root)
            _require(workspace.is_dir(), "task callback did not materialize a workspace")
            _require(isinstance(task.prompt, bytes), "task callback prompt is not bytes")
            environment = dict(task.environment)
            _require(
                all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items()),
                "task callback environment is malformed",
            )
            _require("ESG_EXECUTION_NONCE" not in environment, "task callback controls the ownership nonce")
            command = self.command_callback(request, task)
            _require(isinstance(command, tuple) and command == request.command, "command callback differs from frozen subject command")
            base = dict(task.attestation)
            _require(set(base) == self._BASE_ATTESTATION_KEYS, "task callback attestation fields drifted")
            gated = prepare_gated_process(
                command, cwd=workspace, env=environment,
                command_sha256=request.command_sha256,
                ownership_token_sha256=request.ownership_token_sha256,
                process_identity_observer=self.process_identity_observer,
            )
        except BaseException:
            if self.partial_cleanup_callback is not None:
                self._partial_cleanup_evidence[_request_binding(request)] = (
                    self.partial_cleanup_callback(request, attempt_root)
                )
            elif self.cleanup_callback is not None:
                self.cleanup_callback(request, task)
            raise
        attestation = {
            **base,
            "command_sha256": request.command_sha256,
            "process_identity_sha256": gated.process_identity_sha256,
            "container_identity_sha256": digest({"resolved_image": request.task["resolved_image"]}),
            "prompt_sha256": hashlib.sha256(task.prompt).hexdigest(),
            "gated_before_exec": True,
        }
        state = LocalPreparedAttempt(
            request_binding_sha256=_request_binding(request),
            attempt_root=attempt_root,
            task=replace(task, workspace=workspace, environment=environment),
            subject=gated,
        )
        return PreparedAttempt(state=state, attestation=attestation)

    def partial_cleanup_evidence(self, request: AttemptRequest) -> dict[str, Any] | None:
        return self._partial_cleanup_evidence.get(_request_binding(request))

    def prelaunch_evidence(
        self, request: AttemptRequest, prepared: Any,
    ) -> dict[str, Any] | None:
        """Return the already-observed successor sentinel before subject release."""

        state = self._state(request, prepared)
        context = state.task.context if isinstance(state.task.context, dict) else {}
        evidence = context.get("successor_prelaunch")
        _require(
            evidence is None or isinstance(evidence, dict),
            "successor prelaunch evidence is malformed",
        )
        return evidence

    def run_subject(self, request: AttemptRequest, prepared: Any) -> SubjectInvocation:
        state = self._state(request, prepared)
        return run_gated_process(
            state.subject,
            stdin=state.task.prompt,
            timeout_seconds=request.subject_timeout_seconds,
        )

    def prepare_evaluator(
        self, request: AttemptRequest, prepared: Any, subject: SubjectInvocation,
    ) -> GatedProcess:
        state = self._state(request, prepared)
        _require(state.subject.process.poll() is not None, "subject is still running before evaluator preparation")
        _require(state.evaluator is None, "evaluator was already prepared")
        state.evaluator_ownership_marker = digest({"nonce_hex": secrets.token_hex(32)})
        if isinstance(state.task.context, dict):
            state.task.context["evaluator_ownership_marker"] = state.evaluator_ownership_marker
        plan = self.evaluator_callback(request, state.task, subject)
        _require(isinstance(plan, LocalEvaluatorPlan), "evaluator callback returned malformed plan")
        context = state.task.context if isinstance(state.task.context, dict) else {}
        state.evaluator_injection_sha256 = context.get("evaluator_injection_sha256")
        state.evaluator_dataset_sha256 = context.get("evaluator_dataset_sha256")
        state.source_row_identity_sha256 = context.get("source_row_identity_sha256")
        _require(
            isinstance(state.evaluator_injection_sha256, str)
            and len(state.evaluator_injection_sha256) == 64,
            "evaluator execution identity is absent",
        )
        _require(
            isinstance(state.evaluator_dataset_sha256, str)
            and len(state.evaluator_dataset_sha256) == 64
            and isinstance(state.source_row_identity_sha256, str)
            and len(state.source_row_identity_sha256) == 64,
            "frozen evaluator dataset binding is absent",
        )
        planned_cwd = Path(plan.cwd).resolve(strict=True)
        cwd = (
            planned_cwd
            if self.trusted_evaluator_root is not None
            and planned_cwd == self.trusted_evaluator_root
            else _private_local_path(planned_cwd, beneath=state.attempt_root)
        )
        _require(cwd.is_dir() and isinstance(plan.stdin, bytes), "evaluator plan inputs are malformed")
        environment = dict(plan.environment)
        _require(
            all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items())
            and "ESG_EXECUTION_NONCE" not in environment,
            "evaluator environment is malformed",
        )
        _require(bool(plan.command), "evaluator command is empty")
        if self.evaluator_mode == "local_docker":
            state.evaluator_containers_before = _docker_container_ids(
                request.task["resolved_image"]
            )
            state.evaluator_docker_event_since_ns = time.time_ns()
        evaluator_command_sha256 = digest(list(plan.command))
        evaluator_ownership_sha256 = state.evaluator_ownership_marker
        gated = prepare_gated_process(
            plan.command, cwd=cwd, env=environment,
            command_sha256=evaluator_command_sha256,
            ownership_token_sha256=evaluator_ownership_sha256,
            process_identity_observer=self.process_identity_observer,
        )
        state.evaluator_plan = replace(plan, cwd=cwd, environment=environment)
        state.evaluator = gated
        gated.container_identity_sha256 = digest(
            {
                "resolved_image": request.task["resolved_image"],
                "evaluator_mode": self.evaluator_mode,
                "baseline_container_ids": sorted(
                    state.evaluator_containers_before or set()
                ),
                "execution_identity_sha256": state.evaluator_injection_sha256,
                "evaluator_dataset_sha256": state.evaluator_dataset_sha256,
                "source_row_identity_sha256": state.source_row_identity_sha256,
            }
        )
        return gated

    def run_evaluator(
        self, request: AttemptRequest, prepared: Any, gated: GatedProcess,
    ) -> EvaluatorInvocation:
        state = self._state(request, prepared)
        _require(state.evaluator is gated and state.evaluator_plan is not None, "evaluator process does not belong to this attempt")
        try:
            raw = run_gated_process(
                gated,
                stdin=state.evaluator_plan.stdin,
                timeout_seconds=(
                    request.evaluator_timeout_seconds + 180
                    if self.evaluator_mode == "azure_batch"
                    else request.evaluator_timeout_seconds
                ),
            )
        finally:
            if self.evaluator_mode == "local_docker":
                self._capture_evaluator_containers(request, state)
        result = state.evaluator_plan.decode(raw)
        _validate_evaluator_result(result)
        if self.evaluator_mode == "azure_batch":
            return replace(
                result,
                prediction=state.evaluator_plan.prediction,
                patch=state.evaluator_plan.patch,
            )
        return replace(result, stdout=raw.stdout, stderr=raw.stderr,
            prediction=state.evaluator_plan.prediction, patch=state.evaluator_plan.patch)

    def evaluate(
        self, request: AttemptRequest, prepared: Any, subject: SubjectInvocation,
    ) -> EvaluatorInvocation:
        gated = self.prepare_evaluator(request, prepared, subject)
        return self.run_evaluator(request, prepared, gated)

    def abort(self, request: AttemptRequest, prepared: Any) -> None:
        state = self._state(request, prepared)
        if state.evaluator is not None:
            abort_gated_process(state.evaluator)
        abort_gated_process(state.subject)

    def _capture_evaluator_containers(
        self, request: AttemptRequest, state: LocalPreparedAttempt,
    ) -> set[str]:
        _require(state.evaluator_docker_event_since_ns is not None, "evaluator Docker event boundary is absent")
        _require(state.evaluator_ownership_marker is not None, "evaluator ownership marker is absent")
        state.evaluator_docker_event_until_ns = time.time_ns()
        lifecycle = _docker_lifecycle_events(
            request.task["resolved_image"], state.evaluator_docker_event_since_ns,
            state.evaluator_docker_event_until_ns,
        )
        owned_creates = [
            event for event in lifecycle
            if event["action"] == "create"
            and event["ownership_marker_sha256"] == state.evaluator_ownership_marker
        ]
        _require(
            all(
                event["ownership_marker_sha256"] == state.evaluator_ownership_marker
                for event in lifecycle if event["action"] == "create"
            ),
            "same-image Docker create event lacks the invocation ownership label",
        )
        _require(
            len({event["container_id"] for event in owned_creates}) == len(owned_creates),
            "Docker lifecycle contains duplicate owned create events",
        )
        candidates = {event["container_id"] for event in owned_creates}
        for container_id in candidates:
            events = [event for event in lifecycle if event["container_id"] == container_id]
            _require(
                all(
                    event["ownership_marker_sha256"] == state.evaluator_ownership_marker
                    for event in events
                )
                and len([event for event in events if event["action"] == "destroy"]) <= 1,
                "owned Docker lifecycle event label or cardinality drifted",
            )
        current = _docker_container_ids(request.task["resolved_image"])
        current_owned = candidates & current
        observations = _docker_observations(current_owned)
        for item in observations:
            labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
            _require(
                labels.get("engineering-scope-guard.ownership") == state.evaluator_ownership_marker,
                "live Docker container lacks the invocation-unique ownership label",
            )
        for container_id in candidates - current_owned:
            events = [event for event in lifecycle if event["container_id"] == container_id]
            created = next(event for event in events if event["action"] == "create")
            destroyed = [event for event in events if event["action"] == "destroy"]
            _require(
                len(destroyed) == 1 and destroyed[0]["time_nano"] >= created["time_nano"],
                "owned Docker container disappeared without a terminal destroy event",
            )
        state.evaluator_docker_lifecycle_events = lifecycle
        state.evaluator_container_ids = candidates
        return candidates

    def prove_not_running(
        self, request: AttemptRequest, prepared: Any, phase: str,
    ) -> dict[str, Any]:
        state = self._state(request, prepared)
        _require(phase in {"subject", "evaluator"}, "unknown local process phase")
        gated = state.subject if phase == "subject" else state.evaluator
        _require(gated is not None, "requested local process phase was never prepared")
        _require(not verify_process_identity(gated), "owned local process is still running")
        if phase == "evaluator":
            if self.evaluator_mode == "azure_batch":
                context = state.task.context if isinstance(state.task.context, dict) else {}
                receipt_path = context.get("azure_evaluator_receipt_path")
                _require(
                    isinstance(receipt_path, str) and Path(receipt_path).is_file(),
                    "Azure evaluator terminal receipt is absent",
                )
                receipt = read_object(Path(receipt_path))
                _require(
                    isinstance(receipt, dict)
                    and receipt.get("status") in {
                        "pass", "evaluator_infrastructure_failure"
                    },
                    "Azure evaluator is not proven terminal",
                )
                observations = []
            else:
                self._capture_evaluator_containers(request, state)
                observations = _terminal_evaluator_container_observations(
                    request.task["resolved_image"],
                    state.evaluator_container_ids,
                    state.evaluator_docker_lifecycle_events or [],
                )
        else:
            context = state.task.context if isinstance(state.task.context, dict) else {}
            materialization_id = context.get("materialization_container_id")
            observations = _docker_observations(
                {materialization_id} if isinstance(materialization_id, str) else set()
            )
            _require(all(item["running"] is False for item in observations), "materialization container is still running")
        return _canonical_artifact(
            {
                "schema_name": durable.OWNERSHIP_RECEIPT_SCHEMA,
                "schema_version": durable.SCHEMA_VERSION,
                "contract_sha256": self.contract["contract_sha256"],
                "schedule_sha256": self.contract["schedule"]["schedule_sha256"],
                "cell_id": request.cell_id,
                "attempt": request.attempt,
                "command_sha256": gated.command_sha256,
                "ownership_token_sha256": gated.ownership_token_sha256,
                "process_identity_sha256": gated.process_identity_sha256,
                "container_identity_sha256": digest(observations),
                "container_observations": observations,
                "status": "not_running",
            }
        )

    def cleanup(self, request: AttemptRequest, prepared: Any) -> dict[str, Any]:
        state = self._state(request, prepared)
        self.abort(request, state)
        errors: list[BaseException] = []
        context = state.task.context if isinstance(state.task.context, dict) else {}
        materialization_id = context.get("materialization_container_id")
        try:
            if state.evaluator is not None and self.evaluator_mode == "local_docker":
                self._capture_evaluator_containers(request, state)
            evaluator_observations = _terminal_evaluator_container_observations(
                request.task["resolved_image"],
                set(state.evaluator_container_ids or set()),
                state.evaluator_docker_lifecycle_events or [],
            ) if state.evaluator is not None and self.evaluator_mode == "local_docker" else []
            owned_ids: set[str] = set()
            if isinstance(materialization_id, str):
                owned_ids.add(materialization_id)
            observations = sorted(
                [*_stop_owned_docker_containers(owned_ids), *evaluator_observations],
                key=lambda item: item["id"],
            )
        except BaseException as error:
            observations = []
            errors.append(error)
        try:
            if self.cleanup_callback is not None:
                self.cleanup_callback(request, state.task)
        except BaseException as error:
            errors.append(error)
        docker_ownership = {
            "schema_name": "engineering-scope-guard.reasoning-effort-v2-docker-ownership",
            "schema_version": durable.SCHEMA_VERSION,
            "contract_sha256": self.contract["contract_sha256"],
            "cell_id": request.cell_id, "attempt": request.attempt,
            "resolved_image": request.task["resolved_image"],
            "materialization_container_id": materialization_id,
            "prelaunch_ownership_token_sha256": request.ownership_token_sha256,
            "baseline_container_ids": sorted(state.evaluator_containers_before or set()),
            "create_event_container_ids": sorted(state.evaluator_container_ids or set()),
            "event_window_start_ns": state.evaluator_docker_event_since_ns,
            "event_window_end_ns": state.evaluator_docker_event_until_ns,
            "attribution_mode": (
                "python_sitecustomize_docker_sdk_label_and_prune_suppression"
                if state.evaluator is not None and self.evaluator_mode == "local_docker"
                else "azure_batch_worker_receipt"
                if state.evaluator is not None
                else None
            ),
            "evaluator_mode": self.evaluator_mode,
            "ownership_marker_sha256": state.evaluator_ownership_marker,
            "injection_sha256": state.evaluator_injection_sha256,
            "injection_relative_path": (
                f"attempts/{request.cell_id}/attempt-{request.attempt}/"
                "evaluator-python-injection/sitecustomize.py"
                if state.evaluator is not None and self.evaluator_mode == "local_docker"
                else None
            ),
            "evaluator_dataset_sha256": state.evaluator_dataset_sha256,
            "evaluator_dataset_relative_path": (
                f"attempts/{request.cell_id}/attempt-{request.attempt}/"
                "evaluator-dataset/task.jsonl"
                if state.evaluator is not None and self.evaluator_mode == "local_docker"
                else None
            ),
            "source_row_identity_sha256": state.source_row_identity_sha256,
            "lifecycle_events": state.evaluator_docker_lifecycle_events or [],
            "final_observations": observations,
        }
        if errors:
            raise CleanupFailure(
                "local cleanup could not prove every owned resource terminal",
                docker_ownership if observations else None,
            ) from errors[0]
        state.cleaned = True
        return docker_ownership


def evaluator_executable(path: Path) -> Path:
    """Keep the venv entry path while verifying its symlink target exists."""

    absolute = path.absolute()
    _require(
        absolute.is_file() and absolute.resolve(strict=True).is_file(),
        "evaluator Python is missing or invalid",
    )
    return absolute


def freeze_private_pool_task_from_dataset(
    *, root: Path, evaluator_python: Path, dataset_root: Path,
    qualification_receipt: dict[str, Any], candidate_slot: int,
) -> dict[str, Any]:
    """Resolve one row provider-free and preserve mutable tag vs immutable digest."""

    qualifier_live.validate_receipt(qualification_receipt)
    candidates = {
        candidate["slot"]: candidate for candidate in qualification_receipt["candidates"]
    }
    candidate = candidates.get(candidate_slot)
    _require(candidate is not None and candidate["status"] == "qualified", "pool task is not qualified")
    selected = next(
        (
            item for item in [
                *qualification_receipt["selection"]["primary"],
                *qualification_receipt["selection"]["alternates"],
            ]
            if item["slot"] == candidate_slot
        ),
        None,
    )
    _require(selected is not None, "qualified task is outside the terminal selection")
    language = candidate["language"]
    task_id = candidate["instance_id"]
    repository = candidate["repo"]
    docker_image = candidate["docker_image"]
    resolved_image = selected["resolved_image"]
    resolved = resolve_dataset_task(
        root.resolve(), evaluator_executable(evaluator_python), dataset_root.resolve(),
        language, task_id, "resolve",
    )
    _require(
        resolved.get("instance_id") == task_id
        and resolved.get("language") == language
        and resolved.get("repo") == repository
        and resolved.get("docker_image") == docker_image,
        "dataset row differs from proposed private-pool identity",
    )
    _require(
        isinstance(resolved_image, str) and "@sha256:" in resolved_image
        and len(candidate["manifest_sha256"]) == 64,
        "private-pool immutable image or snapshot binding is malformed",
    )
    source_row_identity_sha256 = digest({
        "instance_id": task_id, "language": language, "repo": repository,
        "base_commit": resolved["base_commit"], "docker_image": docker_image,
        "problem_statement_sha256": resolved["problem_statement_sha256"],
    })
    return {
        "task_id": task_id, "repository": repository, "language": language,
        "base_commit": resolved["base_commit"], "docker_image": docker_image,
        "resolved_image": resolved_image,
        "problem_statement_sha256": resolved["problem_statement_sha256"],
        "task_snapshot_sha256": candidate["manifest_sha256"],
        "source_row_identity_sha256": source_row_identity_sha256,
    }


def build_local_execution_backend(
    *, root: Path, contract: dict[str, Any], live_seal: dict[str, Any],
    work_root: Path, evaluator_root: Path, dataset_root: Path,
    evaluator_python: Path, codex_binary: str, source_codex_home: Path,
    model_catalog: Path, reserve_receipt: Path,
    successor_runtime_gate: Path | None = None,
    azure_evaluator_state_root: Path | None = None,
    azure_evaluator_worker: Path | None = None,
    process_identity_observer: Callable[..., dict[str, Any]] | None = None,
) -> LocalExecutionBackend:
    """Build the project-wired live backend from the frozen v1 primitives.

    The returned backend performs no work until ``execute_one_attempt`` selects
    exactly one replay-authorized cell.  Docker containers are deliberately not
    removed automatically; their identity receipt remains for reconciliation.
    """

    root = root.resolve()
    evaluator_root = evaluator_root.resolve()
    dataset_root = dataset_root.resolve()
    evaluator_python = evaluator_executable(evaluator_python)
    source_codex_home = source_codex_home.resolve(strict=True)
    model_catalog = model_catalog.resolve(strict=True)
    reserve_receipt = reserve_receipt.resolve(strict=True)
    resolved_codex = Path(shutil.which(codex_binary) or codex_binary).resolve(strict=True)
    azure_mode = azure_evaluator_state_root is not None or azure_evaluator_worker is not None
    _require(
        not azure_mode
        or (azure_evaluator_state_root is not None and azure_evaluator_worker is not None),
        "Azure evaluator inputs must be provided together",
    )
    resolved_azure_state = (
        _private_local_path(azure_evaluator_state_root)
        if azure_evaluator_state_root is not None
        else None
    )
    resolved_azure_worker = (
        azure_evaluator_worker.resolve(strict=True)
        if azure_evaluator_worker is not None
        else None
    )
    successor_gate: dict[str, Any] | None = None
    if successor_runtime_gate is not None:
        successor_gate_path = successor_runtime_gate.resolve(strict=True)
        _require_private_path(successor_gate_path)
        successor_gate = read_object(successor_gate_path)
        _require(
            isinstance(successor_gate, dict)
            and successor_gate.get("schema_name")
            == "engineering-scope-guard.launch-surface-successor-runtime-gate"
            and successor_gate.get("schema_version") == 1
            and successor_gate.get("successor_runtime_gate_sha256")
            == digest(
                {
                    key: value
                    for key, value in successor_gate.items()
                    if key != "successor_runtime_gate_sha256"
                }
            ),
            "successor runtime gate is malformed",
        )
        validate_runtime_receipt(successor_gate["runtime_receipt"])
        validate_launch_contract(successor_gate["launch_contract"])
        _require(
            contract["runtime"]["runtime_identity"]
            == successor_gate["runtime_receipt"]["receipt_sha256"]
            and contract["source"]["evaluator_identity"]
            == successor_gate["preflight"]["evaluator_identity_sha256"],
            "successor gate differs from the frozen contract",
        )

    def _task_callback_impl(
        request: AttemptRequest, attempt_root: Path,
    ) -> LocalTaskPreparation:
        task = request.task
        required = {
            "task_id", "repository", "language", "base_commit", "docker_image", "resolved_image",
            "problem_statement_sha256", "task_snapshot_sha256", "source_row_identity_sha256",
        }
        _require(required <= set(task), "frozen private task lacks live materialization fields")
        raw = attempt_root / "raw"
        repository = attempt_root / "repository"
        derived = attempt_root / "derived"
        codex_home = attempt_root / "codex-home"
        for path in (raw, repository, derived, codex_home):
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        prompt_path = raw / "task-prompt.txt"
        qualification_receipt = live_seal["qualification_gate"]["qualification_receipt"]
        source_args = argparse.Namespace(
            root=root, reserve=reserve_receipt, evaluator_root=evaluator_root,
            dataset_root=dataset_root, evaluator_python=evaluator_python,
            codex_binary=resolved_codex, model_catalog=model_catalog,
        )
        qualifier_live._revalidate_sources(source_args, qualification_receipt)
        help_result = subprocess.run(
            [str(resolved_codex), "exec", "--help"],
            capture_output=True, text=True, check=False,
        )
        _require(help_result.returncode == 0, "Codex subject interface is unavailable")
        successor_prelaunch: dict[str, Any] | None = None
        if successor_gate is None:
            observed_runtime = qualifier_live._codex_runtime(resolved_codex, model_catalog)
            try:
                validate_treatment_pair(
                    build_launch_profile(
                        executable=resolved_codex,
                        model=contract["runtime"]["model"],
                        reasoning_effort="low",
                    ),
                    build_launch_profile(
                        executable=resolved_codex,
                        model=contract["runtime"]["model"],
                        reasoning_effort="medium",
                    ),
                    exec_help=help_result.stdout,
                )
            except LaunchSurfaceError as error:
                raise ExperimentConfigurationError(
                    f"Codex subject launch surface is incompatible: {error}"
                ) from error
            _require(
                observed_runtime == qualification_receipt["runtime_observation"],
                "current Codex/Docker/model runtime differs from qualification",
            )
            runtime_identity = digest(observed_runtime)
            codex_version = observed_runtime["codex_version"]
            source_identity = digest(qualification_receipt["source"])
            evaluator_identity = digest({
                key: qualification_receipt["source"][key]
                for key in (
                    "evaluator_revision", "evaluator_tree_sha256", "evaluator_python",
                    "embedded_repolaunch_revision", "repolaunch_tree_sha256",
                )
            })
        else:
            runtime_receipt = successor_gate["runtime_receipt"]
            launch_contract = successor_gate["launch_contract"]
            try:
                runtime_observation = sentinel(runtime_receipt)
                validate_launch_contract(
                    launch_contract, exec_help=help_result.stdout
                )
                treatment_diff = launch_contract["treatment_diff"]
            except (LaunchSurfaceError, RuntimeIdentityError) as error:
                raise ExperimentConfigurationError(
                    f"successor runtime or launch sentinel failed: {error}"
                ) from error
            cell = next(
                item for item in contract["schedule"]["cells"]
                if item["cell_id"] == request.cell_id
            )
            profile = launch_contract["profiles"][cell["reasoning_effort"]]
            _require(
                tuple(rendered_command(profile)) == request.command,
                "subject command differs from the frozen successor launch profile",
            )
            successor_prelaunch_body = {
                "schema_name": "engineering-scope-guard.launch-surface-pre-cell-sentinel",
                "schema_version": 1,
                "contract_sha256": contract["contract_sha256"],
                "cell_id": request.cell_id,
                "attempt": request.attempt,
                "reasoning_effort": cell["reasoning_effort"],
                "runtime": runtime_observation,
                "runtime_receipt_sha256": runtime_receipt["receipt_sha256"],
                "successor_runtime_gate_sha256": successor_gate[
                    "successor_runtime_gate_sha256"
                ],
                "launch_surface_contract_sha256": launch_contract["contract_sha256"],
                "launch_profile_sha256": launch_contract["profile_sha256s"][
                    cell["reasoning_effort"]
                ],
                "treatment_diff_sha256": launch_contract["treatment_diff_sha256"],
                "treatment_only": treatment_diff["treatment_only"],
                "command_sha256": request.command_sha256,
                "status": "pass",
            }
            successor_prelaunch = {
                **successor_prelaunch_body,
                "pre_cell_sentinel_sha256": digest(successor_prelaunch_body),
            }
            runtime_identity = runtime_receipt["receipt_sha256"]
            codex_version = runtime_receipt["codex_version"]
            source_identity = contract["source"]["source_identity"]
            evaluator_identity = contract["source"]["evaluator_identity"]
        resolved = resolve_dataset_task(
            root, evaluator_python, dataset_root, task["language"], task["task_id"], "resolve"
        )
        expected = {
            "instance_id": task["task_id"], "language": task["language"],
            "repo": task["repository"], "base_commit": task["base_commit"],
            "docker_image": task["docker_image"],
            "problem_statement_sha256": task["problem_statement_sha256"],
        }
        _require(resolved == expected, "dataset task identity differs from the frozen private task")
        image = subprocess.run(
            ["docker", "image", "inspect", task["docker_image"],
             "--format", "{{json .RepoDigests}}"],
            capture_output=True, text=True, check=False,
        )
        try:
            repo_digests = json.loads(image.stdout) if image.returncode == 0 else []
        except json.JSONDecodeError as error:
            raise ExperimentConfigurationError("local frozen image identity is malformed") from error
        _require(
            isinstance(repo_digests, list) and task["resolved_image"] in repo_digests,
            "mutable dataset image tag no longer resolves to the qualified digest",
        )
        prompt_identity = resolve_dataset_task(
            root, evaluator_python, dataset_root, task["language"], task["task_id"],
            "prompt", prompt_path,
        )
        prompt = _validate_prompt_bytes(
            prompt_path, prompt_identity, task["problem_statement_sha256"]
        )
        created = subprocess.run(
            [
                "docker", "create", "--platform", "linux/amd64",
                "--label", f"engineering-scope-guard.ownership={request.ownership_token_sha256}",
                task["resolved_image"], "true",
            ],
            capture_output=True, text=True, check=False,
        )
        _require(created.returncode == 0 and bool(created.stdout.strip()), "cannot create frozen task image")
        container_id = created.stdout.strip()
        _write_private_bytes(raw / "materialization-container-id", (container_id + "\n").encode())
        copied = subprocess.run(
            ["docker", "cp", f"{container_id}:/testbed/.", str(repository)],
            capture_output=True, check=False,
        )
        _require(copied.returncode == 0, "cannot materialize frozen task repository")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repository,
            capture_output=True, text=True, check=False,
        )
        _require(head.returncode == 0 and head.stdout.strip() == task["base_commit"], "materialized repository base commit drifted")
        baseline = capture_repository_baseline(repository, derived)
        provision_file_auth(source_codex_home, codex_home)
        environment = v1_environment(codex_home, dataset_root.parent / "hf-cache")
        cell = next(cell for cell in contract["schedule"]["cells"] if cell["cell_id"] == request.cell_id)
        attestation = {
            "runtime_identity": runtime_identity,
            "source_identity": source_identity,
            "evaluator_identity": evaluator_identity,
            "image_pool_identity": live_seal["qualification_gate"]["image_pool_identity"],
            "codex_version": codex_version,
            "model": contract["runtime"]["model"],
            "reasoning_effort": cell["reasoning_effort"],
            "resolved_image": task["resolved_image"],
            "credential_isolated": True, "fresh_worktree": True,
            "sandbox": "workspace-write", "network_access": False,
            "user_config_loaded": False, "external_tools_enabled": False,
        }
        return LocalTaskPreparation(
            workspace=repository, prompt=prompt, environment=environment,
            attestation=attestation,
            context={
                "baseline": baseline, "derived": derived, "codex_home": codex_home,
                "materialization_container_id": container_id,
                "successor_prelaunch": successor_prelaunch,
            },
        )

    def task_callback(request: AttemptRequest, attempt_root: Path) -> LocalTaskPreparation:
        try:
            return _task_callback_impl(request, attempt_root)
        except PreLaunchFailure:
            raise
        except ExperimentConfigurationError as error:
            message = str(error)
            if any(fragment in message for fragment in (
                "frozen private task", "dataset task identity", "dataset bridge",
                "mutable dataset image tag", "prompt", "base commit drifted",
            )):
                raise PreLaunchFailure(
                    "frozen_task_binding_corrupt", "frozen_task_binding_prelaunch"
                ) from error
            if any(fragment in message for fragment in (
                "create frozen task image", "materialize frozen task repository",
                "Docker", "repository",
            )):
                raise PreLaunchFailure(
                    "task_repository_or_container_unavailable",
                    "task_materialization_prelaunch",
                ) from error
            if any(fragment in message for fragment in (
                "Codex subject interface", "current Codex", "qualification",
            )):
                raise PreLaunchFailure(
                    "runtime_or_source_identity_drift", "prelaunch_source_runtime_drift"
                ) from error
            raise

    def command_callback(request: AttemptRequest, _task: LocalTaskPreparation) -> tuple[str, ...]:
        _require(request.command[0] == str(resolved_codex), "subject command Codex path drifted")
        return request.command

    def evaluator_callback(
        request: AttemptRequest, task_state: LocalTaskPreparation,
        _subject: SubjectInvocation,
    ) -> LocalEvaluatorPlan:
        context = task_state.context
        _require(isinstance(context, dict), "materialized task context is malformed")
        ownership_marker = context.get("evaluator_ownership_marker")
        _require(
            isinstance(ownership_marker, str) and len(ownership_marker) == 64,
            "evaluator invocation ownership marker is absent",
        )
        patch = subject_patch_from_baseline(
            task_state.workspace, context["derived"], context["baseline"]
        )
        prediction = (
            json.dumps(
                {request.task["task_id"]: {"model_patch": patch.decode("utf-8")}},
                sort_keys=True, separators=(",", ":"),
            ) + "\n"
        ).encode()
        if azure_mode:
            assert resolved_azure_state is not None
            assert resolved_azure_worker is not None
            azure_root = task_state.workspace.parent / "azure-evaluator"
            azure_root.mkdir(parents=True, mode=0o700)
            patch_path = azure_root / "patch.diff"
            _write_private_bytes(patch_path, patch)
            safe_cell = re.sub(r"[^A-Za-z0-9_-]", "-", request.cell_id)[:36]
            job_id = f"esgrr002-{safe_cell}-a{request.attempt}"
            azure_task_id = "eval-1"
            request_body = {
                "job_id": job_id,
                "azure_task_id": azure_task_id,
                "task": request.task,
                "patch_path": str(patch_path),
                "evaluator_timeout_seconds": request.evaluator_timeout_seconds,
            }
            request_path = azure_root / "request.json"
            _write_private_bytes(
                request_path,
                (json.dumps(request_body, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            )
            context["evaluator_injection_sha256"] = hashlib.sha256(
                resolved_azure_worker.read_bytes()
            ).hexdigest()
            context["evaluator_dataset_sha256"] = digest(
                {
                    "task_id": request.task["task_id"],
                    "source_row_identity_sha256": request.task[
                        "source_row_identity_sha256"
                    ],
                }
            )
            context["source_row_identity_sha256"] = request.task[
                "source_row_identity_sha256"
            ]
            receipt_path = (
                resolved_azure_state / "receipts"
                / f"{job_id}-{azure_task_id}.json"
            )
            context["azure_evaluator_receipt_path"] = str(receipt_path)
            command = (
                sys.executable,
                str(Path(__file__).resolve().parent / "azure_prediction_evaluator.py"),
                "evaluate",
                "--state-root",
                str(resolved_azure_state),
                "--worker",
                str(resolved_azure_worker),
                "--request",
                str(request_path),
            )
            environment = {
                name: os.environ[name]
                for name in (
                    "PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "SSL_CERT_FILE",
                    "SSL_CERT_DIR", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "ALL_PROXY",
                )
                if name in os.environ
            }

            def decode_azure(raw: SubjectInvocation) -> EvaluatorInvocation:
                receipt = read_object(receipt_path) if receipt_path.is_file() else None
                artifact_root = (
                    resolved_azure_state / "artifacts" / job_id / azure_task_id
                    / "azure-evaluator"
                )
                report_path = artifact_root / "official" / request.task["task_id"] / "report.json"
                results_path = artifact_root / "official" / "results.json"
                stdout_path = artifact_root / "evaluator.stdout"
                stderr_path = artifact_root / "evaluator.stderr"
                report = read_object(report_path) if report_path.is_file() else None
                results = read_object(results_path) if results_path.is_file() else None
                return EvaluatorInvocation(
                    exit_code=(
                        0
                        if isinstance(receipt, dict) and receipt.get("status") == "pass"
                        else raw.exit_code
                    ),
                    timed_out=(
                        bool(receipt.get("timed_out"))
                        if isinstance(receipt, dict)
                        else raw.timed_out
                    ),
                    report=report,
                    results=results,
                    wall_seconds=raw.wall_seconds,
                    stdout=stdout_path.read_bytes() if stdout_path.is_file() else raw.stdout,
                    stderr=stderr_path.read_bytes() if stderr_path.is_file() else raw.stderr,
                    report_bytes=report_path.read_bytes() if report_path.is_file() else None,
                    results_bytes=results_path.read_bytes() if results_path.is_file() else None,
                    infrastructure_failure=not (
                        isinstance(receipt, dict) and receipt.get("status") == "pass"
                    ),
                )

            return LocalEvaluatorPlan(
                command=command,
                cwd=azure_root,
                environment=environment,
                stdin=b"",
                decode=decode_azure,
                prediction=prediction,
                patch=patch,
            )
        injection_dir = task_state.workspace.parent / "evaluator-python-injection"
        injection_path, injection_sha256 = _write_evaluator_docker_sdk_injection(
            injection_dir,
            ownership_marker=ownership_marker,
        )
        context["evaluator_injection_sha256"] = injection_sha256
        prediction_path = context["derived"] / "prediction.json"
        _write_private_bytes(prediction_path, prediction)
        output = task_state.workspace.parent / "evaluator" / "official"
        output.mkdir(parents=True, mode=0o700)
        output.chmod(0o700)
        evaluator_environment = v1_environment(
            context["codex_home"], dataset_root.parent / "hf-cache"
        )
        evaluator_environment["PYTHONPATH"] = (
            str(injection_dir)
            + os.pathsep
            + evaluator_environment.get("PYTHONPATH", "")
        )
        frozen_dataset = task_state.workspace.parent / "evaluator-dataset" / "task.jsonl"
        dataset_sha256, source_row_identity_sha256 = _write_frozen_evaluator_dataset(
            evaluator_python=evaluator_python, dataset_root=dataset_root,
            task=request.task, output=frozen_dataset, environment=evaluator_environment,
        )
        context["evaluator_dataset_sha256"] = dataset_sha256
        context["source_row_identity_sha256"] = source_row_identity_sha256
        command = tuple(official_evaluator_command(
            evaluator_python, frozen_dataset, request.task["language"],
            prediction_path, output, 1, request.task["task_id"],
        ))

        def decode(raw: SubjectInvocation) -> EvaluatorInvocation:
            report_path = output / request.task["task_id"] / "report.json"
            results_path = output / "results.json"
            report = read_object(report_path) if report_path.is_file() else None
            results = read_object(results_path) if results_path.is_file() else None
            return EvaluatorInvocation(
                exit_code=raw.exit_code, timed_out=raw.timed_out,
                report=report, results=results, wall_seconds=raw.wall_seconds,
                report_bytes=report_path.read_bytes() if report_path.is_file() else None,
                results_bytes=results_path.read_bytes() if results_path.is_file() else None,
            )

        return LocalEvaluatorPlan(
            command=command, cwd=evaluator_root,
            environment=evaluator_environment,
            stdin=b"", decode=decode, prediction=prediction, patch=patch,
        )

    def cleanup_callback(_request: AttemptRequest, task_state: LocalTaskPreparation) -> None:
        context = task_state.context
        _require(isinstance(context, dict), "cleanup task context is malformed")
        remove_file_auth(context["codex_home"])
        _require(
            not (context["codex_home"] / "auth.json").exists(),
            "trajectory-local credential cleanup was not proven",
        )

    def partial_cleanup_callback(
        request: AttemptRequest, attempt_root: Path,
    ) -> dict[str, Any]:
        errors: list[BaseException] = []
        owned: set[str] = set()
        observations: list[dict[str, Any]] = []
        try:
            owned = _docker_ids_with_exact_ownership(
                request.task["resolved_image"], request.ownership_token_sha256
            )
            _require(len(owned) <= 1, "partial preparation has ambiguous owned containers")
            observations = _stop_owned_docker_containers(owned)
        except BaseException as error:
            errors.append(error)
        codex_home = attempt_root / "codex-home"
        try:
            if (codex_home / "auth.json").exists():
                remove_file_auth(codex_home)
            _require(
                not (codex_home / "auth.json").exists(),
                "partial preparation credential cleanup was not proven",
            )
        except BaseException as error:
            errors.append(error)
        if errors:
            raise ExperimentConfigurationError(
                "partial preparation cleanup could not prove all owned resources terminal"
            ) from errors[0]
        return {
            "schema_name": "engineering-scope-guard.reasoning-effort-v2-docker-ownership",
            "schema_version": durable.SCHEMA_VERSION,
            "contract_sha256": contract["contract_sha256"],
            "cell_id": request.cell_id, "attempt": request.attempt,
            "resolved_image": request.task["resolved_image"],
            "materialization_container_id": next(iter(owned), None),
            "prelaunch_ownership_token_sha256": request.ownership_token_sha256,
            "baseline_container_ids": [], "create_event_container_ids": [],
            "event_window_start_ns": None, "event_window_end_ns": None,
            "attribution_mode": None, "ownership_marker_sha256": None,
            "injection_sha256": None, "injection_relative_path": None,
            "evaluator_dataset_sha256": None,
            "evaluator_dataset_relative_path": None,
            "source_row_identity_sha256": None,
            "lifecycle_events": [], "final_observations": observations,
        }

    return LocalExecutionBackend(
        contract=contract, live_seal=live_seal, work_root=work_root,
        task_callback=task_callback, command_callback=command_callback,
        evaluator_callback=evaluator_callback, cleanup_callback=cleanup_callback,
        partial_cleanup_callback=partial_cleanup_callback,
        process_identity_observer=process_identity_observer,
        trusted_evaluator_root=evaluator_root if not azure_mode else None,
        evaluator_mode="azure_batch" if azure_mode else "local_docker",
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def _canonical_artifact(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "receipt_sha256": digest(body)}


def _write_artifact(path: Path, body: dict[str, Any]) -> None:
    """Create one immutable, canonical, private artifact with durable readback."""

    artifact = _canonical_artifact(body)
    existing = path.parent
    while not existing.exists():
        existing = existing.parent
    _require_private_path(existing / "placeholder")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    cursor = path.parent
    while cursor.name != ".local" and ".local" in cursor.parts:
        _require(not cursor.is_symlink(), "execution artifact directory is a symlink")
        cursor.chmod(0o700)
        cursor = cursor.parent
    _require_private_path(path)
    encoded = (json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        if path.exists():
            _require(path.read_bytes() == encoded, "execution artifact already differs")
            temporary.unlink()
            return
        os.replace(temporary, path)
        path.chmod(0o600)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        _require(path.read_bytes() == encoded, "execution artifact readback differs")
    finally:
        if temporary.exists():
            temporary.unlink()


def _require_private_path(path: Path) -> None:
    storage_root = durable._execution_storage_root(path)
    _require(not path.is_symlink(), "private evidence path is a symlink")
    cursor = path.parent
    while True:
        if cursor.exists():
            _require(not cursor.is_symlink(), "private evidence ancestor is a symlink")
            _require((cursor.stat().st_mode & 0o777) == 0o700, "private evidence ancestor mode is not 0700")
        if cursor.resolve() == storage_root.resolve():
            break
        _require(cursor.resolve().is_relative_to(storage_root.resolve()), "private evidence escapes execution storage")
        cursor = cursor.parent


def _write_private_bytes(path: Path, content: bytes) -> str:
    """Persist immutable raw evidence privately and return its byte digest."""

    _require(".local" in path.parts, "private evidence is outside .local")
    # Never repair pre-existing unsafe permissions silently: doing so could hide
    # a period in which another local user could observe the evidence.
    existing = path.parent
    while not existing.exists():
        existing = existing.parent
    _require_private_path(existing / "placeholder")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    cursor = path.parent
    while cursor.name != ".local":
        cursor.chmod(0o700)
        cursor = cursor.parent
    _require_private_path(path)
    if path.exists():
        _require(path.is_file() and (path.stat().st_mode & 0o777) == 0o600, "raw evidence file is unsafe")
        _require(path.read_bytes() == content, "raw execution evidence already differs")
    else:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o600)
    return hashlib.sha256(content).hexdigest()


def _write_evaluator_docker_sdk_injection(
    injection_dir: Path, *, ownership_marker: str,
) -> tuple[Path, str]:
    """Inject one invocation label into Docker SDK ``run``/``create`` calls."""

    _require(len(ownership_marker) == 64, "evaluator Docker ownership marker is malformed")
    injection_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    storage_root = durable._execution_storage_root(injection_dir)
    cursor = injection_dir
    while True:
        cursor.chmod(0o700)
        if cursor == storage_root:
            break
        cursor = cursor.parent
    source = f'''"""Attempt-scoped Docker SDK ownership injection; generated by ESG."""
from docker.models.containers import ContainerCollection
from docker.models.images import ImageCollection

_KEY = "engineering-scope-guard.ownership"
_MARKER = "{ownership_marker}"

def _wrap(original):
    def owned(self, *args, **kwargs):
        labels = kwargs.get("labels")
        if labels is None:
            labels = {{}}
        elif not isinstance(labels, dict):
            raise RuntimeError("Docker SDK labels must be a mapping")
        else:
            labels = dict(labels)
        existing = labels.get(_KEY)
        if existing not in (None, _MARKER):
            raise RuntimeError("Docker SDK ownership label conflicts with frozen invocation")
        labels[_KEY] = _MARKER
        kwargs["labels"] = labels
        return original(self, *args, **kwargs)
    return owned

ContainerCollection.run = _wrap(ContainerCollection.run)
ContainerCollection.create = _wrap(ContainerCollection.create)

def _suppress_global_prune(self, *args, **kwargs):
    filters = kwargs.get("filters")
    if args or filters != {{"dangling": True}} or set(kwargs) != {{"filters"}}:
        raise RuntimeError("unscoped Docker image prune is prohibited")
    return {{"ImagesDeleted": [], "SpaceReclaimed": 0}}

ImageCollection.prune = _suppress_global_prune
'''.encode()
    path = injection_dir / "sitecustomize.py"
    return path, _write_private_bytes(path, source)


_FROZEN_EVALUATOR_DATASET_SCRIPT = r"""
import hashlib, json, os, pathlib, sys
import pyarrow.parquet as parquet

dataset_root, language, instance_id, repository, base_commit, source_tag, problem_sha, resolved_image, output = sys.argv[1:]
paths = sorted((pathlib.Path(dataset_root) / "data").glob(f"{language}-*.parquet"))
if len(paths) != 1:
    raise SystemExit("dataset split cardinality drifted")
rows = parquet.read_table(paths[0]).to_pylist()
matches = [row for row in rows if row.get("instance_id") == instance_id]
if len(matches) != 1:
    raise SystemExit("dataset row cardinality drifted")
row = dict(matches[0])
if row.get("repo") != repository or row.get("base_commit") != base_commit or row.get("docker_image") != source_tag:
    raise SystemExit("dataset row identity drifted")
problem = row.get("problem_statement")
if not isinstance(problem, str) or hashlib.sha256(problem.encode()).hexdigest() != problem_sha:
    raise SystemExit("dataset problem statement drifted")
projection = {
    "instance_id": instance_id, "language": language, "repo": repository,
    "base_commit": base_commit, "docker_image": source_tag,
    "problem_statement_sha256": problem_sha,
}
source_identity = hashlib.sha256((json.dumps(projection, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
row["docker_image"] = resolved_image
encoded = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(descriptor, "wb") as handle:
    handle.write(encoded)
    handle.flush()
    os.fsync(handle.fileno())
print(json.dumps({"dataset_sha256": hashlib.sha256(encoded).hexdigest(), "source_row_identity_sha256": source_identity}, sort_keys=True))
"""


def _write_frozen_evaluator_dataset(
    *, evaluator_python: Path, dataset_root: Path, task: dict[str, Any], output: Path,
    environment: Mapping[str, str],
) -> tuple[str, str]:
    """Write one private source-verified row whose image is the frozen digest."""

    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.parent.chmod(0o700)
    completed = subprocess.run(
        [
            str(evaluator_python), "-c", _FROZEN_EVALUATOR_DATASET_SCRIPT,
            str(dataset_root), task["language"], task["task_id"], task["repository"],
            task["base_commit"], task["docker_image"], task["problem_statement_sha256"],
            task["resolved_image"], str(output),
        ],
        cwd=output.parent,
        env=dict(environment), capture_output=True, text=True, check=False,
    )
    _require(completed.returncode == 0, "private frozen evaluator dataset generation failed")
    try:
        metadata = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ExperimentConfigurationError("frozen evaluator dataset metadata is malformed") from error
    expected_source = digest({
        "instance_id": task["task_id"], "language": task["language"],
        "repo": task["repository"], "base_commit": task["base_commit"],
        "docker_image": task["docker_image"],
        "problem_statement_sha256": task["problem_statement_sha256"],
    })
    _require(
        task.get("source_row_identity_sha256") == expected_source,
        "private task source-row identity differs from frozen fields",
    )
    _require_private_path(output)
    _require(
        output.is_file() and (output.stat().st_mode & 0o777) == 0o600
        and metadata == {
            "dataset_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "source_row_identity_sha256": expected_source,
        },
        "frozen evaluator dataset bytes or source-row identity differ",
    )
    return metadata["dataset_sha256"], metadata["source_row_identity_sha256"]


def _work_from_trace(trace: dict[str, Any], wall_seconds: float) -> dict[str, int | float]:
    usage = trace["usage"]["provider_reported"]
    activity = trace["activity"]
    return {
        "input_tokens": usage["input_tokens"],
        "cached_input_tokens": usage["cached_input_tokens"],
        "cache_write_input_tokens": usage["cache_write_input_tokens"],
        "output_tokens": usage["output_tokens"],
        "reasoning_output_tokens": usage["reasoning_output_tokens"],
        "turns": activity["turns"],
        "tool_actions": activity["commands"],
        "search_actions": activity["repository_search_commands"],
        "correction_turns": max(activity["turns"] - 1, 0),
        "wall_seconds": wall_seconds,
    }


def _common(
    contract: dict[str, Any], request: AttemptRequest
) -> dict[str, Any]:
    return {
        "schema_version": durable.SCHEMA_VERSION,
        "contract_sha256": contract["contract_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "cell_id": request.cell_id,
        "attempt": request.attempt,
        "effective_task_commitment_sha256": request.effective_task_commitment_sha256,
    }


def _write_terminal_artifacts(
    execution_root: Path,
    contract: dict[str, Any],
    request: AttemptRequest,
    *,
    status: str,
    subject_started: bool,
    exit_code: int | None,
    evaluator_disposition: str,
    anomaly_codes: list[str],
    work: dict[str, int | float] | None,
) -> None:
    common = _common(contract, request)
    root = execution_root / "artifacts" / request.cell_id / f"attempt-{request.attempt}"
    raw_root = root / "raw"

    def raw_hash(name: str) -> str | None:
        path = raw_root / name
        if not path.exists():
            return None
        _require_private_path(path)
        _require(path.is_file() and (path.stat().st_mode & 0o777) == 0o600, "raw evidence file is unsafe")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    cleanup_path = root / "cleanup.json"
    cleanup_receipt_sha256: str | None = None
    if cleanup_path.exists():
        _require_private_path(cleanup_path)
        cleanup_receipt = json.loads(cleanup_path.read_text(encoding="utf-8"))
        _require(
            isinstance(cleanup_receipt, dict)
            and cleanup_receipt.get("receipt_sha256")
            == digest({key: value for key, value in cleanup_receipt.items() if key != "receipt_sha256"}),
            "cleanup receipt is malformed",
        )
        cleanup_receipt_sha256 = cleanup_receipt["receipt_sha256"]
    evaluator_launch_path = root / "evaluator-launch.json"
    evaluator_launch: dict[str, Any] | None = None
    if evaluator_launch_path.exists():
        _require_private_path(evaluator_launch_path)
        evaluator_launch = json.loads(evaluator_launch_path.read_text(encoding="utf-8"))
        _require(
            isinstance(evaluator_launch, dict)
            and evaluator_launch.get("receipt_sha256")
            == digest({key: value for key, value in evaluator_launch.items() if key != "receipt_sha256"}),
            "evaluator launch receipt is malformed",
        )

    launch = {
        "command_sha256": request.command_sha256 if subject_started else None,
        "ownership_token_sha256": request.ownership_token_sha256 if subject_started else None,
        "process_identity_sha256": request.process_identity_sha256 if subject_started else None,
        "container_identity_sha256": (
            digest({"resolved_image": request.task["resolved_image"]}) if subject_started else None
        ),
    }
    _write_artifact(
        root / "execution.json",
        {
            **common,
            "schema_name": durable.EXECUTION_ARTIFACT_SCHEMA,
            "subject_invocation_started": subject_started,
            **launch,
            "status": status,
            "timed_out": status == "trajectory_timeout",
            "subject_exit_code": exit_code,
            "subject_stdout_sha256": raw_hash("codex.jsonl"),
            "subject_stderr_sha256": raw_hash("codex.stderr"),
            "prediction_sha256": raw_hash("prediction.json"),
            "patch_sha256": raw_hash("patch.diff"),
            "cleanup_receipt_sha256": cleanup_receipt_sha256,
        },
    )
    _write_artifact(
        root / "evaluator.json",
        {
            **common,
            "schema_name": durable.EVALUATOR_ARTIFACT_SCHEMA,
            "evaluator_identity": contract["source"]["evaluator_identity"],
            "disposition": evaluator_disposition,
            "anomaly_codes": anomaly_codes,
            "evaluator_stdout_sha256": raw_hash("evaluator.stdout"),
            "evaluator_stderr_sha256": raw_hash("evaluator.stderr"),
            "report_sha256": raw_hash("evaluator-report.json"),
            "results_sha256": raw_hash("evaluator-results.json"),
            "invocation_started": evaluator_launch is not None,
            "evaluator_command_sha256": None if evaluator_launch is None else evaluator_launch["evaluator_command_sha256"],
            "ownership_token_sha256": None if evaluator_launch is None else evaluator_launch["ownership_token_sha256"],
            "process_identity_sha256": None if evaluator_launch is None else evaluator_launch["process_identity_sha256"],
            "container_identity_sha256": None if evaluator_launch is None else evaluator_launch["container_identity_sha256"],
        },
    )
    _write_artifact(
        root / "measurement.json",
        {
            **common,
            "schema_name": durable.MEASUREMENT_ARTIFACT_SCHEMA,
            "record_completeness": "complete" if work is not None else "absent",
            **(
                work
                if work is not None
                else {
                    field: None
                    for field in (*durable.INTEGER_WORK_FIELDS, *durable.FLOAT_WORK_FIELDS)
                }
            ),
        },
    )


def _effective_task(
    private_pool: dict[str, Any], commitment: str
) -> dict[str, Any]:
    matches = [
        task
        for task in [*private_pool["primaries"], *private_pool["alternates"]]
        if digest(task) == commitment
    ]
    _require(len(matches) == 1, "effective private task binding is absent or ambiguous")
    task = matches[0]
    _require(
        isinstance(task.get("resolved_image"), str) and bool(task["resolved_image"]),
        "effective private task lacks a resolved image",
    )
    return task


def _request(
    contract: dict[str, Any], private_pool: dict[str, Any], *, cell_id: str,
    attempt: int, codex_binary: str, commitment: str,
) -> AttemptRequest:
    command = tuple(subject_command_arguments(contract, cell_id, codex_binary=codex_binary))
    normalized = ("<CODEX_BINARY>", *command[1:])
    _require(
        digest(list(normalized)) == subject_command_identity(contract, cell_id),
        "resolved subject command differs from its frozen path-independent identity",
    )
    ownership_token = secrets.token_bytes(32)
    ownership_sha = digest({"ownership_token_hex": ownership_token.hex()})
    process_sha = digest(
        {
            "contract_sha256": contract["contract_sha256"],
            "cell_id": cell_id,
            "attempt": attempt,
            "ownership_token_sha256": ownership_sha,
        }
    )
    return AttemptRequest(
        cell_id=cell_id,
        attempt=attempt,
        task=_effective_task(private_pool, commitment),
        command=command,
        command_sha256=subject_command_identity(contract, cell_id),
        effective_task_commitment_sha256=commitment,
        ownership_token_sha256=ownership_sha,
        process_identity_sha256=process_sha,
        subject_timeout_seconds=contract["trajectory"]["subject_timeout_seconds"],
        evaluator_timeout_seconds=contract["trajectory"]["evaluator_timeout_seconds"],
    )


def _validate_subject_result(result: SubjectInvocation) -> None:
    _require(type(result.timed_out) is bool, "subject timeout evidence is malformed")
    _require(result.exit_code is None or type(result.exit_code) is int, "subject exit code is malformed")
    _require(isinstance(result.stdout, bytes) and isinstance(result.stderr, bytes), "subject streams are malformed")
    _require(
        type(result.wall_seconds) is float
        and math.isfinite(result.wall_seconds)
        and result.wall_seconds >= 0.0,
        "subject wall measurement is malformed",
    )


def _validate_evaluator_result(result: EvaluatorInvocation) -> None:
    _require(type(result.timed_out) is bool, "evaluator timeout evidence is malformed")
    _require(result.exit_code is None or type(result.exit_code) is int, "evaluator exit code is malformed")
    _require(
        type(result.wall_seconds) is float
        and math.isfinite(result.wall_seconds)
        and result.wall_seconds >= 0.0,
        "evaluator wall measurement is malformed",
    )
    _require(
        (result.report is None or isinstance(result.report, dict))
        and (result.results is None or isinstance(result.results, dict))
        and all(isinstance(value, bytes) for value in (
            result.stdout, result.stderr, result.prediction, result.patch,
        ))
        and (result.report_bytes is None or isinstance(result.report_bytes, bytes))
        and (result.results_bytes is None or isinstance(result.results_bytes, bytes)),
        "evaluator structured evidence is malformed",
    )
    _require(
        type(result.infrastructure_failure) is bool,
        "evaluator infrastructure classification is malformed",
    )


def _validated_preparation(
    prepared: PreparedAttempt, request: AttemptRequest, contract: dict[str, Any],
    live_seal: dict[str, Any], cell: dict[str, Any],
) -> AttemptRequest:
    _require(isinstance(prepared, PreparedAttempt), "backend preparation lacks typed attestation")
    attestation = prepared.attestation
    expected_keys = {
        "runtime_identity", "source_identity", "evaluator_identity", "image_pool_identity",
        "codex_version", "model", "reasoning_effort", "resolved_image",
        "command_sha256", "process_identity_sha256", "container_identity_sha256",
        "prompt_sha256", "credential_isolated", "fresh_worktree", "gated_before_exec",
        "sandbox", "network_access", "user_config_loaded", "external_tools_enabled",
    }
    _require(isinstance(attestation, dict) and set(attestation) == expected_keys, "backend attestation fields drifted")
    _require(
        attestation["runtime_identity"] == live_seal["runtime_identity"] == contract["runtime"]["runtime_identity"]
        and attestation["source_identity"] == live_seal["source_identity"] == contract["source"]["source_identity"]
        and attestation["evaluator_identity"] == live_seal["evaluator_identity"] == contract["source"]["evaluator_identity"]
        and attestation["image_pool_identity"] == live_seal["image_pool_identity"] == contract["source"]["image_pool_identity"]
        and attestation["codex_version"] == contract["runtime"]["codex_version"]
        and attestation["model"] == contract["runtime"]["model"]
        and attestation["reasoning_effort"] == cell["reasoning_effort"]
        and attestation["resolved_image"] == request.task["resolved_image"]
        and attestation["command_sha256"] == request.command_sha256
        and attestation["container_identity_sha256"] == digest({"resolved_image": request.task["resolved_image"]})
        and isinstance(attestation["process_identity_sha256"], str)
        and len(attestation["process_identity_sha256"]) == 64
        and isinstance(attestation["prompt_sha256"], str)
        and len(attestation["prompt_sha256"]) == 64
        and attestation["credential_isolated"] is True
        and attestation["fresh_worktree"] is True
        and attestation["gated_before_exec"] is True
        and attestation["sandbox"] == "workspace-write"
        and attestation["network_access"] is False
        and attestation["user_config_loaded"] is False
        and attestation["external_tools_enabled"] is False,
        "backend attestation differs from frozen runtime/source/image/command isolation",
    )
    return replace(request, process_identity_sha256=attestation["process_identity_sha256"])


def _write_revalidation_receipts(
    root: Path, contract: dict[str, Any], live_seal: dict[str, Any],
    attestation: dict[str, Any],
) -> None:
    _write_artifact(
        root / "runtime-revalidation.json",
        {
            "schema_name": durable.RUNTIME_REVALIDATION_SCHEMA,
            "schema_version": durable.SCHEMA_VERSION,
            "contract_sha256": contract["contract_sha256"],
            "live_seal_sha256": live_seal["live_seal_sha256"],
            "runtime_identity": attestation["runtime_identity"],
            "status": "pass",
        },
    )
    _write_artifact(
        root / "source-revalidation.json",
        {
            "schema_name": durable.SOURCE_REVALIDATION_SCHEMA,
            "schema_version": durable.SCHEMA_VERSION,
            "contract_sha256": contract["contract_sha256"],
            "live_seal_sha256": live_seal["live_seal_sha256"],
            "source_identity": attestation["source_identity"],
            "evaluator_identity": attestation["evaluator_identity"],
            "image_pool_identity": attestation["image_pool_identity"],
            "status": "pass",
        },
    )


def execute_one_attempt(
    *,
    backend: ExecutionBackend,
    contract: dict[str, Any],
    private_pool: dict[str, Any],
    live_seal: dict[str, Any],
    execution_root: Path,
    cell_id: str,
    attempt: int,
    codex_binary: str = "codex",
) -> dict[str, Any]:
    """Execute and reconcile exactly one attempt, never a loop or implicit retry."""

    validate_contract(contract)
    validate_private_pool_binding(private_pool, contract)
    durable.validate_live_seal(contract, private_pool, live_seal)
    root = execution_root.resolve()
    durable._execution_storage_root(root)  # Fail closed unless initialized private authority exists.
    ledger = root / "ledger.jsonl"
    checkpoint = root / "checkpoint.json"
    receipts = root / "receipts"
    lock_path = root / "execution-adapter.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ExperimentConfigurationError(
                "another effort-v2 execution adapter owns the state lock"
            ) from error
        events = durable.read_ledger(ledger, contract)
        validate_harness_source_closure(
            contract["source"]["harness_source_closure"],
            root=Path(__file__).resolve().parents[1],
        )
        validate_prior_evidence_identity(
            contract["source"]["prior_evidence_identity"],
            root=Path(__file__).resolve().parents[1],
        )
        state = durable.replay_attempt_state(contract, durable._semantic(events))
        _require(state["batch_stop_classification"] is None, "batch is already stopped")
        _require(state["next_cell_id"] == cell_id, "requested cell is not the frozen next cell")
        cell = next(item for item in contract["schedule"]["cells"] if item["cell_id"] == cell_id)
        commitment = state["effective_task_commitment_by_slot"][cell["population_slot"]]
        request = _request(
            contract, private_pool, cell_id=cell_id, attempt=attempt,
            codex_binary=codex_binary, commitment=commitment,
        )
        disk_snapshot = disk_safety_snapshot(root, filesystem_path=root)
        disk_receipt = public_disk_safety_receipt(disk_snapshot)
        durable.record_disk_safety_checked(
            ledger, checkpoint, contract, live_seal, private_pool,
            cell_id=cell_id, attempt=attempt, receipt=disk_receipt,
        )
        if disk_receipt["status"] != "pass":
            return {
                "receipt": None,
                "transition": {
                    "action": "batch_stopped_disk_safety_failed",
                    "classification": "durable_evidence_incomplete",
                    "disk_safety_receipt_sha256": digest(disk_receipt),
                },
            }
        if not durable.reserve_attempt_capacity_or_stop(
            ledger, checkpoint, contract, live_seal, private_pool,
            cell_id=cell_id, attempt=attempt,
        ):
            return {
                "receipt": None,
                "transition": {
                    "action": "batch_stopped_capacity_exhausted",
                    "classification": "durable_evidence_incomplete",
                },
            }
        durable.record_attempt_started(
            ledger, checkpoint, contract, live_seal, private_pool,
            cell_id=cell_id, attempt=attempt,
        )
        prepared: Any = None
        preparation_completed = False
        cleanup_completed = False
        active_phase: str | None = None

        def persist_partial_cleanup_evidence() -> None:
            getter = getattr(backend, "partial_cleanup_evidence", None)
            if not callable(getter):
                return
            docker_body = getter(request)
            _require(isinstance(docker_body, dict), "partial cleanup evidence is absent")
            artifact_root = root / "artifacts" / request.cell_id / f"attempt-{request.attempt}"
            _write_artifact(artifact_root / "docker-ownership.json", docker_body)
            _write_artifact(
                artifact_root / "cleanup.json",
                {
                    **_common(contract, request),
                    "schema_name": "engineering-scope-guard.reasoning-effort-v2-cleanup",
                    "status": "pass",
                    "docker_ownership_receipt_sha256": digest(docker_body),
                },
            )

        def finish(
            *, status: str, subject_started: bool, exit_code: int | None,
            evaluator_disposition: str, anomaly_codes: list[str],
            work: dict[str, int | float] | None,
        ) -> dict[str, Any]:
            nonlocal cleanup_completed
            if preparation_completed:
                try:
                    cleanup_result = backend.cleanup(request, prepared.state)
                except BaseException as cleanup_error:
                    cleanup_completed = True
                    if (
                        isinstance(cleanup_error, CleanupFailure)
                        and cleanup_error.docker_ownership is None
                    ):
                        raise
                    failed_docker_sha = None
                    if isinstance(cleanup_error, CleanupFailure) and cleanup_error.docker_ownership is not None:
                        docker_body = cleanup_error.docker_ownership
                        docker_path = (
                            root / "artifacts" / request.cell_id
                            / f"attempt-{request.attempt}" / "docker-ownership.json"
                        )
                        _write_artifact(docker_path, docker_body)
                        failed_docker_sha = digest(docker_body)
                    _write_artifact(
                        root / "artifacts" / request.cell_id
                        / f"attempt-{request.attempt}" / "cleanup.json",
                        {
                            **_common(contract, request),
                            "schema_name": "engineering-scope-guard.reasoning-effort-v2-cleanup",
                            "status": "failed",
                            "docker_ownership_receipt_sha256": failed_docker_sha,
                        },
                    )
                    _write_terminal_artifacts(
                        root, contract, request,
                        status="isolation_contract_violation",
                        subject_started=subject_started, exit_code=exit_code,
                        evaluator_disposition=(
                            "incomplete" if active_phase == "evaluator" else "not_run"
                        ),
                        anomaly_codes=["credential_cleanup_failed"], work=None,
                    )
                    _export_persist_reconcile(root, contract, private_pool, live_seal, request)
                    raise
                cleanup_completed = True
                docker_ownership_receipt_sha256 = None
                if isinstance(cleanup_result, dict):
                    docker_body = dict(cleanup_result)
                    _require("receipt_sha256" not in docker_body, "Docker ownership body is pre-sealed")
                    docker_path = (
                        root / "artifacts" / request.cell_id
                        / f"attempt-{request.attempt}" / "docker-ownership.json"
                    )
                    _write_artifact(docker_path, docker_body)
                    docker_ownership_receipt_sha256 = digest(docker_body)
                _write_artifact(
                    root / "artifacts" / request.cell_id
                    / f"attempt-{request.attempt}" / "cleanup.json",
                    {
                        **_common(contract, request),
                        "schema_name": "engineering-scope-guard.reasoning-effort-v2-cleanup",
                        "status": "pass",
                        "docker_ownership_receipt_sha256": docker_ownership_receipt_sha256,
                    },
                )
            _write_terminal_artifacts(
                root, contract, request, status=status,
                subject_started=subject_started, exit_code=exit_code,
                evaluator_disposition=evaluator_disposition,
                anomaly_codes=anomaly_codes, work=work,
            )
            return _export_persist_reconcile(root, contract, private_pool, live_seal, request)
        try:
            try:
                prepared = backend.prepare(request)
                preparation_completed = True
            except PreLaunchFailure as error:
                persist_partial_cleanup_evidence()
                return finish(status=error.classification,
                    subject_started=False, exit_code=None, evaluator_disposition="not_run",
                    anomaly_codes=[error.anomaly_code], work=None)
            except BaseException:
                persist_partial_cleanup_evidence()
                finish(
                    status="harness_failure", subject_started=False, exit_code=None,
                    evaluator_disposition="not_run",
                    anomaly_codes=["backend_preparation_failed"], work=None,
                )
                raise

            try:
                request = _validated_preparation(prepared, request, contract, live_seal, cell)
            except ExperimentConfigurationError:
                return finish(status="runtime_or_source_identity_drift",
                    subject_started=False, exit_code=None, evaluator_disposition="not_run",
                    anomaly_codes=["prelaunch_attestation_drift"], work=None)
            _write_revalidation_receipts(
                root, contract, live_seal, prepared.attestation
            )
            prelaunch_evidence = getattr(backend, "prelaunch_evidence", None)
            if callable(prelaunch_evidence):
                observed_prelaunch = prelaunch_evidence(request, prepared.state)
                if observed_prelaunch is not None:
                    _write_artifact(
                        root / "artifacts" / cell_id / f"attempt-{attempt}"
                        / "pre-cell-sentinel.json",
                        observed_prelaunch,
                    )
            durable.record_subject_invocation_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell_id, attempt=attempt,
                command_sha256=request.command_sha256,
                ownership_token_sha256=request.ownership_token_sha256,
                process_identity_sha256=request.process_identity_sha256,
            )
            active_phase = "subject"
            # If this call raises, no terminal receipt is invented: the durable
            # ownership boundary must be reconciled with a proven-dead receipt.
            subject = backend.run_subject(request, prepared.state)
            _validate_subject_result(subject)
            evidence_root = root / "artifacts" / cell_id / f"attempt-{attempt}" / "raw"
            stdout_sha = _write_private_bytes(evidence_root / "codex.jsonl", subject.stdout)
            stderr_sha = _write_private_bytes(evidence_root / "codex.stderr", subject.stderr)
            _write_artifact(
                evidence_root / "subject-streams.json",
                {
                    **_common(contract, request),
                    "schema_name": "engineering-scope-guard.reasoning-effort-v2-subject-streams",
                    "stdout_sha256": stdout_sha,
                    "stderr_sha256": stderr_sha,
                    "command_sha256": request.command_sha256,
                    "ownership_token_sha256": request.ownership_token_sha256,
                    "process_identity_sha256": request.process_identity_sha256,
                },
            )
            try:
                trace = parse_subject_trace(subject.stdout)
            except ExperimentConfigurationError:
                status = "trajectory_timeout" if subject.timed_out else "malformed_inconsistent_measurement"
                return finish(status=status, subject_started=True,
                    exit_code=subject.exit_code, evaluator_disposition="not_run",
                    anomaly_codes=["subject_trace_invalid"], work=None)

            work = _work_from_trace(trace, subject.wall_seconds)
            if subject.timed_out:
                status = "trajectory_timeout"
            elif trace["provider_infrastructure_failure"]:
                status = "provider_api_infrastructure_failure"
            elif subject.exit_code != 0:
                status = "agent_subject_failure"
            else:
                status = "returned"
            if status != "returned":
                return finish(status=status, subject_started=True,
                    exit_code=subject.exit_code, evaluator_disposition="not_run",
                    anomaly_codes=[], work=work)

            prepare_evaluator = getattr(backend, "prepare_evaluator", None)
            run_evaluator = getattr(backend, "run_evaluator", None)
            _require(
                callable(prepare_evaluator) and callable(run_evaluator),
                "execution backend lacks the mandatory gated evaluator boundary",
            )
            gated_evaluator = prepare_evaluator(request, prepared.state, subject)
            _require(isinstance(gated_evaluator, GatedProcess), "gated evaluator state is malformed")
            evaluator_command_sha256 = gated_evaluator.command_sha256
            evaluator_ownership_sha256 = gated_evaluator.ownership_token_sha256
            evaluator_process_sha256 = gated_evaluator.process_identity_sha256
            evaluator_container_sha256 = (
                gated_evaluator.container_identity_sha256
                or digest({"resolved_image": request.task["resolved_image"]})
            )
            durable.record_evaluator_invocation_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell_id, attempt=attempt,
                evaluator_command_sha256=evaluator_command_sha256,
                ownership_token_sha256=evaluator_ownership_sha256,
                process_identity_sha256=evaluator_process_sha256,
                container_identity_sha256=evaluator_container_sha256,
            )
            active_phase = "evaluator"
            _write_artifact(
                root / "artifacts" / cell_id / f"attempt-{attempt}" / "evaluator-launch.json",
                {
                    **_common(contract, request),
                    "schema_name": "engineering-scope-guard.reasoning-effort-v2-evaluator-launch",
                    "evaluator_command_sha256": evaluator_command_sha256,
                    "ownership_token_sha256": evaluator_ownership_sha256,
                    "process_identity_sha256": evaluator_process_sha256,
                    "container_identity_sha256": evaluator_container_sha256,
                },
            )
            try:
                evaluator = run_evaluator(request, prepared.state, gated_evaluator)
            except BaseException:
                prove = getattr(backend, "prove_not_running", None)
                if callable(prove):
                    ownership = prove(request, prepared.state, "evaluator")
                    encoded = (
                        json.dumps(ownership, sort_keys=True, separators=(",", ":")) + "\n"
                    ).encode()
                    _write_private_bytes(
                        root / "artifacts" / cell_id / f"attempt-{attempt}"
                        / "evaluator-ownership-not-running.json",
                        encoded,
                    )
                raise
            _validate_evaluator_result(evaluator)
            _write_private_bytes(evidence_root / "prediction.json", evaluator.prediction)
            _write_private_bytes(evidence_root / "patch.diff", evaluator.patch)
            _write_private_bytes(evidence_root / "evaluator.stdout", evaluator.stdout)
            _write_private_bytes(evidence_root / "evaluator.stderr", evaluator.stderr)
            _write_private_bytes(
                evidence_root / "evaluator-report.json",
                evaluator.report_bytes
                if evaluator.report_bytes is not None
                else (json.dumps(evaluator.report, sort_keys=True, separators=(",", ":")) + "\n").encode()
                if evaluator.report is not None else b"null\n",
            )
            _write_private_bytes(
                evidence_root / "evaluator-results.json",
                evaluator.results_bytes
                if evaluator.results_bytes is not None
                else (json.dumps(evaluator.results, sort_keys=True, separators=(",", ":")) + "\n").encode()
                if evaluator.results is not None else b"null\n",
            )
            if evaluator.timed_out:
                execution_status = "local_docker_runtime_infrastructure_failure"
                disposition = "incomplete"
                anomalies = ["evaluator_timeout"]
            elif evaluator.infrastructure_failure:
                execution_status = "local_docker_runtime_infrastructure_failure"
                disposition = "incomplete"
                anomalies = ["azure_evaluator_infrastructure_failure"]
            elif evaluator.exit_code != 0 or evaluator.results is None:
                execution_status = "returned"
                disposition = "error"
                anomalies = ["evaluator_command_error"]
            else:
                try:
                    parsed = parse_official_evaluator_artifacts(
                        request.task["task_id"], evaluator.report or {}, evaluator.results
                    )
                except ExperimentConfigurationError:
                    execution_status = "malformed_inconsistent_measurement"
                    disposition = "not_run"
                    anomalies = ["evaluator_artifact_invalid"]
                else:
                    execution_status = "returned"
                    disposition = {
                        "success": "accepted",
                        "failure": "test_failure",
                        "empty_patch": "empty_patch",
                        "error": "error",
                        "incomplete": "incomplete",
                    }[parsed.disposition]
                    anomalies = []
            return finish(status=execution_status, subject_started=True,
                exit_code=subject.exit_code, evaluator_disposition=disposition,
                anomaly_codes=anomalies, work=work)
        except BaseException:
            current = durable.read_ledger(ledger, contract)
            finished = any(
                event["event_type"] == "attempt_finished"
                and event["payload"].get("cell_id") == cell_id
                and event["payload"].get("attempt") == attempt
                for event in current
            )
            if preparation_completed and active_phase is not None and not finished:
                prove = getattr(backend, "prove_not_running", None)
                _require(callable(prove), "execution backend cannot prove the interrupted process dead")
                ownership = prove(request, prepared.state, active_phase)
                ownership_path = (
                    root / "artifacts" / cell_id / f"attempt-{attempt}"
                    / f"{active_phase}-ownership-not-running.json"
                )
                _write_private_bytes(
                    ownership_path,
                    (json.dumps(ownership, sort_keys=True, separators=(",", ":")) + "\n").encode(),
                )
                reconcile = (
                    durable.reconcile_orphaned_evaluator
                    if active_phase == "evaluator"
                    else durable.reconcile_orphaned_invocation
                )
                reconcile(
                    ledger, checkpoint, receipts, contract, private_pool, live_seal,
                    cell_id=cell_id, attempt=attempt,
                    ownership_receipt_path=ownership_path,
                )
            raise
        finally:
            if preparation_completed and not cleanup_completed:
                backend.cleanup(request, prepared.state)


def _export_persist_reconcile(
    root: Path,
    contract: dict[str, Any],
    private_pool: dict[str, Any],
    live_seal: dict[str, Any],
    request: AttemptRequest,
) -> dict[str, Any]:
    receipt = durable.build_terminal_receipt_from_artifact_root(
        contract, private_pool, root / "ledger.jsonl", root,
        cell_id=request.cell_id, attempt=request.attempt,
    )
    durable.persist_terminal_receipt(root / "receipts", contract, receipt)
    transition = durable.reconcile_attempt(
        root / "ledger.jsonl", root / "checkpoint.json", root / "receipts",
        contract, private_pool, live_seal,
        cell_id=request.cell_id, attempt=request.attempt,
    )
    return {"receipt": receipt, "transition": transition}


def reconcile_proven_dead_attempt(
    *, contract: dict[str, Any], private_pool: dict[str, Any],
    live_seal: dict[str, Any], execution_root: Path, cell_id: str, attempt: int,
    ownership_receipt_path: Path,
) -> dict[str, Any]:
    """Terminalize a post-start crash only from adapter-produced not-running proof."""

    root = execution_root.resolve()
    durable._execution_storage_root(root)
    return durable.reconcile_orphaned_invocation(
        root / "ledger.jsonl", root / "checkpoint.json", root / "receipts",
        contract, private_pool, live_seal,
        cell_id=cell_id, attempt=attempt,
        ownership_receipt_path=ownership_receipt_path,
    )


def reconcile_proven_dead_evaluator(
    *, contract: dict[str, Any], private_pool: dict[str, Any],
    live_seal: dict[str, Any], execution_root: Path, cell_id: str, attempt: int,
    ownership_receipt_path: Path,
) -> dict[str, Any]:
    """Fail closed after a durably-owned evaluator is proven dead; never rerun it."""

    root = execution_root.resolve()
    durable._execution_storage_root(root)
    return durable.reconcile_orphaned_evaluator(
        root / "ledger.jsonl", root / "checkpoint.json", root / "receipts",
        contract, private_pool, live_seal, cell_id=cell_id, attempt=attempt,
        ownership_receipt_path=ownership_receipt_path,
    )


@contextmanager
def _control_lock(execution_root: Path) -> Iterator[None]:
    """Serialize operator recovery with the live execution adapter."""

    lock_path = execution_root / "execution-adapter.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ExperimentConfigurationError(
                "another effort-v2 execution adapter owns the state lock"
            ) from error
        yield


def _unfinished_attempt(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Derive the sole interrupted phase without accepting caller identity."""

    finished = {
        (event["payload"]["cell_id"], event["payload"]["attempt"])
        for event in events if event["event_type"] == "attempt_finished"
    }
    starts = [
        event for event in events
        if event["event_type"] == "attempt_started"
        and (event["payload"]["cell_id"], event["payload"]["attempt"]) not in finished
    ]
    _require(len(starts) <= 1, "ledger has more than one unfinished durable attempt")
    if not starts:
        return None
    payload = starts[0]["payload"]
    matching_types = {
        event["event_type"] for event in events
        if event["payload"].get("cell_id") == payload["cell_id"]
        and event["payload"].get("attempt") == payload["attempt"]
    }
    phase = (
        "evaluator" if "evaluator_invocation_started" in matching_types
        else "subject" if "subject_invocation_started" in matching_types
        else "pre_subject"
    )
    return {
        "cell_id": payload["cell_id"],
        "attempt": payload["attempt"],
        "effective_task_commitment_sha256": payload[
            "effective_task_commitment_sha256"
        ],
        "phase": phase,
    }


def execution_status(
    *, contract: dict[str, Any], private_pool: dict[str, Any],
    live_seal: dict[str, Any], execution_root: Path,
) -> dict[str, Any]:
    """Return a read-only status projection from the validated durable ledger."""

    validate_contract(contract)
    validate_private_pool_binding(private_pool, contract)
    durable.validate_live_seal(contract, private_pool, live_seal)
    root = execution_root.resolve()
    durable._execution_storage_root(root)
    events = durable.read_ledger(root / "ledger.jsonl", contract)
    state = durable.replay_attempt_state(contract, durable._semantic(events))
    unfinished = _unfinished_attempt(events)
    return {
        "action": "interrupted_attempt" if unfinished is not None else "stable_state",
        "unfinished_attempt": unfinished,
        "completed_cells": state["completed_cells"],
        "subject_starts": state["experiment_subject_invocation_starts"],
        "batch_stop_classification": state["batch_stop_classification"],
        "next_cell_id": state["next_cell_id"],
    }


def terminalize_pre_subject(
    *, contract: dict[str, Any], private_pool: dict[str, Any],
    live_seal: dict[str, Any], execution_root: Path,
) -> dict[str, Any]:
    """Stop one interrupted pre-subject attempt without consuming a live start."""

    validate_contract(contract)
    validate_private_pool_binding(private_pool, contract)
    durable.validate_live_seal(contract, private_pool, live_seal)
    root = execution_root.resolve()
    durable._execution_storage_root(root)
    with _control_lock(root):
        events = durable.read_ledger(root / "ledger.jsonl", contract)
        unfinished = _unfinished_attempt(events)
        _require(unfinished is not None, "ledger has no unfinished durable attempt")
        _require(
            unfinished["phase"] == "pre_subject",
            "unfinished attempt already has a durable subject or evaluator start",
        )
        request = _request(
            contract, private_pool,
            cell_id=unfinished["cell_id"], attempt=unfinished["attempt"],
            codex_binary="codex",
            commitment=unfinished["effective_task_commitment_sha256"],
        )
        _write_terminal_artifacts(
            root, contract, request,
            status="durable_evidence_incomplete", subject_started=False,
            exit_code=None, evaluator_disposition="not_run",
            anomaly_codes=["subject_not_started"], work=None,
        )
        result = _export_persist_reconcile(root, contract, private_pool, live_seal, request)
        _require(
            result["transition"]["action"] in {"batch_stopped", "already_reconciled"},
            "pre-subject terminalization did not stop the batch",
        )
        return {
            "action": result["transition"]["action"],
            "classification": "durable_evidence_incomplete",
            "subject_status": "subject_not_started",
            "terminal_receipt_sha256": result["receipt"]["terminal_receipt_sha256"],
        }


def reconcile_proven_dead(
    *, contract: dict[str, Any], private_pool: dict[str, Any],
    live_seal: dict[str, Any], execution_root: Path,
) -> dict[str, Any]:
    """Reconcile the ledger-derived phase only from an existing death proof."""

    validate_contract(contract)
    validate_private_pool_binding(private_pool, contract)
    durable.validate_live_seal(contract, private_pool, live_seal)
    root = execution_root.resolve()
    durable._execution_storage_root(root)
    with _control_lock(root):
        events = durable.read_ledger(root / "ledger.jsonl", contract)
        unfinished = _unfinished_attempt(events)
        _require(unfinished is not None, "ledger has no unfinished durable attempt")
        phase = unfinished["phase"]
        _require(
            phase in {"subject", "evaluator"},
            "pre-subject interruption requires terminalize-pre-subject",
        )
        ownership_path = (
            root / "artifacts" / unfinished["cell_id"]
            / f"attempt-{unfinished['attempt']}" / f"{phase}-ownership-not-running.json"
        )
        _require(
            ownership_path.exists(),
            "private ownership not-running receipt is absent; death cannot be inferred",
        )
        reconcile = (
            reconcile_proven_dead_evaluator
            if phase == "evaluator" else reconcile_proven_dead_attempt
        )
        result = reconcile(
            contract=contract, private_pool=private_pool, live_seal=live_seal,
            execution_root=root, cell_id=unfinished["cell_id"],
            attempt=unfinished["attempt"], ownership_receipt_path=ownership_path,
        )
        return {**result, "phase": phase}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--private-pool", type=Path, required=True)
    parser.add_argument("--live-seal", type=Path, required=True)
    parser.add_argument("--execution-root", type=Path, required=True)
    parser.add_argument("--evaluator-root", type=Path)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--evaluator-python", type=Path)
    parser.add_argument("--codex-binary")
    parser.add_argument("--credential-source-codex-home", type=Path)
    parser.add_argument("--model-catalog", type=Path)
    parser.add_argument("--reserve-receipt", type=Path)
    parser.add_argument(
        "command",
        choices=("execute-next", "status", "terminalize-pre-subject", "reconcile-proven-dead"),
    )
    return parser.parse_args()


def _read_private_cli_input(
    execution_root: Path, path: Path, label: str,
) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    _require(
        resolved.is_relative_to(execution_root)
        and resolved.is_file()
        and not path.is_symlink(),
        f"{label} is outside the initialized private execution root",
    )
    _require_private_path(resolved)
    _require((resolved.stat().st_mode & 0o777) == 0o600, f"{label} mode is not 0600")
    value = read_object(resolved)
    _require(isinstance(value, dict), f"{label} is not an object")
    return value


def _resolve_private_reserve_receipt(
    repository_root: Path,
    path: Path,
    qualification_receipt: dict[str, Any],
) -> Path:
    """Validate the shared qualification reserve without relocating it.

    The reserve predates the execution root and remains under the repository's
    private ``.local`` tree.  Its semantic hash is already frozen into the
    qualification receipt, so copying it into the execution root would create a
    second mutable path without adding authority.
    """

    lexical_root = Path(os.path.abspath(repository_root))
    root = repository_root.resolve(strict=True)
    lexical_local = lexical_root / ".local"
    local = root / ".local"
    lexical = Path(
        os.path.abspath(path if path.is_absolute() else lexical_root / path)
    )
    _require(
        lexical.is_relative_to(lexical_local),
        "reserve receipt is outside the repository private .local tree",
    )
    cursor = lexical_local
    for part in lexical.relative_to(lexical_local).parts:
        cursor = cursor / part
        _require(not cursor.is_symlink(), "reserve receipt path traverses a symlink")
    resolved = lexical.resolve(strict=True)
    _require(
        resolved.is_relative_to(local.resolve(strict=True)),
        "reserve receipt escapes the repository private .local tree",
    )
    cursor = local
    _require(
        cursor.is_dir()
        and not cursor.is_symlink()
        and stat.S_IMODE(cursor.stat().st_mode) == 0o700,
        "reserve receipt .local root is not a private regular directory",
    )
    for part in resolved.parent.relative_to(local).parts:
        cursor = cursor / part
        _require(
            cursor.is_dir()
            and not cursor.is_symlink()
            and stat.S_IMODE(cursor.stat().st_mode) == 0o700,
            "reserve receipt directory is not private mode 0700",
        )
    metadata = resolved.stat()
    _require(
        stat.S_ISREG(metadata.st_mode)
        and not resolved.is_symlink()
        and stat.S_IMODE(metadata.st_mode) == 0o600,
        "reserve receipt is not a private regular file with mode 0600",
    )
    qualifier_live.validate_receipt(qualification_receipt)
    value = read_object(resolved)
    _require(isinstance(value, dict), "reserve receipt is not an object")
    _require(
        qualifier_live.sha256_value(value)
        == qualification_receipt["source"]["reserve_receipt_sha256"],
        "reserve receipt differs from the frozen qualification source",
    )
    return resolved


def _advance_automatic_control_transitions(
    execution_root: Path, contract: dict[str, Any], private_pool: dict[str, Any],
    live_seal: dict[str, Any],
) -> dict[str, Any]:
    """Advance only frozen, outcome-blind control transitions; never start work."""

    ledger = execution_root / "ledger.jsonl"
    checkpoint = execution_root / "checkpoint.json"
    authorization = durable.advance_outcome_blind_attempt_authorization(
        ledger, checkpoint, contract, live_seal, private_pool
    )
    state = durable.replay_attempt_state(
        contract, durable._semantic(durable.read_ledger(ledger, contract))
    )
    audit = None
    if state["completed_cells"] == 4 and state["stage_1_audit_status"] is None:
        audit = durable.record_stage_1_audit(
            ledger, checkpoint, execution_root / "receipts",
            contract, private_pool, live_seal,
            execution_root=execution_root,
            runtime_revalidation_receipt_path=execution_root / "runtime-revalidation.json",
            source_revalidation_receipt_path=execution_root / "source-revalidation.json",
        )
        state = durable.replay_attempt_state(
            contract, durable._semantic(durable.read_ledger(ledger, contract))
        )
    return {"authorization": authorization, "audit": audit, "state": state}


def main() -> int:
    args = _arguments()
    execution_root = args.execution_root.resolve()
    durable._execution_storage_root(execution_root)

    contract = _read_private_cli_input(execution_root, args.contract, "contract")
    private_pool = _read_private_cli_input(execution_root, args.private_pool, "private pool")
    live_seal = _read_private_cli_input(execution_root, args.live_seal, "live seal")
    common = {
        "contract": contract, "private_pool": private_pool,
        "live_seal": live_seal, "execution_root": execution_root,
    }
    if args.command == "status":
        print(json.dumps(execution_status(**common), sort_keys=True))
        return 0
    if args.command == "terminalize-pre-subject":
        print(json.dumps(terminalize_pre_subject(**common), sort_keys=True))
        return 0
    if args.command == "reconcile-proven-dead":
        print(json.dumps(reconcile_proven_dead(**common), sort_keys=True))
        return 0

    live_arguments = {
        "evaluator root": args.evaluator_root,
        "dataset root": args.dataset_root,
        "evaluator Python": args.evaluator_python,
        "Codex binary": args.codex_binary,
        "credential source Codex home": args.credential_source_codex_home,
        "model catalog": args.model_catalog,
        "reserve receipt": args.reserve_receipt,
    }
    _require(
        all(value is not None for value in live_arguments.values()),
        "execute-next requires all live execution arguments",
    )
    reserve_receipt = _resolve_private_reserve_receipt(
        args.root,
        args.reserve_receipt,  # type: ignore[arg-type]
        live_seal["qualification_gate"]["qualification_receipt"],
    )
    automatic = _advance_automatic_control_transitions(
        execution_root, contract, private_pool, live_seal
    )
    if automatic["audit"] is not None and automatic["audit"]["status"] != "pass":
        print(json.dumps({"action": "stage_1_audit_failed"}, sort_keys=True))
        return 0
    events = durable.read_ledger(execution_root / "ledger.jsonl", contract)
    state = durable.replay_attempt_state(contract, durable._semantic(events))
    cell_id = state["next_cell_id"]
    _require(cell_id is not None, "frozen schedule has no executable next cell")
    cell_events = [
        event for event in events
        if event.get("payload", {}).get("cell_id") == cell_id
    ]
    started_attempts = {
        event["payload"]["attempt"] for event in cell_events
        if event["event_type"] == "attempt_started"
    }
    finished_attempts = {
        event["payload"]["attempt"] for event in cell_events
        if event["event_type"] == "attempt_finished"
    }
    _require(
        started_attempts <= finished_attempts,
        "next attempt has an interrupted durable start and requires reconciliation",
    )
    attempt = 2 if any(
        event["event_type"] in {"attempt_2_authorized", "alternate_activated"}
        for event in cell_events
    ) else 1
    successor_gate_path = execution_root / "successor-runtime-gate.json"
    backend = build_local_execution_backend(
        root=args.root, contract=contract, live_seal=live_seal,
        work_root=execution_root / "attempts",
        evaluator_root=args.evaluator_root, dataset_root=args.dataset_root,
        evaluator_python=args.evaluator_python, codex_binary=args.codex_binary,
        source_codex_home=args.credential_source_codex_home,
        model_catalog=args.model_catalog, reserve_receipt=reserve_receipt,
        successor_runtime_gate=(
            successor_gate_path if successor_gate_path.is_file() else None
        ),
        azure_evaluator_state_root=(
            execution_root.parent / "azure"
            if successor_gate_path.is_file() else None
        ),
        azure_evaluator_worker=(
            args.root.resolve() / "scripts" / "azure_prediction_worker.py"
            if successor_gate_path.is_file() else None
        ),
    )
    result = execute_one_attempt(
        backend=backend, contract=contract, private_pool=private_pool,
        live_seal=live_seal, execution_root=execution_root,
        cell_id=cell_id, attempt=attempt,
        codex_binary=str(Path(shutil.which(args.codex_binary) or args.codex_binary).resolve(strict=True)),
    )
    automatic = _advance_automatic_control_transitions(
        execution_root, contract, private_pool, live_seal
    )
    action = result["transition"]["action"]
    if automatic["authorization"] is not None:
        action = automatic["authorization"]["event_type"]
    elif automatic["audit"] is not None:
        action = f"stage_1_audit_{automatic['audit']['status']}"
    print(json.dumps({"action": action}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
