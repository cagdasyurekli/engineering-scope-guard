"""Static inspection of the installed Codex command surface."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from typing import Any

KNOWN_GAPS = [
    "codex exec --json documents event categories, not a frozen exhaustive schema",
    "hooks do not observe hosted tools such as WebSearch",
    "specialized local tool paths may opt out of hooks",
    "hook transcript_path content is not a stable interface",
    "SessionEnd is delayed and is not an immediate turn boundary",
]

_VERSION_RE = re.compile(r"\bcodex-cli\s+([^\s]+)")
_HOOKS_RE = re.compile(r"^hooks\s+(\S+)\s+(true|false)\s*$", re.MULTILINE)


def _run_command(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run one fixed local introspection command without invoking a shell."""

    return subprocess.run(
        list(arguments),
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )


def inspect_codex() -> dict[str, Any]:
    """Inspect static CLI capabilities; never authenticate or contact a provider."""

    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "unsupported",
        "codex": {
            "available": False,
            "version": None,
            "exec_json": False,
            "hooks": {"maturity": None, "enabled": None},
        },
        "known_gaps": list(KNOWN_GAPS),
        "diagnostics": [],
    }

    try:
        version = _run_command(("codex", "--version"))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as error:
        result["diagnostics"].append(f"codex --version failed: {type(error).__name__}")
        return result

    if version.returncode != 0:
        result["diagnostics"].append(
            f"codex --version exited with status {version.returncode}"
        )
        return result

    result["codex"]["available"] = True
    match = _VERSION_RE.search(version.stdout)
    if match:
        result["codex"]["version"] = match.group(1)
    else:
        result["diagnostics"].append("Codex version output was not recognized")

    try:
        exec_help = _run_command(("codex", "exec", "--help"))
    except (subprocess.TimeoutExpired, OSError) as error:
        result["diagnostics"].append(f"codex exec --help failed: {type(error).__name__}")
        return result

    if exec_help.returncode == 0 and re.search(r"^\s*--json\b", exec_help.stdout, re.MULTILINE):
        result["codex"]["exec_json"] = True
    else:
        result["diagnostics"].append("codex exec --json was not found")
        return result

    status = "healthy" if result["codex"]["version"] is not None else "degraded"
    try:
        features = _run_command(("codex", "features", "list"))
    except (subprocess.TimeoutExpired, OSError) as error:
        result["diagnostics"].append(f"codex features list failed: {type(error).__name__}")
        status = "degraded"
    else:
        hook_match = _HOOKS_RE.search(features.stdout) if features.returncode == 0 else None
        if hook_match:
            result["codex"]["hooks"] = {
                "maturity": hook_match.group(1),
                "enabled": hook_match.group(2) == "true",
            }
        else:
            result["diagnostics"].append("hooks feature status was not available")
            status = "degraded"

    result["status"] = status
    return result
