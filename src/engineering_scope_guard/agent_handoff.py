"""Deterministic validation for the repository's current agent handoff."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "1"
REASONING_EFFORT_STATE_VERSION = "evaluator-stable-reasoning-effort-v1"
RUNTIME_LOCKED_STATE_VERSION = "runtime-locked-reasoning-effort-v1"
REASONING_EFFORT_STATE_VERSIONS = frozenset(
    {REASONING_EFFORT_STATE_VERSION, RUNTIME_LOCKED_STATE_VERSION}
)
MAX_HANDOFF_BYTES = 5 * 1024
GOAL_STATUSES = frozenset({"complete", "blocked", "abandoned"})
ACTION_KINDS = frozenset(
    {
        "none",
        "review",
        "persist_and_merge",
        "inspect_pr",
        "merge_if_green",
        "prepare_next_goal",
        "request_authorization",
        "run_authorized_goal",
    }
)
AUTHORIZATION_STATES = frozenset(
    {"explicit_current_request", "standing_user_authorization", "not_authorized"}
)
FORBIDDEN_ACTIONS = frozenset(
    {
        "run_final_live_canary",
        "run_pilot_v2",
        "run_pilot_v3",
        "run_exploratory_experiment",
        "select_or_freeze_exploratory_tasks",
        "run_confirmatory_experiment",
        "freeze_pilot_v2_before_canary_success",
        "automatic_repair_and_rerun_after_material_canary_defect",
        "change_experimental_treatment",
        "expose_held_out_task_bodies",
        "increase_retry_budgets",
        "reset_or_relabel_experimental_evidence",
    }
)
CHECK_STATES = frozenset(
    {
        "passed",
        "failed",
        "not_required",
        "pending_pr",
        "derive_from_pr",
        "derive_from_branch",
    }
)
PRIVACY_KEYS = frozenset(
    {
        "credentials",
        "auth_token",
        "access_token",
        "raw_provider_trace",
        "raw_task_body",
        "private_benchmark_content",
        "local_absolute_path",
        "graphify_output",
        "worktree_path",
        "codex_home",
    }
)
REASONING_EFFORT_SENSITIVE_KEYS = PRIVACY_KEYS | frozenset(
    {
        "api_key",
        "body",
        "client_secret",
        "credential",
        "docker_image",
        "image",
        "image_ref",
        "instance_id",
        "password",
        "patch",
        "patch_content",
        "patch_diff",
        "patch_text",
        "private_key",
        "problem_statement",
        "prompt",
        "prompt_content",
        "prompt_payload",
        "prompt_text",
        "provider_output",
        "provider_response",
        "raw",
        "raw_body",
        "raw_log",
        "raw_logs",
        "raw_output",
        "raw_patch",
        "raw_prompt",
        "raw_trace",
        "repo",
        "repo_path",
        "repo_url",
        "repository_path",
        "repository_url",
        "secret",
        "stderr",
        "stdout",
        "task_body",
        "task_content",
        "task_id",
        "task_payload",
        "task_text",
        "token",
    }
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
SWE_TASK_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-[0-9]+"
    r"(?![A-Za-z0-9_.-])"
)
GITHUB_REPOSITORY_URL_RE = re.compile(
    r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:[/?#]|$)",
    re.IGNORECASE,
)
POSIX_ABSOLUTE_PATH_RE = re.compile(
    r"(?:^|[\s\"'(<\[{=:])/(?!/)[A-Za-z0-9._~%+-]+"
    r"(?:/[^\s\"'<>\])},]*)?"
)
WINDOWS_ABSOLUTE_PATH_RE = re.compile(
    r"(?:^|[\s\"'(<\[{=])[A-Za-z]:[\\/][^\s\"'<>\])},]*",
    re.IGNORECASE,
)
HOME_PATH_RE = re.compile(r"(?:^|[\s\"'(<\[{=])~[\\/]")
FILE_URI_RE = re.compile(r"\bfile:(?://|/)", re.IGNORECASE)
LOCAL_PATH_COMPONENT_RE = re.compile(r"(?:^|[\\/])\.local(?:[\\/]|$)")
TRAVERSAL_PATH_COMPONENT_RE = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")
CREDENTIAL_VALUE_RE = re.compile(
    r"(?:"
    r"AKIA[0-9A-Z]{16}"
    r"|gh[pousr]_[A-Za-z0-9_]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----"
    r"|(?:api[_-]?key|auth[_-]?token|access[_-]?token|client[_-]?secret|password|private[_-]?key)"
    r"\s*[:=]\s*\S+"
    r")",
    re.IGNORECASE,
)
SENSITIVE_VALUE_ALIAS_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"api[_-]?key|auth[_-]?token|access[_-]?token|client[_-]?secret|private[_-]?key"
    r"|problem[_-]?statement|raw[_-]?(?:prompt|patch|body|trace|log|output)"
    r"|provider[_-]?(?:output|response|trace)|prompt[_-]?(?:text|content|payload)"
    r"|patch[_-]?(?:text|content|diff)|task[_-]?(?:body|text|content|payload)"
    r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)
SENSITIVE_CONTENT_LABEL_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:prompt|patch|body|provider[_ -]?output)\s*[:=]",
    re.IGNORECASE,
)
RAW_PATCH_LITERAL_RE = re.compile(
    r"(?:^diff --git |^@@ -[0-9]|^\+\+\+ [ab]/|^--- [ab]/)",
    re.MULTILINE,
)
REASONING_EFFORT_DISPOSITIONS = frozenset(
    {
        "TASK/EVALUATOR POPULATION STILL INSUFFICIENT — LIVE EXPERIMENT NOT STARTED",
        "LOW FAVORED",
        "MEDIUM FAVORED",
        "WORK DIFFERENCE WITHOUT ACCEPTANCE EVIDENCE",
        "NO MATERIAL EXPLORATORY DIFFERENCE DETECTED",
        "INCONCLUSIVE",
        "EXPERIMENT INVALID / TERMINATED",
    }
)
STAGE_1_STATES = frozenset({"not_applicable", "not_reached", "passed", "failed"})
TERMINAL_ARTIFACT_PATHS = {
    "qualification_summary": (
        "experiment/evaluator_stable_reasoning_effort_qualification_summary.json"
    ),
    "terminal_result": "experiment/evaluator_stable_reasoning_effort_terminal_result.json",
    "terminal_report": "docs/EVALUATOR_STABLE_REASONING_EFFORT_TERMINAL_REPORT.md",
    "contract": "experiment/reasoning_effort_v2_contract.json",
    "terminal_envelope": "experiment/reasoning_effort_v2_terminal_envelope.json",
    "analysis": "experiment/reasoning_effort_v2_analysis.json",
}
RUNTIME_LOCKED_TERMINAL_ARTIFACT_PATHS = {
    **TERMINAL_ARTIFACT_PATHS,
    "terminal_result": "experiment/runtime_locked_reasoning_effort_terminal_result.json",
    "terminal_report": "docs/RUNTIME_LOCKED_REASONING_EFFORT_TERMINAL_REPORT.md",
}


class HandoffValidationError(ValueError):
    """Raised when a handoff is malformed, unsafe, or contradictory."""


def canonical_bytes(value: dict[str, Any]) -> bytes:
    """Serialize a handoff to the one canonical repository representation."""

    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode(
        "utf-8"
    ) + b"\n"


def _object(
    value: Any, name: str, required: set[str], optional: set[str] | None = None
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandoffValidationError(f"{name} must be an object")
    allowed = required | (optional or set())
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing:
        raise HandoffValidationError(f"{name} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise HandoffValidationError(f"{name} has unknown fields: {', '.join(sorted(unknown))}")
    return value


def _nonempty(value: Any, name: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise HandoffValidationError(f"{name} must be a non-empty bounded string")
    return value


def _terminal_time(value: Any) -> str:
    text = _nonempty(value, "goal.completed_at", maximum=40)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise HandoffValidationError("goal.completed_at must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise HandoffValidationError("goal.completed_at must include a timezone")
    return text


def _privacy_scan(value: Any, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in PRIVACY_KEYS:
                raise HandoffValidationError(
                    f"privacy-sensitive field is forbidden at {path}"
                )
            _privacy_scan(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _privacy_scan(child, path=f"{path}[{index}]")


def _reasoning_effort_privacy_error(path: str, category: str) -> None:
    raise HandoffValidationError(
        f"reasoning-effort privacy-sensitive violation at {path}: {category}"
    )


def _reasoning_effort_string_privacy_scan(value: str, *, path: str) -> None:
    if GITHUB_REPOSITORY_URL_RE.search(value) and path != "$.git.pr_url":
        _reasoning_effort_privacy_error(path, "github_repository_url")
    if SWE_TASK_ID_RE.search(value):
        _reasoning_effort_privacy_error(path, "task_identity")
    if FILE_URI_RE.search(value):
        _reasoning_effort_privacy_error(path, "file_uri")
    if POSIX_ABSOLUTE_PATH_RE.search(value):
        _reasoning_effort_privacy_error(path, "absolute_path")
    if WINDOWS_ABSOLUTE_PATH_RE.search(value):
        _reasoning_effort_privacy_error(path, "absolute_path")
    if HOME_PATH_RE.search(value):
        _reasoning_effort_privacy_error(path, "home_path")
    normalized = value.replace("\\", "/")
    if LOCAL_PATH_COMPONENT_RE.search(normalized):
        _reasoning_effort_privacy_error(path, "local_path_component")
    if TRAVERSAL_PATH_COMPONENT_RE.search(normalized):
        _reasoning_effort_privacy_error(path, "path_traversal")
    if CREDENTIAL_VALUE_RE.search(value):
        _reasoning_effort_privacy_error(path, "credential_material")
    if SENSITIVE_VALUE_ALIAS_RE.search(value) or SENSITIVE_CONTENT_LABEL_RE.search(
        value
    ):
        _reasoning_effort_privacy_error(path, "sensitive_content_alias")
    if RAW_PATCH_LITERAL_RE.search(value):
        _reasoning_effort_privacy_error(path, "raw_patch_literal")


def _reasoning_effort_value_privacy_scan(value: Any, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in REASONING_EFFORT_SENSITIVE_KEYS:
                _reasoning_effort_privacy_error(path, "sensitive_field_alias")
            _reasoning_effort_string_privacy_scan(key, path=path)
            _reasoning_effort_value_privacy_scan(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reasoning_effort_value_privacy_scan(child, path=f"{path}[{index}]")
    elif isinstance(value, str):
        _reasoning_effort_string_privacy_scan(value, path=path)


def _count(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise HandoffValidationError(f"{name} must be a non-negative integer")
    return value


def _string_list(value: Any, name: str, allowed: frozenset[str]) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or item not in allowed for item in value
    ):
        raise HandoffValidationError(f"{name} contains an unsupported action")
    if len(value) != len(set(value)):
        raise HandoffValidationError(f"{name} contains duplicates")
    return value


def _evidence_path(root: Path, value: Any) -> Path:
    text = _nonempty(value, "evidence.path", maximum=200)
    pure = PurePosixPath(text)
    if pure.is_absolute() or ".." in pure.parts:
        raise HandoffValidationError("evidence.path must be repository-relative")
    if not pure.parts or any(part in {".local", "graphify-out"} for part in pure.parts):
        raise HandoffValidationError("evidence.path points to forbidden local material")
    path = root / pure
    if path.is_symlink():
        raise HandoffValidationError(f"evidence.path must not be a symlink: {text}")
    if not path.is_file():
        raise HandoffValidationError(f"evidence.path does not exist: {text}")
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise HandoffValidationError("evidence.path escapes the repository") from error
    return resolved


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise HandoffValidationError(f"{name} is malformed")
    return value


def _artifact_reference(root: Path, value: Any, name: str, expected_path: str) -> None:
    reference = _object(value, name, {"path", "sha256"})
    if reference["path"] != expected_path:
        raise HandoffValidationError(f"{name}.path differs from the canonical artifact path")
    path = _evidence_path(root, reference["path"])
    digest_value = _sha256(reference["sha256"], f"{name}.sha256")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest_value:
        raise HandoffValidationError(f"{name} digest mismatch")


def _validate_reasoning_effort_state(value: dict[str, Any], root: Path) -> None:
    state = _object(
        value,
        "experimental_state",
        {
            "schema_version",
            "qualification",
            "execution",
            "terminal",
            "public_artifacts",
            "boundaries",
        },
    )
    if state["schema_version"] not in REASONING_EFFORT_STATE_VERSIONS:
        raise HandoffValidationError("experimental_state.schema_version is unsupported")
    runtime_locked = state["schema_version"] == RUNTIME_LOCKED_STATE_VERSION
    qualification = _object(
        state["qualification"],
        "experimental_state.qualification",
        {
            "attempted_candidates",
            "validation_failures",
            "gold_failures",
            "infrastructure_failures",
            "qualified_independent_clusters",
            "minimum_gate_passed",
        },
    )
    qualification_counts = (
        "attempted_candidates",
        "validation_failures",
        "gold_failures",
        "infrastructure_failures",
        "qualified_independent_clusters",
    )
    for field in qualification_counts:
        _count(qualification[field], f"experimental_state.qualification.{field}")
    if type(qualification["minimum_gate_passed"]) is not bool:
        raise HandoffValidationError("qualification minimum gate must be boolean")
    classified = sum(qualification[field] for field in qualification_counts[1:])
    if classified != qualification["attempted_candidates"]:
        raise HandoffValidationError("qualification counts do not reconcile")
    if qualification["minimum_gate_passed"] is not (
        qualification["qualified_independent_clusters"] >= 10
    ):
        raise HandoffValidationError("qualification minimum gate contradicts cluster count")

    execution = _object(
        state["execution"],
        "experimental_state.execution",
        {
            "experiment_started",
            "canary_subject_invocation_starts",
            "experiment_subject_invocation_starts",
            "total_subject_invocation_starts",
            "evaluator_invocation_starts",
            "schedule_cells",
            "completed_cells",
            "admissible_cells",
            "missing_cells",
            "alternates_activated",
            "stage_1_status",
        },
    )
    if type(execution["experiment_started"]) is not bool:
        raise HandoffValidationError("experimental_state.execution.experiment_started must be boolean")
    for field in set(execution) - {"experiment_started", "stage_1_status"}:
        _count(execution[field], f"experimental_state.execution.{field}")
    canary = execution["canary_subject_invocation_starts"]
    experiment = execution["experiment_subject_invocation_starts"]
    total = execution["total_subject_invocation_starts"]
    if (
        canary not in (0, 1)
        or total != canary + experiment
        or total > (48 if runtime_locked else 56)
        or execution["experiment_started"] is not (experiment > 0)
        or execution["evaluator_invocation_starts"] > experiment
        or execution["admissible_cells"] > execution["completed_cells"]
        or execution["completed_cells"] > execution["schedule_cells"]
        or execution["alternates_activated"] > 4
        or execution["missing_cells"]
        != execution["schedule_cells"] - execution["completed_cells"]
    ):
        raise HandoffValidationError("experimental execution counts are inconsistent or exceed its cap")
    if execution["stage_1_status"] not in STAGE_1_STATES:
        raise HandoffValidationError("experimental stage-1 status is unsupported")

    terminal = _object(
        state["terminal"],
        "experimental_state.terminal",
        {"path", "disposition", "esg_rr_002_candidate_decision"},
    )
    if terminal["path"] not in {
        "insufficient_population",
        "pre_subject_integrity_stop",
        "experiment_terminal",
    }:
        raise HandoffValidationError("experimental terminal path is unsupported")
    if terminal["disposition"] not in REASONING_EFFORT_DISPOSITIONS:
        raise HandoffValidationError("experimental terminal disposition is unsupported")
    if terminal["esg_rr_002_candidate_decision"] not in {
        "not_applicable",
        "not_justified",
        "candidate_justified",
    }:
        raise HandoffValidationError("ESG-RR-002 candidate decision is unsupported")

    artifact_paths = (
        RUNTIME_LOCKED_TERMINAL_ARTIFACT_PATHS if runtime_locked
        else TERMINAL_ARTIFACT_PATHS
    )
    artifacts = _object(
        state["public_artifacts"],
        "experimental_state.public_artifacts",
        set(artifact_paths),
    )
    for name in ("qualification_summary", "terminal_result", "terminal_report"):
        _artifact_reference(
            root,
            artifacts[name],
            f"experimental_state.public_artifacts.{name}",
            artifact_paths[name],
        )
    experiment_artifact_names = ("contract", "terminal_envelope", "analysis")
    common_only = terminal["path"] != "experiment_terminal"
    for name in experiment_artifact_names:
        if common_only:
            if artifacts[name] is not None:
                raise HandoffValidationError(
                    "common-only terminal includes experiment artifacts"
                )
        else:
            _artifact_reference(
                root,
                artifacts[name],
                f"experimental_state.public_artifacts.{name}",
                artifact_paths[name],
            )

    boundaries = _object(
        state["boundaries"],
        "experimental_state.boundaries",
        {
            "raw_private_material_tracked",
            "repository_private",
            "publication_authorized",
            "visibility_change_authorized",
            "next_authority_boundary",
        },
    )
    expected_boundaries = {
        "raw_private_material_tracked": False,
        "repository_private": not runtime_locked,
        "publication_authorized": runtime_locked,
        "visibility_change_authorized": False,
        "next_authority_boundary": (
            "authorize_a_separate_successor_program_before_any_retry_or_new_experiment"
            if runtime_locked else "authorize_private_canonical_branch_push"
        ),
    }
    if boundaries != expected_boundaries:
        raise HandoffValidationError("experimental privacy/publication boundary drifted")

    insufficient_disposition = (
        "TASK/EVALUATOR POPULATION STILL INSUFFICIENT — LIVE EXPERIMENT NOT STARTED"
    )
    if terminal["path"] == "insufficient_population":
        if (
            qualification["minimum_gate_passed"] is not False
            or execution["experiment_started"] is not False
            or any(
                execution[field] != 0
                for field in set(execution) - {"experiment_started", "stage_1_status"}
            )
            or execution["stage_1_status"] != "not_applicable"
            or terminal["disposition"] != insufficient_disposition
            or terminal["esg_rr_002_candidate_decision"] != "not_applicable"
        ):
            raise HandoffValidationError("insufficient terminal state is contradictory")
    elif terminal["path"] == "pre_subject_integrity_stop":
        zero_execution = all(
            execution[field] == 0
            for field in set(execution) - {"experiment_started", "stage_1_status"}
        )
        if (
            qualification["minimum_gate_passed"] is not True
            or execution["experiment_started"] is not False
            or not zero_execution
            or execution["stage_1_status"] != "not_applicable"
            or terminal["disposition"] != "EXPERIMENT INVALID / TERMINATED"
            or terminal["esg_rr_002_candidate_decision"] != "not_applicable"
        ):
            raise HandoffValidationError(
                "pre-subject integrity-stop state is contradictory"
            )
    elif (
        qualification["minimum_gate_passed"] is not True
        or execution["schedule_cells"] not in {40, 44, 48}
        or terminal["disposition"] == insufficient_disposition
        or terminal["esg_rr_002_candidate_decision"] == "not_applicable"
        or execution["stage_1_status"] == "not_applicable"
        or (
            terminal["disposition"] != "EXPERIMENT INVALID / TERMINATED"
            and execution["stage_1_status"] != "passed"
        )
        or (
            terminal["disposition"]
            in {"INCONCLUSIVE", "EXPERIMENT INVALID / TERMINATED"}
            and terminal["esg_rr_002_candidate_decision"] != "not_justified"
        )
    ):
        raise HandoffValidationError("experiment terminal state is contradictory")


def validate_handoff(value: Any, root: Path) -> dict[str, Any]:
    """Validate a parsed handoff using deterministic repository facts only."""

    if (
        isinstance(value, dict)
        and isinstance(value.get("experimental_state"), dict)
        and value["experimental_state"].get("schema_version")
        in REASONING_EFFORT_STATE_VERSIONS
    ):
        _reasoning_effort_value_privacy_scan(value)
    _privacy_scan(value)
    data = _object(
        value,
        "handoff",
        {
            "schema_version",
            "repository",
            "goal",
            "current_decision",
            "git",
            "verification",
            "experimental_state",
            "next_action",
            "allowed_actions",
            "forbidden_actions",
            "evidence",
            "notes",
        },
    )
    if data["schema_version"] != SCHEMA_VERSION:
        raise HandoffValidationError("unknown schema_version")
    repository = _nonempty(data["repository"], "repository", maximum=120)
    if not REPOSITORY_RE.fullmatch(repository):
        raise HandoffValidationError("repository must be owner/name")

    goal = _object(
        data["goal"], "goal", {"name", "status", "decision", "completed_at"}
    )
    _nonempty(goal["name"], "goal.name", maximum=120)
    if goal["status"] not in GOAL_STATUSES:
        raise HandoffValidationError("goal.status is not terminal")
    _nonempty(goal["decision"], "goal.decision", maximum=240)
    _terminal_time(goal["completed_at"])

    decision = _object(
        data["current_decision"],
        "current_decision",
        {"goal", "decision", "evidence_commit"},
        {"evidence_commit_semantics"},
    )
    _nonempty(decision["goal"], "current_decision.goal", maximum=120)
    _nonempty(decision["decision"], "current_decision.decision", maximum=240)
    evidence_commit = decision["evidence_commit"]
    evidence_commit_semantics = decision.get(
        "evidence_commit_semantics", "authoritative_evidence_commit"
    )
    if evidence_commit is None:
        if evidence_commit_semantics != "omitted_to_avoid_self_reference":
            raise HandoffValidationError(
                "null current_decision.evidence_commit must explicitly avoid self-reference"
            )
    elif not isinstance(evidence_commit, str) or not GIT_SHA_RE.fullmatch(
        evidence_commit
    ):
        raise HandoffValidationError("current_decision.evidence_commit is malformed")
    elif evidence_commit_semantics != "authoritative_evidence_commit":
        raise HandoffValidationError(
            "current_decision.evidence_commit has unsupported semantics"
        )

    git = _object(
        data["git"],
        "git",
        {
            "base_branch",
            "head_sha",
            "head_sha_semantics",
            "branch",
            "pr_number",
            "pr_url",
        },
    )
    base_branch = _nonempty(git["base_branch"], "git.base_branch", maximum=100)
    if not BRANCH_RE.fullmatch(base_branch) or ".." in base_branch:
        raise HandoffValidationError("git.base_branch is malformed")
    head_sha = git["head_sha"]
    semantics = git["head_sha_semantics"]
    if head_sha is None:
        if semantics != "omitted_to_avoid_self_reference":
            raise HandoffValidationError("null git.head_sha must explicitly avoid self-reference")
    elif not isinstance(head_sha, str) or not GIT_SHA_RE.fullmatch(head_sha):
        raise HandoffValidationError("git.head_sha is malformed")
    elif semantics != "authoritative_evidence_commit":
        raise HandoffValidationError("git.head_sha has unsupported semantics")
    if git["branch"] is not None:
        branch = _nonempty(git["branch"], "git.branch", maximum=120)
        if not BRANCH_RE.fullmatch(branch) or ".." in branch:
            raise HandoffValidationError("git.branch is malformed")
    pr_number = git["pr_number"]
    pr_url = git["pr_url"]
    if (pr_number is None) != (pr_url is None):
        raise HandoffValidationError("git PR number and URL must be both present or both null")
    if pr_number is not None:
        if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number < 1:
            raise HandoffValidationError("git.pr_number is malformed")
        expected = f"https://github.com/{repository}/pull/{pr_number}"
        if pr_url != expected:
            raise HandoffValidationError("git.pr_url does not match repository and PR number")

    verification = _object(
        data["verification"],
        "verification",
        {
            "tests_passed",
            "ci_required",
            "ci_status",
            "codeql_required",
            "codeql_status",
        },
    )
    if verification["tests_passed"] is not None:
        _count(verification["tests_passed"], "verification.tests_passed")
    for prefix in ("ci", "codeql"):
        required = verification[f"{prefix}_required"]
        status = verification[f"{prefix}_status"]
        if not isinstance(required, bool) or status not in CHECK_STATES:
            raise HandoffValidationError(f"verification.{prefix} state is malformed")
        if required and status == "not_required":
            raise HandoffValidationError(f"verification.{prefix} state is contradictory")
        if not required and status not in {"not_required", "passed"}:
            raise HandoffValidationError(f"verification.{prefix} state is contradictory")
        if status == "pending_pr" and pr_number is not None:
            raise HandoffValidationError(
                f"verification.{prefix} is pending_pr despite PR metadata"
            )
        if status == "derive_from_pr" and pr_number is None:
            raise HandoffValidationError(f"verification.{prefix} lacks PR metadata")
        if status == "derive_from_branch" and pr_number is not None:
            raise HandoffValidationError(
                f"verification.{prefix} derives from branch despite PR metadata"
            )

    experimental = data["experimental_state"]
    legacy_experimental_fields = {
        "live_canary_executed",
        "pilot_v2_subject_calls",
        "pilot_v2_evaluator_calls",
        "policy_comparisons",
        "valid_observations",
    }
    if isinstance(experimental, dict) and set(experimental) == legacy_experimental_fields:
        if not isinstance(experimental["live_canary_executed"], bool):
            raise HandoffValidationError(
                "experimental_state.live_canary_executed must be boolean"
            )
        for name in (
            "pilot_v2_subject_calls",
            "pilot_v2_evaluator_calls",
            "policy_comparisons",
            "valid_observations",
        ):
            _count(experimental[name], f"experimental_state.{name}")
        if experimental["valid_observations"] > experimental["policy_comparisons"]:
            raise HandoffValidationError("valid observations exceed policy comparisons")
        reasoning_effort_state = False
    else:
        _validate_reasoning_effort_state(experimental, root.resolve())
        reasoning_effort_state = True

    action = _object(
        data["next_action"],
        "next_action",
        {
            "kind",
            "requires_explicit_user_authorization",
            "authorization",
            "safe_without_explicit_authorization",
            "reason",
        },
    )
    if action["kind"] not in ACTION_KINDS:
        raise HandoffValidationError("next_action.kind is unsupported")
    if action["authorization"] not in AUTHORIZATION_STATES:
        raise HandoffValidationError("next_action.authorization is unsupported")
    if not isinstance(action["requires_explicit_user_authorization"], bool) or not isinstance(
        action["safe_without_explicit_authorization"], bool
    ):
        raise HandoffValidationError("next_action safety fields must be boolean")
    _nonempty(action["reason"], "next_action.reason", maximum=500)
    if (
        not action["requires_explicit_user_authorization"]
        and not action["safe_without_explicit_authorization"]
    ):
        raise HandoffValidationError("unsafe action is falsely marked authorization-free")
    if action["kind"] == "run_authorized_goal" and action["authorization"] == "not_authorized":
        raise HandoffValidationError("run_authorized_goal lacks authorization")
    if action["kind"] == "none" and action["requires_explicit_user_authorization"]:
        raise HandoffValidationError("none action cannot require authorization")
    if goal["status"] in {"blocked", "abandoned"} and action["kind"] == "run_authorized_goal":
        raise HandoffValidationError("terminal stop contradicts run_authorized_goal")

    allowed_actions = _string_list(data["allowed_actions"], "allowed_actions", ACTION_KINDS)
    forbidden_actions = _string_list(
        data["forbidden_actions"], "forbidden_actions", FORBIDDEN_ACTIONS
    )
    if action["kind"] not in allowed_actions:
        raise HandoffValidationError("next_action.kind is not listed in allowed_actions")

    evidence = data["evidence"]
    if not isinstance(evidence, list) or not evidence or len(evidence) > 12:
        raise HandoffValidationError("evidence must contain 1-12 references")
    evidence_paths: set[str] = set()
    for index, item in enumerate(evidence):
        reference = _object(item, f"evidence[{index}]", {"path", "role", "sha256"})
        path = _evidence_path(root.resolve(), reference["path"])
        if reasoning_effort_state and any(
            part.lower() in {"raw", "private"}
            or part.lower().startswith(("raw.", "private."))
            for part in PurePosixPath(reference["path"]).parts
        ):
            raise HandoffValidationError(
                "reasoning-effort evidence path points to raw or private material"
            )
        if reference["path"] in evidence_paths:
            raise HandoffValidationError("evidence contains duplicate paths")
        evidence_paths.add(reference["path"])
        _nonempty(reference["role"], f"evidence[{index}].role", maximum=120)
        sha256 = reference["sha256"]
        if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
            raise HandoffValidationError(f"evidence[{index}].sha256 is malformed")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            raise HandoffValidationError(f"evidence[{index}] digest mismatch")
    if reasoning_effort_state and not {
        "docs/CURRENT_GOAL.md",
        "docs/GOAL_HISTORY.md",
        "docs/DECISIONS.md",
    } <= evidence_paths:
        raise HandoffValidationError(
            "reasoning-effort handoff lacks current-goal, history, or decisions evidence"
        )

    notes = data["notes"]
    if (
        not isinstance(notes, list)
        or len(notes) > 10
        or any(not isinstance(note, str) or not note or len(note) > 500 for note in notes)
    ):
        raise HandoffValidationError("notes must be a bounded string list")
    return data


def load_handoff(path: Path, root: Path) -> dict[str, Any]:
    """Load, validate, and require canonical bytes for one handoff file."""

    raw = path.read_bytes()
    if len(raw) > MAX_HANDOFF_BYTES:
        raise HandoffValidationError("handoff exceeds the 5 KiB limit")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HandoffValidationError("handoff is not valid UTF-8 JSON") from error
    data = validate_handoff(value, root)
    if raw != canonical_bytes(data):
        raise HandoffValidationError("handoff serialization is not canonical")
    return data
