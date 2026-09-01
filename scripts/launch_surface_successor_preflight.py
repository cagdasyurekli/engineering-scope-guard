#!/usr/bin/env python3
"""Revalidate private predecessor evidence for the launch-surface successor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from engineering_scope_guard.evaluator_stable_qualification import validate_receipt
from engineering_scope_guard.launch_surface import canonical_bytes, validate_treatment_pair
from engineering_scope_guard.runtime_lock import sentinel, validate_runtime_receipt
try:
    from scripts import evaluator_stable_qualification as qualification_cli
    from scripts.launch_surface_contract import validate_contract as validate_launch_contract
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    import evaluator_stable_qualification as qualification_cli
    from launch_surface_contract import validate_contract as validate_launch_contract


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _write(path: Path, value: dict[str, Any]) -> None:
    if ".local" not in path.parts:
        raise ValueError("successor preflight must remain below .local")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(canonical_bytes(value))
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def _stability_gate(
    state: dict[str, Any], runtime_receipt: dict[str, Any], launch_contract: dict[str, Any]
) -> dict[str, Any]:
    expected_hash = state.get("state_sha256")
    body = {key: value for key, value in state.items() if key != "state_sha256"}
    if expected_hash != _digest(body):
        raise ValueError("runtime stability state hash drifted")
    if (
        state.get("schema_name")
        != "engineering-scope-guard.runtime-stability-soak"
        or state.get("active_runtime_receipt_sha256")
        != runtime_receipt["receipt_sha256"]
        or len(state.get("launches", [])) > 4
    ):
        raise ValueError("runtime stability state identity drifted")
    passes = {
        effort: [
            item for item in state["launches"]
            if item.get("effort") == effort and item.get("status") == "pass"
        ]
        for effort in ("low", "medium")
    }
    if any(len(items) != 1 for items in passes.values()):
        raise ValueError("LOW and MEDIUM do not each have exactly one passing launch")
    for effort, items in passes.items():
        item = items[0]
        if (
            item.get("runtime_receipt_sha256") != runtime_receipt["receipt_sha256"]
            or item.get("launch_profile_sha256")
            != launch_contract["profile_sha256s"][effort]
            or item.get("launch_surface_contract_sha256")
            != launch_contract["contract_sha256"]
            or item.get("return_code") != 0
            or item.get("prohibited_item_types") != []
            or "turn.completed" not in item.get("event_types", [])
        ):
            raise ValueError(f"passing {effort} launch receipt drifted")
    return {
        "diagnostic_launches_used": len(state["launches"]),
        "low_pass_ordinal": passes["low"][0]["ordinal"],
        "medium_pass_ordinal": passes["medium"][0]["ordinal"],
        "state_sha256": expected_hash,
    }


def _revalidate_historical_provenance(
    args: argparse.Namespace, qualification: dict[str, Any]
) -> None:
    """Reopen immutable sources without pretending the old venv is still live."""

    source = qualification["source"]
    evaluator = qualification_cli._git_source_identity(
        args.evaluator_root, allow_runtime_tmp=True
    )
    repolaunch = qualification_cli._git_source_identity(args.evaluator_root / "launch")
    actual = {
        "dataset_file_sha256": qualification_cli._dataset_hashes(args.dataset_root),
        "evaluator_revision": evaluator["revision"],
        "embedded_repolaunch_revision": repolaunch["revision"],
        "evaluator_tree_sha256": evaluator["tree_sha256"],
        "repolaunch_tree_sha256": repolaunch["tree_sha256"],
        "execution_code_sha256": qualification_cli._execution_code_identity(args.root),
        "reserve_receipt_sha256": qualification_cli.sha256_value(
            qualification_cli.read_json(args.reserve)
        ),
    }
    for field, value in actual.items():
        if source.get(field) != value:
            raise ValueError(f"frozen qualification source drifted: {field}")
def build(args: argparse.Namespace) -> dict[str, Any]:
    qualification = json.loads(args.qualification_receipt.read_text())
    validate_receipt(qualification)
    _revalidate_historical_provenance(args, qualification)
    qualification_cli._verify_completed_stages(args, qualification)
    if qualification.get("status") != "stable_pool_ready":
        raise ValueError("qualification is not stable_pool_ready")
    selected = sorted(
        [
            *qualification["selection"]["primary"],
            *qualification["selection"]["alternates"],
        ],
        key=lambda item: item["slot"],
    )
    if len(selected) < 14 or len({item["repo"] for item in selected}) < 14:
        raise ValueError("qualified population lacks fourteen independent clusters")
    runtime_receipt = json.loads(args.runtime_receipt.read_text())
    validate_runtime_receipt(runtime_receipt)
    runtime_sentinel = sentinel(runtime_receipt)
    launch_contract = json.loads(args.launch_contract.read_text())
    validate_launch_contract(launch_contract, args.codex_binary)
    treatment_diff = validate_treatment_pair(
        launch_contract["profiles"]["low"], launch_contract["profiles"]["medium"]
    )
    stability = _stability_gate(
        json.loads(args.stability_state.read_text()), runtime_receipt, launch_contract
    )
    live_evaluator_python = qualification_cli._python_identity(
        args.evaluator_python, args.evaluator_root
    )
    evaluator_identity = {
        **{
            key: qualification["source"][key]
            for key in (
                "evaluator_revision",
                "evaluator_tree_sha256",
                "embedded_repolaunch_revision",
                "repolaunch_tree_sha256",
            )
        },
        "live_evaluator_python": live_evaluator_python,
    }
    body = {
        "schema_name": "engineering-scope-guard.launch-surface-successor-preflight",
        "schema_version": 1,
        "qualification_receipt_sha256": qualification["state_sha256"],
        "qualified_independent_clusters": len(selected),
        "selection_was_outcome_blind": True,
        "prior_subject_invocation_starts": 0,
        "primary_slots": [item["slot"] for item in selected[:10]],
        "alternate_slots": [item["slot"] for item in selected[10:14]],
        "population_selection_sha256": _digest(selected[:14]),
        "evaluator_revision": qualification["source"]["evaluator_revision"],
        "historical_evaluator_python": qualification["source"]["evaluator_python"],
        "live_evaluator_python": live_evaluator_python,
        "evaluator_identity_sha256": _digest(evaluator_identity),
        "runtime_receipt_sha256": runtime_receipt["receipt_sha256"],
        "runtime_sentinel_identity_sha256": runtime_sentinel[
            "observed_identity_sha256"
        ],
        "launch_surface_contract_sha256": launch_contract["contract_sha256"],
        "treatment_diff_sha256": _digest(treatment_diff),
        "stability_gate": stability,
        "ready_for_external_gates": True,
    }
    body["preflight_sha256"] = _digest(body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--qualification-receipt", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--reserve", type=Path, required=True)
    parser.add_argument("--evaluator-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--evaluator-python", type=Path, required=True)
    parser.add_argument("--codex-binary", type=Path, required=True)
    parser.add_argument("--model-catalog", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--launch-contract", type=Path, required=True)
    parser.add_argument("--stability-state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.root = args.root.resolve()
    for name in (
        "qualification_receipt",
        "raw_root",
        "reserve",
        "evaluator_root",
        "dataset_root",
        "evaluator_python",
        "codex_binary",
        "model_catalog",
        "runtime_receipt",
        "launch_contract",
        "stability_state",
        "output",
    ):
        value = getattr(args, name)
        if not value.is_absolute():
            setattr(args, name, args.root / value)
    result = build(args)
    _write(args.output, result)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "qualified_independent_clusters",
                    "primary_slots",
                    "alternate_slots",
                    "runtime_receipt_sha256",
                    "launch_surface_contract_sha256",
                    "preflight_sha256",
                    "ready_for_external_gates",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
