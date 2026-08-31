#!/usr/bin/env python3
"""Freeze public-safe effort-v1 pool, contract, and execution authority."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from engineering_scope_guard.pilot_contract import canonical_bytes, digest
from engineering_scope_guard.reasoning_effort_v1 import (
    RETRYABLE_INFRASTRUCTURE,
    build_contract,
)


LANGUAGES = ("c", "cpp", "cs", "go", "java", "js", "rust", "ts")
SELECTION_RULE = "first manifest-qualified SHA-256-ranked reserve task per language"
GOLD_REPLACEMENT_CLASSES = {
    "timeout",
    "evaluator_process_failure",
    "evaluator_runtime_failure",
    "official_gold_test_failure",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

try:
    from scripts.pilot_host_qualification import _docker_environment
    from scripts.pilot_runner import (
        _dataset_hashes,
        _verify_evaluator_interface,
        canonical_evaluator_python,
        resolve_dataset_task,
    )
    from scripts.reasoning_effort_v1_runner import (
        EXECUTION_CODE_CLOSURE,
        _codex_executable_identity,
        evaluator_python_identity,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from pilot_host_qualification import _docker_environment
    from pilot_runner import (
        _dataset_hashes,
        _verify_evaluator_interface,
        canonical_evaluator_python,
        resolve_dataset_task,
    )
    from reasoning_effort_v1_runner import (
        EXECUTION_CODE_CLOSURE,
        _codex_executable_identity,
        evaluator_python_identity,
    )


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _task_snapshot(dataset_revision: str, task: dict[str, Any]) -> str:
    return digest({"dataset_revision": dataset_revision, **task})


def _private_commitment(value: Any) -> str:
    """Match the private reserve builder's compact-JSON commitment format."""

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _reserve_rank(seed: str, revision: str, language: str, task_id: str) -> str:
    return hashlib.sha256(
        "\0".join((seed, revision, language, task_id)).encode()
    ).hexdigest()


