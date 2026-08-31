"""Deterministic state for outcome-blind task/evaluator qualification."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from engineering_scope_guard.experiment import ExperimentConfigurationError

SCHEMA_NAME = "engineering-scope-guard.evaluator-stable-qualification"
SCHEMA_VERSION = 2
LANGUAGES = ("c", "cpp", "cs", "go", "java", "js", "rust", "ts")
STAGES = ("q1_environment", "q2_repeated_validation", "q3_gold", "q4_clean_gold")
FAILURE_CLASSES = (
    "build_environment_failure",
    "flaky_validation",
    "gold_patch_evaluation_failure",
    "evaluator_runtime_failure",
    "infrastructure_timeout",
)
MINIMUM_QUALIFIED_CLUSTERS = 10
TARGET_PRIMARY_CLUSTERS = 12
TARGET_ALTERNATE_CLUSTERS = 4
TARGET_QUALIFIED_CLUSTERS = TARGET_PRIMARY_CLUSTERS + TARGET_ALTERNATE_CLUSTERS
MAXIMUM_CANDIDATES = 48


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def canonical_json(value: Any) -> bytes:
    """Return the stable encoding used by private commitments and receipts."""

    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qualification_rank(seed: str, revision: str, language: str, instance_id: str) -> str:
    return hashlib.sha256(
        "\0".join((seed, revision, language, instance_id)).encode()
    ).hexdigest()


def seal_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Bind the complete mutable snapshot to a self-excluding state digest."""

    receipt.pop("state_sha256", None)
    receipt["state_sha256"] = sha256_value(receipt)
    return receipt


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git_revision(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _selected_tasks(reserve: dict[str, Any]) -> list[dict[str, Any]]:
    selection = reserve.get("selection")
    _require(isinstance(selection, dict), "private reserve selection is malformed")
    selected = selection.get("selected")
    _require(isinstance(selected, list), "private reserve tasks are malformed")
    _require(len(selected) == MAXIMUM_CANDIDATES, "private reserve must contain 48 tasks")

    source = reserve.get("source")
    _require(isinstance(source, dict), "private reserve source is malformed")
    seed = selection.get("seed")
    revision = source.get("revision")
    _require(isinstance(seed, str) and bool(seed), "private reserve seed is missing")
    _require(isinstance(revision, str) and bool(revision), "private reserve revision is missing")
    required = {
        "instance_id",
        "repo",
        "language",
        "docker_image",
        "rank_commitment",
        "manifest_sha256",
    }
    normalized: list[dict[str, Any]] = []
    for task in selected:
        _require(isinstance(task, dict), "private reserve task is malformed")
        _require(required <= set(task), "private reserve task fields are incomplete")
        _require(task["language"] in LANGUAGES, "private reserve language is invalid")
        for field in required:
            _require(
                isinstance(task[field], str) and bool(task[field]),
                f"private reserve task {field} is invalid",
            )
        _require(
            task["rank_commitment"]
            == qualification_rank(seed, revision, task["language"], task["instance_id"]),
            "private reserve task rank commitment drifted",
        )
        normalized.append({field: task[field] for field in sorted(required)})

    ids = [task["instance_id"] for task in normalized]
    repos = [task["repo"] for task in normalized]
    _require(len(set(ids)) == len(ids), "private reserve repeats a task")
    _require(len(set(repos)) == len(repos), "private reserve repeats a repository")
    _require(
        sha256_value(sorted(ids)) == selection.get("selected_ids_sha256"),
        "private reserve selected-ID commitment drifted",
    )
    counts = Counter(task["language"] for task in normalized)
    _require(
        counts == Counter({language: 6 for language in LANGUAGES}),
        "private reserve language allocation drifted",
    )
    return normalized


def deterministic_candidate_order(reserve: dict[str, Any]) -> list[dict[str, Any]]:
    """Reuse the frozen language ranks in deterministic round-robin order."""

    selected = _selected_tasks(reserve)
    by_language = {
        language: sorted(
            (task for task in selected if task["language"] == language),
            key=lambda task: (task["rank_commitment"], task["instance_id"]),
        )
        for language in LANGUAGES
    }
    ordered = [
        by_language[language][ordinal]
        for ordinal in range(6)
        for language in LANGUAGES
    ]
    return [
        {
            "slot": slot,
            **task,
            "status": "pending",
            "next_stage": STAGES[0],
            "classification": None,
            "stages": [],
        }
        for slot, task in enumerate(ordered, start=1)
    ]


def build_receipt(
    reserve: dict[str, Any],
    *,
    evaluator_revision: str,
    repolaunch_revision: str,
    dataset_file_sha256: dict[str, str],
    evaluator_python: dict[str, str],
    codex_runtime: dict[str, Any],
    execution_code_sha256: dict[str, str],
    evaluator_tree_sha256: str,
    repolaunch_tree_sha256: str,
) -> dict[str, Any]:
    candidates = deterministic_candidate_order(reserve)
    source = reserve.get("source", {})
    _require(isinstance(source, dict), "private reserve source is malformed")
    _require(
        isinstance(source.get("revision"), str), "private reserve revision is missing"
    )
    _require(
        isinstance(dataset_file_sha256, dict) and bool(dataset_file_sha256),
        "dataset file identities are missing",
    )
    _require(
        all(
            isinstance(name, str)
            and bool(name)
            and isinstance(digest, str)
            and len(digest) == 64
            for name, digest in dataset_file_sha256.items()
        ),
        "dataset file identities are malformed",
    )
    selection = reserve["selection"]
    identity_projection = [
        {
            "slot": candidate["slot"],
            "instance_id": candidate["instance_id"],
            "repo": candidate["repo"],
            "language": candidate["language"],
            "docker_image": candidate["docker_image"],
            "manifest_sha256": candidate["manifest_sha256"],
            "rank_commitment": candidate["rank_commitment"],
        }
        for candidate in candidates
    ]
    receipt = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "status": "in_progress",
        "protocol": {
            "selection_uses_task_bodies_or_subject_outcomes": False,
            "candidate_failures_are_experimental_replacements": False,
            "official_validation_post_patch_runs": 3,
            "official_gold_checks_after_validation": 2,
            "q4_uses_clean_evaluator_invocation": True,
            "minimum_qualified_independent_clusters": MINIMUM_QUALIFIED_CLUSTERS,
            "target_primary_clusters": TARGET_PRIMARY_CLUSTERS,
            "target_alternate_clusters": TARGET_ALTERNATE_CLUSTERS,
            "target_qualified_clusters": TARGET_QUALIFIED_CLUSTERS,
            "maximum_candidates": MAXIMUM_CANDIDATES,
            "workers": 1,
            "timeout_seconds_per_stage": 5400,
            "subject_model_invocations_permitted": 0,
        },
        "source": {
            "dataset": source.get("dataset"),
            "dataset_revision": source["revision"],
            "dataset_file_sha256": dict(sorted(dataset_file_sha256.items())),
            "evaluator_revision": evaluator_revision,
            "embedded_repolaunch_revision": repolaunch_revision,
            "reserve_selected_ids_sha256": selection["selected_ids_sha256"],
            "reserve_receipt_sha256": sha256_value(reserve),
            "reserve_seed": selection["seed"],
            "candidate_order_sha256": sha256_value(identity_projection),
            "evaluator_python": evaluator_python,
            "execution_code_sha256": dict(sorted(execution_code_sha256.items())),
            "evaluator_tree_sha256": evaluator_tree_sha256,
            "repolaunch_tree_sha256": repolaunch_tree_sha256,
        },
        "runtime_observation": codex_runtime,
        "candidates": candidates,
        "selection": None,
        "subject_accounting": {
            "subject_invocation_starts": 0,
            "subject_invocation_returns": 0,
            "frozen_cell_attempts": 0,
        },
    }
    seal_receipt(receipt)
    validate_receipt(receipt)
    return receipt


