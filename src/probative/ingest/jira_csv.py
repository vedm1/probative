"""Jira issue-navigator CSV export (both the "visible fields" and "all
fields" variants — confirmed against real exports of each).

Column lookup is by exact header name via `header.index(...)`, not
`csv.DictReader`: `DictReader` silently keeps only the *last* occurrence of
a repeated header name (the "all fields" export repeats `Labels`,
`Watchers`, `Attachment`, `Comment` and `Sprint` once per value), and none
of PB2's canonical columns are ever repeated — `.index()` makes "first
occurrence, duplicates ignored" an explicit choice rather than an accident.

`Description` and the Acceptance Criteria custom field are Jira wiki
markup, not HTML (confirmed against a real export) — normalised via
`probative.ingest._wiki`.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from probative.core.evidence import UnrecognisedTrackerFormatError
from probative.ingest import _wiki
from probative.ingest._extracted import ExtractedDocument
from probative.ingest._lines import decode_and_normalize_endings
from probative.ingest._tracker_text import TrackerTextBuilder

NORMALIZATION_VERSION = "jira_csv/1"

_REQUIRED_COLUMNS = ["Issue key", "Issue Type", "Status", "Summary"]
_DESCRIPTION_COLUMN = "Description"
_PARENT_KEY_COLUMN = "Parent key"
_ACCEPTANCE_CRITERIA_COLUMN = "Custom field (Acceptance Criteria)"


def extract(path: Path) -> ExtractedDocument:
    text = decode_and_normalize_endings(path)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise UnrecognisedTrackerFormatError(path, "file has no header row")
    header = rows[0]

    missing = [c for c in _REQUIRED_COLUMNS if c not in header]
    if missing:
        raise UnrecognisedTrackerFormatError(
            path, f"missing required column(s) for jira_csv: {', '.join(missing)}"
        )

    key_i = header.index("Issue key")
    type_i = header.index("Issue Type")
    status_i = header.index("Status")
    summary_i = header.index("Summary")
    desc_i = header.index(_DESCRIPTION_COLUMN) if _DESCRIPTION_COLUMN in header else None
    parent_i = header.index(_PARENT_KEY_COLUMN) if _PARENT_KEY_COLUMN in header else None
    ac_i = (
        header.index(_ACCEPTANCE_CRITERIA_COLUMN) if _ACCEPTANCE_CRITERIA_COLUMN in header else None
    )

    builder = TrackerTextBuilder()
    for row in rows[1:]:
        if not row:
            continue
        description = _wiki.to_text(row[desc_i]) if desc_i is not None and row[desc_i] else None
        acceptance_criteria = _wiki.to_text(row[ac_i]) if ac_i is not None and row[ac_i] else None
        parent_key = row[parent_i] if parent_i is not None and row[parent_i] else None
        builder.add_issue(
            key=row[key_i],
            type_=row[type_i],
            status=row[status_i],
            parent_key=parent_key,
            summary=row[summary_i],
            description=description,
            acceptance_criteria=acceptance_criteria,
        )

    return builder.build(NORMALIZATION_VERSION)
