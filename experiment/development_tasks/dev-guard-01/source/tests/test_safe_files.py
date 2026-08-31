import tempfile
import unittest
from pathlib import Path

from src.safe_files import read_one


class SafeFilesTests(unittest.TestCase):
    def test_read_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "value.txt").write_text("value", encoding="utf-8")
            self.assertEqual(read_one(root, "value.txt"), "value")


if __name__ == "__main__":
    unittest.main()
