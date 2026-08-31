from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.pilot_runner import canonical_evaluator_python


class DatasetBridgeInterpreterTests(unittest.TestCase):
    def test_canonical_evaluator_python_preserves_virtualenv_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_python = root / "base-python"
            base_python.touch()
            venv_python = root / ".venv/bin/python"
            venv_python.parent.mkdir(parents=True)
            venv_python.symlink_to(base_python)

            selected = canonical_evaluator_python(root)

            self.assertEqual(selected, venv_python)
            self.assertTrue(selected.is_symlink())
            self.assertNotEqual(selected, selected.resolve())

    def test_explicit_interpreter_becomes_absolute_without_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            explicit = root / "custom/bin/python"
            explicit.parent.mkdir(parents=True)
            target = root / "base-python"
            target.touch()
            explicit.symlink_to(target)

            selected = canonical_evaluator_python(root, explicit)

            self.assertTrue(selected.is_absolute())
            self.assertEqual(selected, explicit)
            self.assertTrue(selected.is_symlink())


if __name__ == "__main__":
    unittest.main()
