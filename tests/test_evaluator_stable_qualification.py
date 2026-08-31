from __future__ import annotations

import json
import argparse
import hashlib
import tempfile
import unittest
from pathlib import Path
import stat
from unittest.mock import patch

from engineering_scope_guard.evaluator_stable_qualification import (
    FAILURE_CLASSES,
    LANGUAGES,
    STAGES,
    build_receipt,
    deterministic_candidate_order,
    next_qualification_stage,
    public_summary,
    record_stage,
    qualification_rank,
    seal_receipt,
    sha256_value,
    validate_receipt,
)
from engineering_scope_guard.experiment import ExperimentConfigurationError
from scripts.evaluator_stable_qualification import (
    EXPECTED_DATASET_REVISION,
    EXPECTED_EVALUATOR_REVISION,
    EXPECTED_REPOLAUNCH_REVISION,
    _execution_code_identity,
    _private_path,
    _reconcile_interrupted_stage,
    _require_expected_pins,
    _restrict_private_inputs,
    _revalidate_sources,
    _run_evaluator,
    _stage_q1,
    _verify_completed_stages,
    _verify_stage_receipt,
    _gold_classification,
)


def reserve() -> dict[str, object]:
    seed = "fixture-seed"
    revision = "d" * 40
    selected = []
    for language in LANGUAGES:
        for ordinal in range(6):
            instance_id = f"private-{language}-{ordinal}"
            selected.append(
                {
                    "instance_id": instance_id,
                    "repo": f"private/repo-{language}-{ordinal}",
                    "language": language,
                    "docker_image": f"private/image-{language}-{ordinal}",
                    "rank_commitment": qualification_rank(
                        seed, revision, language, instance_id
                    ),
                    "manifest_sha256": sha256_value({"image": instance_id}),
                }
            )
    return {
        "schema": "private-fixture",
        "source": {
            "dataset": "SWE-bench-Live/MultiLang",
            "revision": revision,
        },
        "selection": {
            "seed": seed,
            "selected": selected,
            "selected_ids_sha256": sha256_value(
                sorted(task["instance_id"] for task in selected)
            ),
        },
    }


def receipt() -> dict[str, object]:
    return build_receipt(
        reserve(),
        evaluator_revision="e" * 40,
        repolaunch_revision="r" * 40,
        dataset_file_sha256={"c.parquet": "f" * 64},
        evaluator_python={"python": "3.12.13", "executable_sha256": "a" * 64},
        codex_runtime={
            "codex_version": "codex-cli 0.151.0",
            "model": "gpt-5.6-sol",
            "supported_reasoning_efforts": ["low", "medium"],
            "docker_client_server": {"Client": {"Version": "fixture"}},
        },
        execution_code_sha256={"qualifier.py": "b" * 64},
        evaluator_tree_sha256="c" * 64,
        repolaunch_tree_sha256="d" * 64,
    )


def evidence(slot: int, stage: str) -> dict[str, object]:
    value = {
        "stage_receipt_sha256": sha256_value({"slot": slot, "stage": stage}),
        "artifact_set_sha256": sha256_value([]),
        "wall_seconds": 1.0,
    }
    if stage == "q1_environment":
        value["resolved_image_ref"] = f"private/image-{slot}@sha256:{slot:064x}"
    return value


def pass_candidate(value: dict[str, object]) -> None:
    candidate, _ = next_qualification_stage(value)  # type: ignore[arg-type]
    slot = candidate["slot"]
    for stage in STAGES:
        record_stage(
            value,  # type: ignore[arg-type]
            slot=slot,
            stage=stage,
            outcome="pass",
            classification=None,
            evidence=evidence(slot, stage),
        )


def fail_candidate(value: dict[str, object], classification: str = "flaky_validation") -> None:
    candidate, stage = next_qualification_stage(value)  # type: ignore[arg-type]
    if classification == "flaky_validation":
        record_stage(
            value,  # type: ignore[arg-type]
            slot=candidate["slot"],
            stage=stage,
            outcome="pass",
            classification=None,
            evidence=evidence(candidate["slot"], stage),
        )
        candidate, stage = next_qualification_stage(value)  # type: ignore[arg-type]
    record_stage(
        value,  # type: ignore[arg-type]
        slot=candidate["slot"],
        stage=stage,
        outcome="fail",
        classification=classification,
        evidence=evidence(candidate["slot"], stage),
    )