def _candidate_state(candidate: dict[str, Any]) -> None:
    _require(type(candidate.get("slot")) is int, "candidate slot is invalid")
    _require(candidate.get("language") in LANGUAGES, "candidate language is invalid")
    for field in ("instance_id", "repo", "docker_image", "rank_commitment"):
        _require(
            isinstance(candidate.get(field), str) and bool(candidate[field]),
            f"candidate {field} is invalid",
        )
    status = candidate.get("status")
    _require(status in {"pending", "in_progress", "not_qualified", "qualified"}, "candidate status is invalid")
    stages = candidate.get("stages")
    _require(isinstance(stages, list), "candidate stage receipts are malformed")
    expected = list(STAGES[: len(stages)])
    _require([stage.get("stage") for stage in stages] == expected, "candidate stage order drifted")
    if status == "qualified":
        _require(len(stages) == len(STAGES), "qualified candidate lacks all stages")
        _require(all(stage.get("outcome") == "pass" for stage in stages), "qualified candidate has a failed stage")
        _require(candidate.get("classification") == "qualified", "qualified classification drifted")
        _require(candidate.get("next_stage") is None, "qualified candidate has a next stage")
    elif status == "not_qualified":
        _require(candidate.get("classification") in FAILURE_CLASSES, "failure classification is invalid")
        _require(stages and stages[-1].get("outcome") == "fail", "failed candidate lacks terminal stage")
        _require(candidate.get("next_stage") is None, "failed candidate has a next stage")
    else:
        _require(candidate.get("classification") is None, "pending candidate has a classification")
        _require(candidate.get("next_stage") == STAGES[len(stages)], "candidate next stage drifted")
        _require(
            all(stage.get("outcome") == "pass" for stage in stages),
            "active candidate contains a failed prior stage",
        )
    resolved_image = candidate.get("resolved_image")
    if stages and stages[0].get("outcome") == "pass":
        q1_image = stages[0].get("evidence", {}).get("resolved_image_ref")
        _require(
            isinstance(resolved_image, str) and "@sha256:" in resolved_image,
            "environment-qualified candidate lacks an immutable image reference",
        )
        _require(
            resolved_image == q1_image,
            "environment-qualified candidate image drifted from Q1 evidence",
        )
    else:
        _require(resolved_image is None, "candidate has a premature image reference")


