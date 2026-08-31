"""Read-only disk-budget checks for local experiment infrastructure."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

GIB = 1024**3


class DiskSafetyError(RuntimeError):
    """Raised when disk safety cannot be established without ambiguity."""


@dataclass(frozen=True)
class DiskSafetyPolicy:
    """Project-local limits applied before a new experimental attempt."""

    minimum_free_bytes: int = 64 * GIB
    execution_headroom_bytes: int = 64 * GIB
    maximum_retained_repository_bytes: int = 64 * GIB

    @property
    def required_free_bytes(self) -> int:
        return self.minimum_free_bytes + self.execution_headroom_bytes

    def validate(self) -> None:
        values = (
            self.minimum_free_bytes,
            self.execution_headroom_bytes,
            self.maximum_retained_repository_bytes,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise DiskSafetyError("disk-safety limits must be positive integer bytes")


DEFAULT_POLICY = DiskSafetyPolicy()


def _real_directory(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    return stat.S_ISDIR(mode) and not stat.S_ISLNK(mode)


def _validate_directory_ancestors(path: Path, description: str) -> None:
    current = path.absolute()
    while True:
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise DiskSafetyError(
                    f"{description} and its existing ancestors must be real directories"
                )
        if current == current.parent:
            return
        current = current.parent


def validate_write_target(path: Path) -> None:
    """Reject a write root redirected by any existing symlink ancestor."""

    _validate_directory_ancestors(path, "experiment state root")


def discover_attempt_repositories(evidence_root: Path) -> tuple[Path, ...]:
    """Return only ``<run>/attempts/<cell>/<attempt>/repository`` directories."""

    _validate_directory_ancestors(evidence_root, "evidence root")
    try:
        evidence_root.lstat()
    except FileNotFoundError:
        return ()
    if not _real_directory(evidence_root):
        raise DiskSafetyError("evidence root must be a real directory, not a symlink")
    repositories: list[Path] = []
    try:
        runs = sorted(evidence_root.iterdir(), key=lambda path: path.name)
        for run in runs:
            attempts = run / "attempts"
            if not _real_directory(run) or not _real_directory(attempts):
                continue
            for cell in sorted(attempts.iterdir(), key=lambda path: path.name):
                if not _real_directory(cell):
                    continue
                for attempt in sorted(cell.iterdir(), key=lambda path: path.name):
                    repository = attempt / "repository"
                    if _real_directory(attempt) and _real_directory(repository):
                        repositories.append(repository)
    except OSError as error:
        raise DiskSafetyError("attempt repository discovery was incomplete") from error
    return tuple(repositories)


def _allocated_bytes(roots: tuple[Path, ...]) -> int:
    """Measure allocated blocks without following symlinks or double-counting hardlinks."""

    seen: set[tuple[int, int]] = set()
    total = 0
    stack = list(reversed(roots))
    try:
        while stack:
            path = stack.pop()
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                continue
            identity = (metadata.st_dev, metadata.st_ino)
            if identity in seen:
                continue
            seen.add(identity)
            total += metadata.st_blocks * 512
            if stat.S_ISDIR(metadata.st_mode):
                with os.scandir(path) as entries:
                    children = sorted(
                        (Path(entry.path) for entry in entries),
                        key=lambda child: child.name,
                        reverse=True,
                    )
                stack.extend(children)
            elif not stat.S_ISREG(metadata.st_mode):
                raise DiskSafetyError("attempt repository contains a special file")
    except OSError as error:
        raise DiskSafetyError("attempt repository allocation scan was incomplete") from error
    return total


def _available_bytes(path: Path) -> int:
    anchor = path
    while not anchor.exists() and anchor != anchor.parent:
        anchor = anchor.parent
    try:
        values = os.statvfs(anchor)
    except OSError as error:
        raise DiskSafetyError("filesystem free space could not be measured") from error
    available = values.f_bavail * values.f_frsize
    if available < 0:
        raise DiskSafetyError("filesystem reported invalid free space")
    return available


def cleanup_plan(evidence_root: Path) -> dict[str, object]:
    """Build an exact, read-only cleanup candidate plan; never delete anything."""

    repositories = discover_attempt_repositories(evidence_root)
    relative_paths = tuple(path.relative_to(evidence_root).as_posix() for path in repositories)
    path_bytes = ("\n".join(relative_paths) + ("\n" if relative_paths else "")).encode()
    return {
        "schema_name": "engineering-scope-guard.experiment-disk-cleanup-plan",
        "schema_version": 1,
        "mode": "read-only",
        "automatic_deletion_permitted": False,
        "deletion_authorized": False,
        "eligibility": "unclassified; ledger and receipt review required",
        "repository_count": len(relative_paths),
        "repository_allocated_bytes": _allocated_bytes(repositories),
        "target_set_sha256": hashlib.sha256(path_bytes).hexdigest(),
        "targets_relative_to_evidence_root": list(relative_paths),
    }


def disk_safety_snapshot(
    evidence_root: Path,
    *,
    filesystem_path: Path,
    policy: DiskSafetyPolicy = DEFAULT_POLICY,
) -> dict[str, object]:
    """Return a content-free safety decision for the host filesystem."""

    policy.validate()
    plan = cleanup_plan(evidence_root)
    available = _available_bytes(filesystem_path)
    retained = int(plan["repository_allocated_bytes"])
    failures: list[str] = []
    if available < policy.required_free_bytes:
        failures.append("free_space_below_execution_reserve")
    if retained > policy.maximum_retained_repository_bytes:
        failures.append("retained_attempt_repositories_over_budget")
    return {
        "schema_name": "engineering-scope-guard.experiment-disk-safety",
        "schema_version": 1,
        "status": "pass" if not failures else "fail",
        "available_bytes": available,
        "required_free_bytes": policy.required_free_bytes,
        "minimum_free_bytes": policy.minimum_free_bytes,
        "execution_headroom_bytes": policy.execution_headroom_bytes,
        "maximum_retained_repository_bytes": policy.maximum_retained_repository_bytes,
        "retained_repository_count": plan["repository_count"],
        "retained_repository_allocated_bytes": retained,
        "retained_repository_target_set_sha256": plan["target_set_sha256"],
        "failures": failures,
    }


def require_disk_safety(
    evidence_root: Path,
    *,
    filesystem_path: Path,
    policy: DiskSafetyPolicy = DEFAULT_POLICY,
) -> dict[str, object]:
    """Return the snapshot or fail closed before experimental side effects."""

    snapshot = disk_safety_snapshot(
        evidence_root, filesystem_path=filesystem_path, policy=policy
    )
    if snapshot["status"] != "pass":
        reasons = ", ".join(str(reason) for reason in snapshot["failures"])
        raise DiskSafetyError(f"disk-safety gate failed: {reasons}")
    return snapshot


def public_disk_safety_receipt(snapshot: dict[str, object]) -> dict[str, object]:
    """Remove host-specific capacity and retention metadata from public output."""

    policy = {
        key: snapshot[key]
        for key in (
            "minimum_free_bytes",
            "execution_headroom_bytes",
            "required_free_bytes",
            "maximum_retained_repository_bytes",
        )
    }
    return {
        "schema_name": "engineering-scope-guard.experiment-disk-safety-public",
        "schema_version": 1,
        "status": snapshot["status"],
        "policy_sha256": hashlib.sha256(
            json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "failures": list(snapshot["failures"]),
        "dynamic_host_metadata_withheld": True,
    }


def render_json(value: dict[str, object]) -> str:
    """Render stable JSON for command-line tools and tests."""

    return json.dumps(value, indent=2, sort_keys=True) + "\n"
