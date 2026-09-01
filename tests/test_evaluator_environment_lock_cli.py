from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.evaluator_environment_lock import (
    content_tree_hash,
    load_environment_observation,
    parse_pairs,
    validate_gold_result,
    write_private,
)


class EvaluatorEnvironmentLockCliTests(unittest.TestCase):
    def test_parse_pairs_is_order_independent(self) -> None:
        self.assertEqual(parse_pairs(["git=2", "docker=29"]), {"git": "2", "docker": "29"})

    def test_parse_pairs_rejects_duplicate(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_pairs(["git=2", "git=3"])

    def test_private_writer_rejects_public_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "below .local"):
                write_private(Path(directory) / "receipt.json", b"{}\n")

    def test_private_writer_is_atomic_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ".local" / "receipt.json"
            write_private(target, b"{}\n")
            self.assertEqual(target.read_bytes(), b"{}\n")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_environment_observation_requires_exact_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "observation.json"
            target.write_text("{}")
            with self.assertRaisesRegex(ValueError, "fields drifted"):
                load_environment_observation(target)

    def test_content_tree_hash_ignores_bytecode_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "module.py").write_text("value = 1\n")
            before = content_tree_hash(root)
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "module.pyc").write_bytes(b"unstable")
            self.assertEqual(content_tree_hash(root), before)

    def test_gold_result_requires_one_resolved_success(self) -> None:
        validate_gold_result(
            {
                "submitted": 1,
                "success": 1,
                "failure": 0,
                "error": 0,
                "incomplete": 0,
                "success_ids": ["task-a"],
            },
            {"instance_id": "task-a", "resolved": True},
            "task-a",
        )
        with self.assertRaisesRegex(ValueError, "resolved success"):
            validate_gold_result(
                {
                    "submitted": 1,
                    "success": 0,
                    "failure": 1,
                    "error": 0,
                    "incomplete": 0,
                    "success_ids": [],
                },
                {"instance_id": "task-a", "resolved": False},
                "task-a",
            )


if __name__ == "__main__":
    unittest.main()
