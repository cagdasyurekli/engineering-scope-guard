from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_local_markdown_links", ROOT / "scripts/validate_local_markdown_links.py"
)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class LocalMarkdownLinkValidatorTests(unittest.TestCase):
    def root(self, directory: str) -> Path:
        root = Path(directory) / "repo"
        root.mkdir()
        return root

    def write(self, root: Path, name: str, text: str) -> Path:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def codes(self, root: Path, *paths: str) -> list[str]:
        return [
            item.code
            for item in validator.validate_local_markdown_links(
                root, [Path(path) for path in paths]
            )
        ]

    def test_inline_spaces_and_heading_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            self.write(root, "docs/Target File.md", "# Hello, World!\n\n## Repeat\n## Repeat\n")
            self.write(
                root,
                "README.md",
                "[first](docs/Target%20File.md#hello-world)\n"
                "[duplicate](docs/Target%20File.md#repeat-1)\n",
            )
            self.assertEqual(self.codes(root, "README.md"), [])

    def test_reference_links_and_undefined_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            self.write(root, "guide.md", "# Target\n")
            self.write(
                root,
                "README.md",
                "[Guide][doc]\n[again][DOC]\n[missing][absent]\n\n"
                "[doc]: guide.md#target \"title\"\n",
            )
            diagnostics = validator.validate_local_markdown_links(root, [Path("README.md")])
            self.assertEqual([item.code for item in diagnostics], ["undefined-reference-link"])
            self.assertNotIn("absent", diagnostics[0].render())

    def test_code_fences_and_inline_code_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            self.write(
                root,
                "README.md",
                "```markdown\n[broken](missing.md)\n```\n"
                "`[also broken](missing.md)`\n",
            )
            self.assertEqual(self.codes(root, "README.md"), [])

    def test_broken_file_and_anchor_are_deterministic_and_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            self.write(root, "target.md", "# Present\n")
            self.write(
                root,
                "README.md",
                "[secret target](missing-private-name.md)\n"
                "[anchor](target.md#absent-private-anchor)\n",
            )
            first = validator.validate_local_markdown_links(root, [Path("README.md")])
            second = validator.validate_local_markdown_links(root, [Path("README.md")])
            self.assertEqual(first, second)
            self.assertEqual(
                [item.code for item in first],
                ["missing-local-target", "missing-markdown-anchor"],
            )
            rendered = "\n".join(item.render() for item in first)
            self.assertNotIn("missing-private-name", rendered)
            self.assertNotIn("absent-private-anchor", rendered)

    def test_rejects_absolute_file_private_and_traversal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            self.write(
                root,
                "README.md",
                "[absolute](/etc/passwd)\n[file](file:///etc/passwd)\n"
                "[private](.local/evidence.md)\n[escape](../outside.md)\n",
            )
            self.assertEqual(
                self.codes(root, "README.md"),
                [
                    "forbidden-absolute-path",
                    "forbidden-file-url",
                    "forbidden-private-path",
                    "forbidden-path-traversal",
                ],
            )

    def test_symlink_cannot_escape_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            outside = Path(directory) / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")
            (root / "outside-link.md").symlink_to(outside)
            self.write(root, "README.md", "[escape](outside-link.md)\n")
            self.assertEqual(
                self.codes(root, "README.md"), ["local-target-escapes-repository"]
            )

    def test_external_links_and_images_are_ignored_but_local_image_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            self.write(root, "image.png", "fixture")
            self.write(
                root,
                "README.md",
                "[web](https://example.com/a) [mail](mailto:test@example.com)\n"
                "![external](https://example.com/image.png) ![local](image.png)\n",
            )
            self.assertEqual(self.codes(root, "README.md"), [])

    def test_default_discovery_uses_tracked_markdown_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            tracked = self.write(root, "README.md", "[ok](guide.md)\n")
            guide = self.write(root, "guide.md", "# Guide\n")
            self.write(root, "untracked.md", "[broken](missing.md)\n")
            subprocess.run(
                ["git", "-C", str(root), "add", tracked.name, guide.name], check=True
            )
            self.assertEqual(validator.validate_local_markdown_links(root), [])

    def test_directory_scan_skips_private_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.root(directory)
            self.write(root, "README.md", "# Public\n")
            self.write(root, ".local/private.md", "[private](missing.md)\n")
            self.assertEqual(
                validator.validate_local_markdown_links(root, [Path(".")]), []
            )


if __name__ == "__main__":
    unittest.main()
