#!/usr/bin/env python3
"""Run the four registered, exploratory development tasks through three arms."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from engineering_scope_guard.cli import initialize, run_analysis, take_snapshot
from engineering_scope_guard.doctor import inspect_codex
from engineering_scope_guard.experiment import (
    ARMS,
    ExperimentConfigurationError,
    _snapshot_fingerprint,
    capture_run_record,
    prepare_cells,
    run_isolation_canary,
)
from engineering_scope_guard.report import write_json
from engineering_scope_guard.trace import _verification_kind


ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = ROOT / "experiment" / "development_tasks"
POLICIES = ROOT / "experiment" / "arms"
MODEL = "gpt-5.6-terra"
REASONING = "medium"
TIMEOUT_SECONDS = 900
READ_PROGRAMS = {"cat", "find", "head", "ls", "rg", "sed", "tail", "wc"}

WAVE_TASKS = {
    1: ("dev-reuse-01", "dev-irreducible-01"),
    2: ("dev-guard-01", "dev-shared-01"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registry() -> dict[str, Any]:
    value = json.loads((TASKS_ROOT / "registry.json").read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or not isinstance(value.get("tasks"), list)
    ):
        raise ExperimentConfigurationError("development task registry is invalid")
    return value


def audit_registry() -> dict[str, Any]:
    """Verify every registered packet before a provider run."""

    registry = _registry()
    expected_ids = tuple(task for wave in (1, 2) for task in WAVE_TASKS[wave])
    records = registry["tasks"]
    if tuple(record.get("task_id") for record in records) != expected_ids:
        raise ExperimentConfigurationError("registry task IDs/order differ from the frozen design")
    checks: list[dict[str, Any]] = []
    for record in records:
        task_id = record["task_id"]
        packet = TASKS_ROOT / task_id
        actual = {
            "source_fingerprint": _snapshot_fingerprint(packet / "source"),
            "task_sha256": _sha256(packet / "task.md"),
            "evaluator_fingerprint": _snapshot_fingerprint(packet / "evaluator"),
        }
        expected = {name: record[name] for name in actual}
        if actual != expected or record.get("wave") not in (1, 2):
            raise ExperimentConfigurationError(f"registered bytes changed for {task_id}")
        checks.append({"task_id": task_id, "status": "pass", **actual})
    return {
        "schema_name": "engineering-scope-guard.development-registry-audit",
        "schema_version": 1,
        "status": "pass",
        "task_count": len(checks),
        "checks": checks,
    }


def _schedule(wave: int) -> list[tuple[str, str, str]]:
    first, second = WAVE_TASKS[wave]
    schedule: list[tuple[str, str, str]] = []
    for task_id in (first, second):
        schedule.extend((task_id, "r1", arm) for arm in ARMS)
    for task_id in (second, first):
        schedule.extend((task_id, "r2", arm) for arm in reversed(ARMS))
    return schedule


def _prompt(task_id: str, cell: dict[str, Any], state: Path) -> bytes:
    task = (TASKS_ROOT / task_id / "task.md").read_bytes()
    if cell["intervention"] is None:
        return task
    policy = (state / cell["intervention"]).read_bytes()
    return policy + b"\n--- Task ---\n\n" + task


def _command() -> list[str]:
    return [
        "codex", "exec", "-", "--json", "--ephemeral", "--ignore-user-config",
        "--ignore-rules", "--approve-for-me",
        "--skip-git-repo-check", "--color", "never", "--model", MODEL,
        "--config", f'model_reasoning_effort="{REASONING}"',
    ]


def _initialize_git(repository: Path) -> None:
    """Give agent cells the ordinary local diff surface expected by Codex."""

    commands = (
        ["git", "init", "-q"],
        ["git", "config", "user.name", "Development Experiment"],
        ["git", "config", "user.email", "development@example.invalid"],
        ["git", "add", "."],
        ["git", "commit", "-qm", "fixture start"],
    )
    for command in commands:
        completed = subprocess.run(command, cwd=repository, check=False, capture_output=True)
        if completed.returncode != 0:
            raise ExperimentConfigurationError(
                f"cannot initialize task git fixture: {completed.stderr.decode(errors='replace').strip()}"
            )


def _run_process(
    command: list[str], cwd: Path, environment: dict[str, str], timeout: int,
    stdin: bytes | None = None,
) -> tuple[int | None, bool, int, bytes, bytes]:
    started = time.monotonic_ns()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(input=stdin, timeout=timeout)
        timed_out = False
        exit_code: int | None = process.returncode
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        timed_out = True
        exit_code = None
    wall_time_ms = (time.monotonic_ns() - started) // 1_000_000
    return exit_code, timed_out, wall_time_ms, stdout, stderr


def _verification(repository: Path, evaluator: Path, raw: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository)
    commands = [
        ("existing-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("external-acceptance", [sys.executable, "-m", "unittest", "discover", "-s", str(evaluator), "-v"]),
    ]
    results: list[dict[str, Any]] = []
    for name, command in commands:
        completed = subprocess.run(
            command, cwd=repository, env=environment, check=False,
            capture_output=True, timeout=120,
        )
        (raw / f"{name}.stdout").write_bytes(completed.stdout)
        (raw / f"{name}.stderr").write_bytes(completed.stderr)
        results.append({"name": name, "kind": "test", "exit_code": completed.returncode})
    return {"schema_version": 1, "results": results}


def trace_mechanics(trace: Path, repository: Path) -> dict[str, Any]:
    """Extract conservative sequence diagnostics from raw exec JSONL."""

    events: list[tuple[str, Any]] = []
    read_commands = 0
    observed_paths: set[str] = set()
    verification_commands = 0
    failed_verifications = 0
    for line in trace.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("type") != "item.completed":
            continue
        item = record.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") == "command_execution":
            raw_command = item.get("command", "")
            command = " ".join(raw_command) if isinstance(raw_command, list) else str(raw_command)
            kind = _verification_kind(command)
            exit_code = item.get("exit_code")
            events.append(("command", {"kind": kind, "exit_code": exit_code}))
            if kind != "other":
                verification_commands += 1
                if isinstance(exit_code, int) and exit_code != 0:
                    failed_verifications += 1
            try:
                wrapper_tokens = shlex.split(command)
            except ValueError:
                wrapper_tokens = []
            if (
                len(wrapper_tokens) >= 3
                and Path(wrapper_tokens[0]).name in {"bash", "sh", "zsh"}
                and wrapper_tokens[1] in {"-c", "-lc"}
            ):
                try:
                    tokens = shlex.split(wrapper_tokens[2])
                except ValueError:
                    tokens = []
            else:
                tokens = wrapper_tokens
            segments: list[list[str]] = [[]]
            for token in tokens:
                if token in {"&&", "||", ";", "|"}:
                    segments.append([])
                else:
                    segments[-1].append(token)
            for segment in segments:
                while segment and "=" in segment[0] and not segment[0].startswith(("/", "./")):
                    segment = segment[1:]
                if not segment:
                    continue
                program = Path(segment[0]).name
                if program not in READ_PROGRAMS:
                    continue
                read_commands += 1
                for token in segment[1:]:
                    if token.startswith("-"):
                        continue
                    candidate = (repository / token).resolve(strict=False)
                    try:
                        relative = candidate.relative_to(repository.resolve()).as_posix()
                    except ValueError:
                        continue
                    if candidate.exists():
                        observed_paths.add(relative)
        elif item.get("type") == "file_change":
            paths = []
            changes = item.get("changes")
            if isinstance(changes, list):
                for change in changes:
                    if not isinstance(change, dict) or not isinstance(change.get("path"), str):
                        continue
                    path = Path(change["path"])
                    if path.is_absolute():
                        try:
                            normalized = path.relative_to(repository).as_posix()
                        except ValueError:
                            continue
                    else:
                        normalized = path.as_posix()
                    paths.append(normalized)
            events.append(("edit", paths))

    failed_loops = 0
    for index, (kind, value) in enumerate(events):
        if kind == "command" and value["kind"] != "other" and value["exit_code"] not in (0, None):
            if any(later_kind == "edit" for later_kind, _ in events[index + 1:]):
                failed_loops += 1

    rework_paths: set[str] = set()
    for index, (kind, paths) in enumerate(events):
        if kind != "edit":
            continue
        later = events[index + 1:]
        verification_index = next(
            (offset for offset, (later_kind, value) in enumerate(later)
             if later_kind == "command" and value["kind"] != "other"),
            None,
        )
        if verification_index is None:
            continue
        for later_kind, later_paths in later[verification_index + 1:]:
            if later_kind == "edit":
                rework_paths.update(set(paths).intersection(later_paths))

    return {
        "schema_name": "engineering-scope-guard.development-trace-mechanics",
        "schema_version": 1,
        "coverage": "codex exec completed command/file-change items only",
        "read_search_commands": read_commands,
        "observed_repository_paths": sorted(observed_paths),
        "verification_commands": verification_commands,
        "failed_verification_commands": failed_verifications,
        "failed_verification_loops": failed_loops,
        "post_hoc_rework_paths": sorted(rework_paths),
    }


def run_wave(wave: int, state_dir: Path, auth_file: Path) -> dict[str, Any]:
    """Run one frozen twelve-session wave and retain every cell."""

    audit = audit_registry()
    if state_dir.exists() and any(state_dir.iterdir()):
        raise ExperimentConfigurationError("wave state directory must be absent or empty")
    state_dir.mkdir(parents=True, exist_ok=True)
    write_json(state_dir / "registry-audit.json", audit)
    canary_dir = state_dir / "isolation-canary"
    run_isolation_canary(TASKS_ROOT / WAVE_TASKS[wave][0] / "source", canary_dir, POLICIES)

    capability = inspect_codex()
    if capability["codex"]["version"] != "0.150.1":
        raise ExperimentConfigurationError("installed Codex version differs from frozen wave rules")
    auth = auth_file.resolve(strict=True)
    ledger: list[dict[str, Any]] = []
    prepared: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}

    for task_id, run_id, arm in _schedule(wave):
        key = (task_id, run_id)
        if key not in prepared:
            cell_state = state_dir / "runs" / task_id / run_id
            manifest = prepare_cells(TASKS_ROOT / task_id / "source", cell_state, POLICIES)
            prepared[key] = (cell_state, manifest)
        cell_state, manifest = prepared[key]
        cell = next(item for item in manifest["cells"] if item["arm"] == arm)
        repository = (cell_state / cell["repository"]).resolve(strict=True)
        codex_home = (cell_state / cell["codex_home"]).resolve(strict=True)
        raw = (cell_state / cell["raw_output"]).resolve(strict=True)
        derived = (cell_state / cell["derived_output"]).resolve(strict=True)
        auth_link = codex_home / "auth.json"
        auth_link.symlink_to(auth)
        _initialize_git(repository)

        prompt = _prompt(task_id, cell, cell_state)
        (raw / "prompt.bin").write_bytes(prompt)
        environment = os.environ.copy()
        environment.update({
            "CODEX_HOME": str(codex_home),
            "ESG_EXPERIMENT_ARM": arm,
            "ESG_EXPERIMENT_TASK": task_id,
            "ESG_EXPERIMENT_RUN": run_id,
        })

        config = initialize(repository, derived / "v0")
        take_snapshot(config, "before")
        exit_code, timed_out, wall_time_ms, stdout, stderr = _run_process(
            _command(), repository, environment, TIMEOUT_SECONDS, prompt,
        )
        trace = raw / "trace.jsonl"
        trace.write_bytes(stdout)
        (raw / "codex.stderr").write_bytes(stderr)
        take_snapshot(config, "after")
        _analysis_code, events, _report = run_analysis(config, trace, capability)

        verification = _verification(repository, TASKS_ROOT / task_id / "evaluator", raw)
        verification_path = derived / "verification.json"
        write_json(verification_path, verification)
        execution = {
            "schema_version": 1,
            "task_id": task_id,
            "run_id": run_id,
            "arm": arm,
            "wall_time_ms": wall_time_ms,
            "timed_out": timed_out,
            "process_exit_code": exit_code,
        }
        execution_path = derived / "execution.json"
        write_json(execution_path, execution)
        record_path = derived / "record.json"
        record = capture_run_record(
            trace, execution_path, verification_path, events, record_path,
        )
        mechanics = trace_mechanics(trace, repository)
        write_json(derived / "mechanics.json", mechanics)
        receipt = {
            "schema_name": "engineering-scope-guard.development-run-receipt",
            "schema_version": 1,
            "task_id": task_id,
            "run_id": run_id,
            "arm": arm,
            "model": MODEL,
            "reasoning": REASONING,
            "codex_version": capability["codex"]["version"],
            "timeout_seconds": TIMEOUT_SECONDS,
            "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
            "intervention_sha256": cell["intervention_sha256"],
            "repository_start_fingerprint": cell["repository_fingerprint"],
            "shared_auth_symlink": True,
            "billing_supplied": False,
        }
        write_json(derived / "receipt.json", receipt)
        if record["turns"]["started"] == 0 and exit_code not in (0, None):
            result_class = "infrastructure-pre-provider-failure"
        elif timed_out or exit_code != 0:
            result_class = "agent-failure"
        else:
            result_class = "completed"
        ledger.append({
            "task_id": task_id,
            "run_id": run_id,
            "arm": arm,
            "result": result_class,
            "accepted": record["verification"]["all_passed"],
            "record": str(record_path.relative_to(state_dir)),
            "mechanics": str((derived / "mechanics.json").relative_to(state_dir)),
            "receipt": str((derived / "receipt.json").relative_to(state_dir)),
        })
        write_json(state_dir / "ledger.json", {
            "schema_version": 1, "wave": wave, "planned_sessions": 12,
            "completed_sessions": len(ledger), "runs": ledger,
        })
    return {"wave": wave, "sessions": len(ledger), "ledger": ledger}


def summarize_wave(state_dir: Path) -> dict[str, Any]:
    """Build a deterministic diagnostic summary without efficacy statistics."""

    ledger = json.loads((state_dir / "ledger.json").read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for item in ledger["runs"]:
        record = json.loads((state_dir / item["record"]).read_text(encoding="utf-8"))
        mechanics_path = state_dir / item["mechanics"]
        cell = mechanics_path.parent.parent
        trace = cell / "raw" / "trace.jsonl"
        repository = cell / "repository"
        if trace.exists() and repository.is_dir():
            mechanics = trace_mechanics(trace, repository)
            write_json(mechanics_path, mechanics)
        else:
            mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
        structural = next(
            event for event in record["v0_events"] if event["event"] == "structural_delta"
        )
        dependency = next(
            event for event in record["v0_events"] if event["event"] == "dependency_delta"
        )
        rows.append({
            "task_id": item["task_id"],
            "run_id": item["run_id"],
            "arm": item["arm"],
            "result": item["result"],
            "accepted": item["accepted"],
            "wall_time_ms": record["execution"]["wall_time_ms"],
            "timed_out": record["execution"]["timed_out"],
            "turns_completed": record["turns"]["completed"],
            "usage_status": record["usage"]["status"],
            "usage": record["usage"]["components"],
            "billing_status": record["billing"]["status"],
            "failed_verification_loops": mechanics["failed_verification_loops"],
            "verification_commands": mechanics["verification_commands"],
            "failed_verification_commands": mechanics["failed_verification_commands"],
            "post_hoc_rework_paths": mechanics["post_hoc_rework_paths"],
            "read_search_commands": mechanics["read_search_commands"],
            "observed_repository_paths": mechanics["observed_repository_paths"],
            "files": structural["files"]["counts"],
            "loc_added": structural["loc"]["added"],
            "loc_deleted": structural["loc"]["deleted"],
            "dependencies_added": len(dependency["added"]),
            "dependencies_removed": len(dependency["removed"]),
        })

    arms: dict[str, Any] = {}
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        usage_names = sorted({name for row in selected for name in row["usage"]})
        arms[arm] = {
            "runs": len(selected),
            "accepted": sum(row["accepted"] for row in selected),
            "timeouts": sum(row["timed_out"] for row in selected),
            "execution_failures": sum(row["result"] != "completed" for row in selected),
            "wall_time_ms": [row["wall_time_ms"] for row in selected],
            "turns_completed": sum(row["turns_completed"] for row in selected),
            "usage_component_sums": {
                name: sum(row["usage"].get(name, 0) for row in selected)
                for name in usage_names
            },
            "billing_statuses": sorted({row["billing_status"] for row in selected}),
            "failed_verification_loops": sum(row["failed_verification_loops"] for row in selected),
            "verification_commands": sum(row["verification_commands"] for row in selected),
            "failed_verification_commands": sum(row["failed_verification_commands"] for row in selected),
            "post_hoc_rework_path_count": sum(len(row["post_hoc_rework_paths"]) for row in selected),
            "read_search_commands": sum(row["read_search_commands"] for row in selected),
            "observed_repository_path_count": sum(len(row["observed_repository_paths"]) for row in selected),
            "loc_added": sum(row["loc_added"] for row in selected),
            "loc_deleted": sum(row["loc_deleted"] for row in selected),
            "files_added": sum(row["files"]["added"] for row in selected),
            "files_modified": sum(row["files"]["modified"] for row in selected),
            "files_deleted": sum(row["files"]["deleted"] for row in selected),
            "dependencies_added": sum(row["dependencies_added"] for row in selected),
            "dependencies_removed": sum(row["dependencies_removed"] for row in selected),
        }
    summary = {
        "schema_name": "engineering-scope-guard.development-wave-summary",
        "schema_version": 1,
        "interpretation": "exploratory development diagnostics only; not efficacy evidence",
        "wave": ledger["wave"],
        "sessions": len(rows),
        "arms": arms,
        "runs": rows,
    }
    write_json(state_dir / "summary.json", summary)
    return summary


def summarize_experiment(wave_states: list[Path], output: Path) -> dict[str, Any]:
    """Combine two complete wave summaries without pooling their harness versions."""

    summaries = [summarize_wave(path) for path in wave_states]
    if sorted(summary["wave"] for summary in summaries) != [1, 2]:
        raise ExperimentConfigurationError("combined summary requires exactly waves 1 and 2")
    if any(summary["sessions"] != 12 for summary in summaries):
        raise ExperimentConfigurationError("combined summary requires 12 sessions per wave")
    combined: dict[str, Any] = {}
    sum_fields = (
        "runs", "accepted", "timeouts", "execution_failures", "turns_completed",
        "failed_verification_loops", "post_hoc_rework_path_count",
        "verification_commands", "failed_verification_commands",
        "read_search_commands", "observed_repository_path_count", "loc_added",
        "loc_deleted", "files_added", "files_modified", "files_deleted",
        "dependencies_added", "dependencies_removed",
    )
    for arm in ARMS:
        wave_values = [summary["arms"][arm] for summary in summaries]
        usage_names = sorted({
            name for value in wave_values for name in value["usage_component_sums"]
        })
        combined[arm] = {
            **{name: sum(value[name] for value in wave_values) for name in sum_fields},
            "wall_time_ms": sum((value["wall_time_ms"] for value in wave_values), []),
            "usage_component_sums": {
                name: sum(value["usage_component_sums"].get(name, 0) for value in wave_values)
                for name in usage_names
            },
            "billing_statuses": sorted({
                status for value in wave_values for status in value["billing_statuses"]
            }),
        }
    full = combined["full"]
    short = combined["short"]
    result = {
        "schema_name": "engineering-scope-guard.development-experiment-summary",
        "schema_version": 1,
        "interpretation": "exploratory development diagnostics only; not efficacy evidence",
        "policy_version": "v0.1",
        "harness_versions": {"wave_1": "v0.1", "wave_2": "v0.2"},
        "planned_sessions": 24,
        "infrastructure_replacements": 0,
        "pre_provider_failed_invocations": 12,
        "arms": combined,
        "full_minus_short": {
            "accepted": full["accepted"] - short["accepted"],
            "wall_time_ms": sum(full["wall_time_ms"]) - sum(short["wall_time_ms"]),
            "read_search_commands": full["read_search_commands"] - short["read_search_commands"],
            "loc_added": full["loc_added"] - short["loc_added"],
            "files_modified": full["files_modified"] - short["files_modified"],
            "usage_components": {
                name: full["usage_component_sums"].get(name, 0)
                - short["usage_component_sums"].get(name, 0)
                for name in sorted(set(full["usage_component_sums"]) | set(short["usage_component_sums"]))
            },
        },
        "waves": [
            {"wave": summary["wave"], "sessions": summary["sessions"], "arms": summary["arms"]}
            for summary in sorted(summaries, key=lambda item: item["wave"])
        ],
    }
    write_json(output, result)
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    commands.add_parser("audit-registry")
    run = commands.add_parser("run-wave")
    run.add_argument("--wave", required=True, type=int, choices=(1, 2))
    run.add_argument("--state-dir", required=True, type=Path)
    run.add_argument("--auth-file", required=True, type=Path)
    summarize = commands.add_parser("summarize-wave")
    summarize.add_argument("--state-dir", required=True, type=Path)
    combined = commands.add_parser("summarize-experiment")
    combined.add_argument("--wave-state", action="append", required=True, type=Path)
    combined.add_argument("--output", required=True, type=Path)
    return value


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "run-wave":
            run_wave(arguments.wave, arguments.state_dir, arguments.auth_file)
            return 0
        if arguments.command == "audit-registry":
            audit_registry()
        elif arguments.command == "summarize-wave":
            summarize_wave(arguments.state_dir)
        else:
            summarize_experiment(arguments.wave_state, arguments.output)
    except (ExperimentConfigurationError, OSError, ValueError, subprocess.SubprocessError) as error:
        del error
        print("run_development_pool: command failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
