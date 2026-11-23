"""Builders for the PB14 tests. Synthetic data only; no network, no key."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import probative.formulas  # noqa: F401  (registers the formulas)
from probative.core.candidates import CandidateKind, ClaimCandidate, ExtractionResult, candidate_id
from probative.core.evidence import EvidenceKind, Tier
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, Question
from probative.elicit.types import AnswerKind, Basis, Option, Turn
from probative.formulas.validator import FormulaValidator
from probative.ingest import ingest, spans
from probative.ledger.build import claim_patch, source_node

NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
OWNER = "ved"
OPTS = (
    Option(label="I will say what I know", kind=AnswerKind.OPEN),
    Option(label="I do not know", kind=AnswerKind.UNKNOWN),
)


def turn(
    index: int,
    kind: AnswerKind = AnswerKind.OPEN,
    text: str = "",
    basis: Basis | None = Basis.OBSERVED,
    *,
    template: str = "topic:who_is_affected",
    subject: str = "who_is_affected",
    evidence_kind: EvidenceKind | None = EvidenceKind.CUSTOMER,
    question: str = "Who is affected?",
    count: int | None = None,
    round_: int = 0,
) -> Turn:
    return Turn(
        index=index,
        round=round_,
        template_id=template,
        subject_ref=subject,
        question_text=question,
        options=OPTS,
        evidence_kind=evidence_kind,
        answer_kind=kind,
        answer_text=text,
        basis=basis,
        basis_count=count,
        asked_at=NOW,
        prev_hash="0" * 64,
    )


def t1_graph(root: Path, *quotes: str, rel: str = "interviews/finance.md") -> Graph:
    """A settled graph holding one T1 source and a claim per quote."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(quotes) + "\n", encoding="utf-8")
    core = ingest(path, tier=Tier.T1, kind=EvidenceKind.CUSTOMER)
    found = []
    for q in quotes:
        start = core.text.index(q)
        span = spans(core, [(start, start + len(q))])[0]
        found.append(ClaimCandidate(id=candidate_id(CandidateKind.CLAIM, span), evidence=span))
    node = source_node(core, root, owner=OWNER, now=NOW)
    nodes, edges = claim_patch(
        node, core, ExtractionResult(source_id=core.id, claims=found), owner=OWNER, now=NOW
    )
    graph = Graph.empty().with_patch(nodes=[node, *nodes], edges=edges)
    return FormulaValidator().settle(graph)


def claims(graph: Graph) -> list[Claim]:
    return [n for n in graph.current() if isinstance(n, Claim)]


def questions(graph: Graph) -> list[Question]:
    return [n for n in graph.current() if isinstance(n, Question)]
