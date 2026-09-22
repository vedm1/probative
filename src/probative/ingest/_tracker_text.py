"""Shared normalised-text assembly for the four PB2 tracker extractors.

Every extractor writes one block per issue: a `field="header"` line
(`key\\ttype\\tstatus\\tparent_key`) followed by exactly-bounded regions for
`summary`, and — only when present — `description` and
`acceptance_criteria`. Region boundaries match field content exactly (no
trimming needed downstream); the blank-line padding between fields gets
its own untagged region purely to keep `LocatorRegion`'s "no gaps" cover
invariant intact.
"""

from __future__ import annotations

from probative.core.evidence import Locator, LocatorRegion
from probative.ingest._extracted import ExtractedDocument

HEADER_FIELD = "header"
SUMMARY_FIELD = "summary"
DESCRIPTION_FIELD = "description"
ACCEPTANCE_CRITERIA_FIELD = "acceptance_criteria"


class TrackerTextBuilder:
    """Accumulates one Source's worth of issue blocks."""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._regions: list[LocatorRegion] = []
        self._offset = 0

    def _write(self, content: str, *, issue_key: str | None, field: str | None) -> None:
        start = self._offset
        self._parts.append(content)
        self._offset += len(content)
        self._regions.append(
            LocatorRegion(
                start=start,
                end=self._offset,
                locator=Locator(issue_key=issue_key, field=field),
            )
        )

    def add_issue(
        self,
        *,
        key: str,
        type_: str,
        status: str,
        parent_key: str | None,
        summary: str,
        description: str | None,
        acceptance_criteria: str | None,
    ) -> None:
        header = f"{key}\t{type_}\t{status}\t{parent_key or ''}\n"
        self._write(header, issue_key=key, field=HEADER_FIELD)
        self._write(summary, issue_key=key, field=SUMMARY_FIELD)
        self._write("\n\n", issue_key=key, field=None)
        if description:
            self._write(description, issue_key=key, field=DESCRIPTION_FIELD)
            self._write("\n\n", issue_key=key, field=None)
        if acceptance_criteria:
            self._write(acceptance_criteria, issue_key=key, field=ACCEPTANCE_CRITERIA_FIELD)
            self._write("\n\n", issue_key=key, field=None)
        self._write("---\n", issue_key=None, field=None)

    def build(self, normalization_version: str) -> ExtractedDocument:
        return ExtractedDocument(
            text="".join(self._parts),
            locator_regions=self._regions,
            normalization_version=normalization_version,
        )
