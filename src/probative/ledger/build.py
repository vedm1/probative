"""Extraction candidates to graph nodes (PB13).

Pure and deterministic: the same source and candidates give the same nodes and
edges, in id order. A claim's tier and kind are copied from its source (single
record), its text is the normalised span text, and its confidence is a `Computed`
with `value=None` that names the registered formula: the ledger never supplies a
number (I4). Two sources that state the same normalised text give one `Claim`
node and one `EVIDENCED_BY` edge each; that second edge is the corroboration.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from probative.core.candidates import ExtractionResult
from probative.core.evidence import EvidenceKind, Tier
from probative.core.evidence import Source as CoreSource
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.nodes import Claim, EvidenceSpan, NodeBase, Source
from probative.core.graph.values import Computed
from probative.ledger.normalise import normalise

DIRECT = "claim_confidence_direct"
_DIRECT_TIERS = frozenset({Tier.T1, Tier.T2, Tier.T3, Tier.T5})


def source_node(core: CoreSource, source_root: Path, *, owner: str, now: datetime) -> Source:
    root = source_root.resolve()
    try:
        rel = core.path.resolve().relative_to(root)
    except ValueError:
        raise ValueError(f"{core.path} is outside the source root {root}") from None
    return Source.make(
        ingest_id=core.id,
        sha256=core.sha256,
        format=core.format,
        tier=core.tier,
        kind=core.kind,
        extractor=core.extractor,
        extractor_version=core.extractor_version,
        path=rel.as_posix(),
        owner=owner,
        asserted_at=now,
    )


def new_claim(
    text: str, tier: Tier, kind: EvidenceKind | None, *, owner: str, now: datetime
) -> Claim:
    """A claim whose confidence is still to be computed. Its id does not depend on
    the confidence, so the `Computed` can name the claim it belongs to."""
    if tier not in _DIRECT_TIERS:
        raise ValueError(f"the ledger builds claims that rest on sources; {tier.value} cannot")
    first = Claim.make(
        text=text,
        tier=tier,
        evidence_kind=kind,
        confidence=Computed(value=None, formula_id=DIRECT, input_ids=["claim_000000000000"]),
        owner=owner,
        asserted_at=now,
    )
    return Claim.model_validate(
        {
            **first.model_dump(),
            "confidence": Computed(value=None, formula_id=DIRECT, input_ids=(first.id,)),
        }
    )


def claim_patch(
    source: Source,
    core: CoreSource,
    extraction: ExtractionResult,
    *,
    owner: str,
    now: datetime,
) -> tuple[list[NodeBase], list[Edge]]:
    """The claim and span nodes and the `EVIDENCED_BY` edges for one source."""
    nodes: dict[str, NodeBase] = {}
    edges: dict[str, Edge] = {}
    for cand in extraction.claims:
        text = normalise(cand.evidence.text)
        if not any(ch.isalnum() for ch in text):
            continue
        span = EvidenceSpan.make(
            source_ref=source.id,
            start=cand.evidence.start,
            end=cand.evidence.end,
            text=cand.evidence.text,
            locator=cand.evidence.locator,
            owner=owner,
            asserted_at=now,
        )
        claim = new_claim(text, source.tier, source.kind, owner=owner, now=now)
        edge = Edge.make(
            type=EdgeType.EVIDENCED_BY, src=claim.id, dst=span.id, owner=owner, asserted_at=now
        )
        nodes.setdefault(span.id, span)
        nodes.setdefault(claim.id, claim)
        edges.setdefault(edge.id, edge)
    return [nodes[i] for i in sorted(nodes)], [edges[i] for i in sorted(edges)]
