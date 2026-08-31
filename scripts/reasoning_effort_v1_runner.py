#!/usr/bin/env python3
"""Strict one-attempt adapter for the frozen reasoning-effort-v1 experiment.

Preflight, dry-run, and status are provider/evaluator free.  ``execute-next``
launches exactly one fresh Codex subject and at most one official evaluator.
Raw task prompts and traces remain below the ignored state root.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import shlex
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.disk_safety import (
    DiskSafetyError,
    public_disk_safety_receipt,
    require_disk_safety,
    validate_write_target,
)
from engineering_scope_guard.pilot_contract import digest, read_object
from engineering_scope_guard.pilot_integrity import (
    capture_repository_baseline,
    classify_provider_event,
    provision_file_auth,
    remove_file_auth,
    subject_patch_from_baseline,
)
from engineering_scope_guard.pilot_runner import (
    official_evaluator_command,
    parse_official_evaluator_artifacts,
    sha256_file,
)
from engineering_scope_guard.reasoning_effort_v1 import (
    ARMS,
    BATCH_STOP_CLASSES,
    EXPERIMENTAL_OUTCOMES,
    RETRYABLE_INFRASTRUCTURE,
    USAGE_MEASUREMENT_SCOPE,
    append_event,
    authorize_attempt_2,
    read_attempt_ledger,
    record_attempt_start,
    record_cell_completed,
    validate_frozen_identity,
    validate_attempt_ledger,
    validate_usage,
)

try:
    from scripts.pilot_host_qualification import QualificationError, _docker_environment
    from scripts.pilot_runner import (
        _dataset_hashes,
        _verify_evaluator_interface,
        canonical_evaluator_python,
        resolve_dataset_task,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from pilot_host_qualification import QualificationError, _docker_environment
    from pilot_runner import (
        _dataset_hashes,
        _verify_evaluator_interface,
        canonical_evaluator_python,
        resolve_dataset_task,
    )

SCHEMA = "engineering-scope-guard.reasoning-effort-v1-runner"
DEFAULT_STATE_ROOT = Path(".local/reasoning-effort-v1")
DEFAULT_SOURCE_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
ATTEMPT_2_INFRASTRUCTURE_CLASSES = frozenset(
    RETRYABLE_INFRASTRUCTURE
)
EXECUTION_CODE_CLOSURE = (
    "scripts/reasoning_effort_v1_analyze.py",
    "scripts/pilot_dataset_bridge.py",
    "scripts/pilot_host_qualification.py",
    "scripts/pilot_runner.py",
    "scripts/reasoning_effort_v1_runner.py",
    "src/engineering_scope_guard/__init__.py",
    "src/engineering_scope_guard/disk_safety.py",
    "src/engineering_scope_guard/experiment.py",
    "src/engineering_scope_guard/pilot_contract.py",
    "src/engineering_scope_guard/pilot_integrity.py",
    "src/engineering_scope_guard/pilot_runner.py",
    "src/engineering_scope_guard/reasoning_effort_v1.py",
    "src/engineering_scope_guard/reasoning_effort_v1_analysis.py",
    "src/engineering_scope_guard/report.py",
    "src/engineering_scope_guard/repository.py",
    "src/engineering_scope_guard/trace.py",
)
ALLOWED_ENVIRONMENT = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    temporary.replace(path)


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stdin: bytes | None = None,
    timeout: int | None = None,
) -> tuple[int | None, bool, bytes, bytes]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(stdin, timeout=timeout)
        return process.returncode, False, stdout, stderr
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return None, True, stdout, stderr
    except BaseException:
        # The invocation-start event already consumed capacity.  Ensure an operator
        # interruption cannot leave a detached subject/evaluator running and later
        # tempt a duplicate launch during reconciliation.
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


def _checked(command: list[str], cwd: Path | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ExperimentConfigurationError(
            f"immutable-input command failed ({command[0]} exit {completed.returncode})"
        )
    return completed.stdout.strip()


def _canonical_identity(value: dict[str, Any], field: str) -> str:
    return digest({key: item for key, item in value.items() if key != field})


def validate_authorization(value: dict[str, Any]) -> None:
    """Validate the separate authority record without letting it self-authorize by shape."""

    if value.get("authorization_sha256") != _canonical_identity(value, "authorization_sha256"):
        raise ExperimentConfigurationError("execution authorization identity mismatch")
    if value.get("execution_authorized") is not True or value.get("status") != "frozen-authorized":
        raise ExperimentConfigurationError("live execution is not explicitly authorized")
    if value.get("allowed_attempt_2_classes") != sorted(ATTEMPT_2_INFRASTRUCTURE_CLASSES):
        raise ExperimentConfigurationError("attempt-2 infrastructure classes drifted")
    runtime = value.get("runtime")
    source = value.get("source")
    execution = value.get("execution")
    if not all(isinstance(item, dict) for item in (runtime, source, execution)):
        raise ExperimentConfigurationError("authorization runtime/source/execution is malformed")
    if runtime.get("reasoning_efforts") != list(ARMS):
        raise ExperimentConfigurationError("authorization reasoning efforts drifted")
    if runtime.get("runtime_identity") != _canonical_identity(runtime, "runtime_identity"):
        raise ExperimentConfigurationError("authorized runtime identity mismatch")
    codex_executable = runtime.get("codex_executable")
    if not isinstance(codex_executable, dict) or set(codex_executable) != {
        "resolved_path_sha256",
        "file_sha256",
    } or any(
        not isinstance(value, str) or len(value) != 64
        for value in codex_executable.values()
    ):
        raise ExperimentConfigurationError("authorized Codex executable identity is malformed")
    if runtime.get("subject_interface") != {
        "one_fresh_codex_exec_per_cell": True,
        "sandbox": "workspace-write",
        "subject_network_access": False,
        "user_config_loaded": False,
        "user_rules_loaded": False,
        "browser_apps_plugins_multi_agent_disabled": True,
    }:
        raise ExperimentConfigurationError("authorized subject interface drifted")
    if execution != {
        "one_codex_exec_per_cell": True,
        "corrective_resume_permitted": False,
        "qualification_subject_executions": 1,
        "subject_timeout_seconds": 900,
        "evaluator_timeout_seconds": 1800,
        "workers": 1,
        "stage_1_cell_count": 4,
        "maximum_subject_executions_including_qualification": 64,
        "maximum_attempts_per_cell": 2,
        "attempt_3_permitted": False,
    }:
        raise ExperimentConfigurationError("authorized execution controls drifted")
    hashes = source.get("dataset_snapshot_files_sha256")
    if not isinstance(hashes, dict) or len(hashes) != 8 or any(
        not isinstance(name, str)
        or not isinstance(item, str)
        or len(item) != 64
        for name, item in hashes.items()
    ):
        raise ExperimentConfigurationError("exact eight-file dataset snapshot is not frozen")


def _tracked_head_bytes(root: Path, path: Path) -> bytes:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as error:
        raise ExperimentConfigurationError("frozen input must be inside the repository") from error
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative], cwd=root, capture_output=True, check=False
    )
    committed = subprocess.run(
        ["git", "show", f"HEAD:{relative}"], cwd=root, capture_output=True, check=False
    )
    if tracked.returncode != 0 or committed.returncode != 0 or committed.stdout != path.read_bytes():
        raise ExperimentConfigurationError(f"frozen input is not tracked HEAD bytes: {relative}")
    return committed.stdout


def _execution_code_identity(root: Path) -> dict[str, str]:
    """Hash the complete repository-owned code path that can affect one cell."""

    return {
        relative: hashlib.sha256(_tracked_head_bytes(root, root / relative)).hexdigest()
        for relative in EXECUTION_CODE_CLOSURE
    }


def _codex_executable_identity(codex_binary: str) -> tuple[Path, dict[str, str]]:
    """Resolve and hash the exact executable without persisting its private path."""

    located = shutil.which(codex_binary)
    resolved = Path(located if located is not None else codex_binary).resolve()
    if not resolved.is_file():
        raise ExperimentConfigurationError("Codex executable is absent")
    return resolved, {
        "resolved_path_sha256": hashlib.sha256(str(resolved).encode("utf-8")).hexdigest(),
        "file_sha256": sha256_file(resolved),
    }


def _require_clean_worktree(path: Path, label: str) -> None:
    status = _checked(["git", "status", "--porcelain=v1", "--untracked-files=all"], path)
    if status:
        raise ExperimentConfigurationError(f"{label} worktree is not clean")


def evaluator_python_identity(path: Path) -> dict[str, str]:
    """Bind the evaluator interpreter, virtual-environment path, and package set."""

    if not path.is_file():
        raise ExperimentConfigurationError("official evaluator Python is absent")
    package_script = (
        "import importlib.metadata as m;"
        "print('\\n'.join(sorted((d.metadata.get('Name','').lower()+'=='+d.version) "
        "for d in m.distributions())))"
    )
    packages = subprocess.run(
        [str(path), "-c", package_script], capture_output=True, check=False
    )
    version = subprocess.run(
        [str(path), "--version"], capture_output=True, check=False
    )
    if packages.returncode != 0 or version.returncode != 0:
        raise ExperimentConfigurationError("official evaluator Python identity is unavailable")
    return {
        "path_sha256": hashlib.sha256(str(path.absolute()).encode("utf-8")).hexdigest(),
        "resolved_executable_sha256": sha256_file(path.resolve()),
        "version_sha256": hashlib.sha256(
            (version.stdout + version.stderr).strip()
        ).hexdigest(),
        "package_set_sha256": hashlib.sha256(packages.stdout).hexdigest(),
    }


def _pool_tasks(pool: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = pool.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 8:
        raise ExperimentConfigurationError("execution pool must contain exactly eight tasks")
    required = {
        "task_id",
        "repository",
        "language",
        "base_commit",
        "docker_image",
        "image_id",
        "problem_statement_sha256",
        "manifest_sha256",
    }
    if any(not isinstance(task, dict) or set(task) != required for task in tasks):
        raise ExperimentConfigurationError("execution pool exposes unsupported task fields")
    return tasks


def _task_snapshot(dataset_revision: str, task: dict[str, Any]) -> str:
    return digest(
        {
            "dataset_revision": dataset_revision,
            **{
                key: task[key]
                for key in (
                    "task_id",
                    "repository",
                    "language",
                    "base_commit",
                    "docker_image",
                    "image_id",
                    "problem_statement_sha256",
                    "manifest_sha256",
                )
            },
        }
    )


def _model_catalog_identity(path: Path) -> str:
    if not path.is_file():
        raise ExperimentConfigurationError("frozen model catalog is absent")
    return sha256_file(path)


def docker_manifest_sha256(image: str) -> str:
    """Hash the exact registry-manifest bytes used by reserve qualification."""

    completed = subprocess.run(
        ["docker", "manifest", "inspect", image], capture_output=True, check=False
    )
    if completed.returncode != 0 or not completed.stdout:
        raise ExperimentConfigurationError(f"official image manifest is unavailable: {image}")
    return hashlib.sha256(completed.stdout).hexdigest()


def strict_preflight(
    *,
    root: Path,
    contract_path: Path,
    pool_path: Path,
    authorization_path: Path,
    evaluator_root: Path,
    dataset_root: Path,
    evaluator_python: Path,
    model_catalog_path: Path,
    codex_binary: str,
    state_root: Path,
    enforce_disk_safety: bool = True,
) -> dict[str, Any]:
    """Verify every frozen live identity without provider or evaluator execution."""

    if enforce_disk_safety:
        try:
            validate_write_target(state_root)
            disk_safety = require_disk_safety(
                state_root.parent, filesystem_path=state_root
            )
            disk_safety = public_disk_safety_receipt(disk_safety)
        except DiskSafetyError as error:
            raise ExperimentConfigurationError(str(error)) from error
    else:
        disk_safety = {
            "status": "not_enforced",
            "reason": "non-execution command remains available for recovery",
        }

    contract = read_object(contract_path)
    pool = read_object(pool_path)
    authorization = read_object(authorization_path)
    validate_authorization(authorization)
    contract_bytes = _tracked_head_bytes(root, contract_path)
    pool_bytes = _tracked_head_bytes(root, pool_path)
    authorization_bytes = _tracked_head_bytes(root, authorization_path)
    binding = authorization.get("binding", {})
    expected_binding = {
        "contract_path": contract_path.relative_to(root).as_posix(),
        "contract_sha256": contract.get("contract_sha256"),
        "contract_file_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "schedule_sha256": contract.get("schedule", {}).get("schedule_sha256"),
        "pool_path": pool_path.relative_to(root).as_posix(),
        "pool_sha256": pool.get("pool_sha256"),
        "pool_file_sha256": hashlib.sha256(pool_bytes).hexdigest(),
        "execution_code_files_sha256": _execution_code_identity(root),
    }
    if binding != expected_binding:
        raise ExperimentConfigurationError("contract/pool authorization binding drifted")
    if hashlib.sha256(authorization_bytes).hexdigest() != sha256_file(authorization_path):
        raise ExperimentConfigurationError("authorization file changed during preflight")
    validate_frozen_identity(
        contract,
        expected_contract_sha256=binding["contract_sha256"],
        expected_schedule_sha256=binding["schedule_sha256"],
    )
    if contract["attempt_accounting"]["qualification_subject_executions"] != 1:
        raise ExperimentConfigurationError("contract does not count the prior instrumentation canary")
    pool_tasks = _pool_tasks(pool)
    schedule_tasks = {
        task["task_id"]: task for task in contract["schedule"]["tasks"]
    }
    if pool.get("pool_sha256") != contract["schedule"]["pool_sha256"] or {
        (task["task_id"], task["repository"]) for task in pool_tasks
    } != {
        (task["task_id"], task["repository"]) for task in schedule_tasks.values()
    }:
        raise ExperimentConfigurationError("pool and frozen schedule tasks differ")
    selection_integrity = authorization.get("source", {}).get("selection_integrity")
    if (
        not isinstance(selection_integrity, dict)
        or pool.get("selection_integrity_sha256") != digest(selection_integrity)
    ):
        raise ExperimentConfigurationError("reserve-selection integrity binding drifted")
    runtime = authorization["runtime"]
    subject = contract["subject"]
    if any(
        subject.get(key) != runtime[key]
        for key in ("model", "codex_version", "runtime_identity")
    ):
        raise ExperimentConfigurationError("contract and authorized runtime differ")
    resolved_codex, codex_executable_identity = _codex_executable_identity(codex_binary)
    if codex_executable_identity != runtime["codex_executable"]:
        raise ExperimentConfigurationError("Codex executable bytes or resolved path changed")
    codex_version = _checked([str(resolved_codex), "--version"])
    if codex_version != f"codex-cli {runtime['codex_version']}":
        raise ExperimentConfigurationError("Codex version changed")
    help_text = _checked([str(resolved_codex), "exec", "--help"])
    for flag in (
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--approve-for-me",
        "--config",
        "--disable",
        "--sandbox",
    ):
        if flag not in help_text:
            raise ExperimentConfigurationError(f"Codex subject interface lacks {flag}")
    subject_command_sha256 = validate_subject_commands(contract, str(resolved_codex))
    if _model_catalog_identity(model_catalog_path) != runtime["model_catalog_sha256"]:
        raise ExperimentConfigurationError("model catalog identity changed")
    catalog = read_object(model_catalog_path)
    models = catalog.get("models") if isinstance(catalog.get("models"), list) else catalog
    entries = models if isinstance(models, list) else []
    selected = next((entry for entry in entries if entry.get("slug") == runtime["model"]), None)
    efforts = set()
    if isinstance(selected, dict):
        for item in selected.get("supported_reasoning_levels", []):
            if isinstance(item, dict) and isinstance(item.get("effort"), str):
                efforts.add(item["effort"])
            elif isinstance(item, str):
                efforts.add(item)
    if not set(ARMS).issubset(efforts):
        raise ExperimentConfigurationError("frozen model catalog lacks low/medium")
    source = authorization["source"]
    contract_source = contract["source"]
    if any(
        contract_source.get(key) != source[authorized_key]
        for key, authorized_key in (
            ("dataset_revision", "dataset_revision"),
            ("evaluator_revision", "evaluator_revision"),
            ("repolaunch_revision", "repolaunch_revision"),
        )
    ) or contract_source.get("pool_sha256") != pool["pool_sha256"]:
        raise ExperimentConfigurationError("contract and authorized source differ")
    if contract["trajectory"] != {
        "subject_invocations_per_cell": 1,
        "corrective_followup_invocations": 0,
        "prompt_framing": "exact UTF-8 problem_statement bytes plus one LF on stdin",
        "subject_timeout_seconds": authorization["execution"]["subject_timeout_seconds"],
        "evaluator_timeout_seconds": authorization["execution"]["evaluator_timeout_seconds"],
    }:
        raise ExperimentConfigurationError("authorized trajectory differs from contract")
    if _dataset_hashes(dataset_root) != source["dataset_snapshot_files_sha256"]:
        raise ExperimentConfigurationError("pinned dataset snapshot bytes changed")
    if not (dataset_root.parent / "hf-cache").is_dir():
        raise ExperimentConfigurationError("qualified offline evaluator cache is absent")
    if _checked(["git", "rev-parse", "HEAD"], evaluator_root) != source["evaluator_revision"]:
        raise ExperimentConfigurationError("official evaluator revision changed")
    if _checked(["git", "-C", str(evaluator_root / "launch"), "rev-parse", "HEAD"]) != source["repolaunch_revision"]:
        raise ExperimentConfigurationError("RepoLaunch revision changed")
    _require_clean_worktree(evaluator_root, "official evaluator")
    _require_clean_worktree(evaluator_root / "launch", "RepoLaunch")
    if evaluator_python_identity(evaluator_python) != source.get("evaluator_python_identity"):
        raise ExperimentConfigurationError("official evaluator Python environment changed")
    try:
        docker = _docker_environment()
    except QualificationError as error:
        raise ExperimentConfigurationError("fixed Docker environment changed") from error
    if docker != runtime["docker_environment"]:
        raise ExperimentConfigurationError("fixed Docker resources changed")
    interface = _verify_evaluator_interface(evaluator_root)
    if digest(interface) != source["evaluator_interface_sha256"]:
        raise ExperimentConfigurationError("official evaluator interface changed")
    task_bindings = {task["task_id"]: task for task in pool_tasks}
    if len(task_bindings) != 8:
        raise ExperimentConfigurationError("pool task identities are not unique")
    if set(task_bindings) != set(schedule_tasks):
        raise ExperimentConfigurationError("authorized task identities differ from schedule")
    events = read_attempt_ledger(state_root / "ledger.jsonl", contract)
    for task in pool_tasks:
        bound = task_bindings[task["task_id"]]
        if schedule_tasks[task["task_id"]]["task_snapshot_sha256"] != _task_snapshot(
            source["dataset_revision"], task
        ):
            raise ExperimentConfigurationError("task snapshot differs from frozen manifest")
        image_id = _checked(["docker", "image", "inspect", bound["docker_image"], "--format", "{{.Id}}"])
        if image_id != bound["image_id"]:
            raise ExperimentConfigurationError(f"official image identity changed: {task['task_id']}")
        if (
            not events
            and docker_manifest_sha256(bound["docker_image"])
            != bound["manifest_sha256"]
        ):
            raise ExperimentConfigurationError(
                f"official image manifest bytes changed: {task['task_id']}"
            )
    image_pool_identity = digest(
        [
            {
                "task_id": task["task_id"],
                "image_id": task["image_id"],
                "manifest_sha256": task["manifest_sha256"],
            }
            for task in sorted(pool_tasks, key=lambda item: item["task_id"])
        ]
    )
    if contract_source.get("image_pool_identity") != image_pool_identity:
        raise ExperimentConfigurationError("frozen image-pool identity changed")
    _validate_finished_evidence(state_root, events)
    if not events and (state_root / "attempts").exists():
        raise ExperimentConfigurationError("attempt roots exist without an effort-v1 ledger")
    if any(state_root.glob("attempts/*/*/codex-home/auth.json")):
        raise ExperimentConfigurationError("trajectory-local authentication remains")
    status = runner_status(contract, events)
    return {
        "schema_name": f"{SCHEMA}.preflight",
        "schema_version": 1,
        "status": "pass",
        "contract_sha256": binding["contract_sha256"],
        "pool_sha256": binding["pool_sha256"],
        "authorization_sha256": authorization["authorization_sha256"],
        "tracked_head_exact": True,
        "codex_version": codex_version,
        "codex_executable": codex_executable_identity,
        "execution_code_files_sha256": binding["execution_code_files_sha256"],
        "model_catalog_sha256": runtime["model_catalog_sha256"],
        "subject_command_sha256_by_arm": subject_command_sha256,
        "dataset_snapshot_files_sha256": source["dataset_snapshot_files_sha256"],
        "evaluator_revision": source["evaluator_revision"],
        "repolaunch_revision": source["repolaunch_revision"],
        "qualified_image_ids": {task_id: task["image_id"] for task_id, task in task_bindings.items()},
        "registry_manifest_revalidation": (
            "performed-before-cell-1"
            if not events
            else "not-repeated-after-cell-1; exact local image IDs revalidated"
        ),
        "next_action": status["next_action"],
        "disk_safety": disk_safety,
        "subject_invocations": 0,
        "evaluator_invocations": 0,
    }


def parse_subject_trace(content: bytes) -> dict[str, Any]:
    """Extract content-free terminal usage and deterministic activity counts."""

    events: list[dict[str, Any]] = []
    for number, raw in enumerate(content.splitlines(), start=1):
        try:
            event = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExperimentConfigurationError(f"malformed Codex JSONL line {number}") from error
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ExperimentConfigurationError("malformed Codex event")
        events.append(event)
    completed = [event for event in events if event["type"] == "turn.completed"]
    failed = [event for event in events if event["type"] == "turn.failed"]
    threads = [event.get("thread_id") for event in events if event["type"] == "thread.started"]
    if len(completed) != 1 or failed or len(threads) != 1 or not isinstance(threads[0], str):
        raise ExperimentConfigurationError("Codex trace lacks one unambiguous final turn")
    usage = completed[0].get("usage")
    if not isinstance(usage, dict):
        raise ExperimentConfigurationError("Codex final usage is absent")
    validated = validate_usage(usage, measurement_scope=USAGE_MEASUREMENT_SCOPE)
    items = [event.get("item") for event in events if event["type"] == "item.completed"]
    if any(not isinstance(item, dict) or not isinstance(item.get("type"), str) for item in items):
        raise ExperimentConfigurationError("Codex item evidence is malformed")
    item_types: dict[str, int] = {}
    command_count = repository_search_commands = external_search_items = 0
    prohibited_tool_count = 0
    for item in items:
        item_type = item["type"]
        item_types[item_type] = item_types.get(item_type, 0) + 1
        is_command = item_type in {"command_execution", "commandExecution"}
        command_count += is_command
        if is_command:
            repository_search_commands += _is_repository_search_command(item.get("command"))
        external_search_items += item_type in {"web_search", "webSearch"}
        if item_type in {"mcp_tool_call", "dynamic_tool_call", "collab_agent_tool_call"}:
            prohibited_tool_count += 1
    if external_search_items or prohibited_tool_count:
        raise ExperimentConfigurationError("browser/plugin/multi-agent tool use was observed")
    return {
        "session_id": threads[0],
        "usage": validated,
        "activity": {
            "events": len(events),
            "turns": len(completed),
            "completed_items": len(items),
            "commands": command_count,
            "repository_search_commands": repository_search_commands,
            "external_search_items": external_search_items,
            "item_types": dict(sorted(item_types.items())),
        },
        "provider_infrastructure_failure": any(classify_provider_event(event) for event in events),
    }


def _is_repository_search_command(command: Any) -> int:
    """Classify a command item by executable tokens without retaining its text."""

    if isinstance(command, list) and all(isinstance(item, str) for item in command):
        candidates = [command]
    elif isinstance(command, str):
        candidates = []
        for segment in re.split(r"(?:&&|\|\||;|\|)", command):
            try:
                tokens = shlex.split(segment)
            except ValueError:
                continue
            if tokens:
                candidates.append(tokens)
    else:
        return 0
    for tokens in candidates:
        executable = Path(tokens[0]).name
        if executable in {"sh", "bash", "zsh"}:
            for option in ("-c", "-lc"):
                if option in tokens:
                    index = tokens.index(option)
                    if index + 1 < len(tokens):
                        return _is_repository_search_command(tokens[index + 1])
        if executable in {"rg", "grep", "find", "fd"}:
            return 1
        if executable == "git" and "grep" in tokens[1:4]:
            return 1
    return 0


def _validate_prompt_bytes(
    prompt_path: Path, prompt_identity: dict[str, Any], problem_statement_sha256: str
) -> bytes:
    """Validate the exact bytes passed on stdin against both bridge identities."""

    prompt_bytes = prompt_path.read_bytes()
    if (
        prompt_identity.get("prompt_sha256") != hashlib.sha256(prompt_bytes).hexdigest()
        or prompt_identity.get("prompt_bytes") != len(prompt_bytes)
        or not prompt_bytes.endswith(b"\n")
        or hashlib.sha256(prompt_bytes[:-1]).hexdigest() != problem_statement_sha256
    ):
        raise ExperimentConfigurationError("exact task prompt bytes changed")
    return prompt_bytes


def subject_command(
    codex_binary: str, contract: dict[str, Any], cell: dict[str, Any]
) -> list[str]:
    """Return the frozen fresh-session command for exactly one arm."""

    effort = cell.get("reasoning_effort")
    if effort not in ARMS or cell.get("arm") != effort:
        raise ExperimentConfigurationError("cell reasoning effort is outside the frozen arms")
    return [
        codex_binary,
        "exec",
        "-",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--approve-for-me",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--color",
        "never",
        "--model",
        contract["subject"]["model"],
        "--config",
        f'model_reasoning_effort="{effort}"',
        "--config",
        'web_search="disabled"',
        "--config",
        "sandbox_workspace_write.network_access=false",
        "--disable",
        "apps",
        "--disable",
        "plugins",
        "--disable",
        "browser_use",
        "--disable",
        "in_app_browser",
        "--disable",
        "computer_use",
        "--disable",
        "image_generation",
        "--disable",
        "multi_agent",
        "--disable",
        "multi_agent_v2",
        "--disable",
        "skill_search",
    ]


def validate_subject_commands(
    contract: dict[str, Any], codex_binary: str = "codex"
) -> dict[str, str]:
    """Verify both arms use a closed tool surface and differ only in effort."""

    commands: dict[str, list[str]] = {}
    expected_disabled = {
        "apps",
        "plugins",
        "browser_use",
        "in_app_browser",
        "computer_use",
        "image_generation",
        "multi_agent",
        "multi_agent_v2",
        "skill_search",
    }
    for arm in ARMS:
        cell = next(cell for cell in contract["schedule"]["cells"] if cell["arm"] == arm)
        command = subject_command(codex_binary, contract, cell)
        disabled = {
            command[index + 1]
            for index, value in enumerate(command[:-1])
            if value == "--disable"
        }
        if disabled != expected_disabled or 'web_search="disabled"' not in command:
            raise ExperimentConfigurationError("subject external-tool closure drifted")
        if "sandbox_workspace_write.network_access=false" not in command or "resume" in command:
            raise ExperimentConfigurationError("subject isolation/fresh-session boundary drifted")
        commands[arm] = command
    normalized = {
        arm: [
            "<EFFORT>" if item == f'model_reasoning_effort="{arm}"' else item
            for item in command
        ]
        for arm, command in commands.items()
    }
    if normalized["low"] != normalized["medium"]:
        raise ExperimentConfigurationError("subject arms differ beyond reasoning effort")
    return {arm: digest(command) for arm, command in commands.items()}


def classify_evaluator_attempt(
    *, timed_out: bool, structured_malformed: bool, disposition: str | None
) -> str:
    """Apply the prospective evaluator taxonomy without reading outcome content."""

    if structured_malformed:
        return "malformed_inconsistent_measurement"
    if timed_out:
        return "local_docker_runtime_infrastructure_failure"
    if disposition is None:
        return "official_evaluator_error"
    try:
        return {
            "success": "accepted_completed",
            "failure": "evaluator_test_failure",
            "empty_patch": "empty_patch_failure",
            "error": "official_evaluator_error",
            "incomplete": "official_evaluator_incomplete",
        }[disposition]
    except KeyError as error:
        raise ExperimentConfigurationError(
            "official evaluator disposition is outside the frozen taxonomy"
        ) from error


def runner_status(contract: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the sole legal next attempt from the replayed hash-chain state."""

    finishes: dict[tuple[str, int], dict[str, Any]] = {}
    for event in events:
        if event["event_type"] != "attempt_finished":
            continue
        payload = event["payload"]
        key = (payload.get("cell_id"), payload.get("attempt"))
        if (
            not isinstance(key[0], str)
            or key[1] not in (1, 2)
            or key in finishes
            or payload.get("classification")
            not in set(EXPERIMENTAL_OUTCOMES) | set(RETRYABLE_INFRASTRUCTURE) | set(BATCH_STOP_CLASSES)
        ):
            raise ExperimentConfigurationError("attempt-finished evidence is malformed or repeated")
        finishes[key] = payload
    stopped = next(
        (
            event
            for event in reversed(events)
            if event["event_type"] in {"batch_stopped", "stage_1_failed"}
        ),
        None,
    )
    completed = {
        event["payload"]["cell_id"] for event in events if event["event_type"] == "cell_completed"
    }
    starts: dict[str, list[int]] = {}
    invocations: set[tuple[str, int]] = set()
    returned_invocations: set[tuple[str, int]] = set()
    authorized: set[str] = set()
    stage_1_boundary = any(
        event["event_type"] == "stage_1_boundary_reached" for event in events
    )
    stage_2_authorized = any(event["event_type"] == "stage_2_authorized" for event in events)
    for event in events:
        payload = event["payload"]
        if event["event_type"] == "attempt_started":
            starts.setdefault(payload["cell_id"], []).append(payload["attempt"])
        elif event["event_type"] == "subject_invocation_started":
            invocations.add((payload["cell_id"], payload["attempt"]))
        elif event["event_type"] == "subject_invocation_returned":
            returned_invocations.add((payload["cell_id"], payload["attempt"]))
        elif event["event_type"] == "attempt_2_authorized":
            finish = finishes.get((payload["cell_id"], 1))
            if (
                finish is None
                or finish["classification"] not in RETRYABLE_INFRASTRUCTURE
                or payload.get("classification") != finish["classification"]
            ):
                raise ExperimentConfigurationError("attempt-2 authority lacks matching infrastructure evidence")
            authorized.add(payload["cell_id"])
        elif event["event_type"] == "cell_completed":
            finish = finishes.get((payload["cell_id"], payload["attempt"]))
            if finish is None or finish["classification"] not in EXPERIMENTAL_OUTCOMES:
                raise ExperimentConfigurationError("cell completion lacks matching outcome evidence")
    for key, finish in finishes.items():
        if finish["classification"] in EXPERIMENTAL_OUTCOMES and key not in returned_invocations:
            raise ExperimentConfigurationError("experimental outcome lacks returned subject evidence")
    schedule_ids = [cell["cell_id"] for cell in contract["schedule"]["cells"]]
    completed_positions = {schedule_ids.index(cell_id) for cell_id in completed}
    if completed_positions != set(range(len(completed_positions))):
        raise ExperimentConfigurationError("completed cells are not a frozen schedule prefix")
    current_cell = schedule_ids[len(completed_positions)] if len(completed_positions) < len(schedule_ids) else None
    if set(starts) - completed - ({current_cell} if current_cell else set()):
        raise ExperimentConfigurationError("attempt ledger violates frozen schedule order")
    subject_executions = contract["attempt_accounting"]["qualification_subject_executions"] + len(
        invocations
    )
    if stopped:
        action: dict[str, Any] = {"action": "stopped", "reason": stopped["payload"]["reason"]}
    elif len(completed) == contract["staging"]["stage_1_cell_count"] and not stage_1_boundary:
        action = {"action": "reconcile_stage_1_boundary"}
    elif stage_1_boundary and not stage_2_authorized:
        action = {"action": "await_stage_1_authorization"}
    else:
        action = {"action": "complete"}
        for cell in contract["schedule"]["cells"]:
            cell_id = cell["cell_id"]
            if cell_id in completed:
                continue
            attempts = starts.get(cell_id, [])
            if not attempts:
                action = {"action": "execute", "cell": cell, "attempt": 1}
            elif attempts == [1] and cell_id in authorized:
                action = {"action": "execute", "cell": cell, "attempt": 2}
            else:
                latest = attempts[-1]
                if (cell_id, latest) not in finishes:
                    action = {"action": "reconcile", "cell": cell, "attempt": latest}
                elif (cell_id, latest) in finishes:
                    action = {
                        "action": "reconcile_transition",
                        "cell": cell,
                        "attempt": latest,
                        "classification": finishes[(cell_id, latest)]["classification"],
                    }
                else:
                    action = {"action": "stopped", "reason": "incomplete durable transition"}
            break
    if action["action"] == "execute" and subject_executions >= contract[
        "attempt_accounting"
    ]["maximum_subject_executions_including_qualification"]:
        action = {"action": "stopped", "reason": "global_subject_execution_cap_reached"}
    return {
        "schema_name": f"{SCHEMA}.status",
        "schema_version": 1,
        "completed_cells": len(completed),
        "subject_executions_including_qualification": subject_executions,
        "harness_attempts": sum(len(values) for values in starts.values()),
        "next_action": action,
    }


