#!/usr/bin/env python3
"""Freeze effort-v2 privately and admit cell 1 only after interface evidence.

This module never invokes Codex.  ``freeze`` prepares a narrowly scoped,
contentless-canary authority when the terminal qualifier does not already carry
current event/usage/tool-interface evidence.  ``verify`` consumes the resulting
receipt, records its one subject start, and only then creates the live seal.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from engineering_scope_guard.evaluator_stable_qualification import validate_receipt
from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import canonical_bytes, digest
from engineering_scope_guard.reasoning_effort_v1 import USAGE_FIELDS
from engineering_scope_guard.reasoning_effort_v2 import (
    ARMS,
    MAXIMUM_SUBJECT_INVOCATION_STARTS,
    build_contract,
    build_harness_source_closure,
    build_private_pool,
    subject_command_arguments,
    subject_command_identity,
    validate_contract,
    validate_harness_source_closure,
    validate_prior_evidence_identity,
    validate_private_pool_binding,
)

try:
    from scripts import evaluator_stable_qualification as qualifier_live
    from scripts import reasoning_effort_v2_execution_adapter as adapter
    from scripts import reasoning_effort_v2_runner as durable
    from scripts.reasoning_effort_v1_runner import parse_subject_trace
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    import evaluator_stable_qualification as qualifier_live
    import reasoning_effort_v2_execution_adapter as adapter
    import reasoning_effort_v2_runner as durable
    from reasoning_effort_v1_runner import parse_subject_trace


SCHEMA_VERSION = 1
FREEZE_STATE_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-freeze-state"
CANARY_AUTHORITY_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-canary-authority"
CANARY_RECEIPT_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-canary-receipt"
INTERFACE_OBSERVATION_SCHEMA = (
    "engineering-scope-guard.reasoning-effort-v2-subject-interface-observation"
)
CANARY_PROMPT = b"Reply with exactly CANARY and do not use tools.\n"
CANARY_EFFORT = "low"
_SAFE_CANARY_ITEM_TYPES = {"agent_message", "reasoning"}
_EVENT_TYPES = (
    "thread.started",
    "turn.started",
    "item.started",
    "item.completed",
    "turn.completed",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def _self_hash(value: dict[str, Any], field: str) -> bool:
    actual = value.get(field)
    return (
        isinstance(actual, str)
        and len(actual) == 64
        and actual == digest({key: item for key, item in value.items() if key != field})
    )


def _canonical_private_read(path: Path, label: str) -> dict[str, Any]:
    durable._require_private_artifact_path(path)
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError(f"{label} is unreadable or malformed") from error
    _require(isinstance(value, dict), f"{label} is not an object")
    expected = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _require(raw == expected, f"{label} is not canonical JSON")
    return value


def _write_private_json(path: Path, value: dict[str, Any], *, replace: bool = False) -> None:
    root = durable._execution_storage_root(path)
    _require(path.resolve().is_relative_to(root.resolve()), "freeze artifact escapes execution root")
    relative = path.absolute().relative_to(root.absolute())
    cursor = root
    for part in relative.parts[:-1]:
        cursor = cursor / part
        if cursor.exists() or cursor.is_symlink():
            _require(cursor.is_dir() and not cursor.is_symlink(), "freeze artifact traverses a symlink")
        else:
            cursor.mkdir(mode=0o700)
        cursor.chmod(0o700)
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if path.exists() and not replace:
        _require(
            path.is_file() and not path.is_symlink()
            and (path.stat().st_mode & 0o777) == 0o600,
            "existing freeze artifact is not an owner-private regular file",
        )
        _require(path.read_bytes() == encoded, "existing freeze artifact differs")
        return
    durable._atomic_json(path, value)
    path.chmod(0o600)
    _require(path.read_bytes() == encoded, "freeze artifact readback differs")


def _selected(receipt: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validate_receipt(receipt)
    _require(receipt["status"] == "stable_pool_ready", "qualification is not stable_pool_ready")
    selection = receipt.get("selection")
    _require(isinstance(selection, dict), "terminal qualification selection is missing")
    primaries = selection.get("primary")
    alternates = selection.get("alternates")
    _require(
        isinstance(primaries, list) and 10 <= len(primaries) <= 12,
        "terminal qualification must select 10 to 12 primaries",
    )
    _require(
        isinstance(alternates, list) and len(alternates) <= 4,
        "terminal qualification selected more than four alternates",
    )
    _require(
        [item.get("slot") for item in [*primaries, *alternates]]
        == sorted(item.get("slot") for item in [*primaries, *alternates]),
        "terminal qualification population order is not deterministic",
    )
    return primaries, alternates


def _source_identities(receipt: dict[str, Any]) -> dict[str, str]:
    source = receipt["source"]
    candidates = {candidate["slot"]: candidate for candidate in receipt["candidates"]}
    primaries, alternates = _selected(receipt)
    evaluator = digest(
        {
            key: source[key]
            for key in (
                "evaluator_revision",
                "evaluator_tree_sha256",
                "evaluator_python",
                "embedded_repolaunch_revision",
                "repolaunch_tree_sha256",
            )
        }
    )
    images = digest(
        [
            {"slot": item["slot"], "resolved_image": candidates[item["slot"]]["resolved_image"]}
            for item in [*primaries, *alternates]
        ]
    )
    return {
        "runtime_identity": digest(receipt["runtime_observation"]),
        "source_identity": digest(source),
        "evaluator_identity": evaluator,
        "image_pool_identity": images,
    }


def _tool_configuration_identity(contract: dict[str, Any]) -> str:
    commands: dict[str, list[str]] = {}
    for arm in ARMS:
        cell = next(item for item in contract["schedule"]["cells"] if item["arm"] == arm)
        commands[arm] = subject_command_arguments(contract, cell["cell_id"])
    return digest(
        {
            "schema_name": "engineering-scope-guard.reasoning-effort-v2-tool-configuration",
            "schema_version": SCHEMA_VERSION,
            "commands_by_arm": commands,
            "arms_differ_only_by_reasoning_effort": True,
            "sandbox": "workspace-write",
            "usage_fields": list(USAGE_FIELDS),
        }
    )


def _embedded_interface_observation(runtime: dict[str, Any]) -> bool:
    observation = runtime.get("subject_interface_observation")
    if not isinstance(observation, dict):
        return False
    expected_keys = {
        "schema_name",
        "schema_version",
        "model",
        "reasoning_efforts",
        "event_types",
        "usage_fields",
        "command_tool_prohibited",
        "interface_observation_sha256",
    }
    return (
        set(observation) == expected_keys
        and observation["schema_name"] == INTERFACE_OBSERVATION_SCHEMA
        and observation["schema_version"] == SCHEMA_VERSION
        and observation["model"] == runtime.get("model")
        and observation["reasoning_efforts"] == list(ARMS)
        and observation["event_types"] == list(_EVENT_TYPES)
        and observation["usage_fields"] == list(USAGE_FIELDS)
        and observation["command_tool_prohibited"] is True
        and _self_hash(observation, "interface_observation_sha256")
    )


def _contract(
    private_pool: dict[str, Any], receipt: dict[str, Any], *, canary_maximum: int,
    pool_reliability_audit_sha256: str,
) -> dict[str, Any]:
    runtime = receipt["runtime_observation"]
    identities = _source_identities(receipt)
    harness_source_closure = build_harness_source_closure(Path(__file__).resolve().parents[1])
    common = dict(
        model=runtime["model"],
        codex_version=runtime["codex_version"],
        runtime_identity=identities["runtime_identity"],
        source_identity=identities["source_identity"],
        qualification_receipt_sha256=receipt["state_sha256"],
        evaluator_identity=identities["evaluator_identity"],
        image_pool_identity=identities["image_pool_identity"],
        maximum_contentless_canary_subject_invocation_starts=canary_maximum,
        harness_source_closure=harness_source_closure,
        qualification_reliability_audit_sha256=pool_reliability_audit_sha256,
    )
    provisional = build_contract(
        private_pool,
        tool_configuration_identity=digest({"status": "derive-from-core-command"}),
        **common,
    )
    final = build_contract(
        private_pool,
        tool_configuration_identity=_tool_configuration_identity(provisional),
        **common,
    )
    validate_contract(final)
    return final


def _canary_authority(
    contract: dict[str, Any], private_pool: dict[str, Any], gate: dict[str, Any],
    *, codex_binary: Path,
) -> dict[str, Any]:
    cell = next(item for item in contract["schedule"]["cells"] if item["arm"] == CANARY_EFFORT)
    command = subject_command_arguments(contract, cell["cell_id"], codex_binary=str(codex_binary))
    body = {
        "schema_name": CANARY_AUTHORITY_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": "one-contentless-canary-authorized",
        "cell_execution_authorized": False,
        "contract_sha256": contract["contract_sha256"],
        "private_pool_sha256": private_pool["private_pool_sha256"],
        "qualification_gate_sha256": gate["qualification_gate_sha256"],
        "runtime_identity": contract["runtime"]["runtime_identity"],
        "tool_configuration_identity": contract["runtime"]["tool_configuration_identity"],
        "harness_source_closure_sha256": contract["source"]["harness_source_closure"][
            "closure_sha256"
        ],
        "harness_source_closure": deepcopy(contract["source"]["harness_source_closure"]),
        "prior_evidence_identity": deepcopy(contract["source"]["prior_evidence_identity"]),
        "sandbox": contract["runtime"]["sandbox"],
        "codex_binary_sha256": hashlib.sha256(codex_binary.read_bytes()).hexdigest(),
        "codex_version": contract["runtime"]["codex_version"],
        "model": contract["runtime"]["model"],
        "reasoning_effort": CANARY_EFFORT,
        "command": command,
        "command_sha256": digest(command),
        "path_independent_command_sha256": subject_command_identity(contract, cell["cell_id"]),
        "prompt_sha256": hashlib.sha256(CANARY_PROMPT).hexdigest(),
        "prompt_bytes": len(CANARY_PROMPT),
        "prompt_utf8": CANARY_PROMPT.decode("utf-8"),
        "task_content_included": False,
        "maximum_subject_invocation_starts": 1,
        "counts_toward_goal_maximum_56": True,
        "remaining_subject_start_capacity": MAXIMUM_SUBJECT_INVOCATION_STARTS - 1,
        "expected_event_types": list(_EVENT_TYPES),
        "expected_usage_fields": list(USAGE_FIELDS),
        "usage_measurement_scope": "fresh_session_cumulative_final",
        "commands_tools_and_search_permitted": False,
    }
    return {**body, "canary_authority_sha256": digest(body)}


def _validate_freeze_state(
    state: dict[str, Any], contract: dict[str, Any], private_pool: dict[str, Any],
    gate: dict[str, Any],
) -> None:
    expected = {
        "schema_name", "schema_version", "status", "contract_sha256",
        "private_pool_sha256", "schedule_sha256", "qualification_gate_sha256",
        "primary_count", "alternate_count", "cell_count",
        "task_and_repository_identities_withheld", "canary_subject_invocation_starts",
        "canary_authority_sha256", "live_seal_sha256", "freeze_state_sha256",
        "pool_reliability_audit_sha256", "harness_source_closure_sha256",
        "prior_evidence_sha256",
    }
    _require(set(state) == expected, "freeze state fields drifted")
    _require(
        state["schema_name"] == FREEZE_STATE_SCHEMA
        and state["schema_version"] == SCHEMA_VERSION
        and state["status"] in {"awaiting_contentless_canary", "live_authorized"}
        and state["contract_sha256"] == contract["contract_sha256"]
        and state["private_pool_sha256"] == private_pool["private_pool_sha256"]
        and state["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
        and state["qualification_gate_sha256"] == gate["qualification_gate_sha256"]
        and state["pool_reliability_audit_sha256"]
        == contract["source"]["qualification_reliability_audit_sha256"]
        and state["harness_source_closure_sha256"]
        == contract["source"]["harness_source_closure"]["closure_sha256"]
        and state["prior_evidence_sha256"]
        == contract["source"]["prior_evidence_identity"]["prior_evidence_sha256"]
        and state["primary_count"] == len(private_pool["primaries"])
        and state["alternate_count"] == len(private_pool["alternates"])
        and state["cell_count"] == len(contract["schedule"]["cells"])
        and state["task_and_repository_identities_withheld"] is True
        and state["canary_subject_invocation_starts"] in (0, 1)
        and _self_hash(state, "freeze_state_sha256"),
        "freeze state differs from the frozen authority",
    )


def _validate_canary_authority(
    authority: dict[str, Any], contract: dict[str, Any], private_pool: dict[str, Any],
    gate: dict[str, Any], *, codex_binary: Path,
) -> None:
    expected = {
        "schema_name", "schema_version", "status", "cell_execution_authorized",
        "contract_sha256", "private_pool_sha256", "qualification_gate_sha256",
        "runtime_identity", "tool_configuration_identity", "sandbox",
        "harness_source_closure_sha256",
        "harness_source_closure",
        "prior_evidence_identity",
        "codex_binary_sha256", "codex_version", "model",
        "reasoning_effort", "command", "command_sha256",
        "path_independent_command_sha256", "prompt_sha256", "prompt_bytes",
        "prompt_utf8",
        "task_content_included", "maximum_subject_invocation_starts",
        "counts_toward_goal_maximum_56", "remaining_subject_start_capacity",
        "expected_event_types", "expected_usage_fields", "usage_measurement_scope",
        "commands_tools_and_search_permitted", "canary_authority_sha256",
    }
    _require(set(authority) == expected, "canary authority fields drifted")
    expected_authority = _canary_authority(
        contract, private_pool, gate, codex_binary=codex_binary
    )
    _require(
        canonical_bytes(authority) == canonical_bytes(expected_authority)
        and _self_hash(authority, "canary_authority_sha256"),
        "canary authority differs from the frozen command/runtime interface",
    )


def _safe_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: state[key]
        for key in (
            "status",
            "contract_sha256",
            "private_pool_sha256",
            "schedule_sha256",
            "qualification_gate_sha256",
            "pool_reliability_audit_sha256",
            "harness_source_closure_sha256",
            "prior_evidence_sha256",
            "primary_count",
            "alternate_count",
            "cell_count",
            "canary_subject_invocation_starts",
            "live_seal_sha256",
        )
    }


def freeze(
    *,
    qualification_receipt_path: Path,
    qualification_raw_root: Path,
    execution_root: Path,
    root: Path,
    evaluator_python: Path,
    dataset_root: Path,
    codex_binary: Path,
    model_catalog: Path,
    reliability_investigation_path: Path | None = None,
    runtime_observer: Callable[[Path, Path], dict[str, Any]] | None = None,
    task_freezer: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Freeze private artifacts; withhold cell authority pending canary evidence."""

    durable.initialize_execution_storage(execution_root)
    execution_root = execution_root.resolve()
    durable._execution_storage_root(execution_root)
    durable._require_private_local_file(qualification_receipt_path, "qualification receipt")
    receipt, _receipt_raw = durable._canonical_json_file(
        qualification_receipt_path, "qualification receipt"
    )
    validate_receipt(receipt)
    investigation = None
    if reliability_investigation_path is not None:
        durable._require_private_local_file(
            reliability_investigation_path, "Phase-7 reliability investigation"
        )
        investigation, _investigation_raw = durable._canonical_json_file(
            reliability_investigation_path, "Phase-7 reliability investigation"
        )
    reliability_audit = durable.build_pool_reliability_audit(receipt, investigation)
    durable.validate_pool_reliability_audit(receipt, reliability_audit)
    _require(
        reliability_audit["status"] == "pass"
        and reliability_audit["investigation"]["cluster_presence_blocks_freeze"] is False,
        "Phase-7 reliability clusters require a complete private investigation",
    )
    primaries, alternates = _selected(receipt)
    observer = runtime_observer or qualifier_live._codex_runtime
    resolved_codex = codex_binary.resolve(strict=True)
    resolved_catalog = model_catalog.resolve(strict=True)
    current_runtime = observer(resolved_codex, resolved_catalog)
    _require(current_runtime == receipt["runtime_observation"], "current Codex/model runtime differs from qualification")
    _require(
        current_runtime.get("model") == "gpt-5.6-sol"
        and set(ARMS).issubset(current_runtime.get("supported_reasoning_efforts", [])),
        "current model or LOW/MEDIUM availability differs from the experiment",
    )
    _require(
        current_runtime.get("codex_executable_sha256")
        == hashlib.sha256(resolved_codex.read_bytes()).hexdigest()
        and current_runtime.get("model_catalog_sha256")
        == hashlib.sha256(resolved_catalog.read_bytes()).hexdigest(),
        "current Codex binary or model catalog hash differs from qualification",
    )
    freezer = task_freezer or adapter.freeze_private_pool_task_from_dataset
    common = {
        "root": root.resolve(),
        "evaluator_python": evaluator_python.resolve(strict=True),
        "dataset_root": dataset_root.resolve(),
        "qualification_receipt": receipt,
    }
    primary_tasks = [freezer(**common, candidate_slot=item["slot"]) for item in primaries]
    alternate_tasks = [freezer(**common, candidate_slot=item["slot"]) for item in alternates]
    private_pool = build_private_pool(primary_tasks, alternate_tasks)
    interface_ready = _embedded_interface_observation(current_runtime)
    contract = _contract(
        private_pool,
        receipt,
        canary_maximum=0 if interface_ready else 1,
        pool_reliability_audit_sha256=reliability_audit[
            "pool_reliability_audit_sha256"
        ],
    )
    gate = durable.build_qualification_gate_from_receipt(
        contract,
        private_pool,
        qualification_receipt_path,
        qualification_raw_root,
        pool_reliability_audit=reliability_audit,
    )
    authority = None if interface_ready else _canary_authority(
        contract, private_pool, gate, codex_binary=resolved_codex
    )
    live_seal = (
        durable.build_live_seal(contract, private_pool, gate) if interface_ready else None
    )
    state_body = {
        "schema_name": FREEZE_STATE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": "live_authorized" if live_seal is not None else "awaiting_contentless_canary",
        "contract_sha256": contract["contract_sha256"],
        "private_pool_sha256": private_pool["private_pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "qualification_gate_sha256": gate["qualification_gate_sha256"],
        "pool_reliability_audit_sha256": reliability_audit[
            "pool_reliability_audit_sha256"
        ],
        "harness_source_closure_sha256": contract["source"][
            "harness_source_closure"
        ]["closure_sha256"],
        "prior_evidence_sha256": contract["source"]["prior_evidence_identity"][
            "prior_evidence_sha256"
        ],
        "primary_count": len(primaries),
        "alternate_count": len(alternates),
        "cell_count": len(contract["schedule"]["cells"]),
        "task_and_repository_identities_withheld": True,
        "canary_subject_invocation_starts": 0,
        "canary_authority_sha256": (
            None if authority is None else authority["canary_authority_sha256"]
        ),
        "live_seal_sha256": None if live_seal is None else live_seal["live_seal_sha256"],
    }
    state = {**state_body, "freeze_state_sha256": digest(state_body)}
    for name, value in (
        ("private-pool.json", private_pool),
        ("pool-reliability-audit.json", reliability_audit),
        ("contract.json", contract),
        ("qualification-gate.json", gate),
        ("freeze-state.json", state),
    ):
        _write_private_json(execution_root / name, value)
    if authority is not None:
        _write_private_json(execution_root / "canary-authority.json", authority)
    if live_seal is not None:
        _write_private_json(execution_root / "live-seal.json", live_seal)
    return _safe_summary(state)


def _validate_canary_events(events: Any) -> dict[str, Any]:
    _require(isinstance(events, list) and events, "canary events are missing")
    _require(all(isinstance(event, dict) for event in events), "canary event is malformed")
    types = [event.get("type") for event in events]
    _require(
        types[0] == "thread.started"
        and len(types) >= 3
        and types[1] == "turn.started"
        and types[-1] == "turn.completed"
        and types.count("thread.started") == 1
        and types.count("turn.started") == 1
        and types.count("turn.completed") == 1
        and "turn.failed" not in types
        and all(item in _EVENT_TYPES for item in types),
        "canary thread/item/turn sequence is invalid",
    )
    for event in events:
        if event["type"] in {"item.started", "item.completed"}:
            item = event.get("item")
            _require(
                isinstance(item, dict)
                and item.get("type") in _SAFE_CANARY_ITEM_TYPES,
                "canary used a command, tool, search, or unknown item type",
            )
    encoded = b"".join(
        (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for event in events
    )
    trace = parse_subject_trace(encoded)
    _require(
        trace["activity"]["commands"] == 0
        and trace["activity"]["repository_search_commands"] == 0
        and trace["activity"]["external_search_items"] == 0
        and trace["provider_infrastructure_failure"] is False,
        "canary observed prohibited activity or provider failure",
    )
    _require(
        set(trace["usage"]["provider_reported"]) == set(USAGE_FIELDS),
        "canary usage fields differ from the frozen five-field schema",
    )
    return trace


def validate_canary_receipt(
    receipt: dict[str, Any], authority: dict[str, Any], private_pool: dict[str, Any]
) -> None:
    expected_keys = {
        "schema_name",
        "schema_version",
        "canary_authority_sha256",
        "contract_sha256",
        "subject_invocation_starts",
        "command_sha256",
        "codex_binary_sha256",
        "codex_version",
        "model",
        "reasoning_effort",
        "runtime_identity",
        "reservation_event_sha256",
        "ownership_nonce_sha256",
        "process_event_sha256",
        "process_identity_sha256",
        "prompt_sha256",
        "exit_code",
        "timed_out",
        "stderr_sha256",
        "events",
        "canary_receipt_sha256",
    }
    _require(set(receipt) == expected_keys, "canary receipt fields drifted")
    _require(
        receipt["schema_name"] == CANARY_RECEIPT_SCHEMA
        and receipt["schema_version"] == SCHEMA_VERSION
        and _self_hash(receipt, "canary_receipt_sha256")
        and receipt["canary_authority_sha256"] == authority["canary_authority_sha256"]
        and receipt["contract_sha256"] == authority["contract_sha256"]
        and receipt["subject_invocation_starts"] == 1
        and receipt["command_sha256"] == authority["command_sha256"]
        and receipt["codex_binary_sha256"] == authority["codex_binary_sha256"]
        and receipt["codex_version"] == authority["codex_version"]
        and receipt["model"] == authority["model"]
        and receipt["reasoning_effort"] == authority["reasoning_effort"]
        and receipt["runtime_identity"] == authority["runtime_identity"]
        and isinstance(receipt["reservation_event_sha256"], str)
        and len(receipt["reservation_event_sha256"]) == 64
        and isinstance(receipt["ownership_nonce_sha256"], str)
        and len(receipt["ownership_nonce_sha256"]) == 64
        and isinstance(receipt["process_event_sha256"], str)
        and len(receipt["process_event_sha256"]) == 64
        and isinstance(receipt["process_identity_sha256"], str)
        and len(receipt["process_identity_sha256"]) == 64
        and receipt["prompt_sha256"] == authority["prompt_sha256"]
        and receipt["exit_code"] == 0
        and receipt["timed_out"] is False
        and isinstance(receipt["stderr_sha256"], str)
        and len(receipt["stderr_sha256"]) == 64
        and set(receipt["stderr_sha256"]) <= set("0123456789abcdef"),
        "canary receipt differs from its exact runtime/command/prompt authority",
    )
    _validate_canary_events(receipt["events"])
    serialized = canonical_bytes(receipt)
    for task in [*private_pool["primaries"], *private_pool["alternates"]]:
        _require(
            task["task_id"].encode() not in serialized
            and task["repository"].encode() not in serialized,
            "canary receipt contains a private task or repository identity",
        )


def verify(
    *,
    qualification_receipt_path: Path,
    qualification_raw_root: Path,
    execution_root: Path,
    canary_receipt_path: Path,
    codex_binary: Path,
    model_catalog: Path,
    runtime_observer: Callable[[Path, Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate one externally produced canary receipt, then create cell authority."""

    execution_root = execution_root.resolve()
    durable._execution_storage_root(execution_root)
    contract = _canonical_private_read(execution_root / "contract.json", "contract")
    private_pool = _canonical_private_read(execution_root / "private-pool.json", "private pool")
    gate = _canonical_private_read(execution_root / "qualification-gate.json", "qualification gate")
    reliability_audit = _canonical_private_read(
        execution_root / "pool-reliability-audit.json", "pool reliability audit"
    )
    state = _canonical_private_read(execution_root / "freeze-state.json", "freeze state")
    authority = _canonical_private_read(execution_root / "canary-authority.json", "canary authority")
    validate_private_pool_binding(private_pool, contract)
    durable.validate_pool_reliability_audit(
        gate["qualification_receipt"], reliability_audit
    )
    _require(
        canonical_bytes(reliability_audit)
        == canonical_bytes(gate["pool_reliability_audit"]),
        "private pool reliability audit differs from the qualification gate",
    )
    validate_harness_source_closure(
        contract["source"]["harness_source_closure"],
        root=Path(__file__).resolve().parents[1],
    )
    validate_prior_evidence_identity(
        contract["source"]["prior_evidence_identity"],
        root=Path(__file__).resolve().parents[1],
    )
    _validate_freeze_state(state, contract, private_pool, gate)
    _validate_canary_authority(
        authority, contract, private_pool, gate,
        codex_binary=codex_binary.resolve(strict=True),
    )
    _require(
        state["status"] in {"awaiting_contentless_canary", "live_authorized"}
        and state["canary_authority_sha256"] == authority["canary_authority_sha256"],
        "freeze state does not authorize this canary",
    )
    rebuilt_gate = durable.build_qualification_gate_from_receipt(
        contract,
        private_pool,
        qualification_receipt_path,
        qualification_raw_root,
        pool_reliability_audit=reliability_audit,
    )
    _require(canonical_bytes(rebuilt_gate) == canonical_bytes(gate), "qualification gate readback differs")
    qualification = gate["qualification_receipt"]
    observer = runtime_observer or qualifier_live._codex_runtime
    resolved_codex = codex_binary.resolve(strict=True)
    resolved_catalog = model_catalog.resolve(strict=True)
    current_runtime = observer(resolved_codex, resolved_catalog)
    _require(current_runtime == qualification["runtime_observation"], "current runtime differs before canary admission")
    _require(
        hashlib.sha256(resolved_codex.read_bytes()).hexdigest()
        == authority["codex_binary_sha256"],
        "current Codex binary differs from canary authority",
    )
    _require(
        current_runtime.get("model_catalog_sha256")
        == hashlib.sha256(resolved_catalog.read_bytes()).hexdigest(),
        "current model catalog differs from canary authority",
    )
    canary = _canonical_private_read(canary_receipt_path, "candidate canary receipt")
    validate_canary_receipt(canary, authority, private_pool)
    lifecycle = durable.replay_canary_lifecycle(
        execution_root / "canary-ledger.jsonl", authority
    )
    _require(
        lifecycle["terminal_status"] == "success"
        and lifecycle["reservation"] is not None
        and lifecycle["process"] is not None
        and lifecycle["terminal"] is not None
        and lifecycle["terminal"]["payload"]["canary_receipt_sha256"]
        == canary["canary_receipt_sha256"]
        and canary["reservation_event_sha256"]
        == lifecycle["reservation"]["event_sha256"]
        and canary["ownership_nonce_sha256"]
        == lifecycle["reservation"]["payload"]["ownership_nonce_sha256"]
        and canary["process_event_sha256"] == lifecycle["process"]["event_sha256"]
        and canary["process_identity_sha256"]
        == lifecycle["process"]["payload"]["process_identity_sha256"],
        "canary receipt lacks the exactly-once durable pre-live lifecycle",
    )
    existing_canary = execution_root / "canary-receipt.json"
    if existing_canary.exists():
        persisted = _canonical_private_read(existing_canary, "persisted canary receipt")
        _require(
            canonical_bytes(persisted) == canonical_bytes(canary),
            "a different second canary receipt is forbidden",
        )
    else:
        _write_private_json(existing_canary, canary)
    live_seal = durable.build_live_seal(contract, private_pool, gate)
    _write_private_json(execution_root / "live-seal.json", live_seal)
    events = durable.read_ledger(execution_root / "ledger.jsonl", contract)
    canary_events = [
        event for event in events
        if event["event_type"] == "canary_lifecycle_imported"
    ]
    if not canary_events:
        _require(not events, "canary must precede every frozen cell event")
        durable.append_ledger_event(
            execution_root / "ledger.jsonl",
            execution_root / "checkpoint.json",
            contract,
            live_seal,
            private_pool,
            "canary_lifecycle_imported",
            {
                "lifecycle_terminal_event_sha256": lifecycle["terminal"]["event_sha256"],
                "canary_receipt_sha256": canary["canary_receipt_sha256"],
            },
        )
    else:
        _require(
            len(canary_events) == 1
            and canary_events[0]["payload"]["canary_receipt_sha256"]
            == canary["canary_receipt_sha256"],
            "duplicate or different canary start is forbidden",
        )
    updated_body = {
        key: value
        for key, value in state.items()
        if key != "freeze_state_sha256"
    }
    updated_body.update(
        {
            "status": "live_authorized",
            "canary_subject_invocation_starts": 1,
            "live_seal_sha256": live_seal["live_seal_sha256"],
        }
    )
    updated = {**updated_body, "freeze_state_sha256": digest(updated_body)}
    _write_private_json(execution_root / "freeze-state.json", updated, replace=True)
    return _safe_summary(updated)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "verify"))
    parser.add_argument("--qualification-receipt", type=Path, required=True)
    parser.add_argument("--qualification-raw-root", type=Path, required=True)
    parser.add_argument("--execution-root", type=Path, required=True)
    parser.add_argument("--codex-binary", type=Path, required=True)
    parser.add_argument("--model-catalog", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--evaluator-python", type=Path)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--reliability-investigation", type=Path)
    parser.add_argument("--canary-receipt", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if args.command == "freeze":
        _require(args.evaluator_python is not None, "freeze requires --evaluator-python")
        _require(args.dataset_root is not None, "freeze requires --dataset-root")
        result = freeze(
            qualification_receipt_path=args.qualification_receipt,
            qualification_raw_root=args.qualification_raw_root,
            execution_root=args.execution_root,
            root=args.root,
            evaluator_python=args.evaluator_python,
            dataset_root=args.dataset_root,
            codex_binary=args.codex_binary,
            model_catalog=args.model_catalog,
            reliability_investigation_path=args.reliability_investigation,
        )
    else:
        _require(args.canary_receipt is not None, "verify requires --canary-receipt")
        result = verify(
            qualification_receipt_path=args.qualification_receipt,
            qualification_raw_root=args.qualification_raw_root,
            execution_root=args.execution_root,
            canary_receipt_path=args.canary_receipt,
            codex_binary=args.codex_binary,
            model_catalog=args.model_catalog,
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
