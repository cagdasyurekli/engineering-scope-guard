"""Canonical evaluator-environment identities for frozen experiments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Sequence


SCHEMA_NAME = "engineering-scope-guard.evaluator-environment-lock"
SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_DIGEST = re.compile(r"^.+@sha256:([0-9a-f]{64})$")
_NON_SEMANTIC_FIELDS = {
    "observed_at",
    "temporary_path",
    "worker_id",
    "azure_task_id",
    "hostname",
    "process_id",
}


class EvaluatorEnvironmentError(ValueError):
    """The evaluator receipt is incomplete, mutable, or internally inconsistent."""


def canonical_bytes(value: Any) -> bytes:
    """Encode canonical JSON using the repository convention."""

    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def digest(value: Any) -> str:
    """Return the SHA-256 of one canonical JSON value."""

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def normalize_package_name(name: str) -> str:
    """Normalize one Python distribution name using PEP 503 semantics."""

    normalized = re.sub(r"[-_.]+", "-", name).lower()
    if not normalized or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", normalized):
        raise EvaluatorEnvironmentError(f"invalid Python package name: {name!r}")
    return normalized


def normalize_packages(packages: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Return a sorted, unique, explicit Python package manifest."""

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for package in packages:
        if set(package) != {"name", "version"}:
            raise EvaluatorEnvironmentError("Python package fields drifted")
        name = normalize_package_name(package["name"])
        version = package["version"].strip()
        if not version:
            raise EvaluatorEnvironmentError(f"package {name!r} lacks a version")
        if name in seen:
            raise EvaluatorEnvironmentError(f"duplicate Python package: {name}")
        seen.add(name)
        normalized.append({"name": name, "version": version})
    return sorted(normalized, key=lambda item: (item["name"], item["version"]))