def _validate_reserve(reserve: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if reserve.get("schema") != "engineering-scope-guard.private-current-runtime-reserve-v1":
        raise RuntimeError("unexpected private reserve schema")
    source = reserve.get("source")
    selection = reserve.get("selection")
    if not isinstance(source, dict) or not isinstance(selection, dict):
        raise RuntimeError("private reserve source/selection is malformed")
    revision = source.get("revision")
    seed = selection.get("seed")
    selected = selection.get("selected")
    if not isinstance(revision, str) or not revision or not isinstance(seed, str) or not seed:
        raise RuntimeError("private reserve revision/seed is malformed")
    if not isinstance(selected, list) or not all(isinstance(item, dict) for item in selected):
        raise RuntimeError("private reserve selected tasks are malformed")
    if selection.get("selection_uses_task_bodies_or_outcomes") is not False:
        raise RuntimeError("private reserve selection must be metadata-only")
    if selection.get("manifest_checks_passed") is not True:
        raise RuntimeError("reserve manifest qualification did not pass")
    if selection.get("selected_count") != len(selected) or len(selected) != 48:
        raise RuntimeError("private reserve must bind exactly 48 selected tasks")

    task_ids = [item.get("instance_id") for item in selected]
    repositories = [item.get("repo") for item in selected]
    languages = [item.get("language") for item in selected]
    if not all(isinstance(value, str) and value for value in task_ids + repositories):
        raise RuntimeError("private reserve task identity is malformed")
    if len(set(task_ids)) != len(task_ids) or len(set(repositories)) != len(repositories):
        raise RuntimeError("private reserve tasks and repositories must be distinct")
    if selection.get("selected_repository_count") != len(set(repositories)):
        raise RuntimeError("private reserve repository count disagrees with selected tasks")
    counts = dict(sorted(Counter(languages).items()))
    if counts != {language: 6 for language in LANGUAGES}:
        raise RuntimeError("private reserve must contain six tasks per frozen language")
    if selection.get("selected_by_language") != counts:
        raise RuntimeError("private reserve language counts disagree with selected tasks")
    expected_ids_commitment = _private_commitment(sorted(task_ids))
    if selection.get("selected_ids_sha256") != expected_ids_commitment:
        raise RuntimeError("private reserve selected-ID commitment mismatch")

    ranked: dict[str, list[dict[str, Any]]] = {language: [] for language in LANGUAGES}
    for item in selected:
        language = item.get("language")
        task_id = item.get("instance_id")
        manifest = item.get("manifest_sha256")
        if language not in ranked:
            raise RuntimeError("private reserve contains an unexpected language")
        if item.get("rank_commitment") != _reserve_rank(seed, revision, language, task_id):
            raise RuntimeError("private reserve rank commitment mismatch")
        if not isinstance(manifest, str) or SHA256_PATTERN.fullmatch(manifest) is None:
            raise RuntimeError("private reserve manifest commitment is malformed")
        ranked[language].append(item)
    for language in LANGUAGES:
        ranked[language].sort(
            key=lambda item: (item["rank_commitment"], item["instance_id"])
        )
    return ranked


def _validate_gold_identity(
    gold: dict[str, Any],
    reserve: dict[str, Any],
    ranked: dict[str, list[dict[str, Any]]],
    *,
    dataset_hashes: dict[str, str],
    evaluator_revision: str,
    repolaunch_revision: str,
) -> dict[str, Any]:
    if gold.get("schema") != "engineering-scope-guard.private-current-evaluator-qualification-v1":
        raise RuntimeError("unexpected gold qualification schema")
    source = gold.get("source")
    design = gold.get("design")
    if not isinstance(source, dict) or not isinstance(design, dict):
        raise RuntimeError("gold qualification source/design is malformed")
    expected_source = {
        "dataset_revision": reserve["source"]["revision"],
        "reserve_selected_ids_sha256": reserve["selection"]["selected_ids_sha256"],
        "evaluator_revision": evaluator_revision,
        "embedded_repolaunch_revision": repolaunch_revision,
        "dataset_files": dataset_hashes,
    }
    if source != expected_source:
        raise RuntimeError("gold qualification identity/commitment mismatch")
    if (
        design.get("selection") != SELECTION_RULE
        or design.get("task_body_or_model_outcome_used") is not False
        or design.get("languages") != list(LANGUAGES)
        or design.get("tasks") != 8
        or design.get("gold_repetitions_per_task") != 2
        or design.get("workers") != 1
        or design.get("timeout_seconds") != 3600
    ):
        raise RuntimeError("gold qualification design disagrees with frozen selection rule")

    audit = gold.get("replacement_audit", [])
    if not isinstance(audit, list) or not all(isinstance(item, dict) for item in audit):
        raise RuntimeError("gold replacement audit is malformed")
    audited_by_language: dict[str, list[dict[str, Any]]] = {
        language: [] for language in LANGUAGES
    }
    for item in audit:
        language = item.get("language")
        if language not in audited_by_language:
            raise RuntimeError("gold replacement audit has an unexpected language")
        audited_by_language[language].append(item)

    gold_tasks = gold.get("tasks")
    if not isinstance(gold_tasks, list) or len(gold_tasks) != 8:
        raise RuntimeError("gold qualification must contain eight tasks")
    if [task.get("language") for task in gold_tasks] != list(LANGUAGES):
        raise RuntimeError("gold tasks must follow the frozen language order")
    private_audit: list[dict[str, Any]] = []
    for gold_task, language in zip(gold_tasks, LANGUAGES, strict=True):
        replacements = sorted(
            audited_by_language[language], key=lambda item: item.get("reserve_ordinal", -1)
        )
        if len(replacements) > 2:
            raise RuntimeError("gold replacement allowance exceeded")
        for ordinal, item in enumerate(replacements):
            candidate = ranked[language][ordinal]
            classifications = item.get("classifications")
            if (
                item.get("reserve_ordinal") != ordinal
                or item.get("instance_id") != candidate["instance_id"]
                or item.get("repo") != candidate["repo"]
                or not isinstance(classifications, list)
                or not 1 <= len(classifications) <= 2
                or not all(value in GOLD_REPLACEMENT_CLASSES for value in classifications)
            ):
                raise RuntimeError("gold replacement audit is not the deterministic prefix")
        final = ranked[language][len(replacements)]
        if (
            gold_task.get("instance_id") != final["instance_id"]
            or gold_task.get("repo") != final["repo"]
            or gold_task.get("docker_image") != final["docker_image"]
        ):
            raise RuntimeError("gold task is not the deterministic first qualified reserve task")
        private_audit.append(
            {
                "language": language,
                "replacement_candidates": replacements,
                "final_task_id": final["instance_id"],
                "final_repository": final["repo"],
                "final_reserve_ordinal": len(replacements),
            }
        )
    return {
        "selection_rule": SELECTION_RULE,
        "reserve_commitment_sha256": digest(reserve),
        "reserve_selected_ids_sha256": reserve["selection"]["selected_ids_sha256"],
        "gold_receipt_commitment_sha256": digest(gold),
        "selection_audit_sha256": digest(private_audit),
        "replacement_count": len(audit),
    }


def build_artifacts(
    *,
    reserve: dict[str, Any],
    gold: dict[str, Any],
    resolved_tasks: dict[str, dict[str, Any]],
    image_ids: dict[str, str],
    dataset_hashes: dict[str, str],
    evaluator_interface: dict[str, Any],
    docker_environment: dict[str, Any],
    model_catalog_sha256: str,
    codex_executable_identity: dict[str, str],
    execution_code_files_sha256: dict[str, str],
    evaluator_python_environment_identity: dict[str, str],
    codex_version: str,
    evaluator_revision: str,
    repolaunch_revision: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return pool, contract, authorization, and sanitized qualification."""

    if set(execution_code_files_sha256) != set(EXECUTION_CODE_CLOSURE) or any(
        not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None
        for value in execution_code_files_sha256.values()
    ):
        raise RuntimeError("execution-code closure identity is malformed")
    if set(codex_executable_identity) != {"resolved_path_sha256", "file_sha256"} or any(
        not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None
        for value in codex_executable_identity.values()
    ):
        raise RuntimeError("Codex executable identity is malformed")
    if set(evaluator_python_environment_identity) != {
        "path_sha256",
        "resolved_executable_sha256",
        "version_sha256",
        "package_set_sha256",
    } or any(
        not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None
        for value in evaluator_python_environment_identity.values()
    ):
        raise RuntimeError("evaluator Python environment identity is malformed")

    ranked = _validate_reserve(reserve)
    if gold.get("status") != "complete":
        raise RuntimeError("current-evaluator gold qualification is incomplete")
    selection_integrity = _validate_gold_identity(
        gold,
        reserve,
        ranked,
        dataset_hashes=dataset_hashes,
        evaluator_revision=evaluator_revision,
        repolaunch_revision=repolaunch_revision,
    )
    gold_tasks = gold.get("tasks")
    if not isinstance(gold_tasks, list) or len(gold_tasks) != 8:
        raise RuntimeError("gold qualification must contain eight tasks")
    if any(
        len(task.get("runs", [])) != 2
        or any(
            run.get("classification") != "official_gold_success"
            for run in task["runs"]
        )
        for task in gold_tasks
    ):
        raise RuntimeError("every frozen task needs two current-evaluator gold successes")
    reserve_tasks = {
        task["instance_id"]: task for task in reserve["selection"]["selected"]
    }

    tasks: list[dict[str, Any]] = []
    identity_tasks: list[dict[str, str]] = []
    for gold_task in gold_tasks:
        task_id = gold_task["instance_id"]
        selected = reserve_tasks.get(task_id)
        resolved = resolved_tasks.get(task_id)
        image_id = image_ids.get(task_id)
        if selected is None or resolved is None or not isinstance(image_id, str):
            raise RuntimeError("gold task is absent from frozen reserve/runtime identity")
        task = {
            "task_id": task_id,
            "repository": resolved["repo"],
            "language": resolved["language"],
            "base_commit": resolved["base_commit"],
            "docker_image": resolved["docker_image"],
            "image_id": image_id,
            "problem_statement_sha256": resolved["problem_statement_sha256"],
            "manifest_sha256": selected["manifest_sha256"],
        }
        if (
            task["repository"] != gold_task["repo"]
            or task["language"] != gold_task["language"]
            or task["docker_image"] != gold_task["docker_image"]
            or resolved.get("instance_id") != task_id
        ):
            raise RuntimeError("gold receipt and dataset task identity disagree")
        snapshot = _task_snapshot(reserve["source"]["revision"], task)
        tasks.append(task)
        identity_tasks.append(
            {
                "task_id": task_id,
                "repository": task["repository"],
                "task_snapshot_sha256": snapshot,
            }
        )
    if len({task["repository"] for task in tasks}) != 8:
        raise RuntimeError("frozen effort-v1 tasks must use distinct repositories")

    runtime = {
        "model": "gpt-5.6-sol",
        "codex_version": codex_version,
        "reasoning_efforts": ["low", "medium"],
        "model_catalog_sha256": model_catalog_sha256,
        "codex_executable": codex_executable_identity,
        "docker_environment": docker_environment,
        "subject_interface": {
            "one_fresh_codex_exec_per_cell": True,
            "sandbox": "workspace-write",
            "subject_network_access": False,
            "user_config_loaded": False,
            "user_rules_loaded": False,
            "browser_apps_plugins_multi_agent_disabled": True,
        },
    }
    runtime["runtime_identity"] = digest(runtime)
    image_pool_identity = digest(
        [
            {
                "task_id": task["task_id"],
                "image_id": task["image_id"],
                "manifest_sha256": task["manifest_sha256"],
            }
            for task in sorted(tasks, key=lambda item: item["task_id"])
        ]
    )
    contract = build_contract(
        identity_tasks,
        model=runtime["model"],
        codex_version=codex_version,
        runtime_identity=runtime["runtime_identity"],
        source_revision=reserve["source"]["revision"],
        evaluator_revision=evaluator_revision,
        qualification_subject_executions=1,
        dataset_identity=f"SWE-bench-Live/MultiLang@{reserve['source']['revision']}",
        evaluator_identity="microsoft/SWE-bench-Live official evaluator",
        repolaunch_revision=repolaunch_revision,
        image_pool_identity=image_pool_identity,
    )
    pool = {
        "schema_name": "engineering-scope-guard.reasoning-effort-v1-pool",
        "schema_version": 1,
        "pool_sha256": contract["schedule"]["pool_sha256"],
        "selection_integrity_sha256": digest(selection_integrity),
        "selection_uses_task_bodies_or_model_outcomes": False,
        "tasks": sorted(tasks, key=lambda item: item["task_id"]),
    }
    source = {
        "dataset_revision": reserve["source"]["revision"],
        "evaluator_revision": evaluator_revision,
        "repolaunch_revision": repolaunch_revision,
        "dataset_snapshot_files_sha256": dataset_hashes,
        "evaluator_interface_sha256": digest(evaluator_interface),
        "evaluator_python_identity": evaluator_python_environment_identity,
        "selection_integrity": selection_integrity,
    }
    execution = {
        "one_codex_exec_per_cell": True,
        "corrective_resume_permitted": False,
        "qualification_subject_executions": 1,
        "subject_timeout_seconds": 900,
        "evaluator_timeout_seconds": 1800,
        "workers": 1,
        "stage_1_cell_count": 4,
        "maximum_subject_executions_including_qualification": 64,
        "maximum_attempts_per_cell": 2,
        "attempt_3_permitted": False,
    }
    authorization = {
        "schema_name": "engineering-scope-guard.reasoning-effort-v1-execution-authorization",
        "schema_version": 1,
        "status": "frozen-authorized",
        "execution_authorized": True,
        "authority": "explicit autonomous sprint request and D-066; strict preflight still required",
        "allowed_attempt_2_classes": sorted(RETRYABLE_INFRASTRUCTURE),
        "binding": {
            "execution_code_files_sha256": execution_code_files_sha256,
        },
        "runtime": runtime,
        "source": source,
        "execution": execution,
    }
    qualification = {
        "schema_name": "engineering-scope-guard.reasoning-effort-v1-source-qualification",
        "schema_version": 1,
        "status": "pass",
        "dataset": {
            "name": reserve["source"]["dataset"],
            "revision": reserve["source"]["revision"],
            "public_provenance": True,
            "license": "MIT",
            "objective_executable_evaluator": True,
            "contamination_risk": "medium-or-unknown; no resistance claim permitted",
            "files_sha256": dataset_hashes,
        },
        "evaluator_revision": evaluator_revision,
        "repolaunch_revision": repolaunch_revision,
        "evaluator_python_environment_sha256": digest(
            evaluator_python_environment_identity
        ),
        "reserve": {
            "eligible_tasks_after_metadata_and_historical_exclusions": reserve["selection"]["eligible_fresh_task_count"],
            "eligible_repositories_after_metadata_and_historical_exclusions": reserve["selection"]["eligible_fresh_repository_count"],
            "manifest_qualified_tasks": reserve["selection"]["selected_count"],
            "manifest_qualified_repositories": reserve["selection"]["selected_repository_count"],
            "selected_ids_sha256": reserve["selection"]["selected_ids_sha256"],
            "overflow_tasks": reserve["selection"]["overflow_count"],
            "overflow_repositories": reserve["selection"]["overflow_repository_count"],
            "overflow_ids_sha256": reserve["selection"]["overflow_ids_sha256"],
            "reserve_ids_or_bodies_emitted": False,
            "reserve_commitment_sha256": selection_integrity["reserve_commitment_sha256"],
            "selected_ids_commitment_verified": True,
        },
        "gold": {
            "tasks": 8,
            "repositories": 8,
            "languages": sorted(task["language"] for task in tasks),
            "attempts": 16,
            "official_gold_successes": 16,
            "all_tasks_repeatably_gold_successful": True,
            "task_bodies_or_model_outcomes_used_for_selection": False,
            "receipt_commitment_sha256": selection_integrity["gold_receipt_commitment_sha256"],
            "selection_audit_sha256": selection_integrity["selection_audit_sha256"],
            "replacement_count": selection_integrity["replacement_count"],
            "deterministic_selection_verified": True,
        },
        "subject_attempts": 0,
        "experimental_outcomes": 0,
    }
    return pool, contract, authorization, qualification


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--reserve", type=Path, required=True)
    parser.add_argument("--gold-receipt", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--evaluator-root", type=Path, required=True)
    parser.add_argument("--evaluator-python", type=Path)
    parser.add_argument("--model-catalog", type=Path, required=True)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--pool-output", type=Path, default=Path("experiment/reasoning_effort_v1_pool.json"))
    parser.add_argument("--contract-output", type=Path, default=Path("experiment/reasoning_effort_v1_contract.json"))
    parser.add_argument("--authorization-output", type=Path, default=Path("experiment/reasoning_effort_v1_execution_authorization.json"))
    parser.add_argument("--qualification-output", type=Path, default=Path("experiment/reasoning_effort_v1_source_qualification.json"))
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    root = args.root.resolve()
    reserve = _read(args.reserve)
    gold = _read(args.gold_receipt)
    evaluator_root = args.evaluator_root.resolve()
    dataset_root = args.dataset_root.resolve()
    evaluator_python = canonical_evaluator_python(evaluator_root, args.evaluator_python)
    dataset_hashes = _dataset_hashes(dataset_root)
    evaluator_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=evaluator_root, text=True, capture_output=True, check=True
    ).stdout.strip()
    repolaunch_revision = subprocess.run(
        ["git", "-C", str(evaluator_root / "launch"), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    if gold.get("status") != "complete":
        raise RuntimeError("current-evaluator gold qualification is incomplete")
    _validate_gold_identity(
        gold,
        reserve,
        _validate_reserve(reserve),
        dataset_hashes=dataset_hashes,
        evaluator_revision=evaluator_revision,
        repolaunch_revision=repolaunch_revision,
    )
    resolved = {
        task["instance_id"]: resolve_dataset_task(
            root,
            evaluator_python,
            dataset_root,
            task["language"],
            task["instance_id"],
            "resolve",
        )
        for task in gold["tasks"]
    }
    image_ids = {
        task["instance_id"]: subprocess.run(
            ["docker", "image", "inspect", task["docker_image"], "--format", "{{.Id}}"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        for task in gold["tasks"]
    }
    resolved_codex, codex_executable_identity = _codex_executable_identity(
        args.codex_binary
    )
    codex_version = subprocess.run(
        [str(resolved_codex), "--version"], text=True, capture_output=True, check=True
    ).stdout.strip().removeprefix("codex-cli ")
    execution_code_files_sha256 = {
        relative: _sha256(root / relative) for relative in EXECUTION_CODE_CLOSURE
    }
    pool, contract, authorization, qualification = build_artifacts(
        reserve=reserve,
        gold=gold,
        resolved_tasks=resolved,
        image_ids=image_ids,
        dataset_hashes=dataset_hashes,
        evaluator_interface=_verify_evaluator_interface(evaluator_root),
        docker_environment=_docker_environment(),
        model_catalog_sha256=_sha256(args.model_catalog),
        codex_executable_identity=codex_executable_identity,
        execution_code_files_sha256=execution_code_files_sha256,
        evaluator_python_environment_identity=evaluator_python_identity(
            evaluator_python
        ),
        codex_version=codex_version,
        evaluator_revision=evaluator_revision,
        repolaunch_revision=repolaunch_revision,
    )
    pool_path = root / args.pool_output
    contract_path = root / args.contract_output
    _write(pool_path, pool)
    _write(contract_path, contract)
    authorization["binding"].update({
        "contract_path": args.contract_output.as_posix(),
        "contract_sha256": contract["contract_sha256"],
        "contract_file_sha256": _sha256(contract_path),
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "pool_path": args.pool_output.as_posix(),
        "pool_sha256": pool["pool_sha256"],
        "pool_file_sha256": _sha256(pool_path),
    })
    authorization["authorization_sha256"] = digest(authorization)
    _write(root / args.authorization_output, authorization)
    _write(root / args.qualification_output, qualification)
    print(json.dumps({
        "status": "frozen",
        "tasks": 8,
        "cells": 32,
        "contract_sha256": contract["contract_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "pool_sha256": pool["pool_sha256"],
        "subject_attempts": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
