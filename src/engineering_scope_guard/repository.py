"""Filesystem snapshots and deterministic structural measurements."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import stat
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

EXCLUDED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}

SNAPSHOT_SCHEMA_VERSION = 2
LOC_DEFINITION_VERSION = "strict-utf8-lines-v1"
INFRASTRUCTURE_PATTERN_SET_VERSION = "candidate-infrastructure-paths-v1"

_PYTHON_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_PYTHON_NORMALIZE = re.compile(r"[-_.]+")


class SnapshotError(RuntimeError):
    """Raised when a complete, trustworthy snapshot cannot be produced."""


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_text(value: str) -> str:
    return _hash_bytes(value.encode("utf-8"))


def _read_stable(path: Path) -> tuple[bytes, os.stat_result]:
    for _attempt in range(2):
        before = path.stat(follow_symlinks=False)
        data = path.read_bytes()
        after = path.stat(follow_symlinks=False)
        signature_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        signature_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if signature_before == signature_after:
            return data, after
    raise SnapshotError(f"file changed while being read: {path}")


def _file_entry(path: Path, relative: str) -> dict[str, Any]:
    try:
        data, _metadata = _read_stable(path)
    except OSError as error:
        raise SnapshotError(f"cannot read {relative}: {error.strerror or error}") from error

    text_metadata: dict[str, Any] | None = None
    if b"\0" not in data:
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            lines = decoded.splitlines(keepends=True)
            text_metadata = {
                "line_count": len(lines),
                "line_hashes": [_hash_bytes(line.encode("utf-8")) for line in lines],
            }

    return {
        "path": relative,
        "kind": "file",
        "sha256": _hash_bytes(data),
        "bytes": len(data),
        "text": text_metadata,
    }


def _symlink_entry(path: Path, relative: str) -> dict[str, Any]:
    try:
        target = os.readlink(path)
    except OSError as error:
        raise SnapshotError(f"cannot read symlink {relative}: {error.strerror or error}") from error
    encoded = os.fsencode(target)
    return {
        "path": relative,
        "kind": "symlink",
        "sha256": _hash_bytes(encoded),
        "bytes": len(encoded),
        "text": None,
    }


def _walk_entries(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []

    def visit(directory: Path) -> None:
        try:
            children = sorted(os.scandir(directory), key=lambda child: child.name)
        except OSError as error:
            relative = directory.relative_to(root).as_posix() or "."
            raise SnapshotError(f"cannot scan {relative}: {error.strerror or error}") from error

        for child in children:
            path = Path(child.path)
            relative = path.relative_to(root).as_posix()
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as error:
                raise SnapshotError(f"cannot stat {relative}: {error.strerror or error}") from error

            mode = metadata.st_mode
            if stat.S_ISLNK(mode):
                entries.append(_symlink_entry(path, relative))
            elif stat.S_ISDIR(mode):
                if child.name not in EXCLUDED_DIRECTORIES:
                    visit(path)
            elif stat.S_ISREG(mode):
                entries.append(_file_entry(path, relative))
            else:
                entries.append(
                    {
                        "path": relative,
                        "kind": "special",
                        "sha256": None,
                        "bytes": metadata.st_size,
                        "text": None,
                    }
                )
                warnings.append(f"special filesystem entry was not read: {relative}")

    visit(root)
    return entries, warnings


def _python_dependency(requirement: str) -> tuple[str, str] | None:
    match = _PYTHON_NAME.match(requirement)
    if not match:
        return None
    name = _PYTHON_NORMALIZE.sub("-", match.group(1)).lower()
    return name, _hash_text(requirement.strip())


def _package_json_dependencies(data: bytes, relative: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        return {}, [f"cannot parse dependency manifest {relative}: {type(error).__name__}"]
    if not isinstance(payload, dict):
        return {}, [f"dependency manifest {relative} top-level JSON is not an object"]

    section_map = {
        "dependencies": "runtime",
        "devDependencies": "development",
        "optionalDependencies": "runtime-optional",
        "peerDependencies": "peer",
    }
    scopes: dict[str, dict[str, str]] = {}
    for source, target in section_map.items():
        values = payload.get(source, {})
        if not isinstance(values, dict):
            warnings.append(f"dependency section {relative}:{source} is not an object")
            continue
        scopes[target] = {
            str(name): _hash_text(str(specification))
            for name, specification in sorted(values.items())
            if isinstance(name, str)
        }
    return {"path": relative, "ecosystem": "npm", "scopes": scopes}, warnings


def _pyproject_dependencies(data: bytes, relative: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    try:
        payload = tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        return {}, [f"cannot parse dependency manifest {relative}: {type(error).__name__}"]

    scopes: dict[str, dict[str, str]] = {}

    def add_requirements(scope: str, values: object) -> None:
        if not isinstance(values, list):
            warnings.append(f"dependency section {relative}:{scope} is not an array")
            return
        dependencies: dict[str, str] = {}
        for value in values:
            if isinstance(value, dict) and "include-group" in value:
                continue
            if not isinstance(value, str):
                warnings.append(f"unsupported dependency entry in {relative}:{scope}")
                continue
            parsed = _python_dependency(value)
            if parsed is None:
                warnings.append(f"unrecognized dependency in {relative}:{scope}")
                continue
            dependencies[parsed[0]] = parsed[1]
        scopes[scope] = dict(sorted(dependencies.items()))

    project = payload.get("project", {})
    if isinstance(project, dict):
        if "dependencies" in project:
            add_requirements("runtime", project["dependencies"])
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group, values in sorted(optional.items()):
                add_requirements(f"optional:{group}", values)
        elif optional:
            warnings.append(f"dependency section {relative}:optional-dependencies is not a table")
    elif project:
        warnings.append(f"dependency section {relative}:project is not a table")

    groups = payload.get("dependency-groups", {})
    if isinstance(groups, dict):
        for group, values in sorted(groups.items()):
            add_requirements(f"development:{group}", values)
    elif groups:
        warnings.append(f"dependency section {relative}:dependency-groups is not a table")

    return {"path": relative, "ecosystem": "python", "scopes": scopes}, warnings


def _extract_manifests(
    root: Path, entries: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    manifests: list[dict[str, Any]] = []
    warnings: list[str] = []
    for entry in entries:
        if entry["kind"] != "file":
            continue
        relative = entry["path"]
        path = root / PurePosixPath(relative)
        try:
            data, _metadata = _read_stable(path)
        except OSError as error:
            raise SnapshotError(f"cannot reread dependency manifest {relative}: {error}") from error
        if _hash_bytes(data) != entry["sha256"]:
            raise SnapshotError(f"dependency manifest changed during snapshot: {relative}")
        if path.name == "package.json":
            manifest, manifest_warnings = _package_json_dependencies(data, relative)
        elif path.name == "pyproject.toml":
            manifest, manifest_warnings = _pyproject_dependencies(data, relative)
        else:
            continue
        if manifest:
            manifests.append(manifest)
        warnings.extend(manifest_warnings)
    return sorted(manifests, key=lambda item: item["path"]), warnings


def snapshot_repository(root: Path, label: str) -> dict[str, Any]:
    """Create a content-free structural snapshot of *root*."""

    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise SnapshotError(f"repository root is not a directory: {resolved}")
    entries, warnings = _walk_entries(resolved)
    manifests, manifest_warnings = _extract_manifests(resolved, entries)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "kind": "repository_snapshot",
        "label": label,
        "measurement_definition": {
            "loc": LOC_DEFINITION_VERSION,
            "text": "regular file with strict UTF-8 decoding and no NUL byte",
            "lines": "Python splitlines(keepends=True); replacements count as deletions plus additions",
            "non_text": "binary, symlink, and special entries contribute zero LOC",
            "symlinks": "record link target metadata; never follow the target",
        },
        "entries": entries,
        "dependencies": manifests,
        "warnings": sorted(warnings + manifest_warnings),
    }


def _entry_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return any(before.get(key) != after.get(key) for key in ("kind", "sha256", "bytes"))


def _line_delta(before: dict[str, Any] | None, after: dict[str, Any] | None) -> tuple[int, int]:
    old = before.get("text") if before else None
    new = after.get("text") if after else None
    if old is None and new is None:
        return 0, 0
    if old is None:
        return int(new["line_count"]), 0
    if new is None:
        return 0, int(old["line_count"])

    additions = deletions = 0
    matcher = difflib.SequenceMatcher(
        None,
        old["line_hashes"],
        new["line_hashes"],
        autojunk=False,
    )
    for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if operation in {"insert", "replace"}:
            additions += new_end - new_start
        if operation in {"delete", "replace"}:
            deletions += old_end - old_start
    return additions, deletions


def is_test_file(path: str) -> bool:
    pure = PurePosixPath(path)
    segments = set(pure.parts[:-1])
    if segments.intersection({"test", "tests", "__tests__"}):
        return True
    name = pure.name
    stem = pure.stem
    return (
        stem.startswith("test_")
        or stem.endswith("_test")
        or ".test." in name
        or ".spec." in name
    )


def infrastructure_pattern(path: str) -> str | None:
    pure = PurePosixPath(path)
    name = pure.name
    if name == "Dockerfile" or name.startswith("Dockerfile."):
        return "dockerfile-basename-anywhere"
    if name in {
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        ".gitlab-ci.yml",
        "Jenkinsfile",
        "Chart.yaml",
        "fly.toml",
        "vercel.json",
        "netlify.toml",
    }:
        return "known-config-basename-anywhere"
    if name.endswith(".tf"):
        return "terraform-extension-anywhere"
    if path.startswith((".circleci/", "terraform/", "k8s/", "kubernetes/", "helm/")):
        return "known-infrastructure-directory-prefix-at-root"
    if (
        len(pure.parts) == 3
        and pure.parts[:2] == (".github", "workflows")
        and pure.suffix in {".yml", ".yaml"}
    ):
        return "github-workflow-yaml-direct-child"
    return None


def is_infrastructure_artifact(path: str) -> bool:
    return infrastructure_pattern(path) is not None


def _flatten_dependencies(snapshot: dict[str, Any]) -> dict[tuple[str, str, str], str]:
    flattened: dict[tuple[str, str, str], str] = {}
    for manifest in snapshot.get("dependencies", []):
        for scope, dependencies in manifest["scopes"].items():
            for name, specification in dependencies.items():
                flattened[(manifest["path"], scope, name)] = specification
    return flattened


def compare_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
    instruction_files: list[str],
) -> dict[str, Any]:
    """Compare two snapshots and return deterministic facts and review signals."""

    old_entries = {entry["path"]: entry for entry in before["entries"]}
    new_entries = {entry["path"]: entry for entry in after["entries"]}
    old_paths = set(old_entries)
    new_paths = set(new_entries)
    added = sorted(new_paths - old_paths)
    deleted = sorted(old_paths - new_paths)
    modified = sorted(
        path
        for path in old_paths & new_paths
        if _entry_changed(old_entries[path], new_entries[path])
    )

    loc_added = loc_deleted = 0
    for path in added:
        add, delete = _line_delta(None, new_entries[path])
        loc_added += add
        loc_deleted += delete
    for path in deleted:
        add, delete = _line_delta(old_entries[path], None)
        loc_added += add
        loc_deleted += delete
    for path in modified:
        add, delete = _line_delta(old_entries[path], new_entries[path])
        loc_added += add
        loc_deleted += delete

    changed_paths = added + deleted + modified
    changed_kind_counts = {"text": 0, "binary": 0, "symlink": 0, "special": 0}
    for path in changed_paths:
        entries = [entry for entry in (old_entries.get(path), new_entries.get(path)) if entry]
        if any(entry["kind"] == "symlink" for entry in entries):
            changed_kind_counts["symlink"] += 1
        elif any(entry["kind"] == "special" for entry in entries):
            changed_kind_counts["special"] += 1
        elif any(entry.get("text") is None for entry in entries):
            changed_kind_counts["binary"] += 1
        else:
            changed_kind_counts["text"] += 1
    test_delta = {
        "added": [path for path in added if is_test_file(path)],
        "deleted": [path for path in deleted if is_test_file(path)],
        "modified": [path for path in modified if is_test_file(path)],
    }

    instruction_delta: list[dict[str, Any]] = []
    for path in sorted(set(instruction_files)):
        old = old_entries.get(path)
        new = new_entries.get(path)
        old_bytes = int(old["bytes"]) if old else 0
        new_bytes = int(new["bytes"]) if new else 0
        if old_bytes != new_bytes:
            instruction_delta.append(
                {
                    "path": path,
                    "before_bytes": old_bytes,
                    "after_bytes": new_bytes,
                    "delta_bytes": new_bytes - old_bytes,
                }
            )

    old_dependencies = _flatten_dependencies(before)
    new_dependencies = _flatten_dependencies(after)
    old_keys = set(old_dependencies)
    new_keys = set(new_dependencies)

    def dependency_record(key: tuple[str, str, str], **extra: str) -> dict[str, str]:
        manifest, scope, name = key
        return {"manifest": manifest, "scope": scope, "name": name, **extra}

    dependency_delta = {
        "added": [
            dependency_record(key, specification_sha256=new_dependencies[key])
            for key in sorted(new_keys - old_keys)
        ],
        "removed": [
            dependency_record(key, specification_sha256=old_dependencies[key])
            for key in sorted(old_keys - new_keys)
        ],
        "changed": [
            dependency_record(
                key,
                before_sha256=old_dependencies[key],
                after_sha256=new_dependencies[key],
            )
            for key in sorted(old_keys & new_keys)
            if old_dependencies[key] != new_dependencies[key]
        ],
    }

    infrastructure_candidates = [
        {"path": path, "pattern_id": infrastructure_pattern(path)}
        for path in added
        if infrastructure_pattern(path) is not None
    ]
    runtime_added = [
        item
        for item in dependency_delta["added"]
        if item["scope"] in {"runtime", "runtime-optional"}
    ]

    signals: list[dict[str, Any]] = []
    if len(runtime_added) >= 2:
        signals.append(
            {
                "rule_id": "multiple_runtime_dependencies_added",
                "count": len(runtime_added),
                "dependencies": runtime_added,
            }
        )
    for item in instruction_delta:
        delta = item["delta_bytes"]
        before_bytes = item["before_bytes"]
        if delta >= 4096 and (before_bytes == 0 or delta / before_bytes >= 0.25):
            signals.append({"rule_id": "substantial_instruction_growth", **item})
    for candidate in infrastructure_candidates:
        signals.append(
            {
                "rule_id": "candidate_infrastructure_artifact",
                "pattern_set_version": INFRASTRUCTURE_PATTERN_SET_VERSION,
                **candidate,
            }
        )

    signals.sort(key=lambda item: (item["rule_id"], item.get("path", "")))
    return {
        "files": {
            "added": added,
            "deleted": deleted,
            "modified": modified,
            "counts": {
                "added": len(added),
                "deleted": len(deleted),
                "modified": len(modified),
            },
        },
        "loc": {
            "definition_version": LOC_DEFINITION_VERSION,
            "added": loc_added,
            "deleted": loc_deleted,
            "changed_entry_kinds": changed_kind_counts,
        },
        "dependencies": dependency_delta,
        "tests": test_delta,
        "instructions": instruction_delta,
        "infrastructure": {
            "pattern_set_version": INFRASTRUCTURE_PATTERN_SET_VERSION,
            "candidates": infrastructure_candidates,
        },
        "candidate_review_events": signals,
        "snapshot_warnings": sorted(set(before.get("warnings", []) + after.get("warnings", []))),
        "changed_paths": sorted(changed_paths),
    }
