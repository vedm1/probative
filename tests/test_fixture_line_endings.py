"""A fixture whose bytes matter must reach CI byte for byte.

A recording is keyed by a hash of the prompt, which contains the fixture's text. The Confluence
fixtures are MIME and must be CRLF; a committer with `core.autocrlf=input` (or CI with other
settings) silently rewrites them to LF, the prompt changes, and every recording that reads them
fails on CI while passing on the machine that made it. PB1 and PB2 each added `-text` for their
corpora after being bitten; this keeps the next corpus from being bitten too.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"


def _tracked_text_fixtures_with_cr() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", str(FIXTURES)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    found: list[Path] = []
    for name in filter(None, listed.split("\0")):
        path = REPO / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\r" in data and b"\0" not in data:  # a binary file is never converted
            found.append(path)
    return found


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
@pytest.mark.skipif(not (REPO / ".git").exists(), reason="not a git checkout (sdist)")
def test_every_text_fixture_with_a_carriage_return_is_protected_from_conversion() -> None:
    unprotected: list[str] = []
    for path in _tracked_text_fixtures_with_cr():
        relative = path.relative_to(REPO)
        attribute = subprocess.run(
            ["git", "check-attr", "text", "--", str(relative)],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        if not attribute.strip().endswith("unset"):
            unprotected.append(str(relative))
    assert not unprotected, (
        "these fixtures contain CR but git may rewrite their line endings; add "
        f"`<dir>/** -text` to .gitattributes: {unprotected}"
    )
