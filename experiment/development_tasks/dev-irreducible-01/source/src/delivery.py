from collections.abc import Callable


def deliver(channel: Callable[[str], None], message: str) -> None:
    channel(message)
