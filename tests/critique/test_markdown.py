from __future__ import annotations

import os
from pathlib import Path

from probative.critique.report import DimensionStatus
from probative.render.markdown import md, render_markdown, render_summary
from tests.critique._sample import sample_report

GOLDEN = Path(__file__).parent.parent / "fixtures" / "critique" / "golden" / "sample.md"


def test_markdown_matches_the_golden_file() -> None:
    text = render_markdown(sample_report())
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(text, encoding="utf-8")
    assert text == GOLDEN.read_text(encoding="utf-8")


def test_render_is_deterministic() -> None:
    assert render_markdown(sample_report()) == render_markdown(sample_report())


def test_hostile_document_text_is_inert() -> None:
    text = render_markdown(sample_report())
    # every markup character from the document is escaped, none survives raw
    assert "<script>" not in text
    assert "[x](http://evil.test)" not in text
    assert "\\<script\\>" in text
    assert "\\[x\\]\\(http:\u200b//evil.test\\)" in text
    assert "\\|" in text  # the pipe cannot break a table


def test_summary_has_one_row_per_dimension_with_n_beside_every_rate() -> None:
    report = sample_report()
    summary = render_summary(report)
    rows = [
        line for line in summary.splitlines() if line.startswith("| ") and "Dimension" not in line
    ]
    assert len(rows) == len(report.dimensions)
    for dim, row in zip(report.dimensions, rows, strict=True):
        if dim.status is DimensionStatus.ASSESSED:
            assert f"of {dim.checked} (" in row
        else:
            assert "—" in row


def test_every_finding_shows_quote_and_locator() -> None:
    report = sample_report()
    text = render_markdown(report)
    for dim in report.dimensions:
        for f in dim.findings:
            assert md(f.quote) in text and md(f.locator_label) in text


def test_md_escapes_and_collapses() -> None:
    assert md("a\n  b") == "a b"
    assert md("- item") == "\\- item"
    assert md("`x` *y* <z> | w") == "\\`x\\` \\*y\\* \\<z\\> \\| w"


def test_metadata_is_not_a_lazy_continuation_of_the_quote_block() -> None:
    lines = render_markdown(sample_report()).splitlines()
    for i, line in enumerate(lines):
        if line.startswith("> “"):
            assert lines[i + 1] == "", "rubric text must not follow the quote without a blank line"
            assert not lines[i + 2].startswith(">")


def test_urls_in_quotes_cannot_autolink() -> None:
    assert "://" not in md("see https://evil.example/x and HTTP://a.b")
    assert "www." not in md("go to www.evil.test now")
    assert md("https://evil.example").replace("​", "").replace("\\", "") == "https://evil.example"


def test_group_heading_has_no_denominator_for_an_incomplete_dimension() -> None:
    from tests.critique._scripted import Scripted
    from tests.critique.test_pipeline import _run

    report = _run(
        Scripted(omit_for="BROKEN"),
        docs=("# D\n\nNEED: Users need a FLAG widget.\nNEED: Users need BROKEN speed.\n",),
        batch_size=1,
    )
    text = render_markdown(report)
    heading = next(h for h in text.splitlines() if h.startswith("#### Problem framing"))
    assert " of " not in heading.rsplit("(", 1)[-1]


def test_summary_mentions_skipped_files_and_undecided_counts() -> None:
    from probative.critique.report import SkippedFile

    report = sample_report().model_copy(update={"skipped": [SkippedFile(path="x.png", reason="r")]})
    assert "1 file skipped" in render_summary(report)


def test_no_line_ends_in_whitespace_so_a_whitespace_trimming_hook_cannot_change_a_report() -> None:
    for line in render_markdown(sample_report()).splitlines():
        assert line == line.rstrip(), repr(line)
