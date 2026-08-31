import re


def canonical_key(value: str) -> str:
    """Return the repository's canonical comparison key."""

    return re.sub(r"[^a-z0-9]+", "-", value.strip().casefold()).strip("-")
