"""confluence_word.extract's own normalisation: heading nesting, table row
flattening, multi-paragraph cell joining, and the no-gaps invariant."""

from __future__ import annotations

from itertools import pairwise

from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.ingest.confluence import ingest_confluence
from tests.ingest.confluence._paths import FIXTURES


def _lines() -> list[str]:
    source = ingest_confluence(
        FIXTURES / "page_export.doc",
        format=SourceFormat.CONFLUENCE_WORD,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    return source.text.splitlines()


def test_heading_becomes_its_own_line() -> None:
    lines = _lines()
    assert "Widget classification based on availability" in lines
    assert "Definitions" in lines


def test_table_rows_are_flattened_with_pipe_separated_cells() -> None:
    lines = _lines()
    assert "Widget name | Description | Availability" in lines
    assert "Sprocket | Turns the main gear assembly. | Generally available" in lines
    assert "Widget | Placeholder for the thing itself. | Alpha" in lines


def test_multi_paragraph_cell_joins_paragraphs_with_slash() -> None:
    lines = _lines()
    assert "Alpha | Generally available" in lines
    assert (
        "Audience - Internal teams / Stability - Experimentation in progress / Support - None"
        " | Officially launched and used by clients."
    ) in lines


def test_bare_paragraph_outside_a_table_is_its_own_line() -> None:
    lines = _lines()
    assert "Terms used in the table above are defined here." in lines


def test_heading_path_tracks_nesting() -> None:
    source = ingest_confluence(
        FIXTURES / "page_export.doc",
        format=SourceFormat.CONFLUENCE_WORD,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    by_text = {source.text[r.start : r.end].strip("\n"): r for r in source.locator_regions}

    top_table_row = by_text["Sprocket | Turns the main gear assembly. | Generally available"]
    assert top_table_row.locator.heading_path == ["Widget classification based on availability"]

    definitions_row = by_text[
        "Audience - Internal teams / Stability - Experimentation in progress / Support - None"
        " | Officially launched and used by clients."
    ]
    assert definitions_row.locator.heading_path == [
        "Widget classification based on availability",
        "Definitions",
    ]

    notes_paragraph = by_text["A second top-level heading closes out the Definitions section."]
    assert notes_paragraph.locator.heading_path == [
        "Widget classification based on availability",
        "Notes",
    ]


def test_locator_regions_cover_the_full_text_with_no_gaps() -> None:
    source = ingest_confluence(
        FIXTURES / "page_export.doc",
        format=SourceFormat.CONFLUENCE_WORD,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )
    regions = sorted(source.locator_regions, key=lambda r: r.start)
    assert regions[0].start == 0
    for a, b in pairwise(regions):
        assert a.end == b.start
    assert regions[-1].end == len(source.text)
