#!/usr/bin/env python3
"""Launch the single frozen contentless canary through its pre-live ledger."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from typing import Any, Callable, Protocol

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for import_root in (REPOSITORY_ROOT, REPOSITORY_ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import canonical_bytes, digest
from engineering_scope_guard.reasoning_effort_v2 import (
    validate_harness_source_closure,
    validate_prior_evidence_identity,
    validate_private_pool_binding,
)
from scripts import evaluator_stable_qualification as qualifier_live
from scripts import reasoning_effort_v2_execution_adapter as adapter
from scripts import reasoning_effort_v2_freeze as freeze_layer
from scripts import reasoning_effort_v2_runner as durable


@dataclass
class CanaryChild:
    gated: adapter.GatedProcess

    @property
    def pid(self) -> int:
        return self.gated.process.pid

    @property
    def process_identity(self) -> dict[str, Any]:
        assert self.gated.process_identity is not None
        return self.gated.process_identity

    @property
    def process_identity_sha256(self) -> str:
        return self.gated.process_identity_sha256

    def run(self, stdin: bytes, timeout_seconds: int) -> adapter.SubjectInvocation:
        return adapter.run_gated_process(
            self.gated, stdin=stdin, timeout_seconds=timeout_seconds
        )


class Child(Protocol):
    pid: int
    process_identity: dict[str, Any]
    process_identity_sha256: str

    def run(self, stdin: bytes, timeout_seconds: int) -> adapter.SubjectInvocation: ...


class SimulatedCrash(BaseException):
    """Test-only abrupt boundary; production code never raises this itself."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def _read(path: Path, label: str) -> dict[str, Any]:
    return freeze_layer._canonical_private_read(path, label)


def _write_bytes(path: Path, value: bytes) -> str:
    root = durable._execution_storage_root(path)
    _require(path.resolve().is_relative_to(root.resolve()), "canary artifact escapes execution root")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    _require(not path.exists() and not path.is_symlink(), "canary raw artifact already exists")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return hashlib.sha256(value).hexdigest()


def _events(raw: bytes) -> list[dict[str, Any]]:
    _require(raw.endswith(b"\n"), "canary JSONL lacks a terminal newline")
    result: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExperimentConfigurationError("canary JSONL is malformed") from error
        _require(isinstance(value, dict), "canary JSONL event is not an object")
        result.append(value)
    _require(bool(result), "canary JSONL is empty")
    return result


