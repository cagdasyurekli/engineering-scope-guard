from typing import Any


def export_names(records: list[dict[str, Any]]) -> list[str]:
    return [str(record["name"]) for record in records]
