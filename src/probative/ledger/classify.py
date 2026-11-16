"""Tier and kind from where a document lives (PB13, D6).

Tier and kind are facts about provenance, not about bytes, so the only honest
classifier is a table of directory cues. It yields **T1 only**: T2 needs a URL,
a retrieval time and a content hash a local file lacks (DeskResearcher, PB15);
T3 comes from the Elicitor (PB14); T4 and T5 are produced, never ingested. A
source the table cannot place is `Unclassified` and stays out of the ledger.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Final

from probative.core.evidence import EvidenceKind, SourceFormat, Tier

_C, _O, _D, _S, _V = (
    EvidenceKind.CUSTOMER,
    EvidenceKind.OPERATIONAL,
    EvidenceKind.DOCUMENTARY,
    EvidenceKind.SYSTEM,
    EvidenceKind.DELIVERY,
)

CUES: Final[Mapping[str, EvidenceKind]] = MappingProxyType(
    {
        "interviews": _C, "transcripts": _C, "reviews": _C, "surveys": _C, "support": _C,
        "analytics": _O, "metrics": _O, "logs": _O, "incidents": _O,
        "sop": _D, "process": _D, "contracts": _D, "policies": _D,
        "prd": _D, "brd": _D, "specs": _D,
        "schemas": _S, "api": _S,
        "tickets": _V, "delivery": _V, "releases": _V,
    }
)  # fmt: skip
"""Directory name, case-insensitive, to the kind of evidence under it."""

MARKET_CUES: Final = frozenset({"market", "research", "competitors", "analyst", "analysts"})

_TRACKERS = frozenset(
    {
        SourceFormat.JIRA_CSV,
        SourceFormat.JIRA_HTML,
        SourceFormat.JIRA_XML,
        SourceFormat.ADO_CSV,
    }
)


@dataclass(frozen=True)
class Classification:
    tier: Tier
    kind: EvidenceKind
    rule_id: str


@dataclass(frozen=True)
class Unclassified:
    reason: str


def classify_source(relpath: str, fmt: SourceFormat) -> Classification | Unclassified:
    """`relpath` is the source's path relative to the run's source root."""
    folders = [p.casefold() for p in PurePosixPath(relpath.replace("\\", "/")).parent.parts]
    market = sorted(set(folders) & MARKET_CUES)
    if market:
        return Unclassified(
            f"market material ({market[0]}) is T2, which needs a URL and a retrieval record "
            "(DeskResearcher, PB15)"
        )
    cues = sorted({f for f in folders if f in CUES})
    kinds = {CUES[c] for c in cues}
    if len(kinds) > 1:
        return Unclassified(f"conflicting folder cues: {', '.join(cues)}")
    if cues:
        return Classification(Tier.T1, CUES[cues[0]], f"cue:{cues[0]}")
    if fmt in _TRACKERS:
        return Classification(Tier.T1, EvidenceKind.DELIVERY, "format:tracker")
    if fmt is SourceFormat.CONFLUENCE_WORD:
        return Classification(Tier.T1, EvidenceKind.DOCUMENTARY, "format:confluence")
    return Unclassified("no folder cue and no format default")
