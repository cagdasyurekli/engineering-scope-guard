#!/usr/bin/env python3
"""Run and audit fixed-environment SWE-bench-Live gold qualification receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "engineering-scope-guard.pilot-host-qualification"
DATASET = "SWE-bench-Live/MultiLang"
DATASET_REVISION = "62dc0745c40f067fc366ae3eb1a26136e5928f85"
EVALUATOR_REVISION = "bc09878a5d192d0804dbd647dc6e650372fcb0ac"
REPOLAUNCH_REVISION = "c4b623d930f3728e5338664bb634021b98492cbf"
PLATFORM = "linux/amd64"
WORKERS = 1
EXPECTED_CPUS = 6
EXPECTED_MEMORY_MIB = 16_384
REPETITIONS = 3
REPLACEMENT_ALLOWANCE = 8
PARTITION_SEED = "engineering-scope-guard-pilot-v1-2026-08-27"
KNOWLEDGE_CUTOFF = datetime(2026, 2, 16, 23, 59, 59, tzinfo=timezone.utc)
ALLOWED_CONCLUSIONS = {
    "A valid 12-task Pilot pool exists on the fixed environment after applying only pre-authorized infrastructure replacements, and resource burden is operationally feasible.",
    "The task source remains usable, but the frozen pool cannot be qualified on this fixed environment within the authorized replacement/resource constraints.",
    "The official evaluator cannot be operated credibly enough on this environment to support the intended experiment.",
}
EXPECTED_DATASET_SHA256 = {
    "c-00000-of-00001.parquet": "30c0b8cb9e7140e05a4e539f20be0c325be597cbba4bf35e232355987ddddd0c",
    "cpp-00000-of-00001.parquet": "8448db887817b63e4c0c284ca99de1ccda15023f48e5b2234a4084466e0768ae",
    "cs-00000-of-00001.parquet": "29ffe16d0b2cd802e753262b8b0d7fe3f2bb1b489396da238146e79f37937c1f",
    "go-00000-of-00001.parquet": "76d2b5dff0f3fac8303d30fa85495539e487d25974ad7c21cd21a545cb4756e2",
    "java-00000-of-00001.parquet": "00387685808c71d21ada175335304b1c118859453afadd58ea21a00b0d568ee8",
    "js-00000-of-00001.parquet": "bc6ec49ffaf9db97840d55eba6954fae8f5fb0fb071cf49e187f36ffadd55a7a",
    "rust-00000-of-00001.parquet": "02ac78e2c51a84eb174ac393bb07b77478f1f96cf260af18835a711dd8074ebc",
    "ts-00000-of-00001.parquet": "7e23783e27230c9cfab1035690035c25523043d6af635bc78da3fd2010c32714",
}


class QualificationError(RuntimeError):
    """Raised when qualification would violate a frozen boundary."""


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualificationError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _command(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def _checked_output(args: list[str], cwd: Path | None = None) -> str:
    completed = _command(args, cwd)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise QualificationError(f"command failed ({completed.returncode}): {detail}")
    return completed.stdout.strip()


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rank(instance_id: str) -> str:
    material = f"{PARTITION_SEED}\0{DATASET_REVISION}\0{instance_id}".encode()
    return hashlib.sha256(material).hexdigest()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _created_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _eligible_replacement_metadata(
    record: dict[str, Any],
    development_ids: set[str],
) -> bool:
    required_lists = ("FAIL_TO_PASS", "PASS_TO_PASS", "rebuild_cmds", "test_cmds")
    return (
        isinstance(record.get("instance_id"), str)
        and bool(record["instance_id"])
        and isinstance(record.get("repo"), str)
        and bool(record["repo"])
        and isinstance(record.get("docker_image"), str)
        and bool(record["docker_image"])
        and record["instance_id"] not in development_ids
        and (created := _created_at(record.get("created_at"))) is not None
        and created > KNOWLEDGE_CUTOFF
        and all(
            isinstance(record.get(field), list)
            and bool(record[field])
            and all(isinstance(item, str) and item for item in record[field])
            for field in required_lists
        )
    )


def _docker_environment() -> dict[str, Any]:
    info = json.loads(_checked_output(["docker", "info", "--format", "{{json .}}"]))
    settings_path = (
        Path.home()
        / "Library/Group Containers/group.com.docker/settings-store.json"
    )
    settings = _read(settings_path)
    configured_cpus = settings.get("Cpus")
    configured_memory_mib = settings.get("MemoryMiB")
    if (
        configured_cpus != EXPECTED_CPUS
        or configured_memory_mib != EXPECTED_MEMORY_MIB
        or info["NCPU"] != EXPECTED_CPUS
    ):
        raise QualificationError(
            "Docker allocation changed: "
            f"configured {configured_cpus} CPUs/{configured_memory_mib} MiB; "
            f"engine reports {info['NCPU']} CPUs, expected "
            f"{EXPECTED_CPUS} CPUs/{EXPECTED_MEMORY_MIB} MiB"
        )
    if info["Architecture"] != "aarch64" or info["OSType"] != "linux":
        raise QualificationError("Docker engine architecture changed")
    return {
        "engine_architecture": "linux/arm64",
        "engine_version": info["ServerVersion"],
        "configured_cpus": configured_cpus,
        "configured_memory_mib": configured_memory_mib,
        "configured_swap_mib": settings.get("SwapMiB"),
        "engine_reported_cpus": info["NCPU"],
        "engine_usable_memory_bytes": int(info["MemTotal"]),
        "requested_platform": PLATFORM,
    }


def _source_environment(evaluator_root: Path) -> dict[str, Any]:
    evaluator = _checked_output(["git", "rev-parse", "HEAD"], evaluator_root)
    repolaunch = _checked_output(
        ["git", "-C", str(evaluator_root / "launch"), "rev-parse", "HEAD"]
    )
    if evaluator != EVALUATOR_REVISION or repolaunch != REPOLAUNCH_REVISION:
        raise QualificationError("pinned evaluator or RepoLaunch revision changed")
    return {
        "dataset": DATASET,
        "dataset_revision": DATASET_REVISION,
        "evaluator_revision": evaluator,
        "repolaunch_revision": repolaunch,
    }


def initialize(
    output: Path, root: Path, evaluator_root: Path, dataset_root: Path
) -> dict[str, Any]:
    if output.exists():
        raise QualificationError(f"refusing to overwrite existing receipt: {output}")
    partition = _read(root / "experiment/external_task_partition.json")
    if partition["source"]["revision"] != DATASET_REVISION:
        raise QualificationError("partition dataset revision changed")
    tasks = []
    for task in partition["partition"]["pilot_tasks"]:
        tasks.append(
            {
                "instance_id": task["instance_id"],
                "language": task["language"],
                "repo": task["repo"],
                "official_image": task["docker_image"],
                "role": "frozen-pilot",
                "replaces": None,
                "runs": [],
                "host_validity": "pending",
            }
        )
    if len(tasks) != 12:
        raise QualificationError("frozen partition no longer contains 12 tasks")
    if not dataset_root.is_dir():
        raise QualificationError(f"pinned dataset snapshot is missing: {dataset_root}")
    value = {
        "schema_name": SCHEMA,
        "schema_version": 1,
        "status": "in-progress",
        "as_of": time.strftime("%Y-%m-%d"),
        "pilot_authorized": False,
        "policy_experiment": False,
        "codex_runs": 0,
        "policy_arm_runs": 0,
        "fixed_environment": _docker_environment(),
        "source": _source_environment(evaluator_root),
        "procedure": {
            "workers": WORKERS,
            "gold_repetitions_per_task": REPETITIONS,
            "official_images_modified_or_rebuilt": False,
            "dataset_snapshot_path": str(dataset_root),
            "evaluator_checkout_path": str(evaluator_root),
        },
        "validity_rule": {
            "frozen_before_first_run": True,
            "three_successes": "host-valid",
            "mixed_results": "unstable/invalid-on-host",
            "repeated_resource_failure": "invalid-on-fixed-environment",
            "evaluator_image_or_infrastructure_failure": "classify-separately",
        },
        "replacement_rule": {
            "allowance": REPLACEMENT_ALLOWANCE,
            "consumed": 0,
            "rule": "next hash-ranked eligible task in the same frozen language stratum, excluding Pilot repositories",
            "selection_uses_task_bodies_or_policy_performance": False,
            "audit_trail": [],
        },
        "tasks": tasks,
        "deviations": [],
        "bounded_conclusion": None,
    }
    _write(output, value)
    return value


def _leftover_container_states(instance_id: str) -> list[dict[str, Any]]:
    prefix = f"git-launch-{instance_id.replace('/', '_')}"
    listing = _command(
        ["docker", "ps", "-a", "--filter", f"name={prefix}", "--format", "{{.ID}}"]
    )
    if listing.returncode != 0:
        return [{"inspection_error": listing.stderr.strip()}]
    states = []
    for container_id in listing.stdout.split():
        inspected = _command(
            ["docker", "inspect", "--format", "{{json .State}}", container_id]
        )
        if inspected.returncode == 0:
            states.append(json.loads(inspected.stdout))
        else:
            states.append({"container_id": container_id, "inspection_error": inspected.stderr.strip()})
    return states


def _image_receipt(image: str) -> dict[str, Any]:
    inspected = _command(["docker", "image", "inspect", image])
    if inspected.returncode != 0:
        return {"available_after_run": False, "inspection_error": inspected.stderr.strip()}
    item = json.loads(inspected.stdout)[0]
    return {
        "available_after_run": True,
        "id": item.get("Id"),
        "repo_digests": item.get("RepoDigests", []),
        "size_bytes": item.get("Size"),
        "declared_os": item.get("Os"),
        "declared_architecture": item.get("Architecture"),
    }


def classify(
    exit_code: int | None,
    timed_out: bool,
    report: dict[str, Any] | None,
    results: dict[str, Any] | None,
    output: str,
    container_states: list[dict[str, Any]],
) -> tuple[str, str, bool, list[str]]:
    lowered = output.lower()
    oom = any(state.get("OOMKilled") is True for state in container_states) or any(
        marker in lowered
        for marker in ("oomkilled", "out of memory", "cannot allocate memory", "killed process")
    )
    warnings = [
        line.strip()
        for line in output.splitlines()
        if re.search(r"platform.*does not match|exec format|rosetta|qemu|emulat", line, re.I)
    ]
    if timed_out:
        return "FAIL", "timeout", oom, warnings
    if oom:
        return "FAIL", "resource-oom", True, warnings
    if exit_code == 0 and report and report.get("resolved") is True:
        success_ids = results.get("success_ids", []) if results else []
        if report.get("instance_id") in success_ids:
            return "PASS", "official-gold-success", False, warnings
    if exit_code not in (0, None):
        return "FAIL", "evaluator-process-failure", False, warnings
    if results and (results.get("error", 0) or results.get("incomplete", 0)):
        return "FAIL", "evaluator-runtime-failure", False, warnings
    if report and report.get("resolved") is False:
        return "FAIL", "official-gold-test-failure", False, warnings
    return "FAIL", "evaluator-runtime-failure", False, warnings


def run_next(
    receipt_path: Path,
    evaluator_root: Path,
    dataset_root: Path,
    python: Path,
    raw_root: Path,
    instance_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    receipt = _read(receipt_path)
    if receipt.get("status") != "in-progress":
        raise QualificationError("qualification receipt is not in progress")
    if _docker_environment() != receipt["fixed_environment"]:
        raise QualificationError("fixed Docker environment drifted")
    if _source_environment(evaluator_root) != receipt["source"]:
        raise QualificationError("fixed evaluator environment drifted")
    task = next((item for item in receipt["tasks"] if item["instance_id"] == instance_id), None)
    if task is None:
        raise QualificationError(f"task is not authorized in this receipt: {instance_id}")
    if len(task["runs"]) >= REPETITIONS:
        raise QualificationError(f"task already has {REPETITIONS} runs: {instance_id}")
    repetition = len(task["runs"]) + 1
    raw_root = raw_root.resolve()
    run_dir = raw_root / instance_id / f"run-{repetition}"
    run_dir.mkdir(parents=True, exist_ok=False)
    command = [
        str(python), "-m", "evaluation.evaluation",
        "--dataset", str(dataset_root), "--split", task["language"],
        "--platform", "linux", "--patch_dir", "gold",
        "--output_dir", str(run_dir), "--workers", str(WORKERS),
        "--overwrite", "1", "--instance_ids", instance_id,
    ]
    environment = os.environ.copy()
    environment["HF_DATASETS_CACHE"] = str(evaluator_root / "hf-cache")
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=evaluator_root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        exit_code: int | None = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    wall_seconds = round(time.monotonic() - started, 3)
    command_log = run_dir / "evaluator-command.log"
    command_log.write_text(stdout + "\n--- STDERR ---\n" + stderr, encoding="utf-8")
    report_path = run_dir / instance_id / "report.json"
    results_path = run_dir / "results.json"
    report = _read(report_path) if report_path.is_file() else None
    results = _read(results_path) if results_path.is_file() else None
    container_states = _leftover_container_states(instance_id)
    outcome, classification, oom, warnings = classify(
        exit_code, timed_out, report, results, stdout + "\n" + stderr, container_states
    )
    run = {
        "repetition": repetition,
        "command": command,
        "requested_platform": PLATFORM,
        "workers": WORKERS,
        "exit_code": exit_code,
        "outcome": outcome,
        "classification": classification,
        "resolved": report.get("resolved") if report else None,
        "wall_seconds": wall_seconds,
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "oom_or_resource_failure": oom,
        "architecture_or_emulation_warnings": warnings,
        "container_states_after_run": container_states,
        "docker_limits": receipt["fixed_environment"],
        "official_image": _image_receipt(task["official_image"]),
        "raw_output_dir": str(run_dir),
        "command_log_sha256": _sha256(command_log),
        "report": report,
        "results": results,
    }
    task["runs"].append(run)
    if len(task["runs"]) == REPETITIONS:
        passes = sum(item["outcome"] == "PASS" for item in task["runs"])
        classes = {item["classification"] for item in task["runs"]}
        if passes == REPETITIONS:
            task["host_validity"] = "host-valid"
        elif 0 < passes < REPETITIONS:
            task["host_validity"] = "unstable/invalid-on-host"
        elif classes == {"resource-oom"}:
            task["host_validity"] = "invalid-on-fixed-environment"
        else:
            task["host_validity"] = "invalid-classify-separately"
    _write(receipt_path, receipt)
    return run


def recover_relative_output(
    receipt_path: Path,
    evaluator_root: Path,
    instance_id: str,
    repetition: int,
) -> dict[str, Any]:
    """Recover a retained run whose relative output path was resolved by the evaluator."""

    receipt = _read(receipt_path)
    task = next((item for item in receipt["tasks"] if item["instance_id"] == instance_id), None)
    if task is None or not 1 <= repetition <= len(task["runs"]):
        raise QualificationError("run to recover is not present")
    run = task["runs"][repetition - 1]
    if run["report"] is not None or run["results"] is not None:
        raise QualificationError("run already contains evaluator result files")
    actual_dir = evaluator_root / run["raw_output_dir"]
    report_path = actual_dir / instance_id / "report.json"
    results_path = actual_dir / "results.json"
    if not report_path.is_file() or not results_path.is_file():
        raise QualificationError("relative evaluator outputs are not recoverable")
    report = _read(report_path)
    results = _read(results_path)
    prior = {
        "outcome": run["outcome"],
        "classification": run["classification"],
        "raw_output_dir": run["raw_output_dir"],
    }
    outcome, classification, oom, warnings = classify(
        run["exit_code"],
        run["timed_out"],
        report,
        results,
        "",
        run["container_states_after_run"],
    )
    run.update(
        {
            "outcome": outcome,
            "classification": classification,
            "resolved": report.get("resolved"),
            "oom_or_resource_failure": oom,
            "architecture_or_emulation_warnings": warnings,
            "raw_output_dir": str(actual_dir.resolve()),
            "report": report,
            "results": results,
            "report_sha256": _sha256(report_path),
            "results_sha256": _sha256(results_path),
        }
    )
    receipt["deviations"].append(
        {
            "class": "receipt-relative-output-path",
            "instance_id": instance_id,
            "repetition": repetition,
            "effect_on_official_evaluation": "none; official evaluation completed before receipt lookup",
            "retained_prior_wrapper_record": prior,
            "correction": "resolved evaluator output from evaluator working directory and switched future runs to absolute paths",
        }
    )
    _write(receipt_path, receipt)
    return run


def select_replacements(
    receipt_path: Path,
    root: Path,
    dataset_root: Path,
) -> list[dict[str, Any]]:
    """Materialize only required metadata-selected replacement tasks."""

    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:  # pragma: no cover - exercised in evaluator environment
        raise QualificationError("replacement selection requires evaluator pyarrow") from exc
    receipt = _read(receipt_path)
    if receipt["replacement_rule"]["audit_trail"]:
        raise QualificationError("replacement selection is already materialized")
    frozen = [task for task in receipt["tasks"] if task["role"] == "frozen-pilot"]
    if any(len(task["runs"]) != REPETITIONS for task in frozen):
        raise QualificationError("all frozen tasks must finish before replacement selection")
    invalid = [task for task in frozen if task["host_validity"] != "host-valid"]
    remaining = (
        receipt["replacement_rule"]["allowance"]
        - receipt["replacement_rule"]["consumed"]
    )
    if len(invalid) > remaining:
        raise QualificationError("replacement allowance is exhausted")
    registry = _read(root / "experiment/development_tasks/registry.json")
    development_ids = {
        task["task_id"] for task in registry["tasks"] if isinstance(task, dict)
    }
    pilot_repositories = {task["repo"] for task in frozen}
    selected_repositories: set[str] = set()
    used_ids = {task["instance_id"] for task in receipt["tasks"]}
    columns = [
        "instance_id", "repo", "created_at", "docker_image",
        "FAIL_TO_PASS", "PASS_TO_PASS", "rebuild_cmds", "test_cmds",
    ]
    rows_by_language: dict[str, list[dict[str, Any]]] = {}
    for task in invalid:
        language = task["language"]
        if language not in rows_by_language:
            paths = sorted((dataset_root / "data").glob(f"{language}-*.parquet"))
            if len(paths) != 1:
                raise QualificationError(f"expected one pinned parquet split for {language}")
            rows_by_language[language] = parquet.read_table(
                paths[0], columns=columns
            ).to_pylist()
        candidates = sorted(
            (
                row for row in rows_by_language[language]
                if _eligible_replacement_metadata(row, development_ids)
                and row["instance_id"] not in used_ids
                and row["repo"] not in pilot_repositories
                and row["repo"] not in selected_repositories
            ),
            key=lambda row: (_rank(row["instance_id"]), row["instance_id"]),
        )
        if not candidates:
            raise QualificationError(f"no eligible same-language replacement for {task['instance_id']}")
        chosen = candidates[0]
        replacement = {
            "instance_id": chosen["instance_id"],
            "language": language,
            "repo": chosen["repo"],
            "official_image": chosen["docker_image"],
            "role": "infrastructure-replacement",
            "replaces": task["instance_id"],
            "runs": [],
            "host_validity": "pending",
        }
        receipt["tasks"].append(replacement)
        receipt["replacement_rule"]["audit_trail"].append(
            {
                "invalid_task": task["instance_id"],
                "invalid_host_validity": task["host_validity"],
                "replacement_task": chosen["instance_id"],
                "language_stratum": language,
                "replacement_repo": chosen["repo"],
                "rank_commitment": _rank(chosen["instance_id"]),
                "selection_fields": columns + ["language"],
                "task_body_or_policy_performance_inspected": False,
            }
        )
        receipt["replacement_rule"]["consumed"] += 1
        used_ids.add(chosen["instance_id"])
        selected_repositories.add(chosen["repo"])
    _write(receipt_path, receipt)
    return receipt["replacement_rule"]["audit_trail"]


def _distribution(values: list[float]) -> dict[str, float | int]:
    """Return a compact descriptive distribution without inferential claims."""

    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": round(ordered[0], 3),
        "median": round(statistics.median(ordered), 3),
        "max": round(ordered[-1], 3),
        "sum": round(sum(ordered), 3),
    }


def _docker_storage_snapshot() -> dict[str, Any]:
    summary = _checked_output(["docker", "system", "df", "--format", "{{json .}}"])
    image_listing = _checked_output(["docker", "image", "ls", "--format", "{{json .}}"])
    return {
        "system_df": [json.loads(line) for line in summary.splitlines() if line],
        "images": [json.loads(line) for line in image_listing.splitlines() if line],
        "measurement_note": (
            "Docker-reported point-in-time local storage; displayed image sizes share "
            "layers and therefore must not be summed as unique disk usage."
        ),
    }


def _dataset_fingerprint(dataset_root: Path) -> dict[str, str | None]:
    return {
        path.name: _sha256(path)
        for path in sorted((dataset_root / "data").glob("*.parquet"))
    }


def _effective_reserve_receipt(
    receipt: dict[str, Any], dataset_root: Path, root: Path
) -> dict[str, Any]:
    """Recommit the opaque reserve after replacement repositories join Pilot."""

    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:  # pragma: no cover - evaluator environment supplies it
        raise QualificationError("effective reserve calculation requires evaluator pyarrow") from exc
    registry = _read(root / "experiment/development_tasks/registry.json")
    development_ids = {
        task["task_id"] for task in registry["tasks"] if isinstance(task, dict)
    }
    columns = [
        "instance_id", "repo", "created_at", "docker_image",
        "FAIL_TO_PASS", "PASS_TO_PASS", "rebuild_cmds", "test_cmds",
    ]
    eligible: list[dict[str, Any]] = []
    for path in sorted((dataset_root / "data").glob("*.parquet")):
        eligible.extend(
            row for row in parquet.read_table(path, columns=columns).to_pylist()
            if _eligible_replacement_metadata(row, development_ids)
        )
    frozen = [task for task in receipt["tasks"] if task["role"] == "frozen-pilot"]
    replacements = [
        task for task in receipt["tasks"] if task["role"] == "infrastructure-replacement"
    ]
    original_pilot_ids = {task["instance_id"] for task in frozen}
    original_pilot_repos = {task["repo"] for task in frozen}
    replacement_repos = {task["repo"] for task in replacements}
    original_reserve = [
        row for row in eligible
        if row["instance_id"] not in original_pilot_ids
        and row["repo"] not in original_pilot_repos
    ]
    effective_reserve = [
        row for row in original_reserve if row["repo"] not in replacement_repos
    ]
    ranked_ids = [
        row["instance_id"] for row in sorted(
            effective_reserve,
            key=lambda row: (_rank(row["instance_id"]), row["instance_id"]),
        )
    ]
    removed = [row for row in original_reserve if row["repo"] in replacement_repos]
    return {
        "original_confirmatory_reserve_count": len(original_reserve),
        "replacement_repositories_now_excluded": sorted(replacement_repos),
        "tasks_removed_by_replacement_repository_exclusion": len(removed),
        "effective_confirmatory_reserve_count": len(effective_reserve),
        "effective_confirmatory_reserve_repositories": len(
            {row["repo"] for row in effective_reserve}
        ),
        "effective_confirmatory_reserve_ids_sha256": _canonical_hash(ranked_ids),
        "reserve_ids_or_bodies_emitted": False,
        "pilot_and_effective_reserve_repositories_disjoint": True,
    }


def finalize(receipt_path: Path) -> dict[str, Any]:
    """Freeze descriptive evidence and the single authorized conclusion."""

    receipt = _read(receipt_path)
    if receipt.get("status") != "in-progress":
        raise QualificationError("qualification receipt is not in progress")
    if any(len(task["runs"]) != REPETITIONS for task in receipt["tasks"]):
        raise QualificationError("every evaluated task must have exactly three runs")

    frozen = [task for task in receipt["tasks"] if task["role"] == "frozen-pilot"]
    valid_frozen = [task for task in frozen if task["host_validity"] == "host-valid"]
    invalid_frozen = [task for task in frozen if task["host_validity"] != "host-valid"]
    replacements = [
        task for task in receipt["tasks"] if task["role"] == "infrastructure-replacement"
    ]
    valid_replacements = [
        task for task in replacements if task["host_validity"] == "host-valid"
    ]
    invalid_ids = {task["instance_id"] for task in invalid_frozen}
    if (
        len(valid_frozen) + len(valid_replacements) != 12
        or {task["replaces"] for task in valid_replacements} != invalid_ids
        or len(valid_replacements) != len(invalid_frozen)
    ):
        raise QualificationError("a valid replacement-linked 12-task pool does not exist")

    final_pool = valid_frozen + valid_replacements
    all_runs = [run for task in receipt["tasks"] for run in task["runs"]]
    final_runs = [run for task in final_pool for run in task["runs"]]
    task_medians = [
        statistics.median(run["wall_seconds"] for run in task["runs"])
        for task in final_pool
    ]
    one_evaluator_pass_seconds = sum(task_medians)
    planned_trajectories = 48
    trajectories_per_task = planned_trajectories // len(final_pool)
    evaluator_once = one_evaluator_pass_seconds * trajectories_per_task
    evaluator_twice = evaluator_once * 2

    classifications: dict[str, int] = {}
    for run in all_runs:
        classifications[run["classification"]] = (
            classifications.get(run["classification"], 0) + 1
        )
    observed_image_sizes = {
        task["instance_id"]: task["runs"][-1]["official_image"].get("size_bytes")
        for task in receipt["tasks"]
    }
    root = receipt_path.resolve().parents[1]
    dataset_root = Path(receipt["procedure"]["dataset_snapshot_path"])
    effective_reserve = _effective_reserve_receipt(receipt, dataset_root, root)
    resource_feasible = (
        not any(run["oom_or_resource_failure"] or run["timed_out"] for run in all_runs)
        and len(final_pool) == 12
    )
    receipt["summary"] = {
        "evaluated_tasks": len(receipt["tasks"]),
        "recorded_gold_attempts": len(all_runs),
        "pass_attempts": sum(run["outcome"] == "PASS" for run in all_runs),
        "fail_attempts": sum(run["outcome"] == "FAIL" for run in all_runs),
        "classifications": classifications,
        "frozen_host_valid": len(valid_frozen),
        "frozen_invalid": len(invalid_frozen),
        "replacement_host_valid": len(valid_replacements),
        "final_pool_size": len(final_pool),
        "final_pool_instance_ids": sorted(task["instance_id"] for task in final_pool),
        "all_attempt_wall_seconds": _distribution(
            [run["wall_seconds"] for run in all_runs]
        ),
        "final_pool_attempt_wall_seconds": _distribution(
            [run["wall_seconds"] for run in final_runs]
        ),
        "final_pool_task_median_wall_seconds": _distribution(task_medians),
        "resource_evidence": {
            "per_run_capacity_receipts": len(all_runs),
            "oom_or_resource_failures": sum(
                run["oom_or_resource_failure"] for run in all_runs
            ),
            "timeouts": sum(run["timed_out"] for run in all_runs),
            "architecture_or_emulation_warning_lines": sum(
                len(run["architecture_or_emulation_warnings"])
                for run in all_runs
            ),
            "point_sample_limitation": (
                "Capacity, OOM/timeout state, retained evaluator output, and selected "
                "interactive docker-stats point samples are evidence; no continuous "
                "resource telemetry or peak claim was introduced."
            ),
            "selected_interactive_point_samples": [
                {"instance_id": "GitoxideLabs__gitoxide-2476", "repetition": 3,
                 "cpu_percent": 208.41, "memory_usage": "5.298 GiB / 15.6 GiB"},
                {"instance_id": "MudBlazor__MudBlazor-12974", "repetition": 1,
                 "cpu_percent": 112.93, "memory_usage": "2.546 GiB / 15.6 GiB"},
                {"instance_id": "dragonflydb__dragonfly-7493", "repetition": 1,
                 "cpu_percent": None, "memory_usage": "selected points rose from 188 MiB through 1.000, 1.477, and 2.565 GiB before falling to 674 MiB",
                 "block_io": "19 GB written at the observed late point"},
                {"instance_id": "floci-io__floci-1908", "repetition": 1,
                 "cpu_percent": 154.0, "memory_usage": "5.936 GiB / 15.6 GiB"},
            ],
        },
        "storage": {
            "image_inspect_size_bytes_by_task": observed_image_sizes,
            "docker_snapshot": _docker_storage_snapshot(),
        },
        "planned_pilot_burden": {
            "planned_subject_trajectories": planned_trajectories,
            "trajectories_per_task": trajectories_per_task,
            "measured_final_pool_task_median_sum_seconds": round(
                one_evaluator_pass_seconds, 3
            ),
            "aggregate_evaluator_once_for_48_trajectories_seconds": round(
                evaluator_once, 3
            ),
            "aggregate_evaluator_twice_for_48_trajectories_seconds": round(
                evaluator_twice, 3
            ),
            "predeclared_subject_timeout_ceiling_seconds": 48 * 2 * 900,
            "combined_procedural_ceiling_once_seconds": round(
                48 * 2 * 900 + evaluator_once, 3
            ),
            "combined_procedural_ceiling_twice_seconds": round(
                48 * 2 * 900 + evaluator_twice, 3
            ),
            "scope": (
                "Evaluator-only arithmetic from gold medians. It excludes Codex/subject "
                "runtime, provider billing, image pulls, human review, and policy effects; "
                "gold duration is not a prediction of subject duration."
            ),
        },
        "operational_feasibility_basis": (
            "All 48 qualification attempts completed sequentially on the frozen "
            "allocation with zero OOMs/timeouts; all required images fit in the "
            "current Docker store; the projected evaluator-only work is schedulable "
            "sequentially. This does not establish subject/provider feasibility."
        ),
        "operational_feasibility_assessment": (
            "feasible-on-bounded-infrastructure-evidence"
            if resource_feasible else "not-feasible"
        ),
        "effective_confirmatory_reserve": effective_reserve,
    }
    receipt["source"]["dataset_snapshot_files_sha256"] = _dataset_fingerprint(
        dataset_root
    )
    if not resource_feasible:
        raise QualificationError("bounded resource-feasibility evidence did not pass")
    receipt["bounded_conclusion"] = next(
        item for item in ALLOWED_CONCLUSIONS if item.startswith("A valid 12-task")
    )
    receipt["status"] = "complete"
    receipt["completed_at"] = datetime.now(timezone.utc).isoformat()
    _write(receipt_path, receipt)
    return receipt["summary"]


def audit(receipt_path: Path, root: Path, require_complete: bool = False) -> dict[str, Any]:
    receipt = _read(receipt_path)
    partition = _read(root / "experiment/external_task_partition.json")
    expected_ids = {task["instance_id"] for task in partition["partition"]["pilot_tasks"]}
    frozen = [task for task in receipt["tasks"] if task["role"] == "frozen-pilot"]
    replacements = [
        task for task in receipt["tasks"] if task["role"] == "infrastructure-replacement"
    ]
    frozen_by_id = {task["instance_id"]: task for task in frozen}
    replacement_by_id = {task["instance_id"]: task for task in replacements}
    trail = receipt["replacement_rule"]["audit_trail"]
    valid_final_pool = [task for task in frozen if task["host_validity"] == "host-valid"] + [
        task for task in replacements if task["host_validity"] == "host-valid"
    ]
    run_counts = {task["instance_id"]: len(task["runs"]) for task in receipt["tasks"]}
    checks = {
        "schema": receipt.get("schema_name") == SCHEMA,
        "source_revision": receipt["source"]["dataset_revision"] == DATASET_REVISION,
        "evaluator_revision": receipt["source"]["evaluator_revision"] == EVALUATOR_REVISION,
        "repolaunch_revision": receipt["source"]["repolaunch_revision"] == REPOLAUNCH_REVISION,
        "fixed_resources": (
            receipt["fixed_environment"]["configured_cpus"] == EXPECTED_CPUS
            and receipt["fixed_environment"]["configured_memory_mib"] == EXPECTED_MEMORY_MIB
            and receipt["fixed_environment"]["requested_platform"] == PLATFORM
        ),
        "frozen_allocation": len(frozen) == 12 and {task["instance_id"] for task in frozen} == expected_ids,
        "strict_rule": receipt["validity_rule"].get("frozen_before_first_run") is True,
        "replacement_boundary": (
            receipt["replacement_rule"]["consumed"] <= receipt["replacement_rule"]["allowance"]
            and receipt["replacement_rule"]["selection_uses_task_bodies_or_policy_performance"] is False
        ),
        "replacement_audit_trail": (
            len(trail) == len(replacements) == receipt["replacement_rule"]["consumed"]
            and all(
                (replacement := replacement_by_id.get(item["replacement_task"])) is not None
                and (invalid := frozen_by_id.get(item["invalid_task"])) is not None
                and replacement["replaces"] == invalid["instance_id"]
                and replacement["language"] == invalid["language"] == item["language_stratum"]
                and replacement["repo"] == item["replacement_repo"]
                and replacement["repo"] not in {task["repo"] for task in frozen}
                and item["rank_commitment"] == _rank(replacement["instance_id"])
                and item["task_body_or_policy_performance_inspected"] is False
                for item in trail
            )
            and len({task["repo"] for task in replacements}) == len(replacements)
        ),
        "no_policy_or_subject_runs": (
            receipt.get("pilot_authorized") is False
            and receipt.get("policy_experiment") is False
            and receipt.get("codex_runs") == 0
            and receipt.get("policy_arm_runs") == 0
        ),
        "run_fields": all(
            {
                "exit_code", "outcome", "classification", "wall_seconds",
                "timed_out", "oom_or_resource_failure", "requested_platform",
                "architecture_or_emulation_warnings", "official_image",
            }.issubset(run)
            for task in receipt["tasks"] for run in task["runs"]
        ),
        "validity_consistent": all(
            task["host_validity"] == "pending"
            if len(task["runs"]) < REPETITIONS
            else (
                task["host_validity"] == "host-valid"
                if all(run["outcome"] == "PASS" for run in task["runs"])
                else task["host_validity"] != "host-valid"
            )
            for task in receipt["tasks"]
        ),
    }
    if require_complete:
        checks["all_tasks_have_three_runs"] = all(count == REPETITIONS for count in run_counts.values())
        checks["terminal_conclusion"] = receipt.get("bounded_conclusion") in ALLOWED_CONCLUSIONS
        checks["status_complete"] = receipt.get("status") == "complete"
        checks["dataset_snapshot_bytes"] = (
            receipt["source"].get("dataset_snapshot_files_sha256")
            == EXPECTED_DATASET_SHA256
        )
        checks["valid_final_pool"] = (
            len(valid_final_pool) == 12
            and len({task["repo"] for task in valid_final_pool}) == 12
            and all(len(task["runs"]) == REPETITIONS for task in valid_final_pool)
            and all(
                run["outcome"] == "PASS"
                for task in valid_final_pool for run in task["runs"]
            )
        )
        checks["replacement_links"] = (
            receipt.get("summary", {}).get("frozen_invalid")
            == receipt.get("summary", {}).get("replacement_host_valid")
            == receipt["replacement_rule"]["consumed"]
        )
        checks["effective_reserve_disjoint"] = (
            receipt.get("summary", {}).get("effective_confirmatory_reserve", {}).get(
                "pilot_and_effective_reserve_repositories_disjoint"
            ) is True
            and receipt["summary"]["effective_confirmatory_reserve"][
                "original_confirmatory_reserve_count"
            ] == 538
            and receipt["summary"]["effective_confirmatory_reserve"][
                "effective_confirmatory_reserve_count"
            ] == 499
        )
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise QualificationError("qualification checks failed: " + ", ".join(failed))
    return {
        "schema_name": SCHEMA + "-audit",
        "schema_version": 1,
        "status": "pass",
        "checks": checks,
        "recorded_runs": sum(run_counts.values()),
        "task_run_counts": run_counts,
        "host_valid_tasks": sum(task["host_validity"] == "host-valid" for task in receipt["tasks"]),
        "pilot_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    init = subparsers.add_parser("init")
    init.add_argument("--output", type=Path, required=True)
    init.add_argument("--root", type=Path, default=Path("."))
    init.add_argument("--evaluator-root", type=Path, required=True)
    init.add_argument("--dataset-root", type=Path, required=True)
    run = subparsers.add_parser("run-next")
    run.add_argument("--receipt", type=Path, required=True)
    run.add_argument("--evaluator-root", type=Path, required=True)
    run.add_argument("--dataset-root", type=Path, required=True)
    run.add_argument("--python", type=Path, required=True)
    run.add_argument("--raw-root", type=Path, required=True)
    run.add_argument("--instance-id", required=True)
    run.add_argument("--timeout-seconds", type=int, default=9_300)
    recover = subparsers.add_parser("recover-relative-output")
    recover.add_argument("--receipt", type=Path, required=True)
    recover.add_argument("--evaluator-root", type=Path, required=True)
    recover.add_argument("--instance-id", required=True)
    recover.add_argument("--repetition", type=int, required=True)
    select = subparsers.add_parser("select-replacements")
    select.add_argument("--receipt", type=Path, required=True)
    select.add_argument("--root", type=Path, default=Path("."))
    select.add_argument("--dataset-root", type=Path, required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--receipt", type=Path, required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--receipt", type=Path, required=True)
    audit_parser.add_argument("--root", type=Path, default=Path("."))
    audit_parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    if args.action == "init":
        result = initialize(args.output, args.root, args.evaluator_root, args.dataset_root)
        summary = {"status": result["status"], "tasks": len(result["tasks"])}
    elif args.action == "run-next":
        run_result = run_next(
            args.receipt, args.evaluator_root, args.dataset_root, args.python,
            args.raw_root, args.instance_id, args.timeout_seconds,
        )
        summary = {
            key: run_result[key]
            for key in (
                "repetition", "outcome", "classification", "exit_code",
                "wall_seconds", "timed_out", "oom_or_resource_failure",
                "architecture_or_emulation_warnings", "raw_output_dir",
            )
        }
    elif args.action == "recover-relative-output":
        recovered = recover_relative_output(
            args.receipt, args.evaluator_root, args.instance_id, args.repetition
        )
        summary = {
            key: recovered[key]
            for key in (
                "repetition", "outcome", "classification", "exit_code",
                "wall_seconds", "raw_output_dir",
            )
        }
    elif args.action == "select-replacements":
        summary = {
            "status": "selected",
            "replacements": select_replacements(
                args.receipt, args.root, args.dataset_root
            ),
        }
    elif args.action == "finalize":
        summary = finalize(args.receipt)
    else:
        summary = audit(args.receipt, args.root, args.require_complete)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
