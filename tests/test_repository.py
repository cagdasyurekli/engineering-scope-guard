from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.repository import (
    compare_snapshots,
    infrastructure_pattern,
    snapshot_repository,
)


class RepositoryTests(unittest.TestCase):
    def _assert_non_object_package_json_is_degraded(self, content: str) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "package.json").write_text(content, encoding="utf-8")
            snapshot = snapshot_repository(root, "before")
            self.assertEqual(snapshot["dependencies"], [])
            self.assertEqual(
                snapshot["warnings"],
                ["dependency manifest package.json top-level JSON is not an object"],
            )

    def test_package_json_array_top_level_is_degraded(self):
        self._assert_non_object_package_json_is_degraded("[]")

    def test_package_json_null_top_level_is_degraded(self):
        self._assert_non_object_package_json_is_degraded("null")

    def test_package_json_scalar_top_level_is_degraded(self):
        self._assert_non_object_package_json_is_degraded('"package"')

    def test_structural_dependency_test_instruction_and_infrastructure_deltas(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "AGENTS.md").write_text("short\n", encoding="utf-8")
            (root / "src.py").write_text("one\ntwo\n", encoding="utf-8")
            (root / "binary.dat").write_bytes(b"\x00\x01")
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"existing": "1"}}), encoding="utf-8"
            )
            before = snapshot_repository(root, "before")

            (root / "src.py").write_text("one\nchanged\nthree\n", encoding="utf-8")
            (root / "binary.dat").write_bytes(b"\x00\x02")
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "dependencies": {"existing": "2", "alpha": "1", "beta": "1"},
                        "devDependencies": {"dev-only": "1"},
                    }
                ),
                encoding="utf-8",
            )
            (root / "tests").mkdir()
            (root / "tests" / "test_src.py").write_text("assert True\n", encoding="utf-8")
            (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("x" * 5000, encoding="utf-8")
            after = snapshot_repository(root, "after")

            delta = compare_snapshots(before, after, ["AGENTS.md"])

            self.assertEqual(delta["files"]["counts"], {"added": 2, "deleted": 0, "modified": 4})
            self.assertEqual(delta["loc"]["added"], 6)
            self.assertEqual(delta["loc"]["deleted"], 3)
            self.assertEqual(delta["loc"]["definition_version"], "strict-utf8-lines-v1")
            self.assertEqual(
                delta["loc"]["changed_entry_kinds"],
                {"text": 5, "binary": 1, "symlink": 0, "special": 0},
            )
            self.assertEqual(delta["tests"]["added"], ["tests/test_src.py"])
            self.assertEqual(
                delta["infrastructure"],
                {
                    "pattern_set_version": "candidate-infrastructure-paths-v1",
                    "candidates": [
                        {
                            "path": "Dockerfile",
                            "pattern_id": "dockerfile-basename-anywhere",
                        }
                    ],
                },
            )
            self.assertEqual(
                [item["rule_id"] for item in delta["candidate_review_events"]],
                [
                    "candidate_infrastructure_artifact",
                    "multiple_runtime_dependencies_added",
                    "substantial_instruction_growth",
                ],
            )
            changed_dependencies = delta["dependencies"]["changed"]
            self.assertEqual(changed_dependencies[0]["name"], "existing")

    def test_pyproject_standard_tables_and_name_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pyproject.toml").write_text(
                "[project]\ndependencies = ['My_Package>=1']\n",
                encoding="utf-8",
            )
            before = snapshot_repository(root, "before")
            (root / "pyproject.toml").write_text(
                """[project]
dependencies = ['My.Package>=2', 'Added[extra]>=1']
[project.optional-dependencies]
docs = ['Sphinx>=7']
[dependency-groups]
test = ['pytest>=8', {include-group = 'lint'}]
""",
                encoding="utf-8",
            )
            after = snapshot_repository(root, "after")
            delta = compare_snapshots(before, after, [])
            self.assertEqual(delta["dependencies"]["changed"][0]["name"], "my-package")
            names = {item["name"] for item in delta["dependencies"]["added"]}
            self.assertEqual(names, {"added", "pytest", "sphinx"})

    def test_infrastructure_pattern_set_v1_freezes_path_semantics(self):
        expected = {
            "Dockerfile": "dockerfile-basename-anywhere",
            "containers/Dockerfile.dev": "dockerfile-basename-anywhere",
            "netlify.toml": "known-config-basename-anywhere",
            "docs/netlify.toml": "known-config-basename-anywhere",
            "main.tf": "terraform-extension-anywhere",
            "examples/main.tf": "terraform-extension-anywhere",
            "terraform/modules/example.txt":
                "known-infrastructure-directory-prefix-at-root",
            ".circleci/config.yml":
                "known-infrastructure-directory-prefix-at-root",
            ".github/workflows/check.yml": "github-workflow-yaml-direct-child",
        }
        for path, pattern_id in expected.items():
            with self.subTest(path=path):
                self.assertEqual(infrastructure_pattern(path), pattern_id)

        for path in (
            "Dockerfiletxt",
            "docs/netlify.toml.example",
            "docs/terraform/main.txt",
            ".github/workflows/nested/check.yml",
            ".github/workflows/check.json",
        ):
            with self.subTest(path=path):
                self.assertIsNone(infrastructure_pattern(path))

    def test_symlink_is_not_followed_and_cache_directories_are_excluded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root.parent / f"{root.name}-outside"
            outside.write_text("outside", encoding="utf-8")
            self.addCleanup(lambda: outside.unlink(missing_ok=True))
            os.symlink(outside, root / "link")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "package.json").write_text("{}", encoding="utf-8")
            snapshot = snapshot_repository(root, "before")
            entries = {entry["path"]: entry for entry in snapshot["entries"]}
            self.assertEqual(entries["link"]["kind"], "symlink")
            self.assertNotIn("node_modules/package.json", entries)

    def test_loc_changed_kinds_separate_binary_and_symlink_from_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside_one = root.parent / f"{root.name}-outside-one"
            outside_two = root.parent / f"{root.name}-outside-two"
            outside_one.write_text("one", encoding="utf-8")
            outside_two.write_text("two", encoding="utf-8")
            self.addCleanup(lambda: outside_one.unlink(missing_ok=True))
            self.addCleanup(lambda: outside_two.unlink(missing_ok=True))
            (root / "text.txt").write_text("before\n", encoding="utf-8")
            (root / "binary.bin").write_bytes(b"\x00\x01")
            os.symlink(outside_one, root / "link")
            before = snapshot_repository(root, "before")
            (root / "text.txt").write_text("after\n", encoding="utf-8")
            (root / "binary.bin").write_bytes(b"\x00\x02")
            (root / "link").unlink()
            os.symlink(outside_two, root / "link")
            after = snapshot_repository(root, "after")

            delta = compare_snapshots(before, after, [])

            self.assertEqual(delta["loc"]["added"], 1)
            self.assertEqual(delta["loc"]["deleted"], 1)
            self.assertEqual(
                delta["loc"]["changed_entry_kinds"],
                {"text": 1, "binary": 1, "symlink": 1, "special": 0},
            )

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO support")
    def test_special_files_are_skipped_with_visible_degradation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            os.mkfifo(root / "pipe")
            snapshot = snapshot_repository(root, "before")
            self.assertEqual(snapshot["entries"][0]["kind"], "special")
            self.assertEqual(
                snapshot["warnings"],
                ["special filesystem entry was not read: pipe"],
            )


if __name__ == "__main__":
    unittest.main()
