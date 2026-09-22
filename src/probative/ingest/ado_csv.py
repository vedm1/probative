"""Azure DevOps work-item CSV export.

`Parent` is a numeric work-item ID, not a key, and in a real export it
commonly points outside the exported set (confirmed: 0 of 17 distinct
parents resolved within a real 40-row sample) — PB2 records it verbatim
and does not attempt to resolve it; that is a graph-era concern (PB10+),
not this phase's.

`Description` (and, when present, `Acceptance Criteria`) are genuine HTML
from ADO's rich-text editor (confirmed: `<div>`, `&nbsp;`) — normalised via
`probative.ingest._html`, not the Jira wiki-markup path.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from probative.core.evidence import UnrecognisedTrackerFormatError
from probative.ingest import _html
from probative.ingest._extracted import ExtractedDocument
from probative.ingest._lines import decode_and_normalize_endings
from probative.ingest._tracker_text import TrackerTextBuilder

NORMALIZATION_VERSION = "ado_csv/1"

_REQUIRED_COLUMNS = ["ID", "Work Item Type", "State", "Title"]
_DESCRIPTION_COLUMN = "Description"
_PARENT_COLUMN = "Parent"
_ACCEPTANCE_CRITERIA_COLUMN = "Acceptance Criteria"


def extract(path: Path) -> ExtractedDocument:
    text = decode_and_normalize_endings(path)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise UnrecognisedTrackerFormatError(path, "file has no header row")
    header = rows[0]

    missing = [c for c in _REQUIRED_COLUMNS if c not in header]
    if missing:
        raise UnrecognisedTrackerFormatError(
            path, f"missing required column(s) for ado_csv: {', '.join(missing)}"
        )

    id_i = header.index("ID")
    type_i = header.index("Work Item Type")
    state_i = header.index("State")
    title_i = header.index("Title")
    desc_i = header.index(_DESCRIPTION_COLUMN) if _DESCRIPTION_COLUMN in header else None
    parent_i = header.index(_PARENT_COLUMN) if _PARENT_COLUMN in header else None
    ac_i = (
        header.index(_ACCEPTANCE_CRITERIA_COLUMN) if _ACCEPTANCE_CRITERIA_COLUMN in header else None
    )

    builder = TrackerTextBuilder()
    for row in rows[1:]:
        if not row:
            continue
        description = _html.to_text(row[desc_i]) if desc_i is not None and row[desc_i] else None
        acceptance_criteria = _html.to_text(row[ac_i]) if ac_i is not None and row[ac_i] else None
        parent_key = row[parent_i] if parent_i is not None and row[parent_i] else None
        builder.add_issue(
            key=row[id_i],
            type_=row[type_i],
            status=row[state_i],
            parent_key=parent_key,
            summary=row[title_i],
            description=description,
            acceptance_criteria=acceptance_criteria,
        )

    return builder.build(NORMALIZATION_VERSION)