def validate_receipt(receipt: dict[str, Any]) -> None:
    expected_state = receipt.get("state_sha256")
    unsealed = dict(receipt)
    unsealed.pop("state_sha256", None)
    _require(
        isinstance(expected_state, str) and expected_state == sha256_value(unsealed),
        "qualification state seal drifted",
    )
    _require(receipt.get("schema_name") == SCHEMA_NAME, "qualification schema drifted")
    _require(receipt.get("schema_version") == SCHEMA_VERSION, "qualification schema version drifted")
    _require(receipt.get("status") in {"in_progress", "stable_pool_ready", "insufficient"}, "qualification status is invalid")
    protocol = receipt.get("protocol")
    _require(isinstance(protocol, dict), "qualification protocol is malformed")
    expected_protocol = {
        "selection_uses_task_bodies_or_subject_outcomes": False,
        "candidate_failures_are_experimental_replacements": False,
        "official_validation_post_patch_runs": 3,
        "official_gold_checks_after_validation": 2,
        "q4_uses_clean_evaluator_invocation": True,
        "minimum_qualified_independent_clusters": MINIMUM_QUALIFIED_CLUSTERS,
        "target_primary_clusters": TARGET_PRIMARY_CLUSTERS,
        "target_alternate_clusters": TARGET_ALTERNATE_CLUSTERS,
        "target_qualified_clusters": TARGET_QUALIFIED_CLUSTERS,
        "maximum_candidates": MAXIMUM_CANDIDATES,
        "workers": 1,
        "timeout_seconds_per_stage": 5400,
        "subject_model_invocations_permitted": 0,
    }
    _require(protocol == expected_protocol, "qualification protocol drifted")
    candidates = receipt.get("candidates")
    _require(isinstance(candidates, list) and len(candidates) == MAXIMUM_CANDIDATES, "qualification candidates are malformed")
    for index, candidate in enumerate(candidates, start=1):
        _require(candidate.get("slot") == index, "candidate slots are not contiguous")
        _candidate_state(candidate)
    source = receipt.get("source")
    _require(isinstance(source, dict), "qualification source is malformed")
    for field in (
        "dataset_revision",
        "evaluator_revision",
        "embedded_repolaunch_revision",
        "reserve_selected_ids_sha256",
        "reserve_receipt_sha256",
        "reserve_seed",
        "candidate_order_sha256",
        "evaluator_tree_sha256",
        "repolaunch_tree_sha256",
    ):
        _require(isinstance(source.get(field), str) and bool(source[field]), f"qualification source {field} is invalid")
    _require(
        isinstance(source.get("dataset_file_sha256"), dict)
        and isinstance(source.get("execution_code_sha256"), dict)
        and isinstance(source.get("evaluator_python"), dict),
        "qualification source identities are incomplete",
    )
    identity_projection = [
        {
            "slot": candidate["slot"],
            "instance_id": candidate["instance_id"],
            "repo": candidate["repo"],
            "language": candidate["language"],
            "docker_image": candidate["docker_image"],
            "manifest_sha256": candidate["manifest_sha256"],
            "rank_commitment": candidate["rank_commitment"],
        }
        for candidate in candidates
    ]
    _require(
        sha256_value(identity_projection) == source["candidate_order_sha256"],
        "qualification candidate order commitment drifted",
    )
    for candidate in candidates:
        _require(
            candidate["rank_commitment"]
            == qualification_rank(
                source["reserve_seed"],
                source["dataset_revision"],
                candidate["language"],
                candidate["instance_id"],
            ),
            "qualification candidate rank drifted",
        )
    _require(len({candidate["repo"] for candidate in candidates}) == len(candidates), "qualification candidates repeat repositories")
    subject = receipt.get("subject_accounting")
    _require(
        subject
        == {
            "subject_invocation_starts": 0,
            "subject_invocation_returns": 0,
            "frozen_cell_attempts": 0,
        },
        "qualification exposed a subject outcome",
    )
    qualified = [candidate for candidate in candidates if candidate["status"] == "qualified"]
    remaining = [candidate for candidate in candidates if candidate["status"] in {"pending", "in_progress"}]
    if receipt["status"] == "stable_pool_ready":
        _require(len(qualified) >= MINIMUM_QUALIFIED_CLUSTERS, "ready pool is below the minimum")
        _require(receipt.get("selection") == select_population(candidates), "qualified population selection drifted")
    elif receipt["status"] == "insufficient":
        _require(not remaining, "insufficient state still has candidates")
        _require(len(qualified) < MINIMUM_QUALIFIED_CLUSTERS, "insufficient state meets the minimum")
        _require(receipt.get("selection") is None, "insufficient state selected a population")
    else:
        _require(remaining, "in-progress state has no remaining candidates")
        _require(len(qualified) < TARGET_QUALIFIED_CLUSTERS, "in-progress state reached its target")
        _require(receipt.get("selection") is None, "in-progress state selected a population")


