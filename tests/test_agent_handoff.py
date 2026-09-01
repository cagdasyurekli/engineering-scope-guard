from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.agent_handoff import (
    MAX_HANDOFF_BYTES,
    HandoffValidationError,
    canonical_bytes,
    load_handoff,
    validate_handoff,
)

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "experiment/agent_handoff.json"
SCHEMA = ROOT / "experiment/agent_handoff.schema.json"


class AgentHandoffTests(unittest.TestCase):
    def value(self) -> dict:
        return json.loads(HANDOFF.read_text(encoding="utf-8"))

    def test_repository_handoff_is_valid_compact_and_externally_actionable(self) -> None:
        value = load_handoff(HANDOFF, ROOT)
        self.assertLessEqual(HANDOFF.stat().st_size, MAX_HANDOFF_BYTES)
        self.assertEqual(
            value["current_decision"]["decision"],
            "EXPERIMENT INVALID / TERMINATED",
        )
        self.assertEqual(
            value["goal"]["decision"],
            "EXPERIMENT INVALID / TERMINATED",
        )
        state = value["experimental_state"]
        self.assertEqual(state["terminal"]["path"], "experiment_terminal")
        self.assertTrue(state["qualification"]["minimum_gate_passed"])
        self.assertEqual(state["qualification"]["qualified_independent_clusters"], 16)
        self.assertFalse(state["execution"]["experiment_started"])
        self.assertEqual(state["execution"]["total_subject_invocation_starts"], 0)
        self.assertEqual(state["execution"]["evaluator_invocation_starts"], 0)
        self.assertEqual(state["execution"]["schedule_cells"], 40)
        self.assertEqual(state["execution"]["completed_cells"], 1)
        self.assertEqual(state["execution"]["missing_cells"], 39)
        self.assertIn(value["next_action"]["kind"], value["allowed_actions"])
        self.assertTrue(value["next_action"]["requires_explicit_user_authorization"])
        self.assertEqual(value["next_action"]["authorization"], "explicit_current_request")
        self.assertIn(value["next_action"]["kind"], {"persist_and_merge", "merge_if_green"})
        self.assertFalse(value["next_action"]["safe_without_explicit_authorization"])
        self.assertIn(value["verification"]["ci_status"], {"pending_pr", "derive_from_pr"})
        self.assertTrue(value["verification"]["codeql_required"])
        self.assertIn(value["verification"]["codeql_status"], {"pending_pr", "derive_from_pr"})
        self.assertNotIn("run_authorized_goal", value["allowed_actions"])
        self.assertIn("run_exploratory_experiment", value["forbidden_actions"])
        self.assertIn("run_confirmatory_experiment", value["forbidden_actions"])
        self.assertIsInstance(value["git"]["pr_number"], (int, type(None)))
        for evidence in value["evidence"]:
            self.assertTrue((ROOT / evidence["path"]).is_file())

    def test_repository_handoff_has_portable_exact_evidence(self) -> None:
        value = load_handoff(HANDOFF, ROOT)
        evidence_commit = value["current_decision"]["evidence_commit"]
        self.assertIsNone(evidence_commit)
        self.assertEqual(
            value["current_decision"]["evidence_commit_semantics"],
            "omitted_to_avoid_self_reference",
        )
        self.assertIsNone(value["git"]["head_sha"])
        for evidence in value["evidence"]:
            blob = (ROOT / evidence["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), evidence["sha256"])

    def test_portable_schema_is_valid_json_and_rejects_additional_properties(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1")
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["properties"]["goal"]["additionalProperties"])

    def test_missing_goal_identity_is_rejected(self) -> None:
        value = self.value()
        del value["goal"]["name"]
        with self.assertRaisesRegex(HandoffValidationError, "goal is missing"):
            validate_handoff(value, ROOT)

    def test_unknown_schema_version_and_invalid_status_are_rejected(self) -> None:
        value = self.value()
        value["schema_version"] = "2"
        with self.assertRaisesRegex(HandoffValidationError, "unknown schema_version"):
            validate_handoff(value, ROOT)
        value = self.value()
        value["goal"]["status"] = "active"
        with self.assertRaisesRegex(HandoffValidationError, "not terminal"):
            validate_handoff(value, ROOT)

    def test_unsafe_action_falsely_marked_authorization_free_is_rejected(self) -> None:
        value = self.value()
        value["next_action"]["requires_explicit_user_authorization"] = False
        value["next_action"]["safe_without_explicit_authorization"] = False
        with self.assertRaisesRegex(HandoffValidationError, "falsely marked"):
            validate_handoff(value, ROOT)

    def test_invalid_experimental_counts_and_contradictory_observations_are_rejected(self) -> None:
        value = self.value()
        value["experimental_state"]["qualification"]["attempted_candidates"] = -1
        with self.assertRaisesRegex(HandoffValidationError, "non-negative"):
            validate_handoff(value, ROOT)
        value = self.value()
        value["experimental_state"]["execution"]["total_subject_invocation_starts"] = 1
        with self.assertRaisesRegex(HandoffValidationError, "inconsistent or exceed"):
            validate_handoff(value, ROOT)

    def test_invalid_or_private_evidence_path_is_rejected(self) -> None:
        for path in ("/tmp/raw.json", "../outside.json", ".local/private.json"):
            with self.subTest(path=path):
                value = self.value()
                value["evidence"][0]["path"] = path
                with self.assertRaises(HandoffValidationError):
                    validate_handoff(value, ROOT)

    def test_symlinked_evidence_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as repository_directory:
            with tempfile.TemporaryDirectory() as outside_directory:
                repository = Path(repository_directory)
                outside = Path(outside_directory) / "evidence.json"
                outside.write_text("outside\n", encoding="utf-8")
                link = repository / "evidence.json"
                link.symlink_to(outside)
                value = self.value()
                for artifact in value["experimental_state"]["public_artifacts"].values():
                    if artifact is None:
                        continue
                    target = repository / artifact["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((ROOT / artifact["path"]).read_bytes())
                value["evidence"] = [
                    {
                        "path": "evidence.json",
                        "role": "test evidence",
                        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                    }
                ]
                with self.assertRaisesRegex(HandoffValidationError, "symlink"):
                    validate_handoff(value, repository)

    def test_privacy_sensitive_field_is_rejected_before_unknown_field_handling(self) -> None:
        value = self.value()
        value["credentials"] = "forbidden"
        with self.assertRaisesRegex(HandoffValidationError, "privacy-sensitive"):
            validate_handoff(value, ROOT)

    def test_oversized_handoff_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            path.write_bytes(b" " * (MAX_HANDOFF_BYTES + 1))
            with self.assertRaisesRegex(HandoffValidationError, "5 KiB"):
                load_handoff(path, ROOT)

    def test_serialization_is_deterministic_and_noncanonical_bytes_are_rejected(self) -> None:
        value = self.value()
        first = canonical_bytes(value)
        second = canonical_bytes(copy.deepcopy(value))
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(HandoffValidationError, "not canonical"):
                load_handoff(path, ROOT)

    def test_self_referential_containing_commit_is_not_required_or_allowed(self) -> None:
        value = self.value()
        value["current_decision"]["evidence_commit"] = None
        value["current_decision"][
            "evidence_commit_semantics"
        ] = "omitted_to_avoid_self_reference"
        value["git"]["head_sha"] = None
        value["git"]["head_sha_semantics"] = "omitted_to_avoid_self_reference"
        validate_handoff(value, ROOT)
        value["current_decision"][
            "evidence_commit_semantics"
        ] = "authoritative_evidence_commit"
        with self.assertRaisesRegex(HandoffValidationError, "self-reference"):
            validate_handoff(value, ROOT)
        value["current_decision"][
            "evidence_commit_semantics"
        ] = "omitted_to_avoid_self_reference"
        value["git"]["head_sha_semantics"] = "containing_handoff_commit"
        with self.assertRaisesRegex(HandoffValidationError, "self-reference"):
            validate_handoff(value, ROOT)

    def test_malformed_pr_and_commit_metadata_are_rejected(self) -> None:
        value = self.value()
        value["git"]["pr_number"] = 1
        value["git"]["pr_url"] = "https://github.com/example/wrong/pull/1"
        with self.assertRaisesRegex(HandoffValidationError, "does not match"):
            validate_handoff(value, ROOT)
        value = self.value()
        value["git"]["head_sha"] = "abc"
        with self.assertRaisesRegex(HandoffValidationError, "head_sha is malformed"):
            validate_handoff(value, ROOT)

    def test_check_state_must_match_requirement_and_pr_metadata(self) -> None:
        value = self.value()
        value["verification"]["ci_status"] = "not_required"
        with self.assertRaisesRegex(HandoffValidationError, "contradictory"):
            validate_handoff(value, ROOT)

        value = self.value()
        value["git"]["pr_number"] = None
        value["git"]["pr_url"] = None
        value["verification"]["ci_status"] = "derive_from_pr"
        with self.assertRaisesRegex(HandoffValidationError, "lacks PR metadata"):
            validate_handoff(value, ROOT)

        value["verification"]["ci_status"] = "pending_pr"
        value["verification"]["codeql_required"] = True
        value["verification"]["codeql_status"] = "pending_pr"
        validate_handoff(value, ROOT)

        value = self.value()
        value["git"]["pr_number"] = 2
        value["git"]["pr_url"] = (
            "https://github.com/cagdasyurekli/engineering-scope-guard/pull/2"
        )
        value["verification"]["ci_status"] = "pending_pr"
        value["verification"]["codeql_status"] = "pending_pr"
        with self.assertRaisesRegex(HandoffValidationError, "despite PR metadata"):
            validate_handoff(value, ROOT)

    def test_terminal_stop_cannot_claim_an_authorized_run(self) -> None:
        value = self.value()
        value["goal"]["status"] = "abandoned"
        value["next_action"].update(
            {
                "kind": "run_authorized_goal",
                "authorization": "explicit_current_request",
                "requires_explicit_user_authorization": True,
                "safe_without_explicit_authorization": False,
            }
        )
        value["allowed_actions"].append("run_authorized_goal")
        with self.assertRaisesRegex(HandoffValidationError, "terminal stop"):
            validate_handoff(value, ROOT)


if __name__ == "__main__":
    unittest.main()
