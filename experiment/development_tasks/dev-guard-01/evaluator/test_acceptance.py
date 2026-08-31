import tempfile
import unittest
from pathlib import Path

from src.safe_files import read_many


class AcceptanceTests(unittest.TestCase):
    def test_reads_all_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.txt").write_text("A", encoding="utf-8")
            (root / "b.txt").write_text("B", encoding="utf-8")
            self.assertEqual(read_many(root, ["a.txt", "b.txt"]), {"a.txt": "A", "b.txt": "B"})

    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "root"
            root.mkdir()
            (parent / "secret.txt").write_text("secret", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_many(root, ["../secret.txt"])

    def test_rejects_absolute_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root.parent / "outside.txt"
            with self.assertRaises(ValueError):
                read_many(root, [str(outside)])


if __name__ == "__main__":
    unittest.main()
