#!/usr/bin/env python3
"""Run one resumable stage of evaluator-stable private qualification."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from engineering_scope_guard.disk_safety import require_disk_safety
from engineering_scope_guard.disk_safety import validate_write_target
from engineering_scope_guard.evaluator_stable_qualification import (
    STAGES,
    atomic_write_json,
    build_receipt,
    git_revision,
    next_qualification_stage,
    public_summary,
    read_json,
    record_stage,
    seal_receipt,
    sha256_file,
    sha256_value,
    validate_receipt,
)
from engineering_scope_guard.experiment import ExperimentConfigurationError

EXTRACT_INSTANCE = r"""
import json
import sys
from pathlib import Path
import pyarrow.parquet as parquet

dataset_root = Path(sys.argv[1])
language = sys.argv[2]
instance_id = sys.argv[3]
output = Path(sys.argv[4])
expected_repo = sys.argv[5]
expected_image = sys.argv[6]
resolved_image = sys.argv[7]
matches = []
for path in sorted((dataset_root / "data").glob(f"{language}-*.parquet")):
    table = parquet.read_table(path)
    matches.extend(row for row in table.to_pylist() if row.get("instance_id") == instance_id)
if len(matches) != 1:
    raise SystemExit(f"expected exactly one dataset row, observed {len(matches)}")
if matches[0].get("repo") != expected_repo or matches[0].get("docker_image") != expected_image:
    raise SystemExit("dataset row identity does not match the frozen candidate")
matches[0]["docker_image"] = resolved_image
output.write_text(json.dumps(matches[0], sort_keys=True) + "\n", encoding="utf-8")
"""

ANALYZE_VALIDATION_LOG = r"""
import json
import re
import sys
from pathlib import Path
from launch.scripts.parser import run_parser

instance = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()[0])
content = Path(sys.argv[2]).read_text(encoding="utf-8")
parts = re.split(r"eval No\.\d+\s*\n\n========\s*\n\n", content)[1:]
if len(parts) != 3:
    raise SystemExit("expected three validation logs")
