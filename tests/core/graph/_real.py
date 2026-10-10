"""Build graph nodes from a real PB1 ingest, for the I1 round-trip tests."""

from __future__ import annotations

from pathlib import Path

from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.core.evidence import Source as CoreSource
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, EvidenceSpan, Source
from probative.ingest import ingest, spans
from probative.ingest.confluence import ingest_confluence
from probative.ingest.tracker import ingest_tracker
from tests.core.graph._samples import ENV, conf

_TRACKER = {
    SourceFormat.JIRA_CSV,
    SourceFormat.JIRA_HTML,
    SourceFormat.JIRA_XML,
    SourceFormat.ADO_CSV,
}


def ingest_as(path: Path, fmt: SourceFormat | None, tier: Tier) -> CoreSource:
    kind = EvidenceKind.CUSTOMER
    if fmt in _TRACKER:
        return ingest_tracker(path, format=fmt, tier=tier, kind=kind)
    if fmt is SourceFormat.CONFLUENCE_WORD:
        return ingest_confluence(path, format=fmt, tier=tier, kind=kind)
    return ingest(path, tier=tier, kind=kind)


def grounded_graph(
    root: Path,
    name: str,
    phrase: str,
    *,
    tier: Tier = Tier.T1,
    fmt: SourceFormat | None = None,
) -> tuple[Graph, Source, EvidenceSpan, Claim]:
    src = ingest_as(root / name, fmt, tier)
    start = src.text.index(phrase)
    (core_span,) = spans(src, [(start, start + len(phrase))])
    source = Source.make(
        ingest_id=src.id,
        sha256=src.sha256,
        format=src.format,
        tier=src.tier,
        kind=src.kind,
        extractor=src.extractor,
        extractor_version=src.extractor_version,
        path=name,
        **ENV,
    )
    span = EvidenceSpan.make(
        source_ref=source.id,
        start=core_span.start,
        end=core_span.end,
        text=core_span.text,
        locator=core_span.locator,
        **ENV,
    )
    claim = Claim.make(text=phrase, tier=tier, confidence=conf(), **ENV)
    edge = Edge.make(type=EdgeType.EVIDENCED_BY, src=claim.id, dst=span.id, **ENV)
    graph = Graph.empty().with_patch(nodes=[source, span, claim], edges=[edge])
    return graph, source, span, claim