def _preflight(
    execution_root: Path,
    qualification_receipt_path: Path,
    qualification_raw_root: Path,
    codex_binary: Path,
    model_catalog: Path,
    runtime_observer: Callable[[Path, Path], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = _read(execution_root / "contract.json", "contract")
    private_pool = _read(execution_root / "private-pool.json", "private pool")
    gate = _read(execution_root / "qualification-gate.json", "qualification gate")
    state = _read(execution_root / "freeze-state.json", "freeze state")
    authority = _read(execution_root / "canary-authority.json", "canary authority")
    validate_private_pool_binding(private_pool, contract)
    validate_harness_source_closure(
        contract["source"]["harness_source_closure"],
        root=REPOSITORY_ROOT,
    )
    validate_prior_evidence_identity(
        contract["source"]["prior_evidence_identity"],
        root=REPOSITORY_ROOT,
    )
    freeze_layer._validate_freeze_state(state, contract, private_pool, gate)
    resolved_binary = codex_binary.resolve(strict=True)
    resolved_catalog = model_catalog.resolve(strict=True)
    freeze_layer._validate_canary_authority(
        authority, contract, private_pool, gate, codex_binary=resolved_binary
    )
    lifecycle = durable.replay_canary_lifecycle(
        execution_root / "canary-ledger.jsonl", authority
    )
    _require(
        state["status"] == "awaiting_contentless_canary"
        or state["status"] == "live_authorized"
        and lifecycle["terminal_status"] == "success",
        "execution root is not awaiting this contentless canary",
    )
    rebuilt_gate = durable.build_qualification_gate_from_receipt(
        contract,
        private_pool,
        qualification_receipt_path,
        qualification_raw_root,
        pool_reliability_audit=gate["pool_reliability_audit"],
    )
    _require(canonical_bytes(rebuilt_gate) == canonical_bytes(gate), "qualification gate drifted")
    runtime = runtime_observer(resolved_binary, resolved_catalog)
    _require(runtime == gate["qualification_receipt"]["runtime_observation"], "canary runtime drifted")
    _require(
        hashlib.sha256(resolved_binary.read_bytes()).hexdigest()
        == authority["codex_binary_sha256"]
        and runtime.get("model_catalog_sha256")
        == hashlib.sha256(resolved_catalog.read_bytes()).hexdigest(),
        "canary binary or model catalog drifted",
    )
    return contract, private_pool, authority


def _spawn(
    authority: dict[str, Any], cwd: Path, ownership_nonce_sha256: str
) -> CanaryChild:
    return CanaryChild(adapter.prepare_gated_process(
        tuple(authority["command"]), cwd=cwd, env=dict(os.environ),
        command_sha256=authority["command_sha256"],
        ownership_token_sha256=ownership_nonce_sha256,
    ))


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _process_identity_artifact(
    root: Path,
    child: Child,
    authority: dict[str, Any],
    ownership_nonce_sha256: str,
) -> None:
    identity = child.process_identity
    _require(
        set(identity) == {
            "pid", "start_time", "launcher_executable", "target_executable",
            "command_sha256", "ownership_token_sha256", "nonce_sha256",
            "gated_before_exec",
        }
        and identity["pid"] == child.pid
        and type(child.pid) is int
        and child.pid > 0
        and isinstance(identity["start_time"], str)
        and bool(identity["start_time"])
        and identity["launcher_executable"] == adapter._file_identity(sys.executable)
        and identity["target_executable"]
        == adapter._file_identity(authority["command"][0])
        and identity["command_sha256"] == authority["command_sha256"]
        and identity["ownership_token_sha256"] == ownership_nonce_sha256
        and _is_sha256(identity["nonce_sha256"])
        and identity["gated_before_exec"] is True
        and digest(identity) == child.process_identity_sha256,
        "canary process identity is malformed or differs from its authority",
    )
    freeze_layer._write_private_json(
        root / "canary-process-identity.json",
        {
            "schema_name": "engineering-scope-guard.reasoning-effort-v2-canary-process-identity",
            "schema_version": 1,
            "process_identity": child.process_identity,
            "process_identity_sha256": child.process_identity_sha256,
        },
    )


def _default_process_observer(root: Path, attached: dict[str, Any]) -> dict[str, Any]:
    artifact = _read(root / "canary-process-identity.json", "canary process identity")
    identity = artifact.get("process_identity")
    _require(
        isinstance(identity, dict)
        and artifact.get("process_identity_sha256") == digest(identity)
        and artifact["process_identity_sha256"] == attached["process_identity_sha256"],
        "persisted canary process identity drifted",
    )
    pid = attached["pid"]
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        status = "not_running"
        observed_sha = attached["process_identity_sha256"]
    except PermissionError as error:
        raise ExperimentConfigurationError("canary process ownership is unobservable") from error
    else:
        class Process:
            def __init__(self, process_id: int): self.pid = process_id
        current = adapter._process_identity(
            Process(pid), target_executable=identity["target_executable"]["resolved_path"],
            command_sha256=identity["command_sha256"],
            ownership_token_sha256=identity["ownership_token_sha256"],
            nonce_sha256=identity["nonce_sha256"],
        )
        _require(current == identity, "running canary process identity drifted")
        status = "running"
        observed_sha = digest(current)
    return {
        "pid": pid,
        "os_start_identity": attached["os_start_identity"],
        "process_identity_sha256": observed_sha,
        "status": status,
    }


def _summary(lifecycle: dict[str, Any], *, live_authorized: bool = False) -> dict[str, Any]:
    return {
        "reserved": lifecycle["reservation"] is not None,
        "process_attached": lifecycle["process"] is not None,
        "terminal_status": lifecycle["terminal_status"],
        "may_launch": lifecycle["may_launch"],
        "live_authorized": live_authorized,
    }


def _finish_failure(
    lifecycle_path: Path,
    authority: dict[str, Any],
    failure_code: str,
) -> dict[str, Any]:
    durable.finish_canary_lifecycle(
        lifecycle_path,
        authority,
        status="failure",
        failure_code=failure_code,
    )
    return durable.replay_canary_lifecycle(lifecycle_path, authority)


def lifecycle_status(execution_root: Path) -> dict[str, Any]:
    root = execution_root.resolve()
    durable._execution_storage_root(root)
    authority = _read(root / "canary-authority.json", "canary authority")
    return _summary(durable.replay_canary_lifecycle(root / "canary-ledger.jsonl", authority))


def launch(
    *, execution_root: Path, qualification_receipt_path: Path,
    qualification_raw_root: Path, codex_binary: Path, model_catalog: Path,
    runtime_observer: Callable[[Path, Path], dict[str, Any]] | None = None,
    child_factory: Callable[[dict[str, Any], Path, str], Child] = _spawn,
    process_observer: Callable[[int], dict[str, Any]] | None = None,
    boundary_hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    root = execution_root.resolve()
    durable._execution_storage_root(root)
    observe_runtime = runtime_observer or qualifier_live._codex_runtime
    with durable._lock(root / "execution-adapter.lock"):
        contract, private_pool, authority = _preflight(
            root, qualification_receipt_path, qualification_raw_root,
            codex_binary, model_catalog, observe_runtime,
        )
        lifecycle_path = root / "canary-ledger.jsonl"
        lifecycle = durable.replay_canary_lifecycle(lifecycle_path, authority)
        if lifecycle["terminal_status"] == "success":
            verified = freeze_layer.verify(
                qualification_receipt_path=qualification_receipt_path,
                qualification_raw_root=qualification_raw_root, execution_root=root,
                canary_receipt_path=root / "canary-receipt.json",
                codex_binary=codex_binary, model_catalog=model_catalog,
                runtime_observer=observe_runtime,
            )
            return _summary(lifecycle, live_authorized=verified["status"] == "live_authorized")
        if lifecycle["terminal_status"] == "failure":
            return _summary(lifecycle)
        if lifecycle["reservation"] is not None:
            if lifecycle["process"] is None:
                lifecycle = durable.reconcile_canary_process(
                    lifecycle_path, authority, process_observer=lambda _pid: {}
                )
            else:
                attached = lifecycle["process"]["payload"]
                observer = process_observer or (lambda _pid: _default_process_observer(root, attached))
                lifecycle = durable.reconcile_canary_process(
                    lifecycle_path, authority, process_observer=observer
                )
            return _summary(lifecycle)

        cwd = root / "canary-cwd"
        _require(not cwd.is_symlink(), "canary cwd is a symlink")
        cwd.mkdir(mode=0o700)
        cwd.chmod(0o700)
        _require(not any(cwd.iterdir()), "canary cwd is not empty")
        ownership_nonce_sha256 = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        reservation = durable.reserve_canary_start(
            lifecycle_path, authority, ownership_nonce_sha256=ownership_nonce_sha256
        )
        if boundary_hook: boundary_hook("after_reservation")
        try:
            child = child_factory(authority, cwd, ownership_nonce_sha256)
        except SimulatedCrash:
            raise
        except BaseException:
            _finish_failure(lifecycle_path, authority, "spawn_failed")
            raise
        if boundary_hook: boundary_hook("after_spawn")
        try:
            _process_identity_artifact(
                root, child, authority, ownership_nonce_sha256
            )
            process_event = durable.attach_canary_process(
                lifecycle_path, authority, pid=child.pid,
                os_start_identity=child.process_identity["start_time"],
                process_identity_sha256=child.process_identity_sha256,
            )
        except BaseException:
            if isinstance(child, CanaryChild):
                adapter.abort_gated_process(child.gated)
            _finish_failure(lifecycle_path, authority, "process_attachment_failed")
            raise
        if boundary_hook: boundary_hook("after_attach")
        try:
            result = child.run(
                freeze_layer.CANARY_PROMPT,
                contract["trajectory"]["subject_timeout_seconds"],
            )
        except SimulatedCrash:
            raise
        except BaseException:
            if isinstance(child, CanaryChild):
                adapter.abort_gated_process(child.gated)
            _finish_failure(lifecycle_path, authority, "execution_failed")
            raise
        try:
            _write_bytes(root / "canary-raw" / "codex.jsonl", result.stdout)
            stderr_sha = _write_bytes(
                root / "canary-raw" / "codex.stderr", result.stderr
            )
        except BaseException:
            _finish_failure(lifecycle_path, authority, "evidence_persistence_failed")
            raise
        if result.timed_out or result.exit_code != 0:
            return _summary(_finish_failure(
                lifecycle_path,
                authority,
                "timeout" if result.timed_out else "nonzero_exit",
            ))
        try:
            body = {
                "schema_name": freeze_layer.CANARY_RECEIPT_SCHEMA,
                "schema_version": freeze_layer.SCHEMA_VERSION,
                "canary_authority_sha256": authority["canary_authority_sha256"],
                "contract_sha256": authority["contract_sha256"],
                "subject_invocation_starts": 1,
                "command_sha256": authority["command_sha256"],
                "codex_binary_sha256": authority["codex_binary_sha256"],
                "codex_version": authority["codex_version"],
                "model": authority["model"],
                "reasoning_effort": authority["reasoning_effort"],
                "runtime_identity": authority["runtime_identity"],
                "reservation_event_sha256": reservation["event_sha256"],
                "ownership_nonce_sha256": ownership_nonce_sha256,
                "process_event_sha256": process_event["event_sha256"],
                "process_identity_sha256": child.process_identity_sha256,
                "prompt_sha256": authority["prompt_sha256"],
                "exit_code": result.exit_code, "timed_out": result.timed_out,
                "stderr_sha256": stderr_sha, "events": _events(result.stdout),
            }
            receipt = {**body, "canary_receipt_sha256": digest(body)}
            freeze_layer.validate_canary_receipt(receipt, authority, private_pool)
        except ExperimentConfigurationError:
            return _summary(_finish_failure(
                lifecycle_path, authority, "invalid_canary_evidence"
            ))
        receipt_path = root / "canary-receipt.json"
        try:
            freeze_layer._write_private_json(receipt_path, receipt)
        except BaseException:
            _finish_failure(lifecycle_path, authority, "evidence_persistence_failed")
            raise
        if boundary_hook: boundary_hook("after_receipt")
        durable.finish_canary_lifecycle(
            lifecycle_path, authority, status="success",
            canary_receipt_sha256=receipt["canary_receipt_sha256"],
        )
        if boundary_hook: boundary_hook("after_terminal")
        verified = freeze_layer.verify(
            qualification_receipt_path=qualification_receipt_path,
            qualification_raw_root=qualification_raw_root, execution_root=root,
            canary_receipt_path=receipt_path, codex_binary=codex_binary,
            model_catalog=model_catalog, runtime_observer=observe_runtime,
        )
        return _summary(
            durable.replay_canary_lifecycle(lifecycle_path, authority),
            live_authorized=verified["status"] == "live_authorized",
        )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("launch", "status"))
    parser.add_argument("--execution-root", type=Path, required=True)
    parser.add_argument("--qualification-receipt", type=Path)
    parser.add_argument("--qualification-raw-root", type=Path)
    parser.add_argument("--codex-binary", type=Path)
    parser.add_argument("--model-catalog", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if args.command == "status":
        print(json.dumps(lifecycle_status(args.execution_root), sort_keys=True))
        return 0
    _require(
        all((args.qualification_receipt, args.qualification_raw_root, args.codex_binary, args.model_catalog)),
        "launch requires qualification, runtime, binary, and catalog inputs",
    )
    result = launch(
        execution_root=args.execution_root,
        qualification_receipt_path=args.qualification_receipt,
        qualification_raw_root=args.qualification_raw_root,
        codex_binary=args.codex_binary, model_catalog=args.model_catalog,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["live_authorized"] else 2


if __name__ == "__main__":
    sys.exit(main())
