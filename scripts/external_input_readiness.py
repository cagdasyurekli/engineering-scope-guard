#!/usr/bin/env python3
"""Audit the bounded external-input readiness record without running a Pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class ReadinessError(RuntimeError):
    """Raised when the readiness record contradicts its evidence artifacts."""


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReadinessError(f"expected JSON object: {path}")
    return value


def audit(readiness_path: Path, root: Path) -> dict[str, Any]:
    readiness = _read(readiness_path)
    if readiness.get("schema_name") != "engineering-scope-guard.external-input-readiness":
        raise ReadinessError("unsupported readiness schema")
    partition = _read(root / readiness["partition"]["path"])
    smoke = _read(root / readiness["smoke"]["path"])
    checks = {
        "source_identity": (
            readiness["selected_source"]["revision"] == partition["source"]["revision"]
        ),
        "eligible_supply": (
            readiness["supply"]["source_eligible_distinct_tasks"]
            == partition["eligibility"]["eligible_distinct_tasks"]
        ),
        "pilot_count": (
            readiness["supply"]["pilot_tasks"] == partition["partition"]["pilot_count"]
        ),
        "reserve_count": (
            readiness["supply"]["confirmatory_reserve_tasks"]
            == partition["partition"]["confirmatory_reserve_count"]
        ),
        "allocation_commitment": (
            readiness["partition"]["allocation_sha256"]
            == partition["partition"]["allocation_sha256"]
        ),
        "reserve_hidden": (
            partition["partition"]["reserve_ids_or_bodies_emitted"] is False
        ),
        "smoke_pre_subject_failure": (
            smoke["execution"]["failure_class"] == "infrastructure-pre-subject-failure"
            and smoke["execution"]["codex_subject_invoked"] is False
            and smoke["execution"]["evaluator_invoked"] is False
        ),
        "reviewer_capacity_zero": readiness["review"]["independent_experienced_reviewers"] == 0,
        "pilot_not_authorized": readiness["pilot_authorized"] is False,
        "bounded_conclusion": readiness["bounded_conclusion"] == "REDESIGN REQUIRED",
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise ReadinessError(f"readiness checks failed: {failed}")
    return {
        "schema_name": "engineering-scope-guard.external-input-readiness-audit",
        "schema_version": 1,
        "status": "pass",
        "checks": checks,
        "eligible_distinct_tasks": readiness["supply"]["source_eligible_distinct_tasks"],
        "pilot_tasks": readiness["supply"]["pilot_tasks"],
        "confirmatory_reserve_tasks": readiness["supply"]["confirmatory_reserve_tasks"],
        "pilot_authorized": readiness["pilot_authorized"],
        "bounded_conclusion": readiness["bounded_conclusion"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--readiness",
        type=Path,
        default=Path("experiment/external_input_readiness.json"),
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(audit(args.readiness, args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
