import unittest

from src.delivery import deliver_all


class Channel:
    def __init__(self, name: str, error: Exception | None = None):
        self.name = name
        self.error = error
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)
        if self.error is not None:
            raise self.error


class AcceptanceTests(unittest.TestCase):
    def test_attempts_all_channels_and_returns_ordered_results(self):
        first = Channel("mail")
        broken = Channel("sms", RuntimeError("offline"))
        last = Channel("audit")
        results = deliver_all([first, broken, last], "hello")
        self.assertEqual(first.messages, ["hello"])
        self.assertEqual(broken.messages, ["hello"])
        self.assertEqual(last.messages, ["hello"])
        self.assertEqual(len(results), 3)
        self.assertEqual(
            [(item["channel"], item["success"], item["error"]) for item in results],
            [("mail", True, None), ("sms", False, "offline"), ("audit", True, None)],
        )

    def test_empty_channels(self):
        self.assertEqual(deliver_all([], "hello"), [])


if __name__ == "__main__":
    unittest.main()
