import unittest

from src.delivery import deliver


class DeliveryTests(unittest.TestCase):
    def test_deliver_calls_channel(self):
        received: list[str] = []
        deliver(received.append, "hello")
        self.assertEqual(received, ["hello"])


if __name__ == "__main__":
    unittest.main()
