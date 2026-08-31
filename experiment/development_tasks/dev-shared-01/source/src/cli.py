from .names import normalize_username


def cli_username(value: str) -> str:
    return normalize_username(value)
