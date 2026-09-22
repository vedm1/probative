"""reextract_tracker's failure modes — same guarantees as PB1's
reextract(), applied to tracker Sources."""

from __future__ import annotations

import pytest

from probative.core.evidence import (
    CorruptSourceError,
    EvidenceKind,
    SourceFormat,
    StaleNormalizationError,
    Tier,
)
from probative.ingest.tracker import ingest_tracker, issues, reextract_tracker
from tests.ingest.tracker._paths import FIXTURES


def _source():  # type: ignore[no-untyped-def]
    return ingest_tracker(
        FIXTURES / "jira_all_fields.csv",
        format=SourceFormat.JIRA_CSV,
        tier=Tier.T1,
        kind=EvidenceKind.DOCUMENTARY,
    )


def test_rejects_a_span_from_a_different_source() -> None:
    source = _source()
    other = _source().model_copy(update={"id": "src_not_this_one"})
    (issue,) = [i for i in issues(other) if i.key == "DEMO-1"]

    with pytest.raises(ValueError, match="belongs to source"):
        reextract_tracker(source, issue.summary)


def test_rejects_a_stale_normalization_version() -> None:
    source = _source()
    (issue,) = [i for i in issues(source) if i.key == "DEMO-1"]
    stale = source.model_copy(update={"extractor_version": "jira_csv/0-does-not-exist"})

    with pytest.raises(StaleNormalizationError):
        reextract_tracker(stale, issue.summary)


def test_rejects_a_file_that_changed_on_disk(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "jira_all_fields.csv"
    path.write_bytes((FIXTURES / "jira_all_fields.csv").read_bytes())
    source = ingest_tracker(
        path, format=SourceFormat.JIRA_CSV, tier=Tier.T1, kind=EvidenceKind.DOCUMENTARY
    )
    (issue,) = [i for i in issues(source) if i.key == "DEMO-1"]

    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(CorruptSourceError):
        reextract_tracker(source, issue.summary)
