#!/usr/bin/env python3
"""Persist a private read-only GitHub health receipt for successor freeze."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
from typing import Any

from engineering_scope_guard.pilot_contract import canonical_bytes, digest


REPOSITORY = "cagdasyurekli/engineering-scope-guard"
EXPECTED_COMMIT = "e7cb645bd56895fbd20719e5fc6b23112f6da7a1"
REQUIRED_CHECKS = {
    "Python 3.11",
    "Python 3.14",
    "Analyze (actions)",
    "Analyze (python)",
}


def _gh(endpoint: str) -> Any:
    completed = subprocess.run(
        ["gh", "api", endpoint], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "GitHub API request failed")
    return json.loads(completed.stdout)


def build(reader: Any = _gh) -> dict[str, Any]:
    repository = reader(f"repos/{REPOSITORY}")
    commit = reader(f"repos/{REPOSITORY}/commits/main")
    checks = reader(f"repos/{REPOSITORY}/commits/{EXPECTED_COMMIT}/check-runs")
    rulesets = reader(f"repos/{REPOSITORY}/rulesets")
    alerts = reader(f"repos/{REPOSITORY}/code-scanning/alerts?state=open&per_page=100")
    release = reader(f"repos/{REPOSITORY}/releases/tags/esg-rr-001-v0.6")
    check_runs = checks.get("check_runs") if isinstance(checks, dict) else None
    check_runs = check_runs if isinstance(check_runs, list) else []
    successful_checks = {
        item.get("name") for item in check_runs
        if isinstance(item, dict)
        and item.get("status") == "completed"
        and item.get("conclusion") == "success"
    }
    ruleset_values = rulesets if isinstance(rulesets, list) else []
    active_rulesets = sorted(
        str(item.get("name")) for item in ruleset_values
        if isinstance(item, dict) and item.get("enforcement") == "active"
    )
    open_alerts = alerts if isinstance(alerts, list) else []
    canonical_commit = commit.get("sha") if isinstance(commit, dict) else None
    body = {
        "schema_name": "engineering-scope-guard.canonical-repository-health",
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "repository": REPOSITORY,
        "default_branch": repository.get("default_branch"),
        "canonical_commit": canonical_commit,
        "repository_public": repository.get("private") is False,
        "active_rulesets": active_rulesets,
        "main_ruleset_active": bool(active_rulesets),
        "successful_required_checks": sorted(REQUIRED_CHECKS & successful_checks),
        "ci_passed": {"Python 3.11", "Python 3.14"} <= successful_checks,
        "codeql_passed": {"Analyze (actions)", "Analyze (python)"}
        <= successful_checks,
        "open_codeql_alerts": len(open_alerts),
        "prior_release_tag": release.get("tag_name") if isinstance(release, dict) else None,
        "prior_release_immutable": (
            release.get("immutable") is True if isinstance(release, dict) else False
        ),
        "status": "pass",
    }
    if not (
        body["default_branch"] == "main"
        and canonical_commit == EXPECTED_COMMIT
        and body["repository_public"]
        and body["main_ruleset_active"]
        and body["ci_passed"]
        and body["codeql_passed"]
        and body["open_codeql_alerts"] == 0
        and body["prior_release_tag"] == "esg-rr-001-v0.6"
        and body["prior_release_immutable"]
    ):
        body["status"] = "fail"
    return {**body, "canonical_health_sha256": digest(body)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ".local" not in args.output.parts:
        raise ValueError("canonical health receipt must remain below .local")
    receipt = build()
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_bytes(canonical_bytes(receipt))
    args.output.chmod(0o600)
    print(json.dumps({"status": receipt["status"], "canonical_health_sha256": receipt["canonical_health_sha256"]}, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
