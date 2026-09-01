#!/usr/bin/env python3
"""Capture or verify private evaluator-environment lock artifacts."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
from typing import Any

from engineering_scope_guard.evaluator_environment import (
    build_receipt,
    canonical_bytes,
    digest,
    observe_python_packages,
    validate_receipt,
)


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def content_tree_hash(root: Path) -> str:
    manifest = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("content tree contains a symlink")
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        manifest.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "executable": bool(path.stat().st_mode & 0o111),
            }
        )
    if not manifest:
        raise ValueError("content tree contains no files")
    return digest(manifest)


def checked(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"command failed ({command[0]}): {detail}")
    return completed.stdout.strip()


def write_private(path: Path, value: bytes) -> None:
    if ".local" not in path.parts:
        raise ValueError("evaluator environment artifacts must remain below .local")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def parse_pairs(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        name, separator, version = value.partition("=")
        if not separator or not name or not version or name in parsed:
            raise ValueError(f"invalid or duplicate NAME=VERSION value: {value!r}")
        parsed[name] = version
    return parsed


def package_lock(python: Path, output: Path) -> dict[str, Any]:
    packages = [
        package
        for package in observe_python_packages(python)
        if package["name"] not in {"launch", "swebench"}
    ]
    lines = [f"{package['name']}=={package['version']}" for package in packages]
    content = ("\n".join(lines) + "\n").encode()
    write_private(output, content)
    return {
        "package_count": len(packages),
        "requirements_sha256": hashlib.sha256(content).hexdigest(),
    }


_CONTAINER_OBSERVATION = r"""
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform

def sha256_file(path):
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

packages = [
    {"name": distribution.metadata["Name"], "version": distribution.version}
    for distribution in metadata.distributions()
    if distribution.metadata["Name"]
]
system_packages = []
status = Path("/var/lib/dpkg/status")
if status.exists():
    for paragraph in status.read_text(errors="replace").split("\n\n"):
        fields = {}
        for line in paragraph.splitlines():
            name, separator, value = line.partition(": ")
            if separator:
                fields[name] = value
        if fields.get("Status") == "install ok installed":
            system_packages.append(
                {"name": fields["Package"], "version": fields["Version"]}
            )
