from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.critique.sources import (
    discover_and_load,
    load_source,
    reextract_whole,
    sniff_format,
)

FIX = Path(__file__).parent.parent / "fixtures"
T, K = Tier.T4, EvidenceKind.DOCUMENTARY


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("tracker/jira_visible.csv", SourceFormat.JIRA_CSV),
        ("tracker/jira_all_fields.csv", SourceFormat.JIRA_CSV),
        ("tracker/ado_issues.csv", SourceFormat.ADO_CSV),
        ("tracker/jira_issues.html", SourceFormat.JIRA_HTML),
        ("tracker/jira_export.xml", SourceFormat.JIRA_XML),
        ("confluence/page_export.doc", SourceFormat.CONFLUENCE_WORD),
        ("ingest/data.csv", SourceFormat.CSV),
        ("ingest/notes.md", SourceFormat.MARKDOWN),
        ("ingest/plain.txt", SourceFormat.TEXT),
        ("ingest/memo.pdf", SourceFormat.PDF),
        ("ingest/report.docx", SourceFormat.DOCX),
        ("ingest/sheet.xlsx", SourceFormat.XLSX),
        ("confluence/page.pdf", SourceFormat.PDF),
    ],
)
def test_router_picks_the_format(relative: str, expected: SourceFormat) -> None:
    assert sniff_format(FIX / relative) is expected


@pytest.mark.parametrize(
    "relative",
    ["ingest/unsupported.xyz", "confluence/not_mime.doc", "tracker/jira_no_table.html"],
)
def test_router_returns_none_for_what_it_cannot_read(relative: str) -> None:
    assert sniff_format(FIX / relative) is None


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("tracker/jira_malformed_missing_status.csv", SourceFormat.JIRA_CSV),
        ("tracker/ado_malformed_missing_state.csv", SourceFormat.ADO_CSV),
        ("tracker/jira_malformed_missing_status.html", SourceFormat.JIRA_HTML),
    ],
)
def test_a_malformed_tracker_commits_to_its_format_and_fails_there(
    relative: str, expected: SourceFormat
) -> None:
    assert sniff_format(FIX / relative) is expected  # never falls back to plain CSV
    result = discover_and_load(FIX / relative, tier=T, kind=K)
    assert result.loaded == []
    assert len(result.skipped) == 1
    assert "Unrecognised" in result.skipped[0].reason


@pytest.mark.parametrize(
    ("relative", "fmt"),
    [
        ("tracker/jira_visible.csv", SourceFormat.JIRA_CSV),
        ("tracker/ado_issues.csv", SourceFormat.ADO_CSV),
        ("tracker/jira_issues.html", SourceFormat.JIRA_HTML),
        ("tracker/jira_export.xml", SourceFormat.JIRA_XML),
        ("confluence/page_export.doc", SourceFormat.CONFLUENCE_WORD),
        ("ingest/notes.md", SourceFormat.MARKDOWN),
        ("ingest/memo.pdf", SourceFormat.PDF),
    ],
)
def test_load_and_whole_text_reextraction(relative: str, fmt: SourceFormat) -> None:
    loaded = load_source(FIX / relative, tier=T, kind=K, forced=None)
    assert loaded.source.format is fmt and loaded.format_choice == "detected"
    assert reextract_whole(loaded.source) == loaded.source.text


def test_forced_format_overrides_the_router() -> None:
    loaded = load_source(FIX / "ingest/data.csv", tier=T, kind=K, forced=None)
    assert loaded.source.format is SourceFormat.CSV
    forced = load_source(
        FIX / "tracker/ado_issues.csv", tier=T, kind=K, forced=SourceFormat.ADO_CSV
    )
    assert forced.format_choice == "forced"


def test_forced_plain_format_is_refused() -> None:
    with pytest.raises(ValueError, match="--as"):
        load_source(FIX / "ingest/notes.md", tier=T, kind=K, forced=SourceFormat.MARKDOWN)


def test_reextract_whole_detects_a_changed_file(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text("# A\n\nUsers need speed.\n", encoding="utf-8")
    loaded = load_source(path, tier=T, kind=K, forced=None)
    path.write_text("# A\n\nUsers need something else.\n", encoding="utf-8")
    from probative.core.evidence import CorruptSourceError

    with pytest.raises(CorruptSourceError):
        reextract_whole(loaded.source)


def test_folder_discovery_is_sorted_skips_hidden_and_records_everything_else(
    tmp_path: Path,
) -> None:
    (tmp_path / "b.md").write_text("# B\n\nSecond.\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("# A\n\nFirst.\n", encoding="utf-8")
    (tmp_path / ".hidden.md").write_text("# H\n\nhidden\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("third\n", encoding="utf-8")
    (tmp_path / "pic.xyz").write_bytes(b"\x00\x01")
    (tmp_path / "dup.md").write_text("# A\n\nFirst.\n", encoding="utf-8")  # same bytes as a.md
    result = discover_and_load(tmp_path, tier=T, kind=K)
    assert [lf.source.path.name for lf in result.loaded] == ["a.md", "b.md", "c.txt"]
    reasons = {Path(s.path).name: s.reason for s in result.skipped}
    assert set(reasons) == {"dup.md", "pic.xyz"}
    assert "duplicate" in reasons["dup.md"] and "a.md" in reasons["dup.md"]
    assert "Unsupported" in reasons["pic.xyz"]


def test_over_cap_files_are_skipped_with_a_reason(tmp_path: Path) -> None:
    for i in range(4):
        (tmp_path / f"f{i}.md").write_text(f"# F{i}\n\nBody {i}.\n", encoding="utf-8")
    result = discover_and_load(tmp_path, tier=T, kind=K, max_files=2)
    assert [lf.source.path.name for lf in result.loaded] == ["f0.md", "f1.md"]
    assert {Path(s.path).name for s in result.skipped} == {"f2.md", "f3.md"}
    assert all("max-files" in s.reason for s in result.skipped)


def test_an_unreadable_single_file_is_reported_not_raised() -> None:
    result = discover_and_load(FIX / "ingest/empty.txt", tier=T, kind=K)
    assert result.loaded == [] and len(result.skipped) == 1


def test_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        discover_and_load(tmp_path / "nope", tier=T, kind=K)


def test_copying_a_fixture_keeps_identity(tmp_path: Path) -> None:
    copy = tmp_path / "x.md"
    shutil.copy(FIX / "ingest/notes.md", copy)
    a = load_source(FIX / "ingest/notes.md", tier=T, kind=K, forced=None)
    b = load_source(copy, tier=T, kind=K, forced=None)
    assert a.source.id == b.source.id