@contextmanager
def _runner_lock(state_root: Path) -> Iterator[None]:
    state_root.mkdir(parents=True, exist_ok=True)
    with (state_root / "runner.lock").open("a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ExperimentConfigurationError("another effort-v1 runner owns the state lock") from error
        yield


def _environment(codex_home: Path, dataset_cache_root: Path) -> dict[str, str]:
    value = {name: os.environ[name] for name in ALLOWED_ENVIRONMENT if name in os.environ}
    value.update(
        {
            "CODEX_HOME": str(codex_home),
            "HF_DATASETS_OFFLINE": "1",
            "HF_HUB_OFFLINE": "1",
            "HF_DATASETS_CACHE": str(dataset_cache_root),
        }
    )
    return value


def _materialize(task: dict[str, Any], repository: Path, derived: Path) -> dict[str, Any]:
    container = _checked(["docker", "create", "--platform", "linux/amd64", task["docker_image"], "true"])
    try:
        copied = subprocess.run(
            ["docker", "cp", f"{container}:/testbed/.", str(repository)],
            capture_output=True,
            check=False,
        )
        if copied.returncode != 0:
            raise ExperimentConfigurationError("cannot materialize official task repository")
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
    if _checked(["git", "rev-parse", "HEAD"], repository) != task["base_commit"]:
        raise ExperimentConfigurationError("official image repository is not at frozen base commit")
    return capture_repository_baseline(repository, derived)


def _attempt_roots(state_root: Path, cell_id: str, attempt: int) -> dict[str, Path]:
    base = state_root / "attempts" / cell_id / f"attempt-{attempt}"
    return {name: base / name for name in ("repository", "codex-home", "raw", "derived", "evaluator")}


def _cell_evidence(
    cell: dict[str, Any], task: dict[str, Any], classification: str
) -> dict[str, Any]:
    return {
        "task_id": task["task_id"],
        "repository": task["repository"],
        "arm": cell["arm"],
        "reasoning_effort": cell["reasoning_effort"],
        "repetition": cell["repetition"],
        "termination": classification,
        "accepted": classification == "accepted_completed",
    }


def _work_evidence(subject: dict[str, Any], wall_seconds: float) -> dict[str, Any]:
    activity = subject["activity"]
    return {
        **subject["usage"]["provider_reported"],
        "subject_wall_seconds": wall_seconds,
        "subject_turns": activity["turns"],
        "command_count": activity["commands"],
        "search_count": activity["repository_search_commands"],
        "external_search_item_count": activity["external_search_items"],
        "item_count": activity["completed_items"],
        "item_counts": activity["item_types"],
    }


def _record_subject_invocation_start(
    ledger: Path,
    contract: dict[str, Any],
    *,
    cell_id: str,
    attempt: int,
    prompt_sha256: str,
    command_sha256: str,
    codex_executable_sha256: str,
) -> None:
    events = read_attempt_ledger(ledger, contract)
    current = runner_status(contract, events)
    if current["subject_executions_including_qualification"] >= contract[
        "attempt_accounting"
    ]["maximum_subject_executions_including_qualification"]:
        raise ExperimentConfigurationError("global subject-execution cap reached before invocation")
    payload = {
        "cell_id": cell_id,
        "attempt": attempt,
        "prompt_sha256": prompt_sha256,
        "command_sha256": command_sha256,
        "codex_executable_sha256": codex_executable_sha256,
    }
    # Validate before the durable append; a started invocation conservatively consumes capacity.
    validate_attempt_ledger(
        contract, [*events, {"event_type": "subject_invocation_started", "payload": payload}]
    )
    append_event(ledger, "subject_invocation_started", payload)


def _record_subject_invocation_return(
    ledger: Path,
    contract: dict[str, Any],
    *,
    cell_id: str,
    attempt: int,
    exit_code: int | None,
    timed_out: bool,
    stdout_sha256: str,
    stderr_sha256: str,
) -> None:
    events = read_attempt_ledger(ledger, contract)
    payload = {
        "cell_id": cell_id,
        "attempt": attempt,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
    }
    validate_attempt_ledger(
        contract, [*events, {"event_type": "subject_invocation_returned", "payload": payload}]
    )
    append_event(ledger, "subject_invocation_returned", payload)


def _evidence_hashes(roots: dict[str, Path]) -> dict[str, str]:
    """Hash restart-relevant raw/derived evidence without exposing its content."""

    base = next(iter(roots.values())).parent
    hashes: dict[str, str] = {}
    for group in ("raw", "derived", "evaluator"):
        for path in sorted(roots[group].rglob("*")):
            if path.is_file() and path.name not in {"receipt.json", "receipt.json.tmp"}:
                hashes[path.relative_to(base).as_posix()] = sha256_file(path)
    return hashes


def _persist_receipt(roots: dict[str, Path], receipt: dict[str, Any]) -> tuple[dict[str, Any], str]:
    durable = {**receipt, "evidence_files_sha256": _evidence_hashes(roots)}
    path = roots["derived"] / "receipt.json"
    _write_json(path, durable)
    return durable, sha256_file(path)


def _validate_persisted_receipt(roots: dict[str, Path]) -> tuple[dict[str, Any], str]:
    path = roots["derived"] / "receipt.json"
    if not path.is_file():
        raise ExperimentConfigurationError("interrupted attempt lacks a durable receipt")
    receipt = read_object(path)
    expected = receipt.get("evidence_files_sha256")
    if not isinstance(expected, dict) or expected != _evidence_hashes(roots):
        raise ExperimentConfigurationError("interrupted attempt evidence hashes changed")
    return receipt, sha256_file(path)


def _validate_finished_evidence(state_root: Path, events: list[dict[str, Any]]) -> None:
    """Revalidate every durable receipt and its raw/derived evidence on restart."""

    for event in events:
        if event["event_type"] != "attempt_finished":
            continue
        payload = event["payload"]
        receipt_sha256 = payload.get("receipt_file_sha256")
        if receipt_sha256 is None:
            # Pre-execution fixtures and isolation failures have no evidence root.
            continue
        roots = _attempt_roots(state_root, payload["cell_id"], payload["attempt"])
        receipt, observed_sha256 = _validate_persisted_receipt(roots)
        if observed_sha256 != receipt_sha256 or {
            key: value for key, value in payload.items() if key != "receipt_file_sha256"
        } != receipt:
            raise ExperimentConfigurationError("durable receipt differs from the hash-chain ledger")


def reconcile_interrupted_attempt(
    state_root: Path, contract: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Finish only already-durable evidence; never resume or repeat provider work."""

    action = runner_status(contract, events)["next_action"]
    ledger = state_root / "ledger.jsonl"
    if action["action"] == "reconcile_stage_1_boundary":
        append_event(
            ledger,
            "stage_1_boundary_reached",
            {"completed_cell_count": contract["staging"]["stage_1_cell_count"]},
        )
        return runner_status(contract, read_attempt_ledger(ledger, contract))
    if action["action"] == "reconcile_transition":
        _transition_after_finish(
            ledger,
            contract,
            action["cell"]["cell_id"],
            action["attempt"],
            action["classification"],
        )
        return runner_status(contract, read_attempt_ledger(ledger, contract))
    if action["action"] != "reconcile":
        raise ExperimentConfigurationError("there is no interrupted attempt to reconcile")
    cell = action["cell"]
    attempt = action["attempt"]
    roots = _attempt_roots(state_root, cell["cell_id"], attempt)
    receipt_path = roots["derived"] / "receipt.json"
    if receipt_path.is_file():
        try:
            receipt, _ = _validate_persisted_receipt(roots)
        except ExperimentConfigurationError:
            append_event(
                ledger,
                "batch_stopped",
                {"cell_id": cell["cell_id"], "reason": "durable_evidence_incomplete"},
            )
            return runner_status(contract, read_attempt_ledger(ledger, contract))
        classification = receipt.get("classification")
        if (
            receipt.get("cell_id") != cell["cell_id"]
            or receipt.get("attempt") != attempt
            or classification
            not in (
                set(EXPERIMENTAL_OUTCOMES)
                | set(RETRYABLE_INFRASTRUCTURE)
                | set(BATCH_STOP_CLASSES)
            )
        ):
            append_event(
                ledger,
                "batch_stopped",
                {"cell_id": cell["cell_id"], "reason": "durable_evidence_incomplete"},
            )
            return runner_status(contract, read_attempt_ledger(ledger, contract))
    else:
        classification = "durable_evidence_incomplete"
        receipt = {
            "cell_id": cell["cell_id"],
            "attempt": attempt,
            "classification": classification,
            "termination": classification,
            "accepted": False,
            "admissible": False,
            "reconciled_after_interruption": True,
        }
    _classify_and_transition(
        ledger, contract, cell["cell_id"], attempt, classification, receipt, roots
    )
    return runner_status(contract, read_attempt_ledger(ledger, contract))


def cleanup_interrupted_attempt_auth(
    state_root: Path, contract: dict[str, Any], events: list[dict[str, Any]]
) -> int:
    """Remove credentials only from exact ledger-known attempt roots before preflight."""

    known_attempts = {
        (event["payload"]["cell_id"], event["payload"]["attempt"])
        for event in events
        if event["event_type"] == "attempt_started"
    }
    removed = 0
    for cell_id, attempt in sorted(known_attempts):
        roots = _attempt_roots(state_root, cell_id, attempt)
        auth_path = roots["codex-home"] / "auth.json"
        if not auth_path.exists():
            continue
        remove_file_auth(roots["codex-home"])
        if auth_path.exists():
            raise ExperimentConfigurationError("interrupted attempt authentication cleanup failed")
        removed += 1
    return removed


def _sha256_field(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _non_negative_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
    )


def _non_negative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def stage_1_audit(
    contract: dict[str, Any],
    events: list[dict[str, Any]],
    expected_subject_command_sha256: dict[str, str],
) -> dict[str, Any]:
    """Evaluate only content-free Stage-1 infrastructure evidence."""

    status = runner_status(contract, events)
    stage_cells = contract["schedule"]["cells"][: contract["staging"]["stage_1_cell_count"]]
    cell_by_id = {cell["cell_id"]: cell for cell in stage_cells}
    completions = {
        event["payload"]["cell_id"]: event["payload"]["attempt"]
        for event in events
        if event["event_type"] == "cell_completed"
        and event["payload"].get("cell_id") in cell_by_id
    }
    starts = {
        (event["payload"].get("cell_id"), event["payload"].get("attempt")): event["payload"]
        for event in events
        if event["event_type"] == "subject_invocation_started"
    }
    returns = {
        (event["payload"].get("cell_id"), event["payload"].get("attempt")): event["payload"]
        for event in events
        if event["event_type"] == "subject_invocation_returned"
    }
    finishes = {
        (event["payload"].get("cell_id"), event["payload"].get("attempt")): event["payload"]
        for event in events
        if event["event_type"] == "attempt_finished"
    }
    final_keys = {(cell_id, attempt) for cell_id, attempt in completions.items()}

    commands_complete = True
    returns_complete = True
    usage_complete = True
    subject_work_complete = True
    tool_policy_complete = True
    evaluator_complete = True
    durable_receipts_bound = True
    arms = {arm: 0 for arm in ARMS}
    prohibited_item_types = {
        "web_search",
        "webSearch",
        "mcp_tool_call",
        "dynamic_tool_call",
        "collab_agent_tool_call",
    }
    for key in final_keys:
        cell_id, _ = key
        cell = cell_by_id[cell_id]
        arms[cell["arm"]] += 1
        start = starts.get(key, {})
        returned = returns.get(key, {})
        receipt = finishes.get(key, {})
        commands_complete = commands_complete and (
            start.get("command_sha256") == expected_subject_command_sha256.get(cell["arm"])
        )
        returns_complete = returns_complete and bool(start) and bool(returned)
        provider_usage = (
            receipt.get("usage", {}).get("provider_reported")
            if isinstance(receipt.get("usage"), dict)
            else None
        )
        try:
            validated_usage = validate_usage(
                provider_usage,
                measurement_scope=USAGE_MEASUREMENT_SCOPE,
            )
        except (ExperimentConfigurationError, TypeError):
            usage_complete = False
        else:
            usage_complete = usage_complete and receipt.get("usage") == validated_usage and all(
                receipt.get(field) == provider_usage[field] for field in provider_usage
            )
        activity = receipt.get("activity")
        item_types = activity.get("item_types") if isinstance(activity, dict) else None
        subject_work_complete = subject_work_complete and (
            isinstance(activity, dict)
            and _non_negative_number(receipt.get("subject_wall_time_seconds"))
            and receipt.get("subject_wall_seconds")
            == receipt.get("subject_wall_time_seconds")
            and activity.get("turns") == 1
            and receipt.get("subject_turns") == activity.get("turns")
            and _non_negative_integer(activity.get("commands"))
            and receipt.get("command_count") == activity.get("commands")
            and _non_negative_integer(activity.get("repository_search_commands"))
            and receipt.get("search_count")
            == activity.get("repository_search_commands")
            and _non_negative_integer(activity.get("completed_items"))
            and receipt.get("item_count") == activity.get("completed_items")
            and receipt.get("item_counts") == item_types
        )
        tool_policy_complete = tool_policy_complete and (
            isinstance(item_types, dict)
            and activity.get("external_search_items") == 0
            and receipt.get("external_search_item_count") == 0
            and prohibited_item_types.isdisjoint(item_types)
        )
        evaluator_complete = evaluator_complete and (
            receipt.get("subject_exit_code") == 0
            and receipt.get("subject_timed_out") is False
            and receipt.get("evaluator_exit_code") == 0
            and receipt.get("evaluator_timed_out") is False
            and isinstance(receipt.get("evaluator_wall_time_seconds"), (int, float))
            and not isinstance(receipt.get("evaluator_wall_time_seconds"), bool)
            and receipt["evaluator_wall_time_seconds"] >= 0
            and isinstance(receipt.get("official_disposition"), str)
            and bool(receipt["official_disposition"])
            and isinstance(receipt.get("resolved"), bool)
            and _sha256_field(receipt.get("patch_sha256"))
            and _sha256_field(receipt.get("results_sha256"))
        )
        durable_receipts_bound = durable_receipts_bound and _sha256_field(
            receipt.get("receipt_file_sha256")
        )

    criteria = {
        "awaiting_stage_1_authorization": status["next_action"]["action"]
        == "await_stage_1_authorization",
        "exact_four_cell_schedule_prefix": set(completions) == set(cell_by_id),
        "both_arms_have_two_final_cells": arms == {arm: 2 for arm in ARMS},
        "arm_command_receipts_complete": commands_complete,
        "subject_returns_complete": returns_complete,
        "usage_receipts_complete": usage_complete,
        "subject_work_receipts_complete": subject_work_complete,
        "tool_policy_receipts_complete": tool_policy_complete,
        "official_evaluator_receipts_complete": evaluator_complete,
        "durable_receipts_bound": durable_receipts_bound,
        "no_batch_stop": not any(event["event_type"] == "batch_stopped" for event in events),
    }
    audit = {
        "schema_name": f"{SCHEMA}.stage-1-audit",
        "schema_version": 1,
        "status": "pass" if all(criteria.values()) else "fail",
        "criteria": criteria,
        "completed_cells": len(completions),
        "final_cells_by_arm": arms,
        "outcome_direction_inspected": False,
        "outcome_values_emitted": False,
    }
    return audit


def authorize_stage_2(
    state_root: Path,
    contract: dict[str, Any],
    events: list[dict[str, Any]],
    expected_subject_command_sha256: dict[str, str],
) -> dict[str, Any]:
    """Record the explicit provider-free Stage-1 audit boundary decision."""

    action = runner_status(contract, events)["next_action"]
    if action["action"] != "await_stage_1_authorization":
        raise ExperimentConfigurationError("Stage 2 is not awaiting authorization")
    _validate_finished_evidence(state_root, events)
    audit = stage_1_audit(contract, events, expected_subject_command_sha256)
    event_type = "stage_2_authorized" if audit["status"] == "pass" else "stage_1_failed"
    payload = {
        "stage_1_completed_cell_count": contract["staging"]["stage_1_cell_count"],
        "audit": audit,
        "audit_sha256": digest(audit),
    }
    if event_type == "stage_1_failed":
        payload["reason"] = "stage_1_infrastructure_gate_failed"
    append_event(
        state_root / "ledger.jsonl",
        event_type,
        payload,
    )
    return runner_status(
        contract, read_attempt_ledger(state_root / "ledger.jsonl", contract)
    )


def _classify_and_transition(
    ledger: Path,
    contract: dict[str, Any],
    cell_id: str,
    attempt: int,
    classification: str,
    receipt: dict[str, Any],
    roots: dict[str, Path] | None = None,
) -> None:
    ledger_receipt = receipt
    if roots is not None:
        durable, receipt_sha256 = _persist_receipt(roots, receipt)
        ledger_receipt = {**durable, "receipt_file_sha256": receipt_sha256}
    append_event(ledger, "attempt_finished", ledger_receipt)
    _transition_after_finish(ledger, contract, cell_id, attempt, classification)


def _transition_after_finish(
    ledger: Path,
    contract: dict[str, Any],
    cell_id: str,
    attempt: int,
    classification: str,
) -> None:
    """Complete the deterministic post-receipt transition without duplicating evidence."""

    if classification in ATTEMPT_2_INFRASTRUCTURE_CLASSES:
        if attempt == 1:
            events = read_attempt_ledger(ledger, contract)
            executions = contract["attempt_accounting"]["qualification_subject_executions"] + sum(
                event["event_type"] == "subject_invocation_started" for event in events
            )
            if executions >= contract["attempt_accounting"][
                "maximum_subject_executions_including_qualification"
            ]:
                append_event(
                    ledger,
                    "batch_stopped",
                    {"cell_id": cell_id, "reason": "global_subject_execution_cap_reached"},
                )
            else:
                authorize_attempt_2(ledger, contract, cell_id, classification, classification)
        else:
            append_event(
                ledger,
                "batch_stopped",
                {"cell_id": cell_id, "reason": "attempt_2_infrastructure_budget_exhausted"},
            )
    elif classification in BATCH_STOP_CLASSES:
        append_event(ledger, "batch_stopped", {"cell_id": cell_id, "reason": classification})
    elif classification in EXPERIMENTAL_OUTCOMES:
        record_cell_completed(ledger, contract, cell_id, attempt)
        completed = runner_status(contract, read_attempt_ledger(ledger, contract))["completed_cells"]
        if completed == contract["staging"]["stage_1_cell_count"]:
            append_event(
                ledger,
                "stage_1_boundary_reached",
                {"completed_cell_count": completed},
            )
    else:
        raise ExperimentConfigurationError("attempt classification is outside the frozen taxonomy")


def execute_next(
    *,
    root: Path,
    contract: dict[str, Any],
    pool: dict[str, Any],
    authorization: dict[str, Any],
    evaluator_root: Path,
    dataset_root: Path,
    evaluator_python: Path,
    codex_binary: str,
    source_codex_home: Path,
    state_root: Path,
) -> dict[str, Any]:
    """Execute exactly one durable cell attempt; never loop or resume."""

    try:
        validate_write_target(state_root)
    except DiskSafetyError as error:
        raise ExperimentConfigurationError(str(error)) from error
    ledger = state_root / "ledger.jsonl"
    with _runner_lock(state_root):
        try:
            validate_write_target(state_root)
            require_disk_safety(state_root.parent, filesystem_path=state_root)
        except DiskSafetyError as error:
            raise ExperimentConfigurationError(str(error)) from error
        events = read_attempt_ledger(ledger, contract)
        action = runner_status(contract, events)["next_action"]
        if action["action"] != "execute":
            raise ExperimentConfigurationError("there is no legal next attempt")
        cell = action["cell"]
        attempt = action["attempt"]
        record_attempt_start(ledger, contract, cell["cell_id"], attempt)
        task = {item["task_id"]: item for item in _pool_tasks(pool)}[cell["task_id"]]
        roots = _attempt_roots(state_root, cell["cell_id"], attempt)
        if any(path.exists() for path in roots.values()):
            receipt = {
                **_cell_evidence(cell, task, "isolation_contract_violation"),
                "cell_id": cell["cell_id"],
                "attempt": attempt,
                "classification": "isolation_contract_violation",
                "admissible": False,
            }
            _classify_and_transition(
                ledger,
                contract,
                cell["cell_id"],
                attempt,
                "isolation_contract_violation",
                receipt,
            )
            return receipt
        for path in roots.values():
            path.mkdir(parents=True, exist_ok=False)
        auth_created = False
        started = _now()
        try:
            try:
                provision_file_auth(source_codex_home, roots["codex-home"])
                auth_created = True
            except (ExperimentConfigurationError, OSError):
                receipt = {
                    **_cell_evidence(cell, task, "durable_evidence_incomplete"),
                    "cell_id": cell["cell_id"],
                    "attempt": attempt,
                    "started_at": started,
                    "ended_at": _now(),
                    "classification": "durable_evidence_incomplete",
                    "admissible": False,
                }
                _classify_and_transition(
                    ledger, contract, cell["cell_id"], attempt, receipt["classification"], receipt, roots
                )
                return receipt
            prompt_path = roots["raw"] / "task-prompt.txt"
            try:
                resolved = resolve_dataset_task(
                    root,
                    evaluator_python,
                    dataset_root,
                    task["language"],
                    task["task_id"],
                    "resolve",
                )
                if resolved != {
                    "instance_id": task["task_id"],
                    "language": task["language"],
                    "repo": task["repository"],
                    "base_commit": task["base_commit"],
                    "docker_image": task["docker_image"],
                    "problem_statement_sha256": task["problem_statement_sha256"],
                }:
                    raise ExperimentConfigurationError("resolved task identity changed")
                prompt_identity = resolve_dataset_task(
                    root,
                    evaluator_python,
                    dataset_root,
                    task["language"],
                    task["task_id"],
                    "prompt",
                    prompt_path,
                )
                _validate_prompt_bytes(
                    prompt_path, prompt_identity, task["problem_statement_sha256"]
                )
            except (ExperimentConfigurationError, OSError, subprocess.SubprocessError):
                receipt = {
                    **_cell_evidence(cell, task, "malformed_inconsistent_measurement"),
                    "cell_id": cell["cell_id"],
                    "attempt": attempt,
                    "started_at": started,
                    "ended_at": _now(),
                    "classification": "malformed_inconsistent_measurement",
                    "admissible": False,
                }
                _classify_and_transition(
                    ledger, contract, cell["cell_id"], attempt, receipt["classification"], receipt, roots
                )
                return receipt
            try:
                baseline = _materialize(task, roots["repository"], roots["derived"])
            except (ExperimentConfigurationError, OSError, subprocess.SubprocessError):
                receipt = {
                    **_cell_evidence(
                        cell, task, "local_docker_runtime_infrastructure_failure"
                    ),
                    "cell_id": cell["cell_id"],
                    "attempt": attempt,
                    "started_at": started,
                    "ended_at": _now(),
                    "classification": "local_docker_runtime_infrastructure_failure",
                    "admissible": False,
                }
                _classify_and_transition(
                    ledger, contract, cell["cell_id"], attempt, receipt["classification"], receipt, roots
                )
                return receipt
            resolved_codex, codex_identity = _codex_executable_identity(codex_binary)
            if codex_identity != authorization["runtime"]["codex_executable"]:
                raise ExperimentConfigurationError("Codex executable changed after preflight")
            command = subject_command(str(resolved_codex), contract, cell)
            prompt_bytes = prompt_path.read_bytes()
            _record_subject_invocation_start(
                ledger,
                contract,
                cell_id=cell["cell_id"],
                attempt=attempt,
                prompt_sha256=hashlib.sha256(prompt_bytes).hexdigest(),
                command_sha256=digest(command),
                codex_executable_sha256=codex_identity["file_sha256"],
            )
            subject_started = time.monotonic()
            exit_code, timed_out, stdout, stderr = _run(
                command,
                cwd=roots["repository"],
                env=_environment(roots["codex-home"], dataset_root.parent / "hf-cache"),
                stdin=prompt_bytes,
                timeout=authorization["execution"]["subject_timeout_seconds"],
            )
            subject_wall_time_seconds = time.monotonic() - subject_started
            trace = roots["raw"] / "codex.jsonl"
            trace.write_bytes(stdout)
            stderr_path = roots["raw"] / "codex.stderr"
            stderr_path.write_bytes(stderr)
            _record_subject_invocation_return(
                ledger,
                contract,
                cell_id=cell["cell_id"],
                attempt=attempt,
                exit_code=exit_code,
                timed_out=timed_out,
                stdout_sha256=sha256_file(trace),
                stderr_sha256=sha256_file(stderr_path),
            )
            try:
                subject = parse_subject_trace(stdout)
            except ExperimentConfigurationError:
                provider_failure = False
                malformed_line = False
                subject_failure = False
                for raw in stdout.splitlines():
                    try:
                        event = json.loads(raw)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        malformed_line = True
                        continue
                    provider_failure = provider_failure or (
                        isinstance(event, dict) and classify_provider_event(event)
                    )
                    subject_failure = subject_failure or (
                        isinstance(event, dict) and event.get("type") == "turn.failed"
                    )
                classification = (
                    "trajectory_timeout"
                    if timed_out
                    else "malformed_inconsistent_measurement"
                    if malformed_line
                    else "provider_api_infrastructure_failure"
                    if provider_failure
                    else "agent_subject_failure"
                    if subject_failure or exit_code not in (0, None)
                    else "malformed_inconsistent_measurement"
                )
                receipt = {
                    **_cell_evidence(cell, task, classification),
                    "cell_id": cell["cell_id"],
                    "attempt": attempt,
                    "started_at": started,
                    "ended_at": _now(),
                    "classification": classification,
                    "subject_exit_code": exit_code,
                    "subject_timed_out": timed_out,
                    "subject_wall_time_seconds": subject_wall_time_seconds,
                    "admissible": classification in EXPERIMENTAL_OUTCOMES,
                }
                _classify_and_transition(ledger, contract, cell["cell_id"], attempt, classification, receipt, roots)
                return receipt
            if timed_out:
                classification = "trajectory_timeout"
                receipt = {
                    **_cell_evidence(cell, task, classification),
                    "cell_id": cell["cell_id"],
                    "attempt": attempt,
                    "started_at": started,
                    "ended_at": _now(),
                    "classification": classification,
                    "subject_exit_code": exit_code,
                    "subject_timed_out": True,
                    "subject_wall_time_seconds": subject_wall_time_seconds,
                    "usage": subject["usage"],
                    "activity": subject["activity"],
                    **_work_evidence(subject, subject_wall_time_seconds),
                    "admissible": True,
                }
                _classify_and_transition(
                    ledger, contract, cell["cell_id"], attempt, classification, receipt, roots
                )
                return receipt
            if subject["provider_infrastructure_failure"]:
                classification = "provider_api_infrastructure_failure"
                receipt = {
                    **_cell_evidence(cell, task, classification),
                    "cell_id": cell["cell_id"],
                    "attempt": attempt,
                    "started_at": started,
                    "ended_at": _now(),
                    "classification": classification,
                    "subject_exit_code": exit_code,
                    "subject_timed_out": timed_out,
                    "subject_wall_time_seconds": subject_wall_time_seconds,
                    "usage": subject["usage"],
                    "activity": subject["activity"],
                    **_work_evidence(subject, subject_wall_time_seconds),
                    "admissible": False,
                }
                _classify_and_transition(
                    ledger, contract, cell["cell_id"], attempt, classification, receipt, roots
                )
                return receipt
            if exit_code != 0:
                classification = "agent_subject_failure"
                receipt = {
                    **_cell_evidence(cell, task, classification),
                    "cell_id": cell["cell_id"],
                    "attempt": attempt,
                    "started_at": started,
                    "ended_at": _now(),
                    "classification": classification,
                    "subject_exit_code": exit_code,
                    "subject_timed_out": False,
                    "subject_wall_time_seconds": subject_wall_time_seconds,
                    "usage": subject["usage"],
                    "activity": subject["activity"],
                    **_work_evidence(subject, subject_wall_time_seconds),
                    "admissible": True,
                }
                _classify_and_transition(
                    ledger, contract, cell["cell_id"], attempt, classification, receipt, roots
                )
                return receipt
            patch = subject_patch_from_baseline(roots["repository"], roots["derived"], baseline)
            patch_path = roots["derived"] / "prediction.patch"
            patch_path.write_bytes(patch)
            prediction_path = roots["derived"] / "prediction.json"
            _write_json(prediction_path, {task["task_id"]: {"model_patch": patch.decode("utf-8")}})
            output = roots["evaluator"] / "official"
            output.mkdir(exist_ok=False)
            evaluator_command = official_evaluator_command(
                evaluator_python,
                dataset_root,
                task["language"],
                prediction_path,
                output,
                1,
                task["task_id"],
            )
            evaluator_started = time.monotonic()
            eval_code, eval_timeout, eval_stdout, eval_stderr = _run(
                evaluator_command,
                cwd=evaluator_root,
                env=_environment(roots["codex-home"], dataset_root.parent / "hf-cache"),
                timeout=authorization["execution"]["evaluator_timeout_seconds"],
            )
            evaluator_wall_time_seconds = time.monotonic() - evaluator_started
            (output / "command.stdout").write_bytes(eval_stdout)
            (output / "command.stderr").write_bytes(eval_stderr)
            report_path = output / task["task_id"] / "report.json"
            results_path = output / "results.json"
            classification = "malformed_inconsistent_measurement"
            artifacts = None
            structured_malformed = False
            if results_path.is_file():
                try:
                    report = read_object(report_path) if report_path.is_file() else {}
                    artifacts = parse_official_evaluator_artifacts(
                        task["task_id"], report, read_object(results_path)
                    )
                except ExperimentConfigurationError:
                    structured_malformed = True
            classification = classify_evaluator_attempt(
                timed_out=eval_timeout,
                structured_malformed=structured_malformed,
                disposition=None if artifacts is None else artifacts.disposition,
            )
            receipt = {
                **_cell_evidence(cell, task, classification),
                "cell_id": cell["cell_id"],
                "attempt": attempt,
                "started_at": started,
                "ended_at": _now(),
                "classification": classification,
                "subject_exit_code": exit_code,
                "subject_timed_out": timed_out,
                "subject_wall_time_seconds": subject_wall_time_seconds,
                "usage": subject["usage"],
                "activity": subject["activity"],
                **_work_evidence(subject, subject_wall_time_seconds),
                "patch_sha256": sha256_file(patch_path),
                "evaluator_exit_code": eval_code,
                "evaluator_timed_out": eval_timeout,
                "evaluator_wall_time_seconds": evaluator_wall_time_seconds,
                "official_disposition": None if artifacts is None else artifacts.disposition,
                "resolved": None if artifacts is None else artifacts.resolved,
                "report_sha256": sha256_file(report_path) if report_path.is_file() else None,
                "results_sha256": sha256_file(results_path) if results_path.is_file() else None,
                "admissible": classification in EXPERIMENTAL_OUTCOMES,
            }
            _classify_and_transition(ledger, contract, cell["cell_id"], attempt, classification, receipt, roots)
            return receipt
        except (ExperimentConfigurationError, OSError, UnicodeError, ValueError, subprocess.SubprocessError):
            current_events = read_attempt_ledger(ledger, contract)
            finished = any(
                event["event_type"] == "attempt_finished"
                and event["payload"].get("cell_id") == cell["cell_id"]
                and event["payload"].get("attempt") == attempt
                for event in current_events
            )
            receipt = {
                **_cell_evidence(cell, task, "harness_failure"),
                "cell_id": cell["cell_id"],
                "attempt": attempt,
                "started_at": started,
                "ended_at": _now(),
                "classification": "harness_failure",
                "admissible": False,
            }
            if not finished:
                _classify_and_transition(
                    ledger, contract, cell["cell_id"], attempt, receipt["classification"], receipt, roots
                )
            return receipt
        finally:
            if auth_created:
                remove_file_auth(roots["codex-home"])


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--contract", type=Path, default=Path("experiment/reasoning_effort_v1_contract.json"))
    parser.add_argument("--pool", type=Path, default=Path("experiment/reasoning_effort_v1_pool.json"))
    parser.add_argument(
        "--authorization", type=Path, default=Path("experiment/reasoning_effort_v1_execution_authorization.json")
    )
    parser.add_argument("--evaluator-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--evaluator-python", type=Path)
    parser.add_argument("--model-catalog", type=Path, required=True)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--credential-source-codex-home", type=Path, default=DEFAULT_SOURCE_CODEX_HOME)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--output", type=Path, default=Path(".local/reasoning-effort-v1/preflight.json"))
    dry_run = subparsers.add_parser("dry-run")
    dry_run.add_argument("--output", type=Path, default=Path(".local/reasoning-effort-v1/dry-run.json"))
    subparsers.add_parser("status")
    subparsers.add_parser("reconcile")
    subparsers.add_parser("authorize-stage-2")
    subparsers.add_parser("execute-next")
    return parser.parse_args()


def _resolve(root: Path, value: Path) -> Path:
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def _state_root_path(root: Path, value: Path) -> Path:
    """Keep lexical components so the disk guard can detect symlink ancestors."""

    return value.absolute() if value.is_absolute() else (root / value).absolute()


def _enforce_disk_safety(command: str) -> bool:
    return command in {"preflight", "dry-run", "execute-next"}


def main() -> int:
    args = _arguments()
    root = args.root.resolve()
    contract_path = _resolve(root, args.contract)
    pool_path = _resolve(root, args.pool)
    authorization_path = _resolve(root, args.authorization)
    evaluator_root = args.evaluator_root.resolve()
    authorization = read_object(authorization_path)
    dataset_root = (
        args.dataset_root.resolve()
        if args.dataset_root
        else (evaluator_root / "dataset").resolve()
    )
    evaluator_python = canonical_evaluator_python(evaluator_root, args.evaluator_python)
    state_root = _state_root_path(root, args.state_root)
    output: dict[str, Any]
    try:
        contract = read_object(contract_path)
        cleaned_auth_files = 0
        if args.command == "reconcile":
            with _runner_lock(state_root):
                cleaned_auth_files = cleanup_interrupted_attempt_auth(
                    state_root,
                    contract,
                    read_attempt_ledger(state_root / "ledger.jsonl", contract),
                )
        preflight = strict_preflight(
            root=root,
            contract_path=contract_path,
            pool_path=pool_path,
            authorization_path=authorization_path,
            evaluator_root=evaluator_root,
            dataset_root=dataset_root,
            evaluator_python=evaluator_python,
            model_catalog_path=args.model_catalog.resolve(),
            codex_binary=args.codex_binary,
            state_root=state_root,
            enforce_disk_safety=_enforce_disk_safety(args.command),
        )
        pool = read_object(pool_path)
        if args.command == "preflight":
            output = preflight
            _write_json(_resolve(root, args.output), output)
        elif args.command == "status":
            output = runner_status(contract, read_attempt_ledger(state_root / "ledger.jsonl", contract))
        elif args.command == "reconcile":
            with _runner_lock(state_root):
                events = read_attempt_ledger(state_root / "ledger.jsonl", contract)
                action = runner_status(contract, events)["next_action"]["action"]
                if cleaned_auth_files and action not in {
                    "reconcile",
                    "reconcile_transition",
                    "reconcile_stage_1_boundary",
                }:
                    output = runner_status(contract, events)
                    output["credential_files_removed"] = cleaned_auth_files
                else:
                    output = reconcile_interrupted_attempt(state_root, contract, events)
        elif args.command == "authorize-stage-2":
            with _runner_lock(state_root):
                output = authorize_stage_2(
                    state_root,
                    contract,
                    read_attempt_ledger(state_root / "ledger.jsonl", contract),
                    preflight["subject_command_sha256_by_arm"],
                )
        elif args.command == "dry-run":
            status = runner_status(contract, read_attempt_ledger(state_root / "ledger.jsonl", contract))
            output = {
                "schema_name": f"{SCHEMA}.dry-run",
                "schema_version": 1,
                "status": "pass",
                "preflight": preflight,
                "next_action": status["next_action"],
                "isolation_root_template": ".local/reasoning-effort-v1/attempts/<cell_id>/attempt-<n>",
                "codex_invocations": 0,
                "evaluator_invocations": 0,
            }
            _write_json(_resolve(root, args.output), output)
        else:
            output = execute_next(
                root=root,
                contract=contract,
                pool=pool,
                authorization=authorization,
                evaluator_root=evaluator_root,
                dataset_root=dataset_root,
                evaluator_python=evaluator_python,
                codex_binary=args.codex_binary,
                source_codex_home=args.credential_source_codex_home.resolve(),
                state_root=state_root,
            )
        print(json.dumps(output, sort_keys=True))
        return 0
    except (ExperimentConfigurationError, OSError, KeyError, ValueError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