def next_qualification_stage(receipt: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    validate_receipt(receipt)
    if receipt["status"] != "in_progress":
        return None
    for candidate in receipt["candidates"]:
        if candidate["status"] in {"pending", "in_progress"}:
            return candidate, candidate["next_stage"]
    raise ExperimentConfigurationError("qualification state has no legal next stage")


def _allowed_failure(stage: str, classification: str) -> bool:
    allowed = {
        "q1_environment": {
            "build_environment_failure",
            "evaluator_runtime_failure",
            "infrastructure_timeout",
        },
        "q2_repeated_validation": {
            "build_environment_failure",
            "flaky_validation",
            "gold_patch_evaluation_failure",
            "evaluator_runtime_failure",
            "infrastructure_timeout",
        },
        "q3_gold": {
            "gold_patch_evaluation_failure",
            "evaluator_runtime_failure",
            "infrastructure_timeout",
        },
        "q4_clean_gold": {
            "gold_patch_evaluation_failure",
            "evaluator_runtime_failure",
            "infrastructure_timeout",
        },
    }
    return classification in allowed[stage]


def record_stage(
    receipt: dict[str, Any],
    *,
    slot: int,
    stage: str,
    outcome: str,
    classification: str | None,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Record exactly one legal stage and recompute the continuation gate."""

    validate_receipt(receipt)
    pending = next_qualification_stage(receipt)
    _require(pending is not None, "qualification is already terminal")
    candidate, expected_stage = pending
    _require(candidate["slot"] == slot, "qualification slot is out of order")
    _require(stage == expected_stage, "qualification stage is out of order")
    _require(outcome in {"pass", "fail"}, "qualification outcome is invalid")
    _require(isinstance(evidence, dict) and bool(evidence), "qualification evidence is missing")
    _require(
        isinstance(evidence.get("stage_receipt_sha256"), str)
        and len(evidence["stage_receipt_sha256"]) == 64,
        "qualification stage receipt is not hash-bound",
    )
    if outcome == "pass":
        _require(classification is None, "passing stage has a failure classification")
    else:
        _require(
            isinstance(classification, str) and _allowed_failure(stage, classification),
            "stage failure classification is invalid",
        )
    candidate["stages"].append(
        {
            "stage": stage,
            "outcome": outcome,
            "classification": classification,
            "evidence": evidence,
        }
    )
    if stage == "q1_environment" and outcome == "pass":
        resolved_image = evidence.get("resolved_image_ref")
        _require(
            isinstance(resolved_image, str) and "@sha256:" in resolved_image,
            "passing environment stage lacks an immutable image reference",
        )
        candidate["resolved_image"] = resolved_image
    if outcome == "fail":
        candidate["status"] = "not_qualified"
        candidate["classification"] = classification
        candidate["next_stage"] = None
    elif stage == STAGES[-1]:
        candidate["status"] = "qualified"
        candidate["classification"] = "qualified"
        candidate["next_stage"] = None
    else:
        candidate["status"] = "in_progress"
        candidate["next_stage"] = STAGES[len(candidate["stages"])]

    qualified = [item for item in receipt["candidates"] if item["status"] == "qualified"]
    remaining = [item for item in receipt["candidates"] if item["status"] in {"pending", "in_progress"}]
    if len(qualified) >= TARGET_QUALIFIED_CLUSTERS:
        receipt["status"] = "stable_pool_ready"
        receipt["selection"] = select_population(receipt["candidates"])
    elif not remaining:
        if len(qualified) >= MINIMUM_QUALIFIED_CLUSTERS:
            receipt["status"] = "stable_pool_ready"
            receipt["selection"] = select_population(receipt["candidates"])
        else:
            receipt["status"] = "insufficient"
    seal_receipt(receipt)
    validate_receipt(receipt)
    return receipt


def select_population(candidates: Iterable[dict[str, Any]]) -> dict[str, Any]:
    qualified = [candidate for candidate in candidates if candidate["status"] == "qualified"]
    _require(len(qualified) >= MINIMUM_QUALIFIED_CLUSTERS, "qualified pool is below the minimum")
    primary_count = TARGET_PRIMARY_CLUSTERS if len(qualified) >= TARGET_PRIMARY_CLUSTERS else MINIMUM_QUALIFIED_CLUSTERS
    alternate_count = min(TARGET_ALTERNATE_CLUSTERS, len(qualified) - primary_count)
    primary = qualified[:primary_count]
    alternates = qualified[primary_count : primary_count + alternate_count]
    projection = lambda candidate: {
        "slot": candidate["slot"],
        "instance_id": candidate["instance_id"],
        "repo": candidate["repo"],
        "language": candidate["language"],
        "resolved_image": candidate["resolved_image"],
    }
    value = {
        "primary": [projection(candidate) for candidate in primary],
        "alternates": [projection(candidate) for candidate in alternates],
    }
    value["population_sha256"] = sha256_value(value)
    return value


def public_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    """Project a content-free qualification audit safe for tracked artifacts."""

    validate_receipt(receipt)
    candidates = receipt["candidates"]
    attempted = [candidate for candidate in candidates if candidate["status"] != "pending"]
    qualified = [candidate for candidate in candidates if candidate["status"] == "qualified"]
    failures = Counter(
        candidate["classification"]
        for candidate in candidates
        if candidate["status"] == "not_qualified"
    )
    selected = receipt.get("selection") or {"primary": [], "alternates": []}
    return {
        "schema_name": f"{SCHEMA_NAME}.public-summary",
        "schema_version": SCHEMA_VERSION,
        "status": receipt["status"],
        "attempted_candidates": len(attempted),
        "build_environment_failures": failures["build_environment_failure"],
        "flaky_validation_failures": failures["flaky_validation"],
        "gold_patch_evaluation_failures": failures["gold_patch_evaluation_failure"],
        "evaluator_runtime_failures": failures["evaluator_runtime_failure"],
        "infrastructure_timeouts": failures["infrastructure_timeout"],
        "qualified_independent_clusters": len(qualified),
        "qualification_rate": (
            round(len(qualified) / len(attempted), 6) if attempted else None
        ),
        "primary_cluster_count": len(selected["primary"]),
        "alternate_cluster_count": len(selected["alternates"]),
        "minimum_gate_passed": len(qualified) >= MINIMUM_QUALIFIED_CLUSTERS,
        "subject_invocation_starts": 0,
        "task_identities_withheld": True,
        "private_receipt_sha256": sha256_value(receipt),
        "source": {
            "dataset_revision": receipt["source"]["dataset_revision"],
            "evaluator_revision": receipt["source"]["evaluator_revision"],
            "embedded_repolaunch_revision": receipt["source"]["embedded_repolaunch_revision"],
            "candidate_order_sha256": receipt["source"]["candidate_order_sha256"],
        },
    }