def normalize_system_packages(
    packages: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Return a canonical manifest for Debian-style system package names."""

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for package in packages:
        if set(package) != {"name", "version"}:
            raise EvaluatorEnvironmentError("system package fields drifted")
        name = package["name"].strip().lower()
        version = package["version"].strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", name) or not version:
            raise EvaluatorEnvironmentError("system package identity is malformed")
        if name in seen:
            raise EvaluatorEnvironmentError(f"duplicate system package: {name}")
        seen.add(name)
        normalized.append({"name": name, "version": version})
    return sorted(normalized, key=lambda item: (item["name"], item["version"]))


def observe_python_packages(python: Path) -> list[dict[str, str]]:
    """Observe installed distributions without importing evaluator packages."""

    script = (
        "import json; from importlib.metadata import distributions; "
        "print(json.dumps([{'name': d.metadata['Name'], 'version': d.version} "
        "for d in distributions() if d.metadata['Name']]))"
    )
    completed = subprocess.run(
        [str(python), "-c", script], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise EvaluatorEnvironmentError(f"cannot observe Python packages: {detail}")
    try:
        packages = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise EvaluatorEnvironmentError("Python package observation is not JSON") from error
    if not isinstance(packages, list):
        raise EvaluatorEnvironmentError("Python package observation is not a list")
    return normalize_packages(packages)


def semantic_projection(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return only scientifically relevant global evaluator fields."""

    return {
        "schema_name": receipt.get("schema_name"),
        "schema_version": receipt.get("schema_version"),
        "e1_source": receipt.get("e1_source"),
        "e2_images": receipt.get("e2_images"),
        "e3_packages": receipt.get("e3_packages"),
        "e4_runner": receipt.get("e4_runner"),
    }


def task_projection(receipt: Mapping[str, Any], task_identity: str) -> dict[str, Any]:
    """Bind one task's legitimate inputs to the shared global environment."""

    tasks = receipt.get("e5_tasks")
    if not isinstance(tasks, list):
        raise EvaluatorEnvironmentError("task environment mapping is malformed")
    matches = [task for task in tasks if task.get("task_identity") == task_identity]
    if len(matches) != 1:
        raise EvaluatorEnvironmentError("task environment mapping is absent or ambiguous")
    return {
        "global_environment_sha256": receipt.get("global_environment_sha256"),
        "task": matches[0],
    }


def task_environment_identity(receipt: Mapping[str, Any], task_identity: str) -> str:
    """Return one task-specific identity shared by both treatment arms."""

    validate_receipt(receipt)
    return digest(task_projection(receipt, task_identity))


def build_receipt(
    *,
    source: Mapping[str, Any],
    images: Sequence[Mapping[str, str]],
    python: Mapping[str, Any],
    system_packages: Sequence[Mapping[str, str]],
    toolchains: Mapping[str, str],
    runner: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
    observation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and validate one layered evaluator-environment receipt."""

    e1_source = _normalize_source(source)
    e2_images = _normalize_images(images)
    e3_packages = _normalize_package_layer(python, system_packages, toolchains)
    e4_runner = _normalize_runner(runner)
    e5_tasks = _normalize_tasks(tasks, e2_images)
    body: dict[str, Any] = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "e1_source": e1_source,
        "e2_images": e2_images,
        "e3_packages": e3_packages,
        "e4_runner": e4_runner,
        "e5_tasks": e5_tasks,
        "observation": _normalize_observation(observation or {}),
    }
    body["global_environment_sha256"] = digest(semantic_projection(body))
    body["task_environment_sha256s"] = {
        task["task_identity"]: digest(
            {
                "global_environment_sha256": body["global_environment_sha256"],
                "task": task,
            }
        )
        for task in e5_tasks
    }
    body["receipt_sha256"] = digest(body)
    validate_receipt(body)
    return body


def validate_receipt(receipt: Mapping[str, Any]) -> None:
    """Fail closed unless every semantic identity can be reconstructed."""

    expected = {
        "schema_name",
        "schema_version",
        "e1_source",
        "e2_images",
        "e3_packages",
        "e4_runner",
        "e5_tasks",
        "observation",
        "global_environment_sha256",
        "task_environment_sha256s",
        "receipt_sha256",
    }
    if set(receipt) != expected:
        raise EvaluatorEnvironmentError("evaluator environment receipt fields drifted")
    if receipt["schema_name"] != SCHEMA_NAME or receipt["schema_version"] != SCHEMA_VERSION:
        raise EvaluatorEnvironmentError("evaluator environment schema drifted")
    package_layer = receipt["e3_packages"]
    if not isinstance(package_layer, Mapping) or set(package_layer) != {
        "python", "system_packages", "toolchains"
    }:
        raise EvaluatorEnvironmentError("package layer fields drifted")
    normalized_fields = {
        "e1_source": _normalize_source(receipt["e1_source"]),
        "e2_images": _normalize_images(receipt["e2_images"]),
        "e3_packages": _normalize_package_layer(
            package_layer["python"],
            package_layer["system_packages"],
            package_layer["toolchains"],
        ),
        "e4_runner": _normalize_runner(receipt["e4_runner"]),
    }
    normalized_fields["e5_tasks"] = _normalize_tasks(
        receipt["e5_tasks"], normalized_fields["e2_images"]
    )
    normalized_fields["observation"] = _normalize_observation(receipt["observation"])
    if any(receipt[key] != value for key, value in normalized_fields.items()):
        raise EvaluatorEnvironmentError("evaluator environment receipt is non-canonical")
    if receipt.get("global_environment_sha256") != digest(semantic_projection(receipt)):
        raise EvaluatorEnvironmentError("global evaluator environment identity drifted")
    expected_tasks = {
        task["task_identity"]: digest(
            {
                "global_environment_sha256": receipt["global_environment_sha256"],
                "task": task,
            }
        )
        for task in receipt.get("e5_tasks", [])
    }
    if receipt.get("task_environment_sha256s") != expected_tasks:
        raise EvaluatorEnvironmentError("task evaluator environment identity drifted")
    if receipt.get("receipt_sha256") != digest(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    ):
        raise EvaluatorEnvironmentError("evaluator environment receipt hash drifted")


def _require_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise EvaluatorEnvironmentError(f"{field} must be a SHA-256")
    return value


def _normalize_source(source: Mapping[str, Any]) -> dict[str, Any]:
    expected = {"repository", "revision", "tree_sha256", "lock_config_sha256"}
    if set(source) != expected or not all(
        isinstance(source[key], str) and source[key] for key in ("repository", "revision")
    ):
        raise EvaluatorEnvironmentError("evaluator source identity is malformed")
    return {
        "repository": source["repository"],
        "revision": source["revision"],
        "tree_sha256": _require_hash(source["tree_sha256"], "source tree"),
        "lock_config_sha256": _require_hash(source["lock_config_sha256"], "lock config"),
    }


def _normalize_images(images: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for image in images:
        if set(image) != {"name", "resolved_ref"}:
            raise EvaluatorEnvironmentError("execution image fields drifted")
        name = image["name"]
        reference = image["resolved_ref"]
        if not isinstance(name, str) or not name or not isinstance(reference, str):
            raise EvaluatorEnvironmentError("execution image identity is malformed")
        if not _IMAGE_DIGEST.fullmatch(reference):
            raise EvaluatorEnvironmentError("execution image is not content-addressed")
        if name in seen:
            raise EvaluatorEnvironmentError(f"duplicate execution image: {name}")
        seen.add(name)
        normalized.append({"name": name, "resolved_ref": reference})
    if not normalized:
        raise EvaluatorEnvironmentError("at least one execution image is required")
    return sorted(normalized, key=lambda image: image["name"])


def _normalize_package_layer(
    python: Mapping[str, Any],
    system_packages: Sequence[Mapping[str, str]],
    toolchains: Mapping[str, str],
) -> dict[str, Any]:
    expected = {"version", "executable_sha256", "packages"}
    if set(python) != expected or not isinstance(python["version"], str):
        raise EvaluatorEnvironmentError("Python environment identity is malformed")
    systems = normalize_system_packages(system_packages)
    tools = dict(sorted(toolchains.items()))
    if not all(isinstance(key, str) and isinstance(value, str) and key and value for key, value in tools.items()):
        raise EvaluatorEnvironmentError("toolchain identity is malformed")
    return {
        "python": {
            "version": python["version"],
            "executable_sha256": _require_hash(python["executable_sha256"], "Python executable"),
            "packages": normalize_packages(python["packages"]),
        },
        "system_packages": systems,
        "toolchains": tools,
    }


def _normalize_runner(runner: Mapping[str, Any]) -> dict[str, Any]:
    expected = {"source_revision", "source_sha256", "config_sha256", "campaign_clock_version"}
    if set(runner) != expected or not all(
        isinstance(runner[key], str) and runner[key]
        for key in ("source_revision", "campaign_clock_version")
    ):
        raise EvaluatorEnvironmentError("runner identity is malformed")
    return {
        "source_revision": runner["source_revision"],
        "source_sha256": _require_hash(runner["source_sha256"], "runner source"),
        "config_sha256": _require_hash(runner["config_sha256"], "runner config"),
        "campaign_clock_version": runner["campaign_clock_version"],
    }


def _normalize_tasks(
    tasks: Sequence[Mapping[str, Any]], images: Sequence[Mapping[str, str]]
) -> list[dict[str, Any]]:
    image_names = {image["name"] for image in images}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for task in tasks:
        if set(task) != {"task_identity", "image_name", "inputs"}:
            raise EvaluatorEnvironmentError("task environment fields drifted")
        identity = task["task_identity"]
        image_name = task["image_name"]
        inputs = task["inputs"]
        if not isinstance(identity, str) or not _SHA256.fullmatch(identity):
            raise EvaluatorEnvironmentError("task identity must be a SHA-256 commitment")
        if identity in seen or image_name not in image_names or not isinstance(inputs, dict):
            raise EvaluatorEnvironmentError("task environment mapping is malformed")
        if any(key in _NON_SEMANTIC_FIELDS for key in inputs):
            raise EvaluatorEnvironmentError("task inputs contain non-semantic fields")
        seen.add(identity)
        normalized.append(
            {
                "task_identity": identity,
                "image_name": image_name,
                "inputs": dict(sorted(inputs.items())),
            }
        )
    if not normalized:
        raise EvaluatorEnvironmentError("at least one task environment is required")
    return sorted(normalized, key=lambda task: task["task_identity"])


def _normalize_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    if any(key not in _NON_SEMANTIC_FIELDS for key in observation):
        raise EvaluatorEnvironmentError("observation contains a semantic or unknown field")
    return dict(sorted(observation.items()))
