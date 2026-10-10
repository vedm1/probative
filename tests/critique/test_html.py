from __future__ import annotations

import base64
import hashlib
import os
import re
from pathlib import Path

from probative.critique.report import DimensionStatus
from probative.render.html import render_html
from tests.critique._sample import sample_report

GOLDEN = Path(__file__).parent.parent / "fixtures" / "critique" / "golden" / "sample.html"


def _page() -> str:
    return render_html(sample_report())


def test_html_matches_the_golden_file() -> None:
    page = _page()
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(page, encoding="utf-8")
    assert page == GOLDEN.read_text(encoding="utf-8")


def test_render_is_deterministic() -> None:
    assert _page() == _page()


def test_hostile_document_text_is_inert() -> None:
    page = _page()
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert len(re.findall(r"<script\b", page)) == 1  # only the page's own
    assert not re.search(r"\son[a-z]+\s*=", page)  # no inline event handlers
    assert "style=" not in page.replace("style-src", "")  # no style attributes


def test_page_is_self_contained() -> None:
    page = _page()
    assert not re.search(r"<link\b|<img\b|<iframe\b|@import|url\(", page)
    assert not re.search(r"(?:href|src|action)\s*=", page)
    assert 'http-equiv="Content-Security-Policy"' in page
    assert "default-src &#x27;none&#x27;" in page


def test_csp_hashes_match_the_inline_style_and_script() -> None:
    page = _page()
    for tag in ("style", "script"):
        body = re.search(rf"<{tag}>(.*?)</{tag}>", page, flags=re.DOTALL)
        assert body is not None
        digest = base64.b64encode(hashlib.sha256(body.group(1).encode()).digest()).decode()
        assert f"sha256-{digest}" in page


def test_both_themes_are_defined_as_tokens_on_root() -> None:
    page = _page()
    assert re.search(r":root \{\n  --bg: #fbfbf9", page)  # light, outside any media query
    assert "prefers-color-scheme: dark" in page and ':root[data-theme="dark"]' in page


def test_every_finding_is_a_keyboard_reachable_details_with_quote_and_locator() -> None:
    report = sample_report()
    page = _page()
    total = sum(len(d.findings) for d in report.dimensions)
    assert page.count('<details class="finding') == total
    assert page.count("<summary>") == total
    for dim in report.dimensions:
        for f in dim.findings:
            assert f.locator_label in page and "<mark>" in page


def test_severity_is_never_hue_alone() -> None:
    page = _page()
    for word, glyph in (("BLOCK", "✗"), ("WARN", "▲")):
        assert f"{glyph} {word}" in page
    assert "sev-block-box" in page and "sev-warn-box" in page  # distinct border patterns


def test_unassessed_dimensions_are_listed_with_their_status() -> None:
    report = sample_report()
    page = _page()
    for d in report.dimensions:
        if d.status is not DimensionStatus.ASSESSED:
            assert d.label in page
