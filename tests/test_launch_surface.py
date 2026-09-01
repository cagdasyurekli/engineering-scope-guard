import copy
import hashlib
from pathlib import Path
import unittest

from engineering_scope_guard.launch_surface import (
    DISABLED_FEATURES,
    LaunchSurfaceError,
    build_launch_profile,
    canonical_bytes,
    rendered_command,
    validate_launch_contract,
    validate_launch_profile,
    validate_treatment_pair,
)


EXEC_HELP = " ".join(
    (
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
)


class LaunchSurfaceTests(unittest.TestCase):
    def _profile(self, effort: str = "low") -> dict:
        return build_launch_profile(
            executable=Path("/private/runtime/codex"),
            model="gpt-5.6-sol",
            reasoning_effort=effort,
        )

    def test_profiles_use_argv_stdin_and_no_explicit_sandbox(self) -> None:
        profile = self._profile()
        validate_launch_profile(profile, exec_help=EXEC_HELP)
        self.assertEqual(profile["argv"][0], "exec")
        self.assertEqual(profile["argv"][-1], "-")
        self.assertEqual(profile["stdin_mode"], "piped_utf8_prompt")
        self.assertIn("--approve-for-me", profile["argv"])
        self.assertNotIn("--sandbox", profile["argv"])
        self.assertEqual(profile["argv"].count("--disable"), len(DISABLED_FEATURES))
        self.assertEqual(rendered_command(profile)[0], profile["executable"])

    def test_exact_predecessor_mutual_exclusion_is_rejected(self) -> None:
        profile = self._profile()
        profile["argv"][-1:-1] = ["--sandbox", "workspace-write"]
        with self.assertRaisesRegex(
            LaunchSurfaceError,
            "--approve-for-me and --sandbox are mutually exclusive",
        ):
            validate_launch_profile(profile, exec_help=EXEC_HELP)

    def test_duplicate_conflicting_reasoning_setting_is_rejected(self) -> None:
        profile = self._profile()
        profile["argv"][-1:-1] = ["--config", 'model_reasoning_effort="medium"']
        with self.assertRaisesRegex(LaunchSurfaceError, "reasoning settings"):
            validate_launch_profile(profile)

    def test_pair_diff_contains_only_native_reasoning_treatment(self) -> None:
        result = validate_treatment_pair(
            self._profile("low"), self._profile("medium"), exec_help=EXEC_HELP
        )
        self.assertTrue(result["treatment_only"])
        self.assertEqual(len(result["changed_paths"]), 2)
        self.assertIn("/reasoning_effort", result["changed_paths"])
        self.assertTrue(any(path.startswith("/argv/") for path in result["changed_paths"]))

    def test_pair_rejects_environment_confound(self) -> None:
        low = self._profile("low")
        medium = copy.deepcopy(self._profile("medium"))
        medium["environment"]["EXPERIMENT_ARM"] = "medium"
        with self.assertRaisesRegex(LaunchSurfaceError, "outside reasoning effort"):
            validate_treatment_pair(low, medium)

    def test_help_compatibility_is_fail_closed(self) -> None:
        with self.assertRaisesRegex(LaunchSurfaceError, "current Codex exec help lacks"):
            validate_launch_profile(self._profile(), exec_help="--json")

    def test_contract_hashes_fail_closed(self) -> None:
        profiles = {effort: self._profile(effort) for effort in ("low", "medium")}
        treatment_diff = validate_treatment_pair(
            profiles["low"], profiles["medium"], exec_help=EXEC_HELP
        )
        body = {
            "schema_name": "engineering-scope-guard.launch-surface-contract",
            "schema_version": 1,
            "profiles": profiles,
            "profile_sha256s": {
                effort: hashlib.sha256(canonical_bytes(profile)).hexdigest()
                for effort, profile in profiles.items()
            },
            "treatment_diff": treatment_diff,
            "treatment_diff_sha256": hashlib.sha256(
                canonical_bytes(treatment_diff)
            ).hexdigest(),
            "shell": False,
            "diagnostic_launch_cap": 4,
        }
        contract = {
            **body,
            "contract_sha256": hashlib.sha256(canonical_bytes(body)).hexdigest(),
        }
        validate_launch_contract(contract, exec_help=EXEC_HELP)
        contract["profiles"]["low"]["environment"]["DRIFT"] = "1"
        with self.assertRaisesRegex(LaunchSurfaceError, "outside reasoning effort"):
            validate_launch_contract(contract, exec_help=EXEC_HELP)


if __name__ == "__main__":
    unittest.main()