parser = instance.get("log_parser", instance.get("parser", ""))
statuses = [run_parser(parser, part) for part in parts]
canonical = [json.dumps(status, sort_keys=True, separators=(",", ":")) for status in statuses]
print(json.dumps({"run_count": len(statuses), "stable": len(set(canonical)) == 1}, sort_keys=True))
"""

EXPECTED_DATASET_REVISION = "62dc0745c40f067fc366ae3eb1a26136e5928f85"
EXPECTED_EVALUATOR_REVISION = "7c5ee6c11595bb0290832eb9e5b7aa81ead1cfc0"
EXPECTED_REPOLAUNCH_REVISION = "c4b623d930f3728e5338664bb634021b98492cbf"


def _checked(
    command: list[str],
    *,
    cwd: Path | None = None,
    environment: dict[str, str] | None = None,
) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _evaluator_environment(evaluator_root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            (str(evaluator_root.resolve()), str((evaluator_root / "launch").resolve()))
        ),
    }


def _private_path(
    root: Path, path: Path, description: str, *, directory: bool = False
) -> Path:
    local = root / ".local"
    validate_write_target(local)
    lexical = path if path.is_absolute() else root / path
    validate_write_target(lexical if directory else lexical.parent)
    resolved_local = local.resolve()
    resolved = lexical.resolve(strict=False)
    try:
        resolved.relative_to(resolved_local)
    except ValueError as error:
        raise ExperimentConfigurationError(
            f"{description} must remain below the repository .local directory"
        ) from error
    return lexical.absolute()


def _private_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = path
    while current.name != ".local" and current != current.parent:
        os.chmod(current, 0o700)
        current = current.parent


def _private_write_json(path: Path, value: Any) -> None:
    _private_mkdir(path.parent)
    atomic_write_json(path, value)
    os.chmod(path, 0o600)


def _harden_private_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ExperimentConfigurationError("private qualification tree contains a symlink")
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    os.chmod(root, 0o700)


def _restrict_private_tree(root: Path) -> None:
    """Remove group/other access without changing owner executable bits."""

    paths = [root, *sorted(root.rglob("*"))] if root.is_dir() else [root]
    for path in paths:
        if path.is_symlink():
            raise ExperimentConfigurationError("private qualification input contains a symlink")
        mode = path.stat().st_mode & 0o700
        os.chmod(path, mode | (0o700 if path.is_dir() else 0o600))


def _restrict_private_inputs(args: argparse.Namespace) -> None:
    _restrict_private_tree(args.root / ".local/evaluator-stable-reasoning-effort")
    _restrict_private_tree(args.reserve)
    current = args.reserve.parent
    local = (args.root / ".local").resolve()
    while current.resolve() != local:
        os.chmod(current, 0o700)
        current = current.parent


@contextlib.contextmanager
def _qualification_lock(receipt: Path):
    lock_path = receipt.with_suffix(receipt.suffix + ".lock")
    _private_mkdir(lock_path.parent)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        os.close(descriptor)
        raise ExperimentConfigurationError("qualification state is already locked") from error
    try:
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _git_source_identity(root: Path, *, allow_runtime_tmp: bool = False) -> dict[str, str]:
    status = _checked(["git", "status", "--porcelain=v1"], cwd=root).splitlines()
    if allow_runtime_tmp:
        status = [line for line in status if line != "?? tmp/"]
    if status:
        raise ExperimentConfigurationError("pinned source checkout is not clean")
    listing = _checked(["git", "ls-tree", "-r", "--full-tree", "HEAD"], cwd=root)
    return {
        "revision": git_revision(root),
        "tree_sha256": hashlib.sha256(listing.encode()).hexdigest(),
    }


def _execution_code_identity(root: Path) -> dict[str, str]:
    paths = (
        root / "src/engineering_scope_guard/__init__.py",
        root / "src/engineering_scope_guard/evaluator_stable_qualification.py",
        root / "src/engineering_scope_guard/disk_safety.py",
        root / "src/engineering_scope_guard/experiment.py",
        root / "src/engineering_scope_guard/report.py",
        root / "src/engineering_scope_guard/repository.py",
        root / "src/engineering_scope_guard/trace.py",
        root / "scripts/evaluator_stable_qualification.py",
    )
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in paths}


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        return {
            "exit_code": completed.returncode,
            "timed_out": False,
            "wall_seconds": round(time.monotonic() - started, 3),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or "")
        return {
            "exit_code": None,
            "timed_out": True,
            "wall_seconds": round(time.monotonic() - started, 3),
            "stdout": stdout,
            "stderr": stderr,
        }


def _write_command_log(path: Path, result: dict[str, Any]) -> None:
    path.write_text(
        result["stdout"] + "\n--- STDERR ---\n" + result["stderr"],
        encoding="utf-8",
    )


def _dataset_hashes(dataset_root: Path) -> dict[str, str]:
    paths = sorted((dataset_root / "data").glob("*.parquet"))
    if not paths:
        raise ExperimentConfigurationError("dataset parquet files are missing")
    return {path.name: sha256_file(path) for path in paths}


def _python_identity(python: Path, evaluator_root: Path) -> dict[str, str]:
    executable = Path(
        _checked([str(python), "-c", "import sys; print(sys.executable)"])
    )
    versions = json.loads(
        _checked(
            [
                str(python),
                "-c",
                (
                    "import json,sys,fire,pyarrow,datasets; "
                    "print(json.dumps({'python':sys.version.split()[0],"
                    "'fire':fire.__version__,'pyarrow':pyarrow.__version__,"
                    "'datasets':datasets.__version__},sort_keys=True))"
                ),
            ]
        )
    )
    package_set = _checked(
        [
            str(python),
            "-c",
            (
                "from importlib.metadata import distributions; "
                "print('\\n'.join(sorted(f'{d.metadata[\"Name\"]}=={d.version}' "
                "for d in distributions() if d.metadata[\"Name\"])))"
            ),
        ]
    )
    module_paths = json.loads(
        _checked(
            [
                str(python),
                "-c",
                (
                    "import json,evaluation,launch.core.runtime as launch_runtime; "
                    "print(json.dumps({'evaluation':evaluation.__file__,"
                    "'launch':launch_runtime.__file__},sort_keys=True))"
                ),
            ],
            cwd=evaluator_root,
            environment=_evaluator_environment(evaluator_root),
        )
    )
    evaluator_prefix = str(evaluator_root.resolve()) + os.sep
    if not all(
        isinstance(value, str) and str(Path(value).resolve()).startswith(evaluator_prefix)
        for value in module_paths.values()
    ):
        raise ExperimentConfigurationError("evaluator Python resolves mixed source code")
    return {
        "executable_sha256": sha256_file(executable),
        "package_set_sha256": hashlib.sha256(package_set.encode()).hexdigest(),
        "evaluation_module_sha256": sha256_file(Path(module_paths["evaluation"])),
        "launch_module_sha256": sha256_file(Path(module_paths["launch"])),
        **versions,
    }


def _codex_runtime(codex_binary: Path, model_catalog: Path) -> dict[str, Any]:
    catalog = read_json(model_catalog)
    models = [model for model in catalog.get("models", []) if model.get("slug") == "gpt-5.6-sol"]
    if len(models) != 1:
        raise ExperimentConfigurationError("installed model catalog lacks one gpt-5.6-sol entry")
    model = models[0]
    efforts = [entry.get("effort") for entry in model.get("supported_reasoning_levels", [])]
    if "low" not in efforts or "medium" not in efforts:
        raise ExperimentConfigurationError("installed model catalog lacks low or medium")
    return {
        "codex_version": _checked([str(codex_binary), "--version"]),
        "codex_executable_sha256": sha256_file(codex_binary.resolve()),
        "model_catalog_sha256": sha256_file(model_catalog),
        "model_catalog_client_version": catalog.get("client_version"),
        "model_catalog_fetched_at": catalog.get("fetched_at"),
        "model": model["slug"],
        "catalog_default_reasoning_effort": model.get("default_reasoning_level"),
        "supported_reasoning_efforts": efforts,
        "context_window": model.get("context_window"),
        "effective_context_window_percent": model.get("effective_context_window_percent"),
        "host_system": platform.system(),
        "host_machine": platform.machine(),
        "docker_client_server": _docker_identity(),
    }


def _docker_identity() -> dict[str, Any]:
    return json.loads(_checked(["docker", "version", "--format", "{{json .}}"]))


def _require_expected_pins(
    reserve: dict[str, Any],
    evaluator: dict[str, str],
    repolaunch: dict[str, str],
) -> None:
    if reserve.get("source", {}).get("revision") != EXPECTED_DATASET_REVISION:
        raise ExperimentConfigurationError("dataset revision does not match D-069")
    if evaluator.get("revision") != EXPECTED_EVALUATOR_REVISION:
        raise ExperimentConfigurationError("evaluator revision does not match D-069")
    if repolaunch.get("revision") != EXPECTED_REPOLAUNCH_REVISION:
        raise ExperimentConfigurationError("RepoLaunch revision does not match D-069")


def initialize(args: argparse.Namespace) -> dict[str, Any]:
    if args.receipt.exists():
        raise ExperimentConfigurationError("qualification receipt already exists")
    _restrict_private_inputs(args)
    reserve = read_json(args.reserve)
    evaluator = _git_source_identity(args.evaluator_root, allow_runtime_tmp=True)
    repolaunch = _git_source_identity(args.evaluator_root / "launch")
    _require_expected_pins(reserve, evaluator, repolaunch)
    receipt = build_receipt(
        reserve,
        evaluator_revision=evaluator["revision"],
        repolaunch_revision=repolaunch["revision"],
        dataset_file_sha256=_dataset_hashes(args.dataset_root),
        evaluator_python=_python_identity(args.evaluator_python, args.evaluator_root),
        codex_runtime=_codex_runtime(args.codex_binary, args.model_catalog),
        execution_code_sha256=_execution_code_identity(args.root),
        evaluator_tree_sha256=evaluator["tree_sha256"],
        repolaunch_tree_sha256=repolaunch["tree_sha256"],
    )
    _private_write_json(args.receipt, receipt)
    return public_summary(receipt)


def _revalidate_sources(args: argparse.Namespace, receipt: dict[str, Any]) -> None:
    source = receipt["source"]
    evaluator = _git_source_identity(args.evaluator_root, allow_runtime_tmp=True)
    repolaunch = _git_source_identity(args.evaluator_root / "launch")
    actual = {
        "dataset_file_sha256": _dataset_hashes(args.dataset_root),
        "evaluator_revision": evaluator["revision"],
        "embedded_repolaunch_revision": repolaunch["revision"],
        "evaluator_tree_sha256": evaluator["tree_sha256"],
        "repolaunch_tree_sha256": repolaunch["tree_sha256"],
        "evaluator_python": _python_identity(args.evaluator_python, args.evaluator_root),
        "execution_code_sha256": _execution_code_identity(args.root),
        "reserve_receipt_sha256": sha256_value(read_json(args.reserve)),
    }
    for field, value in actual.items():
        if source.get(field) != value:
            raise ExperimentConfigurationError(f"frozen qualification source drifted: {field}")
    if receipt.get("runtime_observation", {}).get("docker_client_server") != _docker_identity():
        raise ExperimentConfigurationError("frozen Docker client/server identity drifted")


def _extract_instance(
    args: argparse.Namespace,
    candidate: dict[str, Any],
    output: Path,
    timeout: int,
) -> dict[str, Any]:
    result = _run(
        [
            str(args.evaluator_python),
            "-c",
            EXTRACT_INSTANCE,
            str(args.dataset_root),
            candidate["language"],
            candidate["instance_id"],
            str(output),
            candidate["repo"],
            candidate["docker_image"],
            candidate["resolved_image"],
        ],
        cwd=args.evaluator_root,
        timeout=timeout,
        environment=_evaluator_environment(args.evaluator_root),
    )
    return result


def _json_or_none(path: Path) -> Any:
    try:
        return read_json(path)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _jsonl_has_instance(path: Path, instance_id: str) -> bool:
    if not path.is_file():
        return False
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except json.JSONDecodeError:
        return False
    return any(value.get("instance_id") == instance_id for value in values if isinstance(value, dict))


def _container_ids(image: str) -> set[str]:
    output = _checked(["docker", "ps", "-aq", "--filter", f"ancestor={image}"])
    return {line for line in output.splitlines() if line}


def _run_evaluator(
    command: list[str],
    *,
    args: argparse.Namespace,
    candidate: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    before = _container_ids(candidate["resolved_image"])
    result = _run(
        command,
        cwd=args.evaluator_root,
        timeout=timeout,
        environment=_evaluator_environment(args.evaluator_root),
    )
    after = _container_ids(candidate["resolved_image"])
    new_containers = sorted(after - before)
    result["orphan_cleanup"] = {
        "new_matching_container_count": len(new_containers),
        "cleaned_container_count": 0,
        "cleanup_exit_code": None,
        "cleanup_timed_out": False,
        "automatic_cleanup_permitted": False,
    }
    result["fresh_runtime_semantics"] = {
        "separate_evaluator_process": True,
        "upstream_constructs_setup_runtime_per_invocation": True,
        "preexisting_matching_container_count": len(before),
        "new_matching_container_count_after_return": len(new_containers),
        "automatic_container_cleanup_permitted": False,
    }
    return result


def _stage_q1(
    args: argparse.Namespace, candidate: dict[str, Any], stage_root: Path, timeout: int
) -> tuple[str, str | None, dict[str, Any]]:
    manifest = _run(
        ["docker", "manifest", "inspect", candidate["docker_image"]],
        cwd=args.root,
        timeout=timeout,
    )
    manifest_log = stage_root / "manifest.log"
    _write_command_log(manifest_log, manifest)
    if manifest["timed_out"]:
        return "fail", "infrastructure_timeout", {"manifest": manifest}
    if manifest["exit_code"] != 0:
        return "fail", "build_environment_failure", {"manifest": manifest}
    observed_manifest_sha256 = hashlib.sha256(manifest["stdout"].encode()).hexdigest()
    expected = candidate["manifest_sha256"]
    if observed_manifest_sha256 != expected:
        raise ExperimentConfigurationError("frozen container manifest identity drifted")
    pull = _run(
        ["docker", "pull", candidate["docker_image"]],
        cwd=args.root,
        timeout=timeout,
    )
    pull_log = stage_root / "pull.log"
    _write_command_log(pull_log, pull)
    if pull["timed_out"]:
        return "fail", "infrastructure_timeout", {"manifest": manifest, "pull": pull}
    if pull["exit_code"] != 0:
        return "fail", "build_environment_failure", {"manifest": manifest, "pull": pull}
    inspect = _run(
        ["docker", "image", "inspect", candidate["docker_image"]],
        cwd=args.root,
        timeout=120,
    )
    inspect_log = stage_root / "inspect.log"
    _write_command_log(inspect_log, inspect)
    if inspect["timed_out"]:
        return "fail", "infrastructure_timeout", {"manifest": manifest, "pull": pull, "inspect": inspect}
    if inspect["exit_code"] != 0:
        return "fail", "build_environment_failure", {"manifest": manifest, "pull": pull, "inspect": inspect}
    image = json.loads(inspect["stdout"])
    if not isinstance(image, list) or len(image) != 1:
        return "fail", "evaluator_runtime_failure", {"manifest": manifest, "pull": pull, "inspect": inspect}
    repo_digests = sorted(image[0].get("RepoDigests") or [])
    if len(repo_digests) != 1 or "@sha256:" not in repo_digests[0]:
        return "fail", "evaluator_runtime_failure", {"manifest": manifest, "pull": pull, "inspect": inspect}
    resolved_manifest = _run(
        ["docker", "manifest", "inspect", repo_digests[0]],
        cwd=args.root,
        timeout=timeout,
    )
    resolved_manifest_log = stage_root / "resolved-manifest.log"
    _write_command_log(resolved_manifest_log, resolved_manifest)
    if resolved_manifest["timed_out"]:
        return "fail", "infrastructure_timeout", {
            "manifest": manifest,
            "pull": pull,
            "inspect": inspect,
            "resolved_manifest": resolved_manifest,
        }
    if resolved_manifest["exit_code"] != 0:
        return "fail", "evaluator_runtime_failure", {
            "manifest": manifest,
            "pull": pull,
            "inspect": inspect,
            "resolved_manifest": resolved_manifest,
        }
    resolved_manifest_sha256 = hashlib.sha256(
        resolved_manifest["stdout"].encode()
    ).hexdigest()
    if resolved_manifest_sha256 != observed_manifest_sha256:
        raise ExperimentConfigurationError(
            "pulled immutable image does not match the frozen registry manifest"
        )
    return "pass", None, {
        "manifest": manifest,
        "pull": pull,
        "inspect": inspect,
        "resolved_manifest": resolved_manifest,
        "image_identity": {
            "id": image[0].get("Id"),
            "repo_digests": repo_digests,
            "resolved_image_ref": repo_digests[0],
            "architecture": image[0].get("Architecture"),
            "os": image[0].get("Os"),
            "manifest_sha256": observed_manifest_sha256,
            "resolved_manifest_sha256": resolved_manifest_sha256,
        },
    }


def _stage_q2(
    args: argparse.Namespace, candidate: dict[str, Any], stage_root: Path, timeout: int
) -> tuple[str, str | None, dict[str, Any]]:
    instance_file = stage_root / "instance.jsonl"
    extraction = _extract_instance(args, candidate, instance_file, min(timeout, 300))
    extraction_log = stage_root / "extraction.log"
    _write_command_log(extraction_log, extraction)
    if extraction["timed_out"]:
        return "fail", "infrastructure_timeout", {"extraction": extraction}
    if extraction["exit_code"] != 0 or not instance_file.is_file():
        return "fail", "evaluator_runtime_failure", {"extraction": extraction}
    output = stage_root / "output"
    output.mkdir()
    command = [
        str(args.evaluator_python),
        "-m",
        "evaluation.validation",
        "--input_dir",
        str(instance_file),
        "--platform",
        "linux",
        "--workers",
        "1",
        "--output_dir",
        str(output),
        "--overwrite",
        "1",
    ]
    result = _run_evaluator(
        command,
        args=args,
        candidate=candidate,
        timeout=timeout,
    )
    log = stage_root / "command.log"
    _write_command_log(log, result)
    status_path = output / candidate["instance_id"] / "status.json"
    validated_path = output / "validated_instances.jsonl"
    status = _json_or_none(status_path)
    if result["timed_out"]:
        return "fail", "infrastructure_timeout", {"result": result}
    if result["orphan_cleanup"]["new_matching_container_count"]:
        return "fail", "evaluator_runtime_failure", {"result": result}
    if result["exit_code"] != 0:
        return "fail", "evaluator_runtime_failure", {"result": result}
    if not isinstance(status, dict):
        return "fail", "evaluator_runtime_failure", {"result": result}
    if not _jsonl_has_instance(validated_path, candidate["instance_id"]):
        post_patch_log = output / candidate["instance_id"] / "post_patch_log.txt"
        stability = _run(
            [
                str(args.evaluator_python),
                "-c",
                ANALYZE_VALIDATION_LOG,
                str(instance_file),
                str(post_patch_log),
            ],
            cwd=args.evaluator_root,
            timeout=120,
            environment=_evaluator_environment(args.evaluator_root),
        )
        stability_log = stage_root / "stability-analysis.log"
        _write_command_log(stability_log, stability)
        if stability["timed_out"]:
            return "fail", "infrastructure_timeout", {"result": result, "stability": stability}
        if stability["exit_code"] != 0:
            return "fail", "evaluator_runtime_failure", {"result": result, "stability": stability}
        stability_value = json.loads(stability["stdout"])
        classification = (
            "gold_patch_evaluation_failure"
            if stability_value.get("stable") is True
            else "flaky_validation"
        )
        return "fail", classification, {"result": result, "stability": stability}
    return "pass", None, {
        "result": result,
        "status_sha256": sha256_file(status_path),
        "validated_instances_sha256": sha256_file(validated_path),
    }


def _gold_classification(
    candidate: dict[str, Any], output: Path, result: dict[str, Any]
) -> tuple[str, str | None]:
    report = _json_or_none(output / candidate["instance_id"] / "report.json")
    results = _json_or_none(output / "results.json")
    if result["timed_out"]:
        return "fail", "infrastructure_timeout"
    if result.get("orphan_cleanup", {}).get("new_matching_container_count", 0):
        return "fail", "evaluator_runtime_failure"
    if result["exit_code"] != 0:
        return "fail", "evaluator_runtime_failure"
    if not isinstance(results, dict) or not isinstance(report, dict):
        return "fail", "evaluator_runtime_failure"
    if results.get("error", 0) or results.get("incomplete", 0):
        return "fail", "evaluator_runtime_failure"
    if report.get("resolved") is True and candidate["instance_id"] in results.get("success_ids", []):
        return "pass", None
    if report.get("resolved") is False:
        return "fail", "gold_patch_evaluation_failure"
    return "fail", "evaluator_runtime_failure"


def _stage_gold(
    args: argparse.Namespace,
    candidate: dict[str, Any],
    stage_root: Path,
    timeout: int,
    validation_root: Path,
) -> tuple[str, str | None, dict[str, Any]]:
    dataset = validation_root / "output" / "validated_instances.jsonl"
    if not _jsonl_has_instance(dataset, candidate["instance_id"]):
        raise ExperimentConfigurationError("validated candidate input is missing")
    output = stage_root / "output"
    output.mkdir()
    command = [
        str(args.evaluator_python),
        "-m",
        "evaluation.evaluation",
        "--dataset",
        str(dataset),
        "--platform",
        "linux",
        "--patch_dir",
        "gold",
        "--output_dir",
        str(output),
        "--workers",
        "1",
        "--overwrite",
        "1",
    ]
    result = _run_evaluator(
        command,
        args=args,
        candidate=candidate,
        timeout=timeout,
    )
    log = stage_root / "command.log"
    _write_command_log(log, result)
    outcome, classification = _gold_classification(candidate, output, result)
    report_path = output / candidate["instance_id"] / "report.json"
    results_path = output / "results.json"
    return outcome, classification, {
        "result": result,
        "report_sha256": sha256_file(report_path) if report_path.is_file() else None,
        "results_sha256": sha256_file(results_path) if results_path.is_file() else None,
    }


def _sanitize_result(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    for key in ("manifest", "pull", "inspect", "extraction", "stability", "result"):
        if isinstance(result.get(key), dict):
            sanitized = {
                field: result[key].get(field)
                for field in ("exit_code", "timed_out", "wall_seconds")
            }
            for field in ("orphan_cleanup", "fresh_runtime_semantics"):
                if field in result[key]:
                    sanitized[field] = result[key][field]
            result[key] = sanitized
    return result


def _execute_stage(
    args: argparse.Namespace,
    receipt: dict[str, Any],
    candidate: dict[str, Any],
    stage: str,
    stage_root: Path,
) -> dict[str, Any]:
    timeout = receipt["protocol"]["timeout_seconds_per_stage"]
    if stage == "q1_environment":
        outcome, classification, details = _stage_q1(args, candidate, stage_root, timeout)
    elif stage == "q2_repeated_validation":
        outcome, classification, details = _stage_q2(args, candidate, stage_root, timeout)
    else:
        validation_root = args.raw_root / f"slot-{candidate['slot']:02d}" / "q2_repeated_validation"
        outcome, classification, details = _stage_gold(
            args, candidate, stage_root, timeout, validation_root
        )
    stage_receipt = {
        "schema_name": "engineering-scope-guard.evaluator-stable-stage-receipt",
        "schema_version": 2,
        "slot": candidate["slot"],
        "stage": stage,
        "outcome": outcome,
        "classification": classification,
        "details": _sanitize_result(details),
        "artifact_sha256": {
            path.relative_to(stage_root).as_posix(): sha256_file(path)
            for path in sorted(stage_root.rglob("*"))
            if path.is_file() and path.name != "stage-receipt.json"
        },
    }
    stage_receipt["stage_receipt_sha256"] = sha256_value(stage_receipt)
    _private_write_json(stage_root / "stage-receipt.json", stage_receipt)
    _harden_private_tree(stage_root)
    return stage_receipt


def _verify_stage_receipt(stage_root: Path, stage_receipt: dict[str, Any]) -> None:
    expected = stage_receipt.get("stage_receipt_sha256")
    unsealed = dict(stage_receipt)
    unsealed.pop("stage_receipt_sha256", None)
    if expected != sha256_value(unsealed):
        raise ExperimentConfigurationError("private stage receipt hash drifted")
    actual_artifacts = {
        path.relative_to(stage_root).as_posix(): sha256_file(path)
        for path in sorted(stage_root.rglob("*"))
        if path.is_file() and path.name != "stage-receipt.json"
    }
    if actual_artifacts != stage_receipt.get("artifact_sha256"):
        raise ExperimentConfigurationError("private stage artifact hash drifted")


def _verify_completed_stages(args: argparse.Namespace, receipt: dict[str, Any]) -> None:
    for candidate in receipt["candidates"]:
        for recorded in candidate["stages"]:
            stage = recorded["stage"]
            stage_root = args.raw_root / f"slot-{candidate['slot']:02d}" / stage
            stage_receipt_path = stage_root / "stage-receipt.json"
            if not stage_receipt_path.is_file():
                raise ExperimentConfigurationError("recorded qualification stage is missing")
            stage_receipt = read_json(stage_receipt_path)
            _verify_stage_receipt(stage_root, stage_receipt)
            evidence = recorded["evidence"]
            if (
                evidence.get("stage_receipt_sha256")
                != stage_receipt.get("stage_receipt_sha256")
                or evidence.get("artifact_set_sha256")
                != sha256_value(stage_receipt.get("artifact_sha256", {}))
            ):
                raise ExperimentConfigurationError(
                    "recorded qualification stage evidence drifted"
                )


def _reconcile_interrupted_stage(
    candidate: dict[str, Any], stage: str, stage_root: Path
) -> dict[str, Any]:
    start_path = stage_root / "stage-start.json"
    if not start_path.is_file():
        raise ExperimentConfigurationError(
            "interrupted qualification stage is missing its start receipt"
        )
    start = read_json(start_path)
    expected_identity = sha256_value(
        {
            "instance_id": candidate["instance_id"],
            "repo": candidate["repo"],
            "language": candidate["language"],
        }
    )
    image = candidate.get("resolved_image") or candidate["docker_image"]
    if (
        start.get("slot") != candidate["slot"]
        or start.get("stage") != stage
        or start.get("candidate_identity_sha256") != expected_identity
        or start.get("matching_container_image") != image
    ):
        raise ExperimentConfigurationError("interrupted qualification stage identity drifted")
    before_value = start.get("pre_stage_matching_container_ids")
    if (
        not isinstance(before_value, list)
        or any(not isinstance(value, str) or not value for value in before_value)
        or len(before_value) != len(set(before_value))
    ):
        raise ExperimentConfigurationError(
            "interrupted qualification stage has an invalid container snapshot"
        )
    before = set(before_value)
    current = _container_ids(image)
    newly_observed = sorted(current - before)
    if newly_observed:
        raise ExperimentConfigurationError(
            "interrupted qualification stage has new matching containers; "
            "automatic cleanup is not attributable and is forbidden"
        )
    stage_receipt = {
        "schema_name": "engineering-scope-guard.evaluator-stable-stage-receipt",
        "schema_version": 2,
        "slot": candidate["slot"],
        "stage": stage,
        "outcome": "fail",
        "classification": "evaluator_runtime_failure",
        "details": {
            "interrupted_stage_reconciled_without_rerun": True,
            "preexisting_matching_container_count": len(before),
            "new_matching_container_count": 0,
            "automatic_container_cleanup_permitted": False,
            "preexisting_matching_containers_preserved": before <= current,
        },
        "artifact_sha256": {
            path.relative_to(stage_root).as_posix(): sha256_file(path)
            for path in sorted(stage_root.rglob("*"))
            if path.is_file() and path.name != "stage-receipt.json"
        },
    }
    stage_receipt["stage_receipt_sha256"] = sha256_value(stage_receipt)
    _private_write_json(stage_root / "stage-receipt.json", stage_receipt)
    _harden_private_tree(stage_root)
    return stage_receipt


def execute_next(args: argparse.Namespace) -> dict[str, Any]:
    with _qualification_lock(args.receipt):
        receipt = read_json(args.receipt)
        validate_receipt(receipt)
        _revalidate_sources(args, receipt)
        _verify_completed_stages(args, receipt)
        pending = next_qualification_stage(receipt)
        if pending is None:
            return public_summary(receipt)
        candidate, stage = pending
        require_disk_safety(args.root / ".local", filesystem_path=args.raw_root)
        stage_root = args.raw_root / f"slot-{candidate['slot']:02d}" / stage
        existing = stage_root / "stage-receipt.json"
        if existing.is_file():
            stage_receipt = read_json(existing)
        elif stage_root.exists():
            stage_receipt = _reconcile_interrupted_stage(candidate, stage, stage_root)
        else:
            image = candidate.get("resolved_image") or candidate["docker_image"]
            pre_stage_containers = sorted(_container_ids(image))
            _private_mkdir(stage_root)
            _private_write_json(
                stage_root / "stage-start.json",
                {
                    "slot": candidate["slot"],
                    "stage": stage,
                    "candidate_identity_sha256": sha256_value(
                        {
                            "instance_id": candidate["instance_id"],
                            "repo": candidate["repo"],
                            "language": candidate["language"],
                        }
                    ),
                    "matching_container_image": image,
                    "pre_stage_matching_container_ids": pre_stage_containers,
                },
            )
            stage_receipt = _execute_stage(args, receipt, candidate, stage, stage_root)
        if stage_receipt.get("slot") != candidate["slot"] or stage_receipt.get("stage") != stage:
            raise ExperimentConfigurationError("private stage receipt identity drifted")
        _verify_stage_receipt(stage_root, stage_receipt)
        expected_sha = stage_receipt["stage_receipt_sha256"]
        image_identity = stage_receipt.get("details", {}).get("image_identity", {})
        evidence = {
            "stage_receipt_sha256": expected_sha,
            "artifact_set_sha256": sha256_value(stage_receipt.get("artifact_sha256", {})),
            "wall_seconds": stage_receipt.get("details", {}).get("result", {}).get("wall_seconds")
            or stage_receipt.get("details", {}).get("pull", {}).get("wall_seconds"),
        }
        if stage == "q1_environment" and stage_receipt["outcome"] == "pass":
            evidence["resolved_image_ref"] = image_identity.get("resolved_image_ref")
        record_stage(
            receipt,
            slot=candidate["slot"],
            stage=stage,
            outcome=stage_receipt["outcome"],
            classification=stage_receipt["classification"],
            evidence=evidence,
        )
        _private_write_json(args.receipt, receipt)
        return public_summary(receipt)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "command",
        choices=(
            "initialize",
            "execute-next",
            "run-until-terminal",
            "status",
            "export-public",
        ),
    )
    result.add_argument("--root", type=Path, default=Path("."))
    result.add_argument("--reserve", type=Path, required=True)
    result.add_argument("--receipt", type=Path, required=True)
    result.add_argument("--evaluator-root", type=Path, required=True)
    result.add_argument("--dataset-root", type=Path, required=True)
    result.add_argument("--evaluator-python", type=Path, required=True)
    result.add_argument("--model-catalog", type=Path, required=True)
    result.add_argument("--codex-binary", type=Path, required=True)
    result.add_argument("--raw-root", type=Path, required=True)
    result.add_argument("--public-output", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    args.root = args.root.resolve()
    for field in (
        "reserve",
        "receipt",
        "evaluator_root",
        "dataset_root",
        "evaluator_python",
        "model_catalog",
        "codex_binary",
        "raw_root",
    ):
        value = getattr(args, field)
        if not value.is_absolute():
            setattr(args, field, args.root / value)
    for field in ("reserve", "receipt", "evaluator_root", "dataset_root", "raw_root"):
        setattr(
            args,
            field,
            _private_path(
                args.root,
                getattr(args, field),
                field,
                directory=field in {"evaluator_root", "dataset_root", "raw_root"},
            ),
        )
    if args.receipt == args.raw_root or args.receipt.is_relative_to(args.raw_root):
        print("evaluator_stable_qualification: receipt and raw root must be distinct", file=sys.stderr)
        return 2
    try:
        if args.command == "initialize":
            with _qualification_lock(args.receipt):
                summary = initialize(args)
        elif args.command == "execute-next":
            summary = execute_next(args)
        elif args.command == "run-until-terminal":
            while True:
                summary = execute_next(args)
                print(json.dumps(summary, sort_keys=True), flush=True)
                if summary["status"] != "in_progress":
                    return 0
        else:
            receipt = read_json(args.receipt)
            summary = public_summary(receipt)
            if args.command == "export-public":
                if args.public_output is None:
                    raise ExperimentConfigurationError("--public-output is required")
                output = args.public_output
                if not output.is_absolute():
                    output = args.root / output
                if output.resolve(strict=False).is_relative_to(args.raw_root.resolve(strict=False)):
                    raise ExperimentConfigurationError("public output cannot be written below raw task material")
                if output.resolve(strict=False) == args.receipt.resolve(strict=False):
                    raise ExperimentConfigurationError("public output cannot overwrite the private receipt")
                atomic_write_json(output, summary)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (ExperimentConfigurationError, OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"evaluator_stable_qualification: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
