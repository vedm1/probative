"""Internal extraction-pipeline shape — not part of the public evidence model.

Each per-format module returns one of these; `probative.ingest.ingest`
turns it into a `Source`.
"""

from __future__ import annotations

from dataclasses import dataclass

from probative.core.evidence import LocatorRegion


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    locator_regions: list[LocatorRegion]
    normalization_version: str
