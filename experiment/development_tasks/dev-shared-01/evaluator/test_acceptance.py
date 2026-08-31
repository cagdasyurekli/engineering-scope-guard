import unittest

from src.api import account_key
from src.cli import cli_username


class AcceptanceTests(unittest.TestCase):
    def test_cli_uses_unicode_casefolding(self):
        self.assertEqual(cli_username(" Straße "), cli_username("STRASSE"))

    def test_shared_api_path_receives_same_fix(self):
        self.assertEqual(account_key(" Straße "), account_key("STRASSE"))


if __name__ == "__main__":
    unittest.main()
