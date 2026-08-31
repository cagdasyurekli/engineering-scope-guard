from pathlib import Path


def safe_path(base: Path, name: str) -> Path:
    root = base.resolve()
    candidate = (root / name).resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError("path escapes base directory")
    return candidate


def read_one(base: Path, name: str) -> str:
    return safe_path(base, name).read_text(encoding="utf-8")
