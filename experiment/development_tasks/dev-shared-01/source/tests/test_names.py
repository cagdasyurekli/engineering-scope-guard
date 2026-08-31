import unittest

from src.cli import cli_username


class NameTests(unittest.TestCase):
    def test_cli_trims_and_lowercases(self):
        self.assertEqual(cli_username(" Alice "), "alice")


if __name__ == "__main__":
    unittest.main()
