"""Precision and recall of an extraction against hand-labelled gold.

Pure functions. These are eval metrics, not node fields, so they sit outside
the I4 formula registry (PB11); PB32's eval harness may absorb them.

A predicted span matches a gold span of the same kind when their character
IoU is at least 0.5, one-to-one, greedily by highest IoU. Precision is `None`
when nothing was predicted and recall `None` when nothing was labelled — an
undefined ratio is reported as undefined, not as a flattering 1.0.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from probative.core.candidates import (
    Candidate,
    CandidateKind,
    ClaimCandidate,
    ConstraintCandidate,
    DependencyCandidate,
    NeedCandidate,
    RejectReason,
    SegmentCandidate,
    StoryCandidate,
    candidate_id,
)
from probative.core.evidence import EvidenceSpan, Source
from probative.extract.resolve import occurrences, resolve_quote

IOU_THRESHOLD = 0.5


class KindScore(BaseModel):
    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None


class ExtractionScore(BaseModel):
    per_kind: dict[CandidateKind, KindScore]
    overall: KindScore


class GoldLabel(BaseModel):
    kind: CandidateKind
    quote: str


class GoldLabelError(Exception):
    """A hand label does not resolve to exactly one place in its document."""


def _iou(a: Candidate, b: Candidate) -> float:
    if a.evidence.source_id != b.evidence.source_id:
        return 0.0
    overlap = min(a.evidence.end, b.evidence.end) - max(a.evidence.start, b.evidence.start)
    if overlap <= 0:
        return 0.0
    union = (a.evidence.end - a.evidence.start) + (b.evidence.end - b.evidence.start) - overlap
    return overlap / union


def _kind_score(tp: int, fp: int, fn: int) -> KindScore:
    return KindScore(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
    )


def _match_count(predicted: list[Candidate], gold: list[Candidate]) -> int:
    pairs = sorted(
        (
            (-iou, p, g)
            for p, pred in enumerate(predicted)
            for g, gold_item in enumerate(gold)
            if (iou := _iou(pred, gold_item)) >= IOU_THRESHOLD
        ),
    )
    used_pred: set[int] = set()
    used_gold: set[int] = set()
    for _, p, g in pairs:
        if p not in used_pred and g not in used_gold:
            used_pred.add(p)
            used_gold.add(g)
    return len(used_pred)


def score_extraction(predicted: Sequence[Candidate], gold: Sequence[Candidate]) -> ExtractionScore:
    per_kind: dict[CandidateKind, KindScore] = {}
    total_tp = total_fp = total_fn = 0
    for kind in CandidateKind:
        pred_k = [c for c in predicted if c.kind is kind]
        gold_k = [c for c in gold if c.kind is kind]
        tp = _match_count(pred_k, gold_k)
        fp, fn = len(pred_k) - tp, len(gold_k) - tp
        per_kind[kind] = _kind_score(tp, fp, fn)
        total_tp, total_fp, total_fn = total_tp + tp, total_fp + fp, total_fn + fn
    return ExtractionScore(per_kind=per_kind, overall=_kind_score(total_tp, total_fp, total_fn))


def gold_candidates(source: Source, labels: Sequence[GoldLabel]) -> list[Candidate]:
    """Resolve hand labels (quotes) to candidates through the same resolver
    the pipeline uses. A label must resolve to exactly one place — judged
    loosely (whitespace-tolerant), so a near-duplicate elsewhere counts — and
    no two labels of a kind may resolve to the same span."""
    out: list[Candidate] = []
    seen: set[tuple[CandidateKind, int, int]] = set()
    window = (0, len(source.text))
    for label in labels:
        resolved = resolve_quote(
            source, label.quote, window=window, claimed=set(), max_quote_chars=10_000
        )
        if isinstance(resolved, RejectReason):
            raise GoldLabelError(f"gold quote not resolvable ({resolved.value}): {label.quote!r}")
        if len(occurrences(source.text, label.quote.strip(), window, loose_only=True)) != 1:
            raise GoldLabelError(f"gold quote is not unique in its document: {label.quote!r}")
        key = (label.kind, resolved.start, resolved.end)
        if key in seen:
            raise GoldLabelError(f"duplicate gold label: {label.quote!r}")
        seen.add(key)
        out.append(_make(label.kind, resolved))
    return out


def _make(kind: CandidateKind, span: EvidenceSpan) -> Candidate:
    cid = candidate_id(kind, span)
    match kind:
        case CandidateKind.CLAIM:
            return ClaimCandidate(id=cid, evidence=span)
        case CandidateKind.NEED:
            return NeedCandidate(id=cid, evidence=span)
        case CandidateKind.STORY:
            return StoryCandidate(id=cid, evidence=span)
        case CandidateKind.CONSTRAINT:
            return ConstraintCandidate(id=cid, evidence=span)
        case CandidateKind.DEPENDENCY:
            return DependencyCandidate(id=cid, evidence=span)
        case CandidateKind.SEGMENT:
            return SegmentCandidate(id=cid, evidence=span)


def load_gold_labels(path: Path) -> list[GoldLabel]:
    return [GoldLabel.model_validate(raw) for raw in json.loads(path.read_text())]
