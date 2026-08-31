import unittest

from src.exporter import export_names


class ExporterTests(unittest.TestCase):
    def test_export_names_preserves_order(self):
        self.assertEqual(export_names([{"name": "First"}, {"name": "Second"}]), ["First", "Second"])


if __name__ == "__main__":
    unittest.main()
