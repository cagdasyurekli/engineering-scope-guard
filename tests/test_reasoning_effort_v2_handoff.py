from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from engineering_scope_guard.agent_handoff import (
    HandoffValidationError,
    MAX_HANDOFF_BYTES,
    REASONING_EFFORT_STATE_VERSION,
    TERMINAL_ARTIFACT_PATHS,
    canonical_bytes,
    load_handoff,
    validate_handoff,
)


INSUFFICIENT = (
    "TASK/EVALUATOR POPULATION STILL INSUFFICIENT — LIVE EXPERIMENT NOT STARTED"
)
SCHEMA = Path(__file__).resolve().parents[1] / "experiment/agent_handoff.schema.json"


def write_artifact(root: Path, relative: str, content: bytes) -> dict[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"path": relative, "sha256": hashlib.sha256(content).hexdigest()}


def fixture(root: Path, *, experiment: bool) -> dict:
    evidence = []
    for relative in (
        "docs/CURRENT_GOAL.md",
        "docs/GOAL_HISTORY.md",
        "docs/DECISIONS.md",
    ):
        reference = write_artifact(root, relative, f"fixture {relative}\n".encode())
        evidence.append({**reference, "role": f"authoritative {relative}"})

    artifacts: dict[str, dict[str, str] | None] = {}
    for name, relative in TERMINAL_ARTIFACT_PATHS.items():
        if not experiment and name in {"contract", "terminal_envelope", "analysis"}:
            artifacts[name] = None
        else:
            artifacts[name] = write_artifact(
                root, relative, f"fixture {name}\n".encode()
            )

    qualification = (
        {
            "attempted_candidates": 16,
            "validation_failures": 0,
            "gold_failures": 0,
            "infrastructure_failures": 0,
            "qualified_independent_clusters": 16,
            "minimum_gate_passed": True,
        }
        if experiment
        else {
            "attempted_candidates": 48,
            "validation_failures": 39,
            "gold_failures": 0,
            "infrastructure_failures": 0,
            "qualified_independent_clusters": 9,
            "minimum_gate_passed": False,
        }
    )
    execution = (
        {
            "experiment_started": True,
            "canary_subject_invocation_starts": 1,
            "experiment_subject_invocation_starts": 48,
            "total_subject_invocation_starts": 49,
            "evaluator_invocation_starts": 48,
            "schedule_cells": 48,
            "completed_cells": 48,
            "admissible_cells": 48,
            "missing_cells": 0,
            "alternates_activated": 0,
            "stage_1_status": "passed",
        }
        if experiment
        else {
            "experiment_started": False,
            "canary_subject_invocation_starts": 0,
            "experiment_subject_invocation_starts": 0,
            "total_subject_invocation_starts": 0,
            "evaluator_invocation_starts": 0,
            "schedule_cells": 0,
            "completed_cells": 0,
            "admissible_cells": 0,
            "missing_cells": 0,
            "alternates_activated": 0,
            "stage_1_status": "not_applicable",
        }
    )
    return {
        "schema_version": "1",
        "repository": "example/engineering-scope-guard",
        "goal": {
            "name": "Evaluator-Stable Reasoning-Effort Exploratory Experiment",
            "status": "complete",
            "decision": "TERMINAL RESEARCH PACKAGE PREPARED",
            "completed_at": "2026-08-31T01:00:00+02:00",
        },
        "current_decision": {
            "goal": "Evaluator-Stable Reasoning-Effort Exploratory Experiment",
            "decision": (
                "NO MATERIAL EXPLORATORY DIFFERENCE DETECTED"
                if experiment
                else INSUFFICIENT
            ),
            "evidence_commit": "a" * 40,
        },
        "git": {
            "base_branch": "main",
            "head_sha": "b" * 40,
            "head_sha_semantics": "authoritative_evidence_commit",
            "branch": "codex/evaluator-stable-reasoning-effort",
            "pr_number": None,
            "pr_url": None,
        },
        "verification": {
            "tests_passed": 137,
            "ci_required": True,
            "ci_status": "pending_pr",
            "codeql_required": True,
            "codeql_status": "pending_pr",
        },
        "experimental_state": {
            "schema_version": REASONING_EFFORT_STATE_VERSION,
            "qualification": qualification,
            "execution": execution,
            "terminal": {
                "path": "experiment_terminal" if experiment else "insufficient_population",
                "disposition": (
                    "NO MATERIAL EXPLORATORY DIFFERENCE DETECTED"
                    if experiment
                    else INSUFFICIENT
                ),
                "esg_rr_002_candidate_decision": (
                    "candidate_justified" if experiment else "not_applicable"
                ),
            },
            "public_artifacts": artifacts,
            "boundaries": {
                "raw_private_material_tracked": False,
                "repository_private": True,
                "publication_authorized": False,
                "visibility_change_authorized": False,
                "next_authority_boundary": "authorize_private_canonical_branch_push",
            },
        },
        "next_action": {
            "kind": "request_authorization",
            "requires_explicit_user_authorization": True,
            "authorization": "not_authorized",
            "safe_without_explicit_authorization": False,
            "reason": "Private canonical push, PR, and merge remain ungranted.",
        },
        "allowed_actions": ["review", "request_authorization"],
        "forbidden_actions": [
            "run_exploratory_experiment",
            "run_confirmatory_experiment",
            "expose_held_out_task_bodies",
        ],
        "evidence": evidence,
        "notes": ["No raw or private task material is tracked."],
    }


