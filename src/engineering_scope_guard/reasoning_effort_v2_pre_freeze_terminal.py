"""Provider-free terminalization before Reasoning Effort v2 contract freeze.

This module records only content-free identity commitments.  It never invokes a
provider, evaluator, dataset reader, or task materializer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from engineering_scope_guard.evaluator_stable_qualification import validate_receipt
from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import digest


SCHEMA_NAME = "engineering-scope-guard.reasoning-effort-v2-pre-freeze-terminal"
SCHEMA_VERSION = 1
CLASSIFICATION = "runtime_identity_mismatch_before_contract_freeze"
RECEIPT_NAME = "pre-freeze-terminal.json"
STORAGE_AUTHORITY_SCHEMA = (
    "engineering-scope-guard.reasoning-effort-v2-storage-authority"
)
_HEX = frozenset("0123456789abcdef")
_REQUIRED_CHANGED_FIELDS = frozenset(
    {"model_catalog_sha256", "model_catalog_fetched_at"}
)
_FORBIDDEN_PRE_FREEZE_NAMES = frozenset(
    {
        "contract.json",
        "private-pool.json",
        "qualification-gate.json",
        "freeze-state.json",
        "live-seal.json",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "status",
        "classification",
        "qualification_state_sha256",
        "storage_authority_sha256",
        "expected_model_catalog_sha256",
        "observed_model_catalog_sha256",
        "expected_runtime_sha256",
        "observed_runtime_sha256",
        "changed_fields",
        "subject_invocation_starts",
        "contract_frozen",
        "provider_calls_performed",
        "evaluator_invocations_performed",
        "task_material_accessed",
        "receipt_sha256",
    }
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def _sha256(value: Any, label: str) -> str:
    _require(
        isinstance(value, str) and len(value) == 64 and set(value) <= _HEX,
        f"{label} is not a SHA-256 digest",
    )
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as error:
        raise ExperimentConfigurationError("pre-freeze terminal value is not canonical JSON") from error
    return (encoded + "\n").encode("utf-8")


def _validate_json_value(value: Any, label: str) -> None:
    if isinstance(value, float):
        _require(math.isfinite(value), f"{label} contains a non-finite number")
    elif isinstance(value, dict):
        _require(
            all(isinstance(key, str) for key in value),
            f"{label} contains a non-text object key",
        )
        for child in value.values():
            _validate_json_value(child, label)
    elif isinstance(value, list):
        for child in value:
            _validate_json_value(child, label)
    else:
        _require(
            value is None or isinstance(value, (str, int, bool)),
            f"{label} contains a non-JSON value",
        )


def _validate_storage_authority(value: dict[str, Any]) -> None:
    _require(
        set(value)
        == {
            "schema_name",
            "schema_version",
            "status",
            "root_identity_sha256",
            "receipt_sha256",
        },
        "storage authority fields drifted",
    )
    body = {key: item for key, item in value.items() if key != "receipt_sha256"}
    _require(
        value["schema_name"] == STORAGE_AUTHORITY_SCHEMA
        and type(value["schema_version"]) is int
        and value["schema_version"] == 1
        and value["status"] == "initialized"
        and _sha256(value["root_identity_sha256"], "storage root identity")
        and value["receipt_sha256"] == digest(body),
        "storage authority is malformed or unsealed",
    )


def validate_pre_freeze_terminal_receipt(
    receipt: dict[str, Any],
    qualification_receipt: dict[str, Any],
    storage_authority: dict[str, Any] | None = None,
) -> None:
    """Validate the content-free terminal receipt and its durable bindings."""

    validate_receipt(qualification_receipt)
    _require(
        qualification_receipt["status"] == "stable_pool_ready",
        "qualification is not stable_pool_ready",
    )
    _require(set(receipt) == _RECEIPT_FIELDS, "pre-freeze terminal fields drifted")
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    changed_fields = receipt["changed_fields"]
    expected_runtime = qualification_receipt["runtime_observation"]
    expected_catalog = expected_runtime.get("model_catalog_sha256")
    _require(
        receipt["schema_name"] == SCHEMA_NAME
        and type(receipt["schema_version"]) is int
        and receipt["schema_version"] == SCHEMA_VERSION
        and receipt["status"] == "terminal"
        and receipt["classification"] == CLASSIFICATION
        and receipt["qualification_state_sha256"]
        == qualification_receipt["state_sha256"]
        and receipt["expected_runtime_sha256"] == digest(expected_runtime)
        and receipt["expected_model_catalog_sha256"] == expected_catalog
        and isinstance(changed_fields, list)
        and changed_fields == sorted(set(changed_fields))
        and all(isinstance(field, str) and field for field in changed_fields)
        and _REQUIRED_CHANGED_FIELDS <= set(changed_fields)
        and receipt["expected_runtime_sha256"] != receipt["observed_runtime_sha256"]
        and receipt["expected_model_catalog_sha256"]
        != receipt["observed_model_catalog_sha256"]
        and type(receipt["subject_invocation_starts"]) is int
        and receipt["subject_invocation_starts"] == 0
        and receipt["contract_frozen"] is False
        and receipt["provider_calls_performed"] is False
        and receipt["evaluator_invocations_performed"] is False
        and receipt["task_material_accessed"] is False
        and receipt["receipt_sha256"] == digest(body),
        "pre-freeze terminal receipt is malformed or unbound",
    )
    for field in (
        "qualification_state_sha256",
        "storage_authority_sha256",
        "expected_model_catalog_sha256",
        "observed_model_catalog_sha256",
        "expected_runtime_sha256",
        "observed_runtime_sha256",
        "receipt_sha256",
    ):
        _sha256(receipt[field], field)
    if storage_authority is not None:
        _validate_storage_authority(storage_authority)
        _require(
            receipt["storage_authority_sha256"]
            == storage_authority["receipt_sha256"],
            "pre-freeze terminal storage-authority binding differs",
        )


def _private_local_ancestor(path: Path) -> Path:
    absolute = path.absolute()
    local = next(
        (item for item in (absolute, *absolute.parents) if item.name == ".local"),
        None,
    )
    _require(local is not None, "private evidence must be below a literal .local directory")
    _require(local.is_dir() and not local.is_symlink(), ".local authority is unsafe")
    return local


def _require_private_file(path: Path, label: str) -> None:
    local = _private_local_ancestor(path)
    cursor = local
    _require(stat.S_IMODE(cursor.stat().st_mode) == 0o700, ".local mode is not 0700")
    for part in path.absolute().parent.relative_to(local.absolute()).parts:
        cursor = cursor / part
        _require(
            cursor.is_dir()
            and not cursor.is_symlink()
            and stat.S_IMODE(cursor.stat().st_mode) == 0o700,
            f"{label} directory is not private mode 0700",
        )
    _require(
        path.is_file()
        and not path.is_symlink()
        and stat.S_IMODE(path.stat().st_mode) == 0o600,
        f"{label} is not a private regular file",
    )


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError(f"{label} is unreadable or malformed") from error
    _require(isinstance(value, dict), f"{label} is not an object")
    return value


def _load_storage_authority(execution_root: Path) -> dict[str, Any]:
    root = execution_root.absolute()
    local = _private_local_ancestor(root)
    _require(
        root.resolve() == execution_root.resolve()
        and root.is_dir()
        and not root.is_symlink()
        and root.resolve().is_relative_to(local.resolve())
        and stat.S_IMODE(root.stat().st_mode) == 0o700,
        "execution root is not an authoritative private directory",
    )
    for name in ("receipt-state.json", "runner.lock", "ledger.jsonl", "checkpoint.json"):
        _require_private_file(root / name, f"execution storage {name}")
    authority_path = root / "receipt-state.json"
    authority = _read_json(authority_path, "storage authority")
    _require(
        authority_path.read_bytes() == _canonical_bytes(authority),
        "storage authority is not canonical JSON",
    )
    _validate_storage_authority(authority)
    _require(
        authority["root_identity_sha256"]
        == digest({"resolved_execution_root": str(root.resolve())}),
        "storage authority is bound to a different execution root",
    )
    return authority


def _require_empty_pre_freeze_state(execution_root: Path) -> None:
    root = execution_root.absolute()
    _require((root / "ledger.jsonl").read_bytes() == b"", "execution ledger is not empty")
    _require((root / "checkpoint.json").read_bytes() == b"", "execution checkpoint is not empty")
    receipts = root / "receipts"
    _require(
        receipts.is_dir()
        and not receipts.is_symlink()
        and stat.S_IMODE(receipts.stat().st_mode) == 0o700,
        "execution receipts directory is not initialized private storage",
    )
    _require(not any(receipts.iterdir()), "execution receipts directory is not empty")
    for name in _FORBIDDEN_PRE_FREEZE_NAMES:
        path = root / name
        _require(
            not path.exists() and not path.is_symlink(),
            f"pre-freeze terminalization found forbidden {name}",
        )
    _require(
        not any(item.name.startswith("canary") for item in root.iterdir()),
        "pre-freeze terminalization found canary state",
    )


@contextmanager
def _storage_lock(execution_root: Path) -> Iterator[None]:
    lock_path = execution_root.absolute() / "runner.lock"
    _require_private_file(lock_path, "execution storage lock")
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_APPEND)
    with os.fdopen(descriptor, "ab") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def _changed_fields(expected: Any, observed: Any, prefix: str = "") -> list[str]:
    if isinstance(expected, dict) and isinstance(observed, dict):
        changed: list[str] = []
        for key in sorted(set(expected) | set(observed)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in expected or key not in observed:
                changed.append(path)
            else:
                changed.extend(_changed_fields(expected[key], observed[key], path))
        return changed
    return [] if expected == observed else [prefix or "$root"]


def _write_once(path: Path, value: dict[str, Any]) -> None:
    _require(not path.exists() and not path.is_symlink(), "pre-freeze terminal receipt already exists")
    encoded = _canonical_bytes(value)
    temporary = path.with_name(
        f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(8)}"
    )
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        _require(path.read_bytes() == encoded, "pre-freeze terminal receipt readback differs")
    finally:
        if temporary.exists():
            temporary.unlink()


def terminalize_pre_freeze_runtime_mismatch(
    *,
    qualification_receipt_path: Path,
    execution_root: Path,
    codex_binary: Path,
    model_catalog: Path,
    runtime_observer: Callable[[Path, Path], dict[str, Any]],
) -> dict[str, Any]:
    """Observe runtime identity once and terminalize only a catalog mismatch."""

    qualification_receipt_path = qualification_receipt_path.absolute()
    execution_root = execution_root.absolute()
    _require_private_file(qualification_receipt_path, "qualification receipt")
    qualification = _read_json(qualification_receipt_path, "qualification receipt")
    qualification_bytes = qualification_receipt_path.read_bytes()
    validate_receipt(qualification)
    _require(qualification["status"] == "stable_pool_ready", "qualification is not stable_pool_ready")
    with _storage_lock(execution_root):
        authority = _load_storage_authority(execution_root)
        _require_empty_pre_freeze_state(execution_root)
        receipt_path = execution_root / RECEIPT_NAME
        if receipt_path.exists() or receipt_path.is_symlink():
            _require_private_file(receipt_path, "pre-freeze terminal receipt")
            existing = _read_json(receipt_path, "pre-freeze terminal receipt")
            _require(
                receipt_path.read_bytes() == _canonical_bytes(existing),
                "pre-freeze terminal receipt is not canonical JSON",
            )
            validate_pre_freeze_terminal_receipt(existing, qualification, authority)
            _require(
                qualification_receipt_path.read_bytes() == qualification_bytes,
                "qualification receipt changed during pre-freeze receipt readback",
            )
            return existing
        expected = qualification["runtime_observation"]
        _validate_json_value(expected, "expected runtime")
        observed = runtime_observer(
            codex_binary.resolve(strict=True), model_catalog.resolve(strict=True)
        )
        _require(isinstance(observed, dict), "runtime observer did not return an object")
        _validate_json_value(observed, "observed runtime")
        changed = _changed_fields(expected, observed)
        _require(changed, "current runtime still matches the qualification receipt")
        _require(
            _REQUIRED_CHANGED_FIELDS <= set(changed),
            "runtime mismatch is not the required model-catalog identity and fetch-time mismatch",
        )
        _require(
            "model_catalog_fetched_at" in expected
            and "model_catalog_fetched_at" in observed
            and expected["model_catalog_fetched_at"]
            != observed["model_catalog_fetched_at"],
            "model catalog fetch-time identity did not change",
        )
        expected_catalog = _sha256(
            expected.get("model_catalog_sha256"), "expected model catalog"
        )
        observed_catalog = _sha256(
            observed.get("model_catalog_sha256"), "observed model catalog"
        )
        _require(expected_catalog != observed_catalog, "model catalog digest did not change")
        body = {
            "schema_name": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "status": "terminal",
            "classification": CLASSIFICATION,
            "qualification_state_sha256": qualification["state_sha256"],
            "storage_authority_sha256": authority["receipt_sha256"],
            "expected_model_catalog_sha256": expected_catalog,
            "observed_model_catalog_sha256": observed_catalog,
            "expected_runtime_sha256": digest(expected),
            "observed_runtime_sha256": digest(observed),
            "changed_fields": changed,
            "subject_invocation_starts": 0,
            "contract_frozen": False,
            "provider_calls_performed": False,
            "evaluator_invocations_performed": False,
            "task_material_accessed": False,
        }
        receipt = {**body, "receipt_sha256": digest(body)}
        validate_pre_freeze_terminal_receipt(receipt, qualification, authority)
        _require(
            qualification_receipt_path.read_bytes() == qualification_bytes,
            "qualification receipt changed during pre-freeze observation",
        )
        _write_once(receipt_path, receipt)
        return receipt


def read_and_validate_pre_freeze_terminal_receipt(
    *, qualification_receipt_path: Path, execution_root: Path
) -> dict[str, Any]:
    """Read back the write-once receipt without observing any live runtime."""

    qualification_receipt_path = qualification_receipt_path.absolute()
    execution_root = execution_root.absolute()
    _require_private_file(qualification_receipt_path, "qualification receipt")
    qualification = _read_json(qualification_receipt_path, "qualification receipt")
    authority = _load_storage_authority(execution_root)
    _require_empty_pre_freeze_state(execution_root)
    path = execution_root / RECEIPT_NAME
    _require_private_file(path, "pre-freeze terminal receipt")
    receipt = _read_json(path, "pre-freeze terminal receipt")
    _require(path.read_bytes() == _canonical_bytes(receipt), "pre-freeze terminal receipt is not canonical JSON")
    validate_pre_freeze_terminal_receipt(receipt, qualification, authority)
    return receipt
