import inspect
import unittest

from src.exporter import find_record


class AcceptanceTests(unittest.TestCase):
    def test_canonical_match_and_first_result(self):
        records = [{"name": " Alpha Beta ", "id": 1}, {"name": "alpha-beta", "id": 2}]
        self.assertIs(find_record(records, "ALPHA___BETA"), records[0])

    def test_no_match(self):
        self.assertIsNone(find_record([{"name": "alpha"}], "beta"))

    def test_existing_canonicalizer_is_reused(self):
        source = inspect.getsource(find_record)
        self.assertIn("canonical_key", source)


if __name__ == "__main__":
    unittest.main()