class ReasoningEffortV2HandoffTests(unittest.TestCase):
    def test_portable_schema_declares_legacy_and_all_reasoning_terminal_shapes(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        experimental = schema["properties"]["experimental_state"]
        self.assertEqual(
            experimental["oneOf"],
            [
                {"$ref": "#/$defs/legacy_experimental_state"},
                {"$ref": "#/$defs/reasoning_effort_experimental_state"},
            ],
        )
        terminal_paths = schema["$defs"]["reasoning_effort_terminal"][
            "properties"
        ]["path"]["enum"]
        self.assertEqual(
            terminal_paths,
            [
                "insufficient_population",
                "pre_subject_integrity_stop",
                "experiment_terminal",
            ],
        )
        pre_subject = schema["$defs"]["reasoning_effort_pre_subject_terminal"]
        self.assertEqual(
            pre_subject["properties"]["terminal"]["properties"],
            {
                "disposition": {"const": "EXPERIMENT INVALID / TERMINATED"},
                "esg_rr_002_candidate_decision": {"const": "not_applicable"},
            },
        )
        self.assertIn(
            {"$ref": "#/$defs/reasoning_effort_zero_execution"},
            pre_subject["allOf"],
        )
        self.assertIn(
            {"$ref": "#/$defs/reasoning_effort_common_only_artifacts"},
            pre_subject["allOf"],
        )

    def test_insufficient_and_experiment_terminal_shapes_validate(self) -> None:
        for experiment in (False, True):
            with self.subTest(experiment=experiment), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                value = fixture(root, experiment=experiment)
                self.assertEqual(validate_handoff(value, root), value)
                self.assertLessEqual(len(canonical_bytes(value)), MAX_HANDOFF_BYTES)

    def test_pre_subject_integrity_stop_shape_validates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = fixture(root, experiment=False)
            value["current_decision"]["decision"] = "EXPERIMENT INVALID / TERMINATED"
            value["experimental_state"]["qualification"] = {
                "attempted_candidates": 20,
                "validation_failures": 1,
                "gold_failures": 0,
                "infrastructure_failures": 3,
                "qualified_independent_clusters": 16,
                "minimum_gate_passed": True,
            }
            value["experimental_state"]["terminal"] = {
                "path": "pre_subject_integrity_stop",
                "disposition": "EXPERIMENT INVALID / TERMINATED",
                "esg_rr_002_candidate_decision": "not_applicable",
            }
            self.assertEqual(validate_handoff(value, root), value)

            changed = deepcopy(value)
            changed["experimental_state"]["execution"]["schedule_cells"] = 40
            changed["experimental_state"]["execution"]["missing_cells"] = 40
            with self.assertRaisesRegex(
                HandoffValidationError, "pre-subject integrity-stop"
            ):
                validate_handoff(changed, root)

    def test_legacy_experimental_state_shape_remains_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = fixture(root, experiment=True)
            value["experimental_state"] = {
                "live_canary_executed": True,
                "pilot_v2_subject_calls": 14,
                "pilot_v2_evaluator_calls": 14,
                "policy_comparisons": 28,
                "valid_observations": 28,
            }
            self.assertEqual(validate_handoff(value, root), value)

    def test_canonical_round_trip_and_authoritative_evidence_commit_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = fixture(root, experiment=True)
            path = root / "handoff.json"
            path.write_bytes(canonical_bytes(value))
            loaded = load_handoff(path, root)
            self.assertEqual(
                loaded["git"]["head_sha_semantics"],
                "authoritative_evidence_commit",
            )
            changed = deepcopy(value)
            changed["git"]["head_sha_semantics"] = "containing_handoff_commit"
            with self.assertRaisesRegex(HandoffValidationError, "unsupported semantics"):
                validate_handoff(changed, root)

    def test_qualification_and_execution_mismatches_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = fixture(root, experiment=True)
            mutations = []
            changed = deepcopy(original)
            changed["experimental_state"]["qualification"]["attempted_candidates"] = 17
            mutations.append(changed)
            changed = deepcopy(original)
            changed["experimental_state"]["execution"]["total_subject_invocation_starts"] = 50
            mutations.append(changed)
            changed = deepcopy(original)
            changed["experimental_state"]["execution"].update(
                {
                    "canary_subject_invocation_starts": 1,
                    "experiment_subject_invocation_starts": 56,
                    "total_subject_invocation_starts": 57,
                }
            )
            mutations.append(changed)
            changed = deepcopy(original)
            changed["experimental_state"]["execution"]["missing_cells"] = 1
            mutations.append(changed)
            for changed in mutations:
                with self.subTest(changed=changed["experimental_state"]):
                    with self.assertRaises(HandoffValidationError):
                        validate_handoff(changed, root)

    def test_terminal_artifact_privacy_and_digest_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = fixture(root, experiment=True)
            changed = deepcopy(original)
            changed["experimental_state"]["public_artifacts"]["analysis"][
                "sha256"
            ] = "0" * 64
            with self.assertRaisesRegex(HandoffValidationError, "digest mismatch"):
                validate_handoff(changed, root)

            changed = deepcopy(original)
            changed["experimental_state"]["raw_task_body"] = "private"
            with self.assertRaisesRegex(HandoffValidationError, "privacy-sensitive"):
                validate_handoff(changed, root)

            changed = deepcopy(original)
            changed["evidence"][0]["path"] = "docs/.local/raw.json"
            with self.assertRaisesRegex(HandoffValidationError, "local_path_component"):
                validate_handoff(changed, root)

            private_reference = write_artifact(
                root, "private/raw.json", b"raw private evidence\n"
            )
            changed = deepcopy(original)
            changed["evidence"][0].update(private_reference)
            with self.assertRaisesRegex(HandoffValidationError, "raw or private"):
                validate_handoff(changed, root)

    def test_reasoning_effort_free_text_privacy_values_fail_closed(self) -> None:
        cases = (
            ("/Users/private/result", "absolute_path"),
            ("/workspace/private/result", "absolute_path"),
            (r"C:\Users\private\result", "absolute_path"),
            ("file:///private/result", "file_uri"),
            ("~/private/result", "home_path"),
            ("cache/.local/raw", "local_path_component"),
            ("docs/../private", "path_traversal"),
            ("ghp_" + "A" * 40, "credential_material"),
            ("-----BEGIN " + "PRIVATE KEY-----", "credential_material"),
            (
                "https://github.com/" + "example/private-repository",
                "github_repository_url",
            ),
            ("example__private-task-" + "12345", "task_identity"),
            ("raw_prompt: private content", "sensitive_content_alias"),
            ("patch_text=private content", "sensitive_content_alias"),
            ("provider_output: private content", "sensitive_content_alias"),
            ("body: private content", "sensitive_content_alias"),
            ("diff --git a/source.py b/source.py", "raw_patch_literal"),
        )
        for leaked_value, category in cases:
            with self.subTest(category=category), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                changed = fixture(root, experiment=False)
                changed["notes"] = [leaked_value]
                with self.assertRaisesRegex(
                    HandoffValidationError,
                    rf"at \$\.notes\[0\]: {category}$",
                ) as caught:
                    validate_handoff(changed, root)
                self.assertNotIn(leaked_value, str(caught.exception))

    def test_reasoning_effort_nested_privacy_values_and_alias_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = fixture(root, experiment=False)

            changed = deepcopy(original)
            changed["evidence"][0]["role"] = "provider_response: private content"
            with self.assertRaisesRegex(
                HandoffValidationError,
                r"at \$\.evidence\[0\]\.role: sensitive_content_alias$",
            ):
                validate_handoff(changed, root)

            changed = deepcopy(original)
            changed["experimental_state"]["raw_prompt"] = "private content"
            with self.assertRaisesRegex(
                HandoffValidationError,
                r"at \$\.experimental_state: sensitive_field_alias$",
            ) as caught:
                validate_handoff(changed, root)
            self.assertNotIn("raw_prompt", str(caught.exception))

            changed = deepcopy(original)
            secret_shaped_key = "ghp_" + "A" * 40
            changed["experimental_state"][secret_shaped_key] = "private content"
            with self.assertRaisesRegex(
                HandoffValidationError,
                r"at \$\.experimental_state: credential_material$",
            ) as caught:
                validate_handoff(changed, root)
            self.assertNotIn(secret_shaped_key, str(caught.exception))

    def test_reasoning_effort_privacy_scan_allows_benign_public_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = fixture(root, experiment=False)
            value["notes"] = [
                "config.local.toml is a public filename.",
                "The local validator uses http://localhost:8000/status.",
                "Commitment " + "a" * 64 + " binds the public projection.",
                "Commit " + "b" * 40 + " is the authoritative evidence commit.",
            ]
            value["git"]["pr_number"] = 1
            value["git"]["pr_url"] = (
                "https://github.com/" + "example/engineering-scope-guard/pull/1"
            )
            value["verification"]["ci_status"] = "derive_from_pr"
            value["verification"]["codeql_status"] = "derive_from_pr"
            self.assertEqual(validate_handoff(value, root), value)

    def test_required_authoritative_evidence_and_terminal_artifact_sets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = fixture(root, experiment=False)
            changed = deepcopy(original)
            changed["evidence"] = [
                item
                for item in changed["evidence"]
                if item["path"] != "docs/DECISIONS.md"
            ]
            with self.assertRaisesRegex(HandoffValidationError, "lacks current-goal"):
                validate_handoff(changed, root)

            changed = deepcopy(original)
            changed["experimental_state"]["public_artifacts"]["analysis"] = {
                "path": TERMINAL_ARTIFACT_PATHS["analysis"],
                "sha256": "0" * 64,
            }
            with self.assertRaisesRegex(HandoffValidationError, "includes experiment"):
                validate_handoff(changed, root)

    def test_terminal_disposition_and_authority_boundary_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = fixture(root, experiment=True)
            changed = deepcopy(original)
            changed["experimental_state"]["terminal"]["disposition"] = "looks good"
            with self.assertRaisesRegex(HandoffValidationError, "disposition"):
                validate_handoff(changed, root)

            changed = deepcopy(original)
            changed["experimental_state"]["boundaries"]["publication_authorized"] = True
            with self.assertRaisesRegex(HandoffValidationError, "boundary drifted"):
                validate_handoff(changed, root)

            changed = deepcopy(original)
            changed["experimental_state"]["boundaries"][
                "next_authority_boundary"
            ] = "authorize_private_canonical_push_pr_merge_of_prepared_branch"
            with self.assertRaisesRegex(HandoffValidationError, "boundary drifted"):
                validate_handoff(changed, root)


if __name__ == "__main__":
    unittest.main()
