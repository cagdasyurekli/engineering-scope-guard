"""Private, fail-closed runtime identity receipts for frozen experiments."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence


class RuntimeIdentityError(RuntimeError):
    """The frozen runtime receipt is malformed or no longer matches observation."""


VersionRunner = Callable[[Path], str]
EnvironmentObserver = Callable[[], dict[str, str]]


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build_runtime_receipt(
    *,
    codex_binary: Path,
    model_catalog: Path,
    model: str,
    command_template: Sequence[str],
    tool_surface: dict[str, Any],
    sandbox: str,
    version_runner: VersionRunner | None = None,
    environment_observer: EnvironmentObserver | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    observation = observe_runtime(
        codex_binary=codex_binary,
        model_catalog=model_catalog,
        model=model,
        command_template=command_template,
        tool_surface=tool_surface,
        sandbox=sandbox,
        version_runner=version_runner,
        environment_observer=environment_observer,
    )
    receipt = {
        "schema_name": "engineering-scope-guard.runtime-lock",
        "schema_version": 1,
        "created_at": created_at or datetime.now(UTC).isoformat(),
        **observation,
        "provider_identity_limitation": (
            "provider-side model changes not exposed by the Codex runtime cannot be frozen or detected"
        ),
    }
    receipt["receipt_sha256"] = digest(receipt)
    validate_runtime_receipt(receipt)
    return receipt


def observe_runtime(
    *,
    codex_binary: Path,
    model_catalog: Path,
    model: str,
    command_template: Sequence[str],
    tool_surface: dict[str, Any],
    sandbox: str,
    version_runner: VersionRunner | None = None,
    environment_observer: EnvironmentObserver | None = None,
) -> dict[str, Any]:
    binary = codex_binary.resolve(strict=True)
    catalog_path = model_catalog.resolve(strict=True)
    catalog_raw = catalog_path.read_bytes()
    try:
        catalog = json.loads(catalog_raw)
    except json.JSONDecodeError as error:
        raise RuntimeIdentityError("model catalog is malformed") from error
    matches = [item for item in catalog.get("models", []) if item.get("slug") == model]
    if len(matches) != 1:
        raise RuntimeIdentityError("model catalog does not contain exactly one requested model")
    model_entry = matches[0]
    efforts = [item.get("effort") for item in model_entry.get("supported_reasoning_levels", [])]
    if not {"low", "medium"}.issubset(efforts):
        raise RuntimeIdentityError("model catalog does not expose native low and medium effort")
    run_version = version_runner or _version
    observe_environment = environment_observer or _environment
    command = list(command_template)
    if sum(item.count("<EFFORT>") for item in command) != 1:
        raise RuntimeIdentityError("command template must contain exactly one <EFFORT> placeholder")
    environment = observe_environment()
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items()):
        raise RuntimeIdentityError("environment identity must contain string keys and values")
    return {
        "invocation_path": str(binary),
        "codex_version": run_version(binary),
        "codex_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "codex_binary_bytes": binary.stat().st_size,
        "codex_binary_mode": oct(binary.stat().st_mode & 0o777),
        "runtime_companions": _runtime_companions(binary),
        "model_catalog_path": str(catalog_path),
        "model_catalog_sha256": hashlib.sha256(catalog_raw).hexdigest(),
        "model_catalog_bytes": len(catalog_raw),
        "model_catalog_client_version": catalog.get("client_version"),
        "model_catalog_fetched_at": catalog.get("fetched_at"),
        "model": model,
        "catalog_default_reasoning_effort": model_entry.get("default_reasoning_level"),
        "supported_reasoning_efforts": efforts,
        "context_window": model_entry.get("context_window"),
        "effective_context_window_percent": model_entry.get("effective_context_window_percent"),
        "command_template": command,
        "config_sha256": digest(command),
        "tool_surface": tool_surface,
        "tool_surface_sha256": digest(tool_surface),
        "sandbox": sandbox,
        "environment_identity": environment,
        "environment_identity_sha256": digest(environment),
    }


def sentinel(
    receipt: dict[str, Any], *,
    version_runner: VersionRunner | None = None,
    environment_observer: EnvironmentObserver | None = None,
) -> dict[str, Any]:
    validate_runtime_receipt(receipt)
    observed = observe_runtime(
        codex_binary=Path(receipt["invocation_path"]),
        model_catalog=Path(receipt["model_catalog_path"]),
        model=receipt["model"],
        command_template=receipt["command_template"],
        tool_surface=receipt["tool_surface"],
        sandbox=receipt["sandbox"],
        version_runner=version_runner,
        environment_observer=environment_observer,
    )
    expected = {
        key: receipt[key]
        for key in observed
    }
    if observed != expected:
        changed = sorted(key for key in observed if observed.get(key) != expected.get(key))
        raise RuntimeIdentityError("runtime identity drift: " + ", ".join(changed))
    return {
        "status": "pass",
        "runtime_receipt_sha256": receipt["receipt_sha256"],
        "observed_identity_sha256": digest(observed),
    }


def validate_runtime_receipt(receipt: dict[str, Any]) -> None:
    expected_hash = receipt.get("receipt_sha256")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if expected_hash != digest(body):
        raise RuntimeIdentityError("runtime receipt hash drifted")
    if receipt.get("schema_name") != "engineering-scope-guard.runtime-lock" or receipt.get("schema_version") != 1:
        raise RuntimeIdentityError("runtime receipt schema drifted")
    for field in (
        "codex_binary_sha256", "model_catalog_sha256", "config_sha256",
        "tool_surface_sha256", "environment_identity_sha256", "receipt_sha256",
    ):
        if re.fullmatch(r"[0-9a-f]{64}", str(receipt.get(field))) is None:
            raise RuntimeIdentityError(f"{field} is not a SHA-256 digest")
    if receipt.get("config_sha256") != digest(receipt.get("command_template")):
        raise RuntimeIdentityError("runtime command configuration drifted")
    if receipt.get("tool_surface_sha256") != digest(receipt.get("tool_surface")):
        raise RuntimeIdentityError("runtime tool surface drifted")
    if receipt.get("environment_identity_sha256") != digest(receipt.get("environment_identity")):
        raise RuntimeIdentityError("runtime environment identity drifted")
    if not {"low", "medium"}.issubset(receipt.get("supported_reasoning_efforts", [])):
        raise RuntimeIdentityError("runtime receipt lacks low or medium effort")
    companions = receipt.get("runtime_companions")
    if not isinstance(companions, dict):
        raise RuntimeIdentityError("runtime companion identity is malformed")
    for name, identity in companions.items():
        if (
            not isinstance(name, str)
            or not isinstance(identity, dict)
            or re.fullmatch(r"[0-9a-f]{64}", str(identity.get("sha256"))) is None
            or not isinstance(identity.get("bytes"), int)
            or not isinstance(identity.get("mode"), str)
        ):
            raise RuntimeIdentityError("runtime companion identity is malformed")


def write_private_receipt(path: Path, receipt: dict[str, Any]) -> None:
    validate_runtime_receipt(receipt)
    if ".local" not in path.parts:
        raise RuntimeIdentityError("runtime receipts must remain below .local")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(canonical_bytes(receipt))
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def _version(binary: Path) -> str:
    result = subprocess.run([str(binary), "--version"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _runtime_companions(binary: Path) -> dict[str, dict[str, Any]]:
    companions: dict[str, dict[str, Any]] = {}
    for name in ("codex-code-mode-host",):
        path = binary.parent / name
        if path.exists():
            resolved = path.resolve(strict=True)
            companions[name] = {
                "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
                "bytes": resolved.stat().st_size,
                "mode": oct(resolved.stat().st_mode & 0o777),
            }
    return companions


def _environment() -> dict[str, str]:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "release": platform.release(),
    }