print(json.dumps({
    "python": {
        "version": platform.python_version(),
        "executable_sha256": sha256_file(os.path.realpath(os.sys.executable)),
        "packages": packages,
    },
    "system_packages": system_packages,
    "toolchains": {"platform": platform.platform()},
}, sort_keys=True))
"""


def load_environment_observation(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) != {
        "python",
        "system_packages",
        "toolchains",
        "observation",
    }:
        raise ValueError("container environment observation fields drifted")
    if not isinstance(value["observation"], dict):
        raise ValueError("container observation metadata is malformed")
    return value


def observe_container(
    image: str, platform_name: str, worker_id: str, output: Path
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            platform_name,
            image,
            "python",
            "-c",
            _CONTAINER_OBSERVATION,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"container environment observation failed: {detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("container environment observation is not JSON") from error
    value["observation"] = {
        "observed_at": datetime.now(UTC).isoformat(),
        "worker_id": worker_id,
        "container_image": image,
        "platform": platform_name,
    }
    write_private(output, canonical_bytes(value))
    return {
        "package_count": len(value["python"]["packages"]),
        "system_package_count": len(value["system_packages"]),
        "worker_id": worker_id,
    }


def capture(args: argparse.Namespace) -> dict[str, Any]:
    qualification = json.loads(args.qualification.read_text())
    source = qualification["source"]
    selected = sorted(
        [*qualification["selection"]["primary"], *qualification["selection"]["alternates"]],
        key=lambda item: item["slot"],
    )
    lock_files = sorted(args.lock_config_file or [args.requirements_lock])
    lock_config_sha256 = digest(
        [
            {"path": str(path), "sha256": sha256_file(path)}
            for path in lock_files
        ]
    )
    environment = (
        load_environment_observation(args.environment_observation)
        if args.environment_observation
        else None
    )
    package_manifest = (
        environment["python"]["packages"]
        if environment
        else observe_python_packages(args.python)
    )
    python_version = (
        environment["python"]["version"]
        if environment
        else checked(
            [str(args.python), "-c", "import platform; print(platform.python_version())"]
        )
    )
    executable_sha256 = (
        environment["python"]["executable_sha256"]
        if environment
        else sha256_file(
            Path(checked([str(args.python), "-c", "import sys; print(sys.executable)"]))
        )
    )
    runner_files = sorted(args.runner_file)
    runner_file_manifest = [
        {"path": str(path), "sha256": sha256_file(path)} for path in runner_files
    ]
    runner_config = json.loads(args.runner_config.read_text())
    images = [
        {"name": f"slot-{item['slot']:02d}", "resolved_ref": item["resolved_image"]}
        for item in selected
    ]
    if args.evaluator_image:
        images.append(
            {"name": "evaluator-runner", "resolved_ref": args.evaluator_image}
        )
    tasks = [
        {
            "task_identity": digest(
                {
                    "slot": item["slot"],
                    "instance_id": item["instance_id"],
                    "repository": item["repo"],
                }
            ),
            "image_name": f"slot-{item['slot']:02d}",
            "inputs": {
                "dataset_revision": source["dataset_revision"],
                "language": item["language"],
                "repository": item["repo"],
            },
        }
        for item in selected
    ]
    system_packages = (
        environment["system_packages"]
        if environment
        else [
            {"name": name, "version": version}
            for name, version in parse_pairs(args.system_package).items()
        ]
    )
    toolchains = (
        environment["toolchains"]
        if environment
        else parse_pairs(args.toolchain)
    )
    observation = {
        "observed_at": datetime.now(UTC).isoformat(),
        "worker_id": args.worker_id,
        "hostname": platform.node(),
        "process_id": os.getpid(),
    }
    if args.python:
        observation["temporary_path"] = str(args.python.parent.parent)
    receipt = build_receipt(
        source={
            "repository": args.evaluator_repository,
            "revision": source["evaluator_revision"],
            "tree_sha256": (
                args.evaluator_tree_sha256 or source["evaluator_tree_sha256"]
            ),
            "lock_config_sha256": lock_config_sha256,
        },
        images=images,
        python={
            "version": python_version,
            "executable_sha256": executable_sha256,
            "packages": package_manifest,
        },
        system_packages=system_packages,
        toolchains=toolchains,
        runner={
            "source_revision": checked(["git", "rev-parse", "HEAD"], cwd=args.root),
            "source_sha256": digest(runner_file_manifest),
            "config_sha256": digest(runner_config),
            "campaign_clock_version": args.campaign_clock_version,
        },
        tasks=tasks,
        observation=observation,
    )
    write_private(args.output, canonical_bytes(receipt))
    return {
        "global_environment_sha256": receipt["global_environment_sha256"],
        "package_count": len(package_manifest),
        "receipt_sha256": receipt["receipt_sha256"],
        "task_count": len(tasks),
    }


def verify(path: Path) -> dict[str, Any]:
    receipt = json.loads(path.read_text())
    validate_receipt(receipt)
    return {
        "global_environment_sha256": receipt["global_environment_sha256"],
        "receipt_sha256": receipt["receipt_sha256"],
        "status": "pass",
    }


def validate_gold_result(results: Any, report: Any, instance_id: str) -> None:
    if not isinstance(results, dict) or not isinstance(report, dict):
        raise ValueError("gold evaluator output is malformed")
    if (
        results.get("submitted") != 1
        or results.get("success") != 1
        or results.get("failure") != 0
        or results.get("error") != 0
        or results.get("incomplete") != 0
        or results.get("success_ids") != [instance_id]
        or report.get("instance_id") != instance_id
        or report.get("resolved") is not True
    ):
        raise ValueError("gold evaluator did not produce one resolved success")


def seal_gold_preflight(args: argparse.Namespace) -> dict[str, Any]:
    environment = json.loads(args.environment_receipt.read_text())
    validate_receipt(environment)
    qualification = json.loads(args.qualification.read_text())
    alternates = qualification.get("selection", {}).get("alternates")
    if not isinstance(alternates, list):
        raise ValueError("qualification alternates are malformed")
    matches = [item for item in alternates if item.get("slot") == args.slot]
    if len(matches) != 1:
        raise ValueError("gold preflight slot is not one frozen alternate")
    selected = matches[0]
    task_identity = digest(
        {
            "slot": selected["slot"],
            "instance_id": selected["instance_id"],
            "repository": selected["repo"],
        }
    )
    expected_task_image = next(
        image["resolved_ref"]
        for image in environment["e2_images"]
        if image["name"] == f"slot-{args.slot:02d}"
    )
    if expected_task_image != selected["resolved_image"]:
        raise ValueError("gold task image differs from the environment receipt")
    expected_runner_image = next(
        image["resolved_ref"]
        for image in environment["e2_images"]
        if image["name"] == "evaluator-runner"
    )
    if expected_runner_image != args.evaluator_image:
        raise ValueError("gold evaluator image differs from the environment receipt")
    results_path = args.output_dir / "results.json"
    reports = sorted(args.output_dir.glob("*/report.json"))
    if len(reports) != 1:
        raise ValueError("gold evaluator report is absent or ambiguous")
    results = json.loads(results_path.read_text())
    report = json.loads(reports[0].read_text())
    validate_gold_result(results, report, selected["instance_id"])
    if args.remaining_container_count != 0:
        raise ValueError("gold evaluator cleanup left a task container")
    artifacts = {
        path.relative_to(args.output_dir).as_posix(): sha256_file(path)
        for path in sorted(args.output_dir.rglob("*"))
        if path.is_file()
    }
    body = {
        "schema_name": "engineering-scope-guard.evaluator-environment-gold-preflight",
        "schema_version": 1,
        "status": "pass",
        "slot": args.slot,
        "task_identity": task_identity,
        "task_environment_sha256": environment["task_environment_sha256s"][task_identity],
        "global_environment_sha256": environment["global_environment_sha256"],
        "evaluator_image": args.evaluator_image,
        "task_image": expected_task_image,
        "qualification_receipt_sha256": sha256_file(args.qualification),
        "environment_receipt_sha256": environment["receipt_sha256"],
        "artifact_sha256": artifacts,
        "remaining_container_count": args.remaining_container_count,
    }
    receipt = {**body, "receipt_sha256": digest(body)}
    write_private(args.output, canonical_bytes(receipt))
    return {
        "artifact_count": len(artifacts),
        "receipt_sha256": receipt["receipt_sha256"],
        "status": "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    lock = subparsers.add_parser("package-lock")
    lock.add_argument("--python", type=Path, required=True)
    lock.add_argument("--output", type=Path, required=True)
    container = subparsers.add_parser("container-observe")
    container.add_argument("--image", required=True)
    container.add_argument("--platform", default="linux/amd64")
    container.add_argument("--worker-id", required=True)
    container.add_argument("--output", type=Path, required=True)
    tree = subparsers.add_parser("tree-hash")
    tree.add_argument("--root", type=Path, required=True)
    gold = subparsers.add_parser("gold-receipt")
    gold.add_argument("--environment-receipt", type=Path, required=True)
    gold.add_argument("--qualification", type=Path, required=True)
    gold.add_argument("--slot", type=int, required=True)
    gold.add_argument("--evaluator-image", required=True)
    gold.add_argument("--output-dir", type=Path, required=True)
    gold.add_argument("--remaining-container-count", type=int, required=True)
    gold.add_argument("--output", type=Path, required=True)
    build = subparsers.add_parser("capture")
    build.add_argument("--root", type=Path, default=Path("."))
    build.add_argument("--qualification", type=Path, required=True)
    build.add_argument("--evaluator-repository", required=True)
    environment_group = build.add_mutually_exclusive_group(required=True)
    environment_group.add_argument("--python", type=Path)
    environment_group.add_argument("--environment-observation", type=Path)
    build.add_argument("--requirements-lock", type=Path, required=True)
    build.add_argument("--lock-config-file", type=Path, action="append")
    build.add_argument("--evaluator-tree-sha256")
    build.add_argument("--runner-file", type=Path, action="append", required=True)
    build.add_argument("--runner-config", type=Path, required=True)
    build.add_argument("--evaluator-image")
    build.add_argument("--system-package", action="append", default=[])
    build.add_argument("--toolchain", action="append", default=[])
    build.add_argument("--campaign-clock-version", required=True)
    build.add_argument("--worker-id", required=True)
    build.add_argument("--output", type=Path, required=True)
    check = subparsers.add_parser("verify")
    check.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "package-lock":
        result = package_lock(args.python, args.output)
    elif args.command == "container-observe":
        result = observe_container(
            args.image, args.platform, args.worker_id, args.output
        )
    elif args.command == "tree-hash":
        result = {"tree_sha256": content_tree_hash(args.root)}
    elif args.command == "gold-receipt":
        result = seal_gold_preflight(args)
    elif args.command == "capture":
        args.root = args.root.resolve()
        result = capture(args)
    else:
        result = verify(args.receipt)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
