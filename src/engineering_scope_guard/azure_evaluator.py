"""Small fail-closed Azure Batch transport for the pinned official evaluator."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import UTC, datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from .campaign_clock import CampaignClock, wait_for_campaign
from .runtime_lock import canonical_bytes, digest


POOL_ID = "esg-rr002-evaluator-pool"
POOL_VM_SIZE = "Standard_D4s_v3"
POOL_IMAGE = {
    "publisher": "canonical",
    "offer": "ubuntu-24_04-lts",
    "sku": "server-gen1",
    "version": "24.04.202608270",
}
NODE_AGENT_SKU = "batch.node.ubuntu 24.04"
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
HOURLY_COST_USD = 0.214


class AzureEvaluatorError(RuntimeError):
    """The Azure evaluator path is unavailable, drifted, or incomplete."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AzureEvaluatorError(message)


def _az(arguments: Sequence[str], *, allow_not_found: bool = False) -> Any:
    completed = subprocess.run(
        ["az", *arguments, "--output", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        if allow_not_found and any(
            marker in detail.lower()
            for marker in ("notfound", "not found", "does not exist")
        ):
            return None
        raise AzureEvaluatorError(
            f"Azure CLI command failed ({' '.join(arguments)}): {detail}"
        )
    return json.loads(completed.stdout) if completed.stdout.strip() else None


@contextmanager
def _json_file(value: Any) -> Iterator[Path]:
    with tempfile.NamedTemporaryFile("wb", delete=False) as handle:
        handle.write(canonical_bytes(value))
        path = Path(handle.name)
    path.chmod(0o600)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def _write_private(path: Path, value: dict[str, Any]) -> None:
    _require(".local" in path.parts, "Azure evaluator receipt must remain below .local")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(canonical_bytes(value))
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def zero_compute_state() -> dict[str, Any]:
    pools = _az(["batch", "pool", "list"])
    jobs = _az(["batch", "job", "list"])
    pool_values = pools if isinstance(pools, list) else []
    job_values = jobs if isinstance(jobs, list) else []
    return {
        "pools": [value.get("id") for value in pool_values if isinstance(value, dict)],
        "jobs": [value.get("id") for value in job_values if isinstance(value, dict)],
        "active_nodes": sum(
            int(value.get("currentDedicatedNodes") or 0)
            + int(value.get("currentLowPriorityNodes") or 0)
            for value in pool_values
            if isinstance(value, dict)
        ),
    }


def occupancy(state_root: Path) -> dict[str, Any]:
    """Seal the live account view without treating this program as a conflict."""

    pools = _az(["batch", "pool", "list"])
    jobs = _az(["batch", "job", "list"])
    pool_values = pools if isinstance(pools, list) else []
    job_values = jobs if isinstance(jobs, list) else []
    own_pools = [
        value for value in pool_values
        if isinstance(value, dict) and value.get("id") == POOL_ID
    ]
    conflicting_pools = sorted(
        str(value.get("id")) for value in pool_values
        if isinstance(value, dict) and value.get("id") != POOL_ID
    )
    own_jobs = sorted(
        str(value.get("id")) for value in job_values
        if isinstance(value, dict)
        and isinstance(value.get("id"), str)
        and value["id"].startswith("esgrr002-")
    )
    conflicting_jobs = sorted(
        str(value.get("id")) for value in job_values
        if isinstance(value, dict)
        and not (
            isinstance(value.get("id"), str)
            and value["id"].startswith("esgrr002-")
        )
    )
    conflicting_active_nodes = sum(
        int(value.get("currentDedicatedNodes") or 0)
        + int(value.get("currentLowPriorityNodes") or 0)
        for value in pool_values
        if isinstance(value, dict) and value.get("id") != POOL_ID
    )
    own_active_tasks = sorted(
        f"{job_id}/{task.get('id')}"
        for job_id in own_jobs
        for task in _task_status(job_id)
        if task.get("state") != "completed"
    )
    status = (
        "pass"
        if len(own_pools) == 1
        and not conflicting_pools
        and not conflicting_jobs
        and conflicting_active_nodes == 0
        and not own_active_tasks
        else "fail"
    )
    body = {
        "schema_name": "engineering-scope-guard.azure-evaluator-occupancy",
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "own_pool_id": POOL_ID if own_pools else None,
        "own_jobs": own_jobs,
        "own_active_tasks": own_active_tasks,
        "conflicting_pools": conflicting_pools,
        "conflicting_jobs": conflicting_jobs,
        "conflicting_active_nodes": conflicting_active_nodes,
        "status": status,
    }
    receipt = {**body, "occupancy_receipt_sha256": digest(body)}
    _write_private(state_root / "occupancy-receipt.json", receipt)
    return receipt


def _start_task() -> str:
    downloads: list[str] = []
    checks: list[str] = []
    for language, file_hash in DATASET_HASHES.items():
        filename = f"{language}-00000-of-00001.parquet"
        url = (
            "https://huggingface.co/datasets/SWE-bench-Live/MultiLang/resolve/"
            f"{DATASET_REVISION}/data/{filename}?download=true"
        )
        downloads.append(
            f"curl -fL --retry 3 {shlex.quote(url)} -o "
            f"/opt/futureq/dataset/data/{filename}"
        )
        checks.append(
            f"printf '%s  %s\\n' {file_hash} "
            f"/opt/futureq/dataset/data/{filename} | sha256sum -c -"
        )
    commands = [
        "set -euo pipefail",
        "export DEBIAN_FRONTEND=noninteractive",
        "apt-get update",
        "apt-get install -y docker.io git python3-venv curl ca-certificates",
        "systemctl enable --now docker",
        "install -d -m 0755 /opt/futureq/dataset/data",
        "git clone --no-checkout https://github.com/microsoft/SWE-bench-Live.git /opt/futureq/evaluator",
        f"git -C /opt/futureq/evaluator checkout --detach {EVALUATOR_REVISION}",
        "git -C /opt/futureq/evaluator submodule update --init launch",
        f'test "$(git -C /opt/futureq/evaluator/launch rev-parse HEAD)" = {REPOLAUNCH_REVISION}',
        "python3 -m venv /opt/futureq/venv",
        "/opt/futureq/venv/bin/pip install --disable-pip-version-check --upgrade pip",
        "/opt/futureq/venv/bin/pip install --disable-pip-version-check -e /opt/futureq/evaluator -e /opt/futureq/evaluator/launch",
        *downloads,
        *checks,
        "docker version --format '{{.Server.Version}}'",
        "/opt/futureq/venv/bin/python -c 'import datasets,fire,pyarrow; print(datasets.__version__,fire.__version__,pyarrow.__version__)'",
    ]
    return "/bin/bash -c " + shlex.quote("; ".join(commands))


def pool_spec() -> dict[str, Any]:
    return {
        "id": POOL_ID,
        "vmSize": POOL_VM_SIZE,
        "virtualMachineConfiguration": {
            "imageReference": POOL_IMAGE,
            "nodeAgentSKUId": NODE_AGENT_SKU,
        },
        "targetDedicatedNodes": 1,
        "targetLowPriorityNodes": 0,
        "taskSlotsPerNode": 1,
        "taskSchedulingPolicy": {"nodeFillType": "pack"},
        "startTask": {
            "commandLine": _start_task(),
            "waitForSuccess": True,
            "userIdentity": {
                "autoUser": {"scope": "pool", "elevationLevel": "admin"}
            },
        },
    }


def prepare_pool(state_root: Path, *, timeout_seconds: int = 1800) -> dict[str, Any]:
    """Create one pinned evaluator worker only from an otherwise empty account."""

    initial = zero_compute_state()
    _require(
        not initial["pools"] and not initial["jobs"] and initial["active_nodes"] == 0,
        "shared Azure Batch account is not empty",
    )
    spec = pool_spec()
    with _json_file(spec) as source:
        _az(["batch", "pool", "create", "--json-file", str(source)])
    deadline = time.monotonic() + timeout_seconds
    node: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        pool = _az(["batch", "pool", "show", "--pool-id", POOL_ID])
        resize_errors = pool.get("resizeErrors") if isinstance(pool, dict) else None
        _require(not resize_errors, "Azure evaluator pool allocation failed")
        nodes = _az(["batch", "node", "list", "--pool-id", POOL_ID])
        values = nodes if isinstance(nodes, list) else []
        failed = [
            value
            for value in values
            if value.get("state") in {"starttaskfailed", "unusable"}
        ]
        _require(not failed, "Azure evaluator pool start task failed")
        node = next(
            (value for value in values if value.get("state") == "idle"), None
        )
        if node is not None:
            break
        time.sleep(10)
    _require(node is not None, "Azure evaluator pool did not become ready")
    body = {
        "schema_name": "engineering-scope-guard.azure-evaluator-pool",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "pool_id": POOL_ID,
        "pool_spec": spec,
        "pool_spec_sha256": digest(spec),
        "worker_node_id": node.get("id"),
        "worker_vm_size": POOL_VM_SIZE,
        "worker_image_identity": ":".join(POOL_IMAGE.values()),
        "evaluator_revision": EVALUATOR_REVISION,
        "repolaunch_revision": REPOLAUNCH_REVISION,
        "dataset_revision": DATASET_REVISION,
        "dataset_hashes": DATASET_HASHES,
        "hourly_cost_usd_upper_bound": HOURLY_COST_USD,
        "status": "ready",
    }
    receipt = {**body, "pool_receipt_sha256": digest(body)}
    _write_private(state_root / "pool-receipt.json", receipt)
    return receipt


def patch_environment(
    patch: bytes, *, chunk_bytes: int = 8000,
) -> dict[str, str]:
    encoded = base64.b64encode(gzip.compress(patch, mtime=0)).decode()
    chunks = [
        encoded[index : index + chunk_bytes]
        for index in range(0, len(encoded), chunk_bytes)
    ] or [""]
    _require(len(chunks) <= 128, "compressed subject patch exceeds Azure transport bound")
    return {
        "ESG_PATCH_CHUNK_COUNT": str(len(chunks)),
        "ESG_PATCH_SHA256": hashlib.sha256(patch).hexdigest(),
        **{
            f"ESG_PATCH_CHUNK_{index:03d}": chunk
            for index, chunk in enumerate(chunks)
        },
    }


def worker_command(worker: bytes) -> str:
    worker_sha256 = hashlib.sha256(worker).hexdigest()
    encoded = base64.b64encode(gzip.compress(worker, mtime=0)).decode()
    script = "; ".join(
        (
            "set -euo pipefail",
            f"printf %s {shlex.quote(encoded)} | base64 -d | gzip -d > azure_prediction_worker.py",
            f"printf '%s  %s\\n' {worker_sha256} azure_prediction_worker.py | sha256sum -c -",
            "sudo -n -E /opt/futureq/venv/bin/python azure_prediction_worker.py",
        )
    )
    return "/bin/bash -c " + shlex.quote(script)


def task_payload(
    *, job_id: str, task_id: str, task: Mapping[str, Any], patch: bytes,
    worker: bytes, evaluator_timeout_seconds: int,
) -> dict[str, Any]:
    for value, label in ((job_id, "job_id"), (task_id, "task_id")):
        _require(
            isinstance(value, str)
            and re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None,
            f"Azure {label} is malformed",
        )
    environment = {
        "ESG_TASK_ID": str(task["task_id"]),
        "ESG_TASK_REPOSITORY": str(task["repository"]),
        "ESG_TASK_LANGUAGE": str(task["language"]),
        "ESG_TASK_IMAGE_TAG": str(task["docker_image"]),
        "ESG_TASK_RESOLVED_IMAGE": str(task["resolved_image"]),
        "ESG_EVALUATOR_TIMEOUT_SECONDS": str(evaluator_timeout_seconds),
        **patch_environment(patch),
    }
    return {
        "id": task_id,
        "commandLine": worker_command(worker),
        "userIdentity": {
            "autoUser": {"scope": "task", "elevationLevel": "admin"}
        },
        "constraints": {
            "maxWallClockTime": f"PT{evaluator_timeout_seconds + 120}S",
            "maxTaskRetryCount": 0,
        },
        "environmentSettings": [
            {"name": name, "value": value}
            for name, value in sorted(environment.items())
        ],
    }


def _task_status(job_id: str) -> list[dict[str, Any]]:
    value = _az(["batch", "task", "list", "--job-id", job_id])
    return value if isinstance(value, list) else []


def _download(job_id: str, task_id: str, remote: str, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.unlink(missing_ok=True)
    completed = subprocess.run(
        [
            "az", "batch", "task", "file", "download", "--job-id", job_id,
            "--task-id", task_id, "--file-path", remote, "--destination",
            str(destination), "--output", "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0 and destination.is_file()


def remote_task_file(logical: str) -> str:
    """Map result-stream files and task working-directory artifacts exactly."""

    _require(
        logical
        and not logical.startswith("/")
        and ".." not in Path(logical).parts,
        "Azure task artifact path is unsafe",
    )
    return logical if logical in {"stdout.txt", "stderr.txt"} else f"wd/{logical}"


def evaluate(
    *, state_root: Path, worker_path: Path, job_id: str, task_id: str,
    task: Mapping[str, Any], patch: bytes, evaluator_timeout_seconds: int,
    campaign_max_seconds: int = 72 * 3600,
) -> dict[str, Any]:
    """Submit, wait, collect, and seal one evaluator task without Azure retry."""

    pool = _az(["batch", "pool", "show", "--pool-id", POOL_ID])
    _require(isinstance(pool, dict), "pinned Azure evaluator pool is absent")
    worker = worker_path.resolve(strict=True).read_bytes()
    payload = task_payload(
        job_id=job_id, task_id=task_id, task=task, patch=patch, worker=worker,
        evaluator_timeout_seconds=evaluator_timeout_seconds,
    )
    if _az(["batch", "job", "show", "--job-id", job_id], allow_not_found=True) is None:
        _az(["batch", "job", "create", "--id", job_id, "--pool-id", POOL_ID])
    _require(
        _az(
            ["batch", "task", "show", "--job-id", job_id, "--task-id", task_id],
            allow_not_found=True,
        ) is None,
        "Azure evaluator task identity already exists",
    )
    requested_at = datetime.now(UTC).isoformat()
    with _json_file(payload) as source:
        _az(
            [
                "batch", "task", "create", "--job-id", job_id,
                "--json-file", str(source),
            ]
        )
    config = {
        "pool_id": POOL_ID,
        "pool_spec_sha256": digest(pool_spec()),
        "evaluator_revision": EVALUATOR_REVISION,
        "dataset_revision": DATASET_REVISION,
        "worker_sha256": hashlib.sha256(worker).hexdigest(),
        "task_surface_sha256": digest(
            {
                "command_line": payload["commandLine"],
                "user_identity": payload["userIdentity"],
                "max_task_retry_count": payload["constraints"]["maxTaskRetryCount"],
            }
        ),
    }
    config_sha256 = digest(config)
    campaign_path = state_root / f"campaign-clock-{config_sha256}.json"
    campaign_uuid = "3da2ca7a-7af4-5e99-8ac7-63f4ea34a0ed"
    campaign = (
        CampaignClock.resume(
            campaign_path, campaign_uuid=campaign_uuid,
            immutable_config_sha256=config_sha256,
        )
        if campaign_path.exists()
        else CampaignClock.create(
            campaign_path, campaign_uuid=campaign_uuid,
            immutable_config_sha256=config_sha256,
            hard_max_duration_seconds=campaign_max_seconds,
        )
    )
    wait_for_campaign(
        [job_id], campaign, lambda current: _task_status(current), poll_seconds=10
    )
    remote = _az(
        ["batch", "task", "show", "--job-id", job_id, "--task-id", task_id]
    )
    execution = remote.get("executionInfo") if isinstance(remote, dict) else {}
    execution = execution if isinstance(execution, dict) else {}
    failure = execution.get("failureInfo") or {}
    artifacts = state_root / "artifacts" / job_id / task_id
    logical_paths = (
            "stdout.txt",
            "stderr.txt",
            "azure-evaluator/worker-receipt.json",
            f"azure-evaluator/official/{task['task_id']}/report.json",
            "azure-evaluator/official/results.json",
            "azure-evaluator/evaluator.stdout",
            "azure-evaluator/evaluator.stderr",
            "azure-evaluator-artifacts.tar.gz",
    )
    downloads = {logical: artifacts / logical for logical in logical_paths}
    downloaded = {
        logical: _download(
            job_id,
            task_id,
            remote_task_file(logical),
            path,
        )
        for logical, path in downloads.items()
    }
    worker_receipt_path = downloads["azure-evaluator/worker-receipt.json"]
    worker_receipt = (
        json.loads(worker_receipt_path.read_text())
        if worker_receipt_path.is_file()
        else None
    )
    report_remote = f"azure-evaluator/official/{task['task_id']}/report.json"
    results_remote = "azure-evaluator/official/results.json"
    worker_body = (
        {key: value for key, value in worker_receipt.items()
         if key != "worker_receipt_sha256"}
        if isinstance(worker_receipt, dict)
        else None
    )
    worker_valid = (
        isinstance(worker_receipt, dict)
        and worker_receipt.get("worker_receipt_sha256") == digest(worker_body)
        and worker_receipt.get("schema_name")
        == "engineering-scope-guard.azure-prediction-worker"
        and worker_receipt.get("status") == "pass"
        and worker_receipt.get("task_id") == task["task_id"]
        and worker_receipt.get("repository") == task["repository"]
        and worker_receipt.get("language") == task["language"]
        and worker_receipt.get("resolved_image") == task["resolved_image"]
        and worker_receipt.get("patch_sha256") == hashlib.sha256(patch).hexdigest()
        and worker_receipt.get("worker_sha256") == config["worker_sha256"]
        and worker_receipt.get("evaluator_revision") == EVALUATOR_REVISION
        and worker_receipt.get("repolaunch_revision") == REPOLAUNCH_REVISION
        and worker_receipt.get("dataset_revision") == DATASET_REVISION
        and worker_receipt.get("owned_container_ids_remaining") == []
        and isinstance(worker_receipt.get("execution"), dict)
        and worker_receipt["execution"].get("exit_code") == 0
        and worker_receipt["execution"].get("timed_out") is False
        and downloads[report_remote].is_file()
        and worker_receipt.get("report_sha256")
        == hashlib.sha256(downloads[report_remote].read_bytes()).hexdigest()
        and downloads[results_remote].is_file()
        and worker_receipt.get("results_sha256")
        == hashlib.sha256(downloads[results_remote].read_bytes()).hexdigest()
    )
    required = (
        "azure-evaluator/worker-receipt.json",
        report_remote,
        results_remote,
        "azure-evaluator/evaluator.stdout",
        "azure-evaluator/evaluator.stderr",
    )
    status = (
        "pass"
        if execution.get("exitCode") == 0
        and not failure
        and all(downloaded[name] for name in required)
        and worker_valid
        else "evaluator_infrastructure_failure"
    )
    body = {
        "schema_name": "engineering-scope-guard.azure-evaluator-receipt",
        "schema_version": 1,
        "requested_at": requested_at,
        "job_id": job_id,
        "task_id": task_id,
        "research_task_sha256": digest(dict(task)),
        "payload_sha256": digest(payload),
        "worker_sha256": config["worker_sha256"],
        "evaluator_revision": EVALUATOR_REVISION,
        "repolaunch_revision": REPOLAUNCH_REVISION,
        "dataset_revision": DATASET_REVISION,
        "worker_vm_size": POOL_VM_SIZE,
        "worker_image_identity": ":".join(POOL_IMAGE.values()),
        "campaign_elapsed_ns": campaign.elapsed_ns,
        "azure_start_time": execution.get("startTime"),
        "azure_end_time": execution.get("endTime"),
        "azure_exit_code": execution.get("exitCode"),
        "azure_retry_count": execution.get("retryCount", 0),
        "azure_requeue_count": execution.get("requeueCount", 0),
        "azure_failure_code": failure.get("code"),
        "timed_out": failure.get("code") == "MaxWallClockTimeExceeded",
        "downloaded": downloaded,
        "artifact_sha256s": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in downloads.items()
            if path.is_file()
        },
        "worker_receipt": worker_receipt,
        "status": status,
    }
    receipt = {**body, "azure_evaluator_receipt_sha256": digest(body)}
    _write_private(state_root / "receipts" / f"{job_id}-{task_id}.json", receipt)
    return receipt


def failure_receipt(
    *, state_root: Path, job_id: str, task_id: str, error: Exception,
) -> dict[str, Any]:
    """Persist a terminal infrastructure receipt when orchestration aborts early."""

    body = {
        "schema_name": "engineering-scope-guard.azure-evaluator-receipt",
        "schema_version": 1,
        "job_id": job_id,
        "task_id": task_id,
        "evaluator_revision": EVALUATOR_REVISION,
        "repolaunch_revision": REPOLAUNCH_REVISION,
        "dataset_revision": DATASET_REVISION,
        "worker_vm_size": POOL_VM_SIZE,
        "worker_image_identity": ":".join(POOL_IMAGE.values()),
        "timed_out": type(error).__name__ == "CampaignTimeout",
        "infrastructure_error": {
            "type": type(error).__name__,
            "message": str(error),
        },
        "status": "evaluator_infrastructure_failure",
    }
    receipt = {**body, "azure_evaluator_receipt_sha256": digest(body)}
    _write_private(state_root / "receipts" / f"{job_id}-{task_id}.json", receipt)
    return receipt


def cleanup(state_root: Path, *, timeout_seconds: int = 900) -> dict[str, Any]:
    """Delete only this program's jobs/pool and wait for an empty account."""

    jobs = _az(["batch", "job", "list"])
    for job in jobs if isinstance(jobs, list) else []:
        job_id = job.get("id") if isinstance(job, dict) else None
        if isinstance(job_id, str) and job_id.startswith("esgrr002-"):
            _az(["batch", "job", "delete", "--job-id", job_id, "--yes"])
    if _az(["batch", "pool", "show", "--pool-id", POOL_ID], allow_not_found=True) is not None:
        _az(
            [
                "batch", "pool", "resize", "--pool-id", POOL_ID,
                "--target-dedicated-nodes", "0", "--target-low-priority-nodes", "0",
            ]
        )
        _az(["batch", "pool", "delete", "--pool-id", POOL_ID, "--yes"])
    deadline = time.monotonic() + timeout_seconds
    state = zero_compute_state()
    while time.monotonic() < deadline and (
        state["pools"] or state["jobs"] or state["active_nodes"]
    ):
        time.sleep(10)
        state = zero_compute_state()
    _require(
        not state["pools"] and not state["jobs"] and state["active_nodes"] == 0,
        "Azure Batch did not return to zero compute",
    )
    body = {
        "schema_name": "engineering-scope-guard.azure-evaluator-cleanup",
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "state": state,
        "status": "pass",
    }
    receipt = {**body, "cleanup_receipt_sha256": digest(body)}
    _write_private(state_root / "cleanup-receipt.json", receipt)
    return receipt
