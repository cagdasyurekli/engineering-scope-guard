"""Deterministic Codex launch profiles for the reasoning-effort experiment."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


class LaunchSurfaceError(ValueError):
    """The proposed launch profile is malformed or treatment-confounded."""


PROFILE_SCHEMA = "engineering-scope-guard.codex-launch-profile"
PROFILE_VERSION = 1
STDIN_MODE = "piped_utf8_prompt"
DISABLED_FEATURES = (
    "apps",
    "plugins",
    "browser_use",
    "in_app_browser",
    "computer_use",
    "image_generation",
    "multi_agent",
    "multi_agent_v2",
    "skill_search",
)
REQUIRED_HELP_FLAGS = (
    "--json",
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--approve-for-me",
    "--skip-git-repo-check",
    "--color",
    "--model",
    "--config",
    "--disable",
)
_SINGLETON_FLAGS = {
    "--json",
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--approve-for-me",
    "--skip-git-repo-check",
    "--color",
    "--model",
    "--sandbox",
    "-s",
    "--ask-for-approval",
    "-a",
    "--dangerously-bypass-approvals-and-sandbox",
}


def canonical_bytes(value: Any) -> bytes:
    """Encode one value with the repository's canonical JSON convention."""

    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def build_launch_profile(
    *, executable: str | Path, model: str, reasoning_effort: str,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build one closed, argv-array Codex launch profile."""

    if reasoning_effort not in {"low", "medium"}:
        raise LaunchSurfaceError("reasoning effort must be low or medium")
    argv = [
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--approve-for-me",
        "--skip-git-repo-check",
        "--color",
        "never",
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--config",
        'web_search="disabled"',
        "--config",
        "sandbox_workspace_write.network_access=false",
    ]
    for feature in DISABLED_FEATURES:
        argv.extend(("--disable", feature))
    argv.append("-")
    return {
        "schema_name": PROFILE_SCHEMA,
        "schema_version": PROFILE_VERSION,
        "executable": str(executable),
        "argv": argv,
        "environment": dict(sorted((environment or {}).items())),
        "stdin_mode": STDIN_MODE,
        "reasoning_effort": reasoning_effort,
        "model": model,
        "sandbox": "workspace-write-via-approve-for-me",
        "output_mode": "jsonl",
    }


def validate_launch_profile(
    profile: Mapping[str, Any], *, exec_help: str | None = None,
) -> None:
    """Reject malformed, conflicting, or treatment-ambiguous CLI profiles."""

    expected_keys = {
        "schema_name",
        "schema_version",
        "executable",
        "argv",
        "environment",
        "stdin_mode",
        "reasoning_effort",
        "model",
        "sandbox",
        "output_mode",
    }
    if set(profile) != expected_keys:
        raise LaunchSurfaceError("launch profile fields drifted")
    if profile["schema_name"] != PROFILE_SCHEMA or profile["schema_version"] != 1:
        raise LaunchSurfaceError("launch profile schema drifted")
    if not isinstance(profile["executable"], str) or not profile["executable"]:
        raise LaunchSurfaceError("launch executable is missing")
    if profile["stdin_mode"] != STDIN_MODE or profile["output_mode"] != "jsonl":
        raise LaunchSurfaceError("launch input or output mode drifted")
    if profile["sandbox"] != "workspace-write-via-approve-for-me":
        raise LaunchSurfaceError("launch sandbox contract drifted")
    if not isinstance(profile["environment"], dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in profile["environment"].items()
    ):
        raise LaunchSurfaceError("launch environment must contain string pairs")
    argv = profile["argv"]
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        raise LaunchSurfaceError("launch argv must be a string array")
    if not argv or argv[0] != "exec" or argv[-1] != "-":
        raise LaunchSurfaceError("launch subcommand or stdin prompt mode drifted")

    counts = {flag: argv.count(flag) for flag in _SINGLETON_FLAGS}
    duplicates = sorted(flag for flag, count in counts.items() if count > 1)
    if duplicates:
        raise LaunchSurfaceError("duplicate singleton options: " + ", ".join(duplicates))
    if "--approve-for-me" in argv and ("--sandbox" in argv or "-s" in argv):
        raise LaunchSurfaceError(
            "--approve-for-me and --sandbox are mutually exclusive"
        )
    if "--approve-for-me" in argv and "--dangerously-bypass-approvals-and-sandbox" in argv:
        raise LaunchSurfaceError("automatic approval modes conflict")
    if "--sandbox" in argv and "-s" in argv:
        raise LaunchSurfaceError("duplicate sandbox option encodings conflict")
    if "--ask-for-approval" in argv and "-a" in argv:
        raise LaunchSurfaceError("duplicate approval option encodings conflict")

    for flag in REQUIRED_HELP_FLAGS:
        if flag == "--config":
            continue
        expected_count = (
            len(DISABLED_FEATURES) if flag == "--disable"
            else 1
        )
        if argv.count(flag) != expected_count:
            raise LaunchSurfaceError(
                f"required option {flag} has an unexpected occurrence count"
            )
    if argv.count("--disable") != len(DISABLED_FEATURES):
        raise LaunchSurfaceError("disabled feature surface drifted")
    disabled = [argv[index + 1] for index, item in enumerate(argv[:-1]) if item == "--disable"]
    if disabled != list(DISABLED_FEATURES):
        raise LaunchSurfaceError("disabled feature ordering or membership drifted")
    if _option_value(argv, "--color") != "never":
        raise LaunchSurfaceError("launch color mode drifted")
    if _option_value(argv, "--model") != profile["model"]:
        raise LaunchSurfaceError("launch model selection drifted")
    effort = profile["reasoning_effort"]
    if effort not in {"low", "medium"}:
        raise LaunchSurfaceError("reasoning effort must be low or medium")
    configs = [argv[index + 1] for index, item in enumerate(argv[:-1]) if item == "--config"]
    expected_effort = f'model_reasoning_effort="{effort}"'
    if configs.count(expected_effort) != 1:
        raise LaunchSurfaceError("native reasoning setting is absent or ambiguous")
    if sum(value.startswith("model_reasoning_effort=") for value in configs) != 1:
        raise LaunchSurfaceError("duplicate conflicting reasoning settings")
    required_configs = {
        expected_effort,
        'web_search="disabled"',
        "sandbox_workspace_write.network_access=false",
    }
    if set(configs) != required_configs or len(configs) != len(required_configs):
        raise LaunchSurfaceError("launch config surface drifted")
    if exec_help is not None:
        missing = [flag for flag in REQUIRED_HELP_FLAGS if flag not in exec_help]
        if missing:
            raise LaunchSurfaceError(
                "current Codex exec help lacks: " + ", ".join(missing)
            )


def validate_treatment_pair(
    low: Mapping[str, Any], medium: Mapping[str, Any], *, exec_help: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic diff and fail unless effort is the only treatment."""

    validate_launch_profile(low, exec_help=exec_help)
    validate_launch_profile(medium, exec_help=exec_help)
    if low["reasoning_effort"] != "low" or medium["reasoning_effort"] != "medium":
        raise LaunchSurfaceError("launch pair arms are mislabeled")
    normalized_low = _normalize_treatment(low)
    normalized_medium = _normalize_treatment(medium)
    if normalized_low != normalized_medium:
        raise LaunchSurfaceError("launch profiles differ outside reasoning effort")
    changed = _structural_diff(low, medium)
    allowed = {
        "/reasoning_effort",
        f"/argv/{_effort_index(low['argv'])}",
    }
    if set(changed) != allowed:
        raise LaunchSurfaceError("normalized launch diff is not treatment-only")
    return {
        "schema_name": "engineering-scope-guard.launch-profile-treatment-diff",
        "schema_version": 1,
        "changed_paths": sorted(changed),
        "low_values": {path: changed[path][0] for path in sorted(changed)},
        "medium_values": {path: changed[path][1] for path in sorted(changed)},
        "treatment_only": True,
    }


def validate_launch_contract(
    contract: Mapping[str, Any], *, exec_help: str | None = None,
) -> None:
    """Validate all hashes and the treatment-only pair in one frozen contract."""

    expected_keys = {
        "schema_name", "schema_version", "profiles", "profile_sha256s",
        "treatment_diff", "treatment_diff_sha256", "shell",
        "diagnostic_launch_cap", "contract_sha256",
    }
    if set(contract) != expected_keys:
        raise LaunchSurfaceError("launch contract fields drifted")
    if (
        contract["schema_name"]
        != "engineering-scope-guard.launch-surface-contract"
        or contract["schema_version"] != 1
        or contract["shell"] is not False
        or contract["diagnostic_launch_cap"] != 4
    ):
        raise LaunchSurfaceError("launch contract schema or policy drifted")
    profiles = contract["profiles"]
    if not isinstance(profiles, Mapping) or set(profiles) != {"low", "medium"}:
        raise LaunchSurfaceError("launch contract profiles drifted")
    treatment_diff = validate_treatment_pair(
        profiles["low"], profiles["medium"], exec_help=exec_help
    )
    if contract["treatment_diff"] != treatment_diff:
        raise LaunchSurfaceError("launch contract treatment diff drifted")
    expected_profile_hashes = {
        effort: hashlib.sha256(canonical_bytes(profile)).hexdigest()
        for effort, profile in profiles.items()
    }
    if contract["profile_sha256s"] != expected_profile_hashes:
        raise LaunchSurfaceError("launch profile hash drifted")
    if contract["treatment_diff_sha256"] != hashlib.sha256(
        canonical_bytes(treatment_diff)
    ).hexdigest():
        raise LaunchSurfaceError("launch treatment diff hash drifted")
    body = dict(contract)
    observed_contract_hash = body.pop("contract_sha256", None)
    if observed_contract_hash != hashlib.sha256(canonical_bytes(body)).hexdigest():
        raise LaunchSurfaceError("launch contract hash drifted")


def rendered_command(profile: Mapping[str, Any]) -> list[str]:
    """Render a validated argv-array process command without a shell."""

    validate_launch_profile(profile)
    return [profile["executable"], *profile["argv"]]


def _option_value(argv: Sequence[str], flag: str) -> str | None:
    try:
        index = argv.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(argv):
        raise LaunchSurfaceError(f"option {flag} lacks its required argument")
    return argv[index + 1]


def _effort_index(argv: Sequence[str]) -> int:
    matches = [
        index for index, value in enumerate(argv)
        if re.fullmatch(r'model_reasoning_effort="(?:low|medium)"', value)
    ]
    if len(matches) != 1:
        raise LaunchSurfaceError("reasoning setting index is ambiguous")
    return matches[0]


def _normalize_treatment(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(profile))
    value["reasoning_effort"] = "<EFFORT>"
    value["argv"][_effort_index(value["argv"])] = 'model_reasoning_effort="<EFFORT>"'
    return value


def _structural_diff(left: Any, right: Any, path: str = "") -> dict[str, tuple[Any, Any]]:
    if type(left) is not type(right):
        return {path or "/": (left, right)}
    if isinstance(left, dict):
        result: dict[str, tuple[Any, Any]] = {}
        for key in sorted(set(left) | set(right)):
            child = f"{path}/{key}"
            if key not in left or key not in right:
                result[child] = (left.get(key), right.get(key))
            else:
                result.update(_structural_diff(left[key], right[key], child))
        return result
    if isinstance(left, list):
        result = {}
        for index in range(max(len(left), len(right))):
            child = f"{path}/{index}"
            if index >= len(left) or index >= len(right):
                result[child] = (
                    left[index] if index < len(left) else None,
                    right[index] if index < len(right) else None,
                )
            else:
                result.update(_structural_diff(left[index], right[index], child))
        return result
    return {} if left == right else {path or "/": (left, right)}
