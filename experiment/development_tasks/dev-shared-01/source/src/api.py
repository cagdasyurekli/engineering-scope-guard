from .names import normalize_username


def account_key(value: str) -> str:
    return "account:" + normalize_username(value)