class EvaluatorStableQualificationTests(unittest.TestCase):
    def test_python_identity_does_not_require_pip_module(self) -> None:
        script_source = Path(
            __import__(
                "scripts.evaluator_stable_qualification",
                fromlist=["__file__"],
            ).__file__
        ).read_text(encoding="utf-8")
        self.assertIn("from importlib.metadata import distributions", script_source)
        self.assertNotIn('"-m", "pip"', script_source)

    def test_initialize_rejects_any_non_d069_source_revision(self) -> None:
        value = reserve()
        with self.assertRaisesRegex(ExperimentConfigurationError, "dataset revision"):
            _require_expected_pins(
                value,
                {"revision": "wrong"},
                {"revision": "wrong"},
            )
        value["source"]["revision"] = EXPECTED_DATASET_REVISION  # type: ignore[index]
        with self.assertRaisesRegex(ExperimentConfigurationError, "evaluator revision"):
            _require_expected_pins(
                value,
                {"revision": "wrong"},
                {"revision": EXPECTED_REPOLAUNCH_REVISION},
            )
        with self.assertRaisesRegex(ExperimentConfigurationError, "RepoLaunch revision"):
            _require_expected_pins(
                value,
                {"revision": EXPECTED_EVALUATOR_REVISION},
                {"revision": "wrong"},
            )

    def test_source_revalidation_rejects_reserve_and_docker_drift(self) -> None:
        value = receipt()
        source = value["source"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reserve_path = root / "reserve.json"
            reserve_path.write_text(json.dumps(reserve()), encoding="utf-8")
            args = argparse.Namespace(
                reserve=reserve_path,
                evaluator_root=root / "evaluator",
                dataset_root=root / "dataset",
                evaluator_python=root / "python",
                root=root,
            )
            evaluator_identity = {
                "revision": source["evaluator_revision"],
                "tree_sha256": source["evaluator_tree_sha256"],
            }
            launch_identity = {
                "revision": source["embedded_repolaunch_revision"],
                "tree_sha256": source["repolaunch_tree_sha256"],
            }
            with (
                patch(
                    "scripts.evaluator_stable_qualification._git_source_identity",
                    side_effect=[evaluator_identity, launch_identity],
                ),
                patch(
                    "scripts.evaluator_stable_qualification._dataset_hashes",
                    return_value=source["dataset_file_sha256"],
                ),
                patch(
                    "scripts.evaluator_stable_qualification._python_identity",
                    return_value=source["evaluator_python"],
                ),
                patch(
                    "scripts.evaluator_stable_qualification._execution_code_identity",
                    return_value=source["execution_code_sha256"],
                ),
            ):
                reserve_path.write_text(json.dumps({"drift": True}), encoding="utf-8")
                with self.assertRaisesRegex(
                    ExperimentConfigurationError, "reserve_receipt_sha256"
                ):
                    _revalidate_sources(args, value)  # type: ignore[arg-type]

            reserve_path.write_text(json.dumps(reserve()), encoding="utf-8")
            with (
                patch(
                    "scripts.evaluator_stable_qualification._git_source_identity",
                    side_effect=[evaluator_identity, launch_identity],
                ),
                patch(
                    "scripts.evaluator_stable_qualification._dataset_hashes",
                    return_value=source["dataset_file_sha256"],
                ),
                patch(
                    "scripts.evaluator_stable_qualification._python_identity",
                    return_value=source["evaluator_python"],
                ),
                patch(
                    "scripts.evaluator_stable_qualification._execution_code_identity",
                    return_value=source["execution_code_sha256"],
                ),
                patch(
                    "scripts.evaluator_stable_qualification._docker_identity",
                    return_value={"drift": True},
                ),
            ):
                with self.assertRaisesRegex(
                    ExperimentConfigurationError, "Docker.*drifted"
                ):
                    _revalidate_sources(args, value)  # type: ignore[arg-type]

    def test_q1_rejects_tag_to_digest_manifest_mismatch(self) -> None:
        tag_manifest = "{\"frozen\":true}"
        digest = "private/image@sha256:" + "1" * 64
        candidate = {
            "docker_image": "private/image:tag",
            "manifest_sha256": hashlib.sha256(tag_manifest.encode()).hexdigest(),
        }

        def result(stdout: str) -> dict[str, object]:
            return {
                "exit_code": 0,
                "timed_out": False,
                "wall_seconds": 0.1,
                "stdout": stdout,
                "stderr": "",
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage_root = root / ".local" / "q1"
            stage_root.mkdir(parents=True)
            args = argparse.Namespace(root=root)
            with patch(
                "scripts.evaluator_stable_qualification._run",
                side_effect=[
                    result(tag_manifest),
                    result("pulled"),
                    result(json.dumps([{"RepoDigests": [digest]}])),
                    result("{\"different\":true}"),
                ],
            ):
                with self.assertRaisesRegex(
                    ExperimentConfigurationError, "does not match"
                ):
                    _stage_q1(args, candidate, stage_root, 10)

    def test_private_input_permissions_are_restricted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / ".local/evaluator-stable-reasoning-effort/sources"
            source.mkdir(parents=True)
            source_file = source / "task.bin"
            source_file.write_bytes(b"private")
            source.chmod(0o755)
            source_file.chmod(0o644)
            reserve_path = root / ".local/autonomous-sprint/reserve.json"
            reserve_path.parent.mkdir(parents=True)
            reserve_path.write_text("{}", encoding="utf-8")
            reserve_path.parent.chmod(0o755)
            reserve_path.chmod(0o644)
            _restrict_private_inputs(
                argparse.Namespace(root=root, reserve=reserve_path)
            )
            self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(source_file.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(reserve_path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(reserve_path.stat().st_mode), 0o600)

    def test_evaluator_never_attempts_automatic_container_cleanup(self) -> None:
        args = argparse.Namespace(evaluator_root=Path("/private/evaluator"), root=Path("/private"))
        candidate = {"resolved_image": "private/image@sha256:" + "1" * 64}
        completed = {
            "exit_code": 0,
            "timed_out": False,
            "wall_seconds": 0.1,
            "stdout": "",
            "stderr": "",
        }
        with (
            patch(
                "scripts.evaluator_stable_qualification._container_ids",
                side_effect=[set(), {"new"}],
            ),
            patch(
                "scripts.evaluator_stable_qualification._run",
                return_value=completed,
            ) as run,
        ):
            observed = _run_evaluator(
                ["official", "evaluator"],
                args=args,
                candidate=candidate,
                timeout=10,
            )
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["official", "evaluator"])
        self.assertEqual(
            run.call_args.kwargs["environment"]["PYTHONPATH"],
            "/private/evaluator:/private/evaluator/launch",
        )
        self.assertEqual(observed["orphan_cleanup"]["new_matching_container_count"], 1)
        self.assertFalse(observed["orphan_cleanup"]["automatic_cleanup_permitted"])

    def test_execution_identity_covers_transitive_repository_imports(self) -> None:
        root = Path(__file__).resolve().parents[1]
        identity = _execution_code_identity(root)
        self.assertEqual(
            set(identity),
            {
                "scripts/evaluator_stable_qualification.py",
                "src/engineering_scope_guard/__init__.py",
                "src/engineering_scope_guard/disk_safety.py",
                "src/engineering_scope_guard/evaluator_stable_qualification.py",
                "src/engineering_scope_guard/experiment.py",
                "src/engineering_scope_guard/report.py",
                "src/engineering_scope_guard/repository.py",
                "src/engineering_scope_guard/trace.py",
            },
        )

    def test_interrupted_stage_never_deletes_unattributable_container_delta(self) -> None:
        candidate = {
            "slot": 1,
            "instance_id": "private-id",
            "repo": "private/repo",
            "language": "python",
            "docker_image": "private/image:tag",
            "resolved_image": "private/image@sha256:" + "1" * 64,
        }
        with tempfile.TemporaryDirectory() as directory:
            stage_root = Path(directory) / ".local" / "stage"
            stage_root.mkdir(parents=True)
            identity = sha256_value(
                {
                    "instance_id": candidate["instance_id"],
                    "repo": candidate["repo"],
                    "language": candidate["language"],
                }
            )
            (stage_root / "stage-start.json").write_text(
                json.dumps(
                    {
                        "slot": 1,
                        "stage": "q2_repeated_validation",
                        "candidate_identity_sha256": identity,
                        "matching_container_image": candidate["resolved_image"],
                        "pre_stage_matching_container_ids": ["preexisting"],
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch(
                    "scripts.evaluator_stable_qualification._container_ids",
                    return_value={"preexisting", "created"},
                ),
                patch(
                    "scripts.evaluator_stable_qualification._run",
                ) as run,
            ):
                with self.assertRaisesRegex(
                    ExperimentConfigurationError, "automatic cleanup.*forbidden"
                ):
                    _reconcile_interrupted_stage(
                        candidate, "q2_repeated_validation", stage_root
                    )
            run.assert_not_called()

            with (
                patch(
                    "scripts.evaluator_stable_qualification._container_ids",
                    return_value={"preexisting"},
                ),
                patch(
                    "scripts.evaluator_stable_qualification._run",
                ) as run,
            ):
                stage_receipt = _reconcile_interrupted_stage(
                    candidate, "q2_repeated_validation", stage_root
                )
            run.assert_not_called()
            self.assertTrue(
                stage_receipt["details"]["preexisting_matching_containers_preserved"]
            )
            self.assertEqual(stage_receipt["details"]["new_matching_container_count"], 0)

    def test_resume_rehashes_completed_prior_stage_artifacts(self) -> None:
        value = receipt()
        candidate, stage = next_qualification_stage(value)  # type: ignore[arg-type]
        with tempfile.TemporaryDirectory() as directory:
            raw_root = Path(directory)
            stage_root = raw_root / "slot-01" / stage
            stage_root.mkdir(parents=True)
            artifact = stage_root / "artifact.txt"
            artifact.write_text("original", encoding="utf-8")
            import hashlib

            stage_receipt = {
                "slot": 1,
                "stage": stage,
                "artifact_sha256": {
                    "artifact.txt": hashlib.sha256(b"original").hexdigest()
                },
            }
            stage_receipt["stage_receipt_sha256"] = sha256_value(stage_receipt)
            (stage_root / "stage-receipt.json").write_text(
                json.dumps(stage_receipt), encoding="utf-8"
            )
            record_stage(
                value,  # type: ignore[arg-type]
                slot=candidate["slot"],
                stage=stage,
                outcome="pass",
                classification=None,
                evidence={
                    **evidence(1, stage),
                    "stage_receipt_sha256": stage_receipt["stage_receipt_sha256"],
                    "artifact_set_sha256": sha256_value(
                        stage_receipt["artifact_sha256"]
                    ),
                },
            )
            args = argparse.Namespace(raw_root=raw_root)
            _verify_completed_stages(args, value)  # type: ignore[arg-type]
            artifact.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "artifact hash"
            ):
                _verify_completed_stages(args, value)  # type: ignore[arg-type]

    def test_state_seal_and_candidate_commitment_detect_tampering(self) -> None:
        value = receipt()
        value["candidates"][0]["instance_id"] = "tampered"  # type: ignore[index]
        with self.assertRaisesRegex(ExperimentConfigurationError, "state seal"):
            validate_receipt(value)  # type: ignore[arg-type]
        seal_receipt(value)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ExperimentConfigurationError, "commitment|rank"):
            validate_receipt(value)  # type: ignore[arg-type]

        image_drift = receipt()
        image_drift["candidates"][0]["docker_image"] = "retargeted/image"  # type: ignore[index]
        seal_receipt(image_drift)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ExperimentConfigurationError, "commitment"):
            validate_receipt(image_drift)  # type: ignore[arg-type]

    def test_resolved_image_must_equal_q1_evidence(self) -> None:
        value = receipt()
        candidate, stage = next_qualification_stage(value)  # type: ignore[arg-type]
        record_stage(
            value,  # type: ignore[arg-type]
            slot=candidate["slot"],
            stage=stage,
            outcome="pass",
            classification=None,
            evidence=evidence(candidate["slot"], stage),
        )
        candidate["resolved_image"] = "private/other@sha256:" + "9" * 64
        seal_receipt(value)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ExperimentConfigurationError, "Q1 evidence"):
            validate_receipt(value)  # type: ignore[arg-type]

    def test_active_candidate_cannot_continue_after_failed_prior_stage(self) -> None:
        value = receipt()
        candidate = value["candidates"][0]  # type: ignore[index]
        candidate["status"] = "in_progress"
        candidate["next_stage"] = "q2_repeated_validation"
        candidate["resolved_image"] = "private/image@sha256:" + "1" * 64
        candidate["stages"].append(
            {
                "stage": "q1_environment",
                "outcome": "fail",
                "classification": "build_environment_failure",
                "evidence": evidence(1, "q1_environment"),
            }
        )
        seal_receipt(value)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ExperimentConfigurationError, "failed prior stage"):
            validate_receipt(value)  # type: ignore[arg-type]

    def test_resume_rehashes_every_stage_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            artifact = root / "artifact.txt"
            artifact.write_text("original", encoding="utf-8")
            stage_receipt = {
                "slot": 1,
                "stage": "q1_environment",
                "artifact_sha256": {"artifact.txt": sha256_value("not-used")},
            }
            # File digests are byte hashes, not canonical JSON hashes.
            import hashlib

            stage_receipt["artifact_sha256"]["artifact.txt"] = hashlib.sha256(
                b"original"
            ).hexdigest()
            stage_receipt["stage_receipt_sha256"] = sha256_value(stage_receipt)
            _verify_stage_receipt(root, stage_receipt)
            artifact.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ExperimentConfigurationError, "artifact hash"):
                _verify_stage_receipt(root, stage_receipt)

    def test_private_paths_cannot_escape_local_or_cross_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".local").mkdir()
            inside = _private_path(
                root,
                root / ".local" / "qualification" / "receipt.json",
                "receipt",
            )
            self.assertTrue(inside.is_relative_to(root / ".local"))
            with self.assertRaisesRegex(ExperimentConfigurationError, "below"):
                _private_path(root, root / "outside.json", "receipt")
            outside = root / "elsewhere"
            outside.mkdir()
            (root / ".local" / "link").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(Exception):
                _private_path(
                    root,
                    root / ".local" / "link" / "raw",
                    "raw_root",
                    directory=True,
                )

    def test_reuses_six_per_language_reserve_in_round_robin_order(self) -> None:
        ordered = deterministic_candidate_order(reserve())
        self.assertEqual(len(ordered), 48)
        self.assertEqual([task["language"] for task in ordered[:8]], list(LANGUAGES))
        self.assertEqual([task["language"] for task in ordered[8:16]], list(LANGUAGES))
        self.assertEqual(len({task["repo"] for task in ordered}), 48)

    def test_rejects_reserve_commitment_or_repository_reuse(self) -> None:
        drifted = reserve()
        drifted["selection"]["selected_ids_sha256"] = "0" * 64  # type: ignore[index]
        with self.assertRaisesRegex(ExperimentConfigurationError, "commitment"):
            deterministic_candidate_order(drifted)  # type: ignore[arg-type]

        repeated = reserve()
        selected = repeated["selection"]["selected"]  # type: ignore[index]
        selected[1]["repo"] = selected[0]["repo"]
        with self.assertRaisesRegex(ExperimentConfigurationError, "repository"):
            deterministic_candidate_order(repeated)  # type: ignore[arg-type]

        reranked = reserve()
        selected = reranked["selection"]["selected"]  # type: ignore[index]
        selected[0]["rank_commitment"], selected[1]["rank_commitment"] = (
            selected[1]["rank_commitment"],
            selected[0]["rank_commitment"],
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "rank"):
            deterministic_candidate_order(reranked)  # type: ignore[arg-type]

    def test_stage_order_is_strict_and_failure_is_not_replacement(self) -> None:
        value = receipt()
        candidate, stage = next_qualification_stage(value)  # type: ignore[arg-type]
        self.assertEqual(stage, "q1_environment")
        with self.assertRaisesRegex(ExperimentConfigurationError, "out of order"):
            record_stage(
                value,  # type: ignore[arg-type]
                slot=candidate["slot"],
                stage="q2_repeated_validation",
                outcome="pass",
                classification=None,
                evidence=evidence(candidate["slot"], "q2_repeated_validation"),
            )
        record_stage(
            value,  # type: ignore[arg-type]
            slot=candidate["slot"],
            stage=stage,
            outcome="fail",
            classification="build_environment_failure",
            evidence=evidence(candidate["slot"], stage),
        )
        self.assertEqual(value["status"], "in_progress")
        self.assertEqual(value["candidates"][0]["status"], "not_qualified")  # type: ignore[index]
        self.assertEqual(value["candidates"][1]["slot"], 2)  # type: ignore[index]
        self.assertFalse(
            value["protocol"]["candidate_failures_are_experimental_replacements"]  # type: ignore[index]
        )
        self.assertNotIn("replacement_count", value["candidates"][0])  # type: ignore[index]

    def test_all_four_passes_are_required_for_qualification(self) -> None:
        value = receipt()
        pass_candidate(value)
        first = value["candidates"][0]  # type: ignore[index]
        self.assertEqual(first["status"], "qualified")
        self.assertEqual([stage["stage"] for stage in first["stages"]], list(STAGES))
        self.assertTrue(all(stage["outcome"] == "pass" for stage in first["stages"]))
        self.assertEqual(value["subject_accounting"]["subject_invocation_starts"], 0)  # type: ignore[index]

    def test_target_selects_twelve_primaries_and_four_alternates(self) -> None:
        value = receipt()
        for _ in range(16):
            pass_candidate(value)
        self.assertEqual(value["status"], "stable_pool_ready")
        self.assertEqual(len(value["selection"]["primary"]), 12)  # type: ignore[index]
        self.assertEqual(len(value["selection"]["alternates"]), 4)  # type: ignore[index]
        self.assertIsNone(next_qualification_stage(value))  # type: ignore[arg-type]
        validate_receipt(value)  # type: ignore[arg-type]

    def test_exhausted_reserve_with_ten_qualifies_minimum_design(self) -> None:
        value = receipt()
        for _ in range(10):
            pass_candidate(value)
        for _ in range(38):
            fail_candidate(value)
        self.assertEqual(value["status"], "stable_pool_ready")
        self.assertEqual(len(value["selection"]["primary"]), 10)  # type: ignore[index]
        self.assertEqual(len(value["selection"]["alternates"]), 0)  # type: ignore[index]

    def test_exhausted_reserve_below_ten_is_terminal_insufficient(self) -> None:
        value = receipt()
        for _ in range(9):
            pass_candidate(value)
        for _ in range(39):
            fail_candidate(value)
        self.assertEqual(value["status"], "insufficient")
        summary = public_summary(value)  # type: ignore[arg-type]
        self.assertFalse(summary["minimum_gate_passed"])
        self.assertEqual(summary["qualified_independent_clusters"], 9)
        self.assertEqual(summary["subject_invocation_starts"], 0)

    def test_public_summary_withholds_task_and_repository_identities(self) -> None:
        value = receipt()
        fail_candidate(value)
        pass_candidate(value)
        summary = public_summary(value)  # type: ignore[arg-type]
        rendered = json.dumps(summary, sort_keys=True)
        self.assertEqual(summary["attempted_candidates"], 2)
        self.assertEqual(summary["flaky_validation_failures"], 1)
        self.assertEqual(summary["qualified_independent_clusters"], 1)
        self.assertNotIn("private-", rendered)
        self.assertNotIn("private/repo", rendered)
        self.assertTrue(summary["task_identities_withheld"])

    def test_rejects_stage_inappropriate_failure_class(self) -> None:
        value = receipt()
        candidate, stage = next_qualification_stage(value)  # type: ignore[arg-type]
        self.assertIn("gold_patch_evaluation_failure", FAILURE_CLASSES)
        with self.assertRaisesRegex(ExperimentConfigurationError, "classification"):
            record_stage(
                value,  # type: ignore[arg-type]
                slot=candidate["slot"],
                stage=stage,
                outcome="fail",
                classification="gold_patch_evaluation_failure",
                evidence=evidence(candidate["slot"], stage),
            )

    def test_gold_classifier_distinguishes_acceptance_failure_and_runtime(self) -> None:
        candidate = {"instance_id": "private-id"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "private-id"
            task.mkdir()
            (task / "report.json").write_text(
                json.dumps({"instance_id": "private-id", "resolved": True}),
                encoding="utf-8",
            )
            (root / "results.json").write_text(
                json.dumps({"success_ids": ["private-id"], "error": 0, "incomplete": 0}),
                encoding="utf-8",
            )
            self.assertEqual(
                _gold_classification(
                    candidate,
                    root,
                    {"timed_out": False, "exit_code": 0},
                ),
                ("pass", None),
            )
            (task / "report.json").write_text(
                json.dumps({"instance_id": "private-id", "resolved": False}),
                encoding="utf-8",
            )
            self.assertEqual(
                _gold_classification(
                    candidate,
                    root,
                    {"timed_out": False, "exit_code": 0},
                ),
                ("fail", "gold_patch_evaluation_failure"),
            )
            self.assertEqual(
                _gold_classification(
                    candidate,
                    root,
                    {"timed_out": True, "exit_code": None},
                ),
                ("fail", "infrastructure_timeout"),
            )


if __name__ == "__main__":
    unittest.main()
