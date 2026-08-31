#!/usr/bin/env python3
"""Validate repository-local Markdown links without reading network resources."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
import re
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlsplit


MARKDOWN_SUFFIXES = {".md", ".markdown"}
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
REFERENCE_DEFINITION_RE = re.compile(
    r"^ {0,3}\[([^]]+)\]:\s*(?:<([^>]+)>|([^\s]+))(?:\s+.*)?$"
)
INLINE_LINK_RE = re.compile(
    r"!?\[[^]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s)]+))(?:\s+[^)]*)?\)"
)
REFERENCE_LINK_RE = re.compile(r"!?\[([^]\n]+)\]\[([^]\n]*)\]")
INLINE_CODE_RE = re.compile(r"(`+)(.*?)\1")
PERCENT_ESCAPE_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
HTML_TAG_RE = re.compile(r"<[^>]*>")
MARKDOWN_FORMAT_RE = re.compile(r"[*_~`]")
ANCHOR_PUNCTUATION_RE = re.compile(r"[^\w\- ]", re.UNICODE)


@dataclass(frozen=True, order=True)
class Diagnostic:
    """One content-free, deterministic link-validation failure."""

    source: str
    line: int
    code: str
    target_sha256: str

    def render(self) -> str:
        return (
            f"{self.source}:{self.line}: {self.code} "
            f"[target_sha256={self.target_sha256}]"
        )


@dataclass(frozen=True)
class Link:
    line: int
    destination: str


def _target_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="surrogateescape")).hexdigest()


def _reference_label(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _content_lines(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("markdown source is unreadable UTF-8") from error
    result: list[tuple[int, str]] = []
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), 1):
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            kind = marker[0]
            if fence is None:
                fence = kind
            elif fence == kind:
                fence = None
            continue
        if fence is None:
            result.append((number, line))
    return result


def _links(path: Path) -> tuple[list[Link], list[tuple[int, str]]]:
    lines = _content_lines(path)
    definitions: dict[str, tuple[int, str]] = {}
    definition_lines: set[int] = set()
    for number, line in lines:
        match = REFERENCE_DEFINITION_RE.match(line)
        if match:
            label = _reference_label(match.group(1))
            destination = match.group(2) or match.group(3)
            definitions.setdefault(label, (number, destination))
            definition_lines.add(number)

    links: list[Link] = []
    missing: list[tuple[int, str]] = []
    used_definitions: set[str] = set()
    for number, line in lines:
        if number in definition_lines:
            continue
        visible = INLINE_CODE_RE.sub(lambda match: " " * len(match.group(0)), line)
        occupied: list[tuple[int, int]] = []
        for match in INLINE_LINK_RE.finditer(visible):
            links.append(Link(number, match.group(1) or match.group(2)))
            occupied.append(match.span())
        for match in REFERENCE_LINK_RE.finditer(visible):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            label = _reference_label(match.group(2) or match.group(1))
            definition = definitions.get(label)
            if definition is None:
                missing.append((number, label))
            elif label not in used_definitions:
                links.append(Link(number, definition[1]))
                used_definitions.add(label)
    return links, missing


def _github_anchor(text: str) -> str:
    value = HTML_TAG_RE.sub("", text.strip()).casefold()
    value = MARKDOWN_FORMAT_RE.sub("", value)
    value = ANCHOR_PUNCTUATION_RE.sub("", value)
    return re.sub(r" +", "-", value)


def _anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for _number, line in _content_lines(path):
        match = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        heading = match.group(1)
        explicit = re.search(r"\s*\{#([A-Za-z][\w:.-]*)\}\s*$", heading)
        if explicit:
            anchors.add(explicit.group(1))
            heading = heading[: explicit.start()]
        base = _github_anchor(heading)
        if not base:
            continue
        occurrence = counts.get(base, 0)
        counts[base] = occurrence + 1
        anchors.add(base if occurrence == 0 else f"{base}-{occurrence}")
    return anchors


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _source_path(root: Path, supplied: Path) -> Path:
    candidate = supplied if supplied.is_absolute() else root / supplied
    resolved = candidate.resolve(strict=True)
    if not _inside(resolved, root) or not resolved.is_file():
        raise ValueError("source path escapes the repository or is not a file")
    if {".git", ".local"}.intersection(resolved.relative_to(root).parts):
        raise ValueError("source path is private repository state")
    if resolved.suffix.casefold() not in MARKDOWN_SUFFIXES:
        raise ValueError("source path is not Markdown")
    return resolved


def _tracked_markdown(root: Path) -> list[Path]:
    process = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", "*.md", "*.markdown"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if process.returncode != 0:
        raise ValueError("default Markdown discovery requires a Git worktree")
    names = process.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    return [_source_path(root, Path(name)) for name in names if name]


def _supplied_markdown(root: Path, values: list[Path]) -> list[Path]:
    result: list[Path] = []
    for value in values:
        candidate = value if value.is_absolute() else root / value
        if candidate.is_dir() and not candidate.is_symlink():
            directory = candidate.resolve(strict=True)
            if not _inside(directory, root):
                raise ValueError("source directory escapes the repository")
            if {".git", ".local"}.intersection(directory.relative_to(root).parts):
                raise ValueError("source directory is private repository state")
            for path in directory.rglob("*"):
                relative_parts = path.absolute().relative_to(root.absolute()).parts
                if (
                    not {".git", ".local"}.intersection(relative_parts)
                    and path.suffix.casefold() in MARKDOWN_SUFFIXES
                    and path.is_file()
                ):
                    result.append(_source_path(root, path))
        else:
            result.append(_source_path(root, value))
    return sorted(set(result), key=lambda path: path.relative_to(root).as_posix())


def discover_markdown(root: Path, paths: list[Path] | None = None) -> list[Path]:
    resolved_root = root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise ValueError("repository root is not a directory")
    found = _tracked_markdown(resolved_root) if not paths else _supplied_markdown(resolved_root, paths)
    return sorted(set(found), key=lambda path: path.relative_to(resolved_root).as_posix())


def _destination_parts(destination: str) -> tuple[str, str] | str:
    if PERCENT_ESCAPE_RE.search(destination):
        return "malformed-url-escape"
    decoded = unquote(destination)
    parsed = urlsplit(decoded)
    scheme = parsed.scheme.casefold()
    if scheme in {"http", "https", "mailto"}:
        return "external"
    if scheme == "file":
        return "forbidden-file-url"
    if scheme or parsed.netloc:
        return "unsupported-url-scheme"
    if parsed.query:
        return "unsupported-local-query"
    return parsed.path, parsed.fragment


def validate_local_markdown_links(
    root: Path, paths: list[Path] | None = None
) -> list[Diagnostic]:
    root = root.resolve(strict=True)
    diagnostics: list[Diagnostic] = []
    try:
        sources = discover_markdown(root, paths)
    except ValueError as error:
        diagnostics.append(Diagnostic(".", 0, str(error), _target_hash("discovery")))
        return diagnostics

    anchor_cache: dict[Path, set[str]] = {}
    for source in sources:
        source_name = source.relative_to(root).as_posix()
        try:
            links, missing = _links(source)
        except ValueError as error:
            diagnostics.append(Diagnostic(source_name, 0, str(error), _target_hash(source_name)))
            continue
        for line, label in missing:
            diagnostics.append(
                Diagnostic(source_name, line, "undefined-reference-link", _target_hash(label))
            )
        for link in links:
            parts = _destination_parts(link.destination)
            if parts == "external":
                continue
            if isinstance(parts, str):
                diagnostics.append(
                    Diagnostic(source_name, link.line, parts, _target_hash(link.destination))
                )
                continue
            relative, fragment = parts
            relative_path = Path(relative) if relative else Path(source.name)
            components = relative_path.parts
            if relative_path.is_absolute():
                code = "forbidden-absolute-path"
            elif ".local" in components:
                code = "forbidden-private-path"
            else:
                candidate = source if not relative else source.parent / relative_path
                lexical = Path(os.path.normpath(candidate))
                if not _inside(lexical, root):
                    code = "forbidden-path-traversal"
                else:
                    try:
                        resolved = candidate.resolve(strict=True)
                    except (OSError, RuntimeError):
                        code = "missing-local-target"
                    else:
                        if not _inside(resolved, root):
                            code = "local-target-escapes-repository"
                        elif not resolved.is_file():
                            code = "local-target-is-not-file"
                        elif fragment and resolved.suffix.casefold() not in MARKDOWN_SUFFIXES:
                            code = "anchor-target-is-not-markdown"
                        elif fragment:
                            anchors = anchor_cache.setdefault(resolved, _anchors(resolved))
                            code = "missing-markdown-anchor" if fragment not in anchors else ""
                        else:
                            code = ""
            if code:
                diagnostics.append(
                    Diagnostic(source_name, link.line, code, _target_hash(link.destination))
                )
    return sorted(diagnostics)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--root", type=Path, default=Path("."))
    value.add_argument("paths", nargs="*", type=Path)
    return value


def main() -> int:
    arguments = parser().parse_args()
    diagnostics = validate_local_markdown_links(
        arguments.root, arguments.paths if arguments.paths else None
    )
    for diagnostic in diagnostics:
        print(diagnostic.render())
    if diagnostics:
        print(f"local-markdown-links: failed ({len(diagnostics)} diagnostics)")
        return 1
    print("local-markdown-links: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
