#!/usr/bin/env python3
"""Run one pinned official evaluator prediction on an isolated Azure Batch node."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tarfile
import time
import traceback
from typing import Any, Mapping


EVALUATOR_REVISION = "7c5ee6c11595bb0290832eb9e5b7aa81ead1cfc0"
REPOLAUNCH_REVISION = "c4b623d930f3728e5338664bb634021b98492cbf"
DATASET_REVISION = "62dc0745c40f067fc366ae3eb1a26136e5928f85"
DATASET_HASHES = {
    "c": "30c0b8cb9e7140e05a4e539f20be0c325be597cbba4bf35e232355987ddddd0c",
    "cpp": "8448db887817b63e4c0c284ca99de1ccda15023f48e5b2234a4084466e0768ae",
    "cs": "29ffe16d0b2cd802e753262b8b0d7fe3f2bb1b489396da238146e79f37937c1f",
    "go": "76d2b5dff0f3fac8303d30fa85495539e487d25974ad7c21cd21a545cb4756e2",
    "java": "00387685808c71d21ada175335304b1c118859453afadd58ea21a00b0d568ee8",
    "js": "bc6ec49ffaf9db97840d55eba6954fae8f5fb0fb071cf49e187f36ffadd55a7a",
    "rust": "02ac78e2c51a84eb174ac393bb07b77478f1f96cf260af18835a711dd8074ebc",
    "ts": "7e23783e27230c9cfab1035690035c25523043d6af635bc78da3fd2010c32714",
}
EVALUATOR = Path("/opt/futureq/evaluator")
PYTHON = Path("/opt/futureq/venv/bin/python")
DATASET = Path("/opt/futureq/dataset")
OUTPUT = Path("azure-evaluator")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def patch_from_environment(environment: Mapping[str, str]) -> bytes:
    """Reassemble deterministic gzip/base64 chunks and verify original bytes."""

    count = int(environment["ESG_PATCH_CHUNK_COUNT"])
    if count <= 0 or count > 128:
        raise ValueError("patch chunk count is outside the frozen bound")
    encoded = "".join(environment[f"ESG_PATCH_CHUNK_{index:03d}"] for index in range(count))
    patch = gzip.decompress(base64.b64decode(encoded, validate=True))
    if sha256_bytes(patch) != environment["ESG_PATCH_SHA256"]:
        raise ValueError("subject patch SHA-256 differs from the launch receipt")
    return patch


def _checked(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({command[0]}): {(completed.stderr or completed.stdout).strip()}"
        )
    return completed.stdout.strip()


def git_head(repository: Path) -> str:
    """Read a root-owned checkout without mutating global Git configuration."""

    return _checked(
        ["git", "-c", f"safe.directory={repository}", "rev-parse", "HEAD"],
        cwd=repository,
    )


def _matching_containers(image: str) -> set[str]:
    return {
        line
        for line in _checked(
            ["docker", "ps", "-aq", "--filter", f"ancestor={image}"]
        ).splitlines()
        if line
    }


def _stop_owned_containers(container_ids: set[str]) -> list[str]:
    stopped: list[str] = []
    for container_id in sorted(container_ids):
        completed = subprocess.run(
            ["docker", "stop", "--time", "5", container_id],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            stopped.append(container_id)
    return stopped


def _source_row(environment: Mapping[str, str]) -> dict[str, Any]:
    import pyarrow.parquet as parquet

    language = environment["ESG_TASK_LANGUAGE"]
    source = DATASET / "data" / f"{language}-00000-of-00001.parquet"
    if sha256_file(source) != DATASET_HASHES[language]:
        raise ValueError("pinned dataset shard identity drifted")
    instance_id = environment["ESG_TASK_ID"]
    matches = [
        row
        for row in parquet.read_table(source).to_pylist()
        if row.get("instance_id") == instance_id
    ]
    if len(matches) != 1:
        raise ValueError("frozen dataset row is absent or ambiguous")
    row = dict(matches[0])
    if (
        row.get("repo") != environment["ESG_TASK_REPOSITORY"]
        or row.get("docker_image") != environment["ESG_TASK_IMAGE_TAG"]
    ):
        raise ValueError("frozen task source identity drifted")
    row["docker_image"] = environment["ESG_TASK_RESOLVED_IMAGE"]
    return row


def _run_evaluator(
    command: list[str], *, timeout_seconds: int, environment: dict[str, str]
) -> dict[str, Any]:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=EVALUATOR,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return {
            "exit_code": process.returncode,
            "timed_out": False,
            "wall_seconds": round(time.monotonic() - started, 6),
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return {
            "exit_code": None,
            "timed_out": True,
            "wall_seconds": round(time.monotonic() - started, 6),
            "stdout": stdout,
            "stderr": stderr,
        }


def run(environment: Mapping[str, str]) -> dict[str, Any]:
    """Execute one prediction and return a self-contained worker receipt."""

    started = time.monotonic()
    wall_started = datetime.now(UTC).isoformat()
    OUTPUT.mkdir(mode=0o700)
    patch = patch_from_environment(environment)
    row = _source_row(environment)
    instance_path = OUTPUT / "instance.jsonl"
    prediction_path = OUTPUT / "prediction.json"
    official_output = OUTPUT / "official"
    instance_path.write_bytes(canonical_bytes(row))
    prediction_path.write_bytes(
        canonical_bytes(
            {environment["ESG_TASK_ID"]: {"model_patch": patch.decode("utf-8")}}
        )
    )
    evaluator_head = git_head(EVALUATOR)
    repolaunch_head = git_head(EVALUATOR / "launch")
    if evaluator_head != EVALUATOR_REVISION or repolaunch_head != REPOLAUNCH_REVISION:
        raise ValueError("Azure evaluator source revision drifted")
    resolved_image = environment["ESG_TASK_RESOLVED_IMAGE"]
    before = _matching_containers(resolved_image)
    evaluator_environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(EVALUATOR), str(EVALUATOR / "launch"))),
    }
    result = _run_evaluator(
        [
            str(PYTHON),
            "-m",
            "evaluation.evaluation",
            "--dataset",
            str(instance_path.resolve()),
            "--split",
            environment["ESG_TASK_LANGUAGE"],
            "--platform",
            "linux",
            "--patch_dir",
            str(prediction_path.resolve()),
            "--output_dir",
            str(official_output.resolve()),
            "--workers",
            "1",
            "--overwrite",
            "1",
            "--instance_ids",
            environment["ESG_TASK_ID"],
        ],
        timeout_seconds=int(environment["ESG_EVALUATOR_TIMEOUT_SECONDS"]),
        environment=evaluator_environment,
    )
    (OUTPUT / "evaluator.stdout").write_bytes(result.pop("stdout"))
    (OUTPUT / "evaluator.stderr").write_bytes(result.pop("stderr"))
    after = _matching_containers(resolved_image)
    owned = after - before
    stopped = _stop_owned_containers(owned)
    remaining = _matching_containers(resolved_image) & owned
    report_path = official_output / environment["ESG_TASK_ID"] / "report.json"
    results_path = official_output / "results.json"
    status = (
        "pass"
        if result["exit_code"] == 0
        and not result["timed_out"]
        and report_path.is_file()
        and results_path.is_file()
        and not remaining
        else "evaluator_infrastructure_failure"
    )
    body = {
        "schema_name": "engineering-scope-guard.azure-prediction-worker",
        "schema_version": 1,
        "task_id": environment["ESG_TASK_ID"],
        "repository": environment["ESG_TASK_REPOSITORY"],
        "language": environment["ESG_TASK_LANGUAGE"],
        "resolved_image": resolved_image,
        "patch_sha256": sha256_bytes(patch),
        "dataset_revision": DATASET_REVISION,
        "evaluator_revision": evaluator_head,
        "repolaunch_revision": repolaunch_head,
        "worker_sha256": sha256_file(Path(__file__)),
        "started_at": wall_started,
        "finished_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "execution": result,
        "preexisting_matching_container_ids": sorted(before),
        "owned_container_ids_after_evaluator": sorted(owned),
        "owned_container_ids_stopped": stopped,
        "owned_container_ids_remaining": sorted(remaining),
        "report_sha256": sha256_file(report_path) if report_path.is_file() else None,
        "results_sha256": sha256_file(results_path) if results_path.is_file() else None,
        "status": status,
    }
    return {**body, "worker_receipt_sha256": sha256_bytes(canonical_bytes(body))}


def main() -> int:
    receipt: dict[str, Any]
    try:
        receipt = run(os.environ)
    except BaseException as error:
        receipt = {
            "schema_name": "engineering-scope-guard.azure-prediction-worker",
            "schema_version": 1,
            "task_id": os.environ.get("ESG_TASK_ID"),
            "status": "evaluator_infrastructure_failure",
            "exception": {"type": type(error).__name__, "message": str(error)},
        }
        receipt["worker_receipt_sha256"] = sha256_bytes(canonical_bytes(receipt))
        (OUTPUT / "worker-traceback.txt").parent.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "worker-traceback.txt").write_text(traceback.format_exc())
    (OUTPUT / "worker-receipt.json").write_bytes(canonical_bytes(receipt))
    with tarfile.open("azure-evaluator-artifacts.tar.gz", "w:gz") as archive:
        archive.add(OUTPUT, arcname="azure-evaluator")
    return 0 if receipt.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
