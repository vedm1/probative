"""PB35-p1: the `paths` globs."""

from __future__ import annotations

import pytest

from probative.interfaces.github.runner import glob_to_regex


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("**/*.md", "a.md", True),
        ("**/*.md", "specs/x/a.md", True),
        ("**/*.md", "a.mdx", False),
        ("*.md", "specs/a.md", False),
        ("*.md", "a.md", True),
        ("specs/**", "specs/a/b.md", True),
        ("specs/**", "other/specs/a.md", False),
        ("docs/?.md", "docs/a.md", True),
        ("docs/?.md", "docs/ab.md", False),
        ("a+b/**/*.md", "a+b/c.md", True),
        ("a+b/**/*.md", "aab/c.md", False),
    ],
)
def test_glob(pattern: str, path: str, expected: bool) -> None:
    assert bool(glob_to_regex(pattern).match(path)) is expected
