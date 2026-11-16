"""Builders for the ledger tests. Synthetic data only; no network, no key."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from probative.core.candidates import CandidateKind, ClaimCandidate, ExtractionResult, candidate_id
from probative.core.evidence import EvidenceKind, Tier
from probative.core.evidence import Source as CoreSource
from probative.ingest import ingest, spans

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
OWNER = "ved"


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def ingest_file(
    root: Path, rel: str, text: str, *, kind: EvidenceKind = EvidenceKind.CUSTOMER
) -> CoreSource:
    return ingest(write(root, rel, text), tier=Tier.T1, kind=kind)


def claims_of(source: CoreSource, *quotes: str) -> ExtractionResult:
    """An extraction result holding one claim candidate per quote (each must occur once)."""
    found: list[ClaimCandidate] = []
    for quote in quotes:
        start = source.text.index(quote)
        span = spans(source, [(start, start + len(quote))])[0]
        found.append(ClaimCandidate(id=candidate_id(CandidateKind.CLAIM, span), evidence=span))
    return ExtractionResult(source_id=source.id, claims=found)
