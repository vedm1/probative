"""Answers to graph content (PB14). Pure and deterministic: the same turns give the same
nodes, in id order. Nothing here supplies a number: a claim's confidence is a `Computed`
with `value=None` that names the registered formula, and the `Committer` fills it (I4).

What an answer becomes (D4: the basis decides claim or Question, never a weight):

* `observed` or `told` with words  -> one T3 `Claim` whose text is the respondent's own
  words, one `EvidenceSpan` over those words only, one `EVIDENCED_BY` edge (I1).
* `document`                       -> a `gap` `Question`: which document is it.
* `belief`, no basis, or `unknown` -> an `elicitation` `Question`. Never a `Hypothesis`: I2
  would need a `Test` with a kill criterion, and I6 forbids asking a person to write one.
* `deny` of a source claim         -> a `Question` about that claim (`RAISED_ABOUT`).

The question text is never inside a span, so a leading question cannot become evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from probative.core.evidence import EvidenceKind, Tier
from probative.core.evidence import Source as CoreSource
from probative.core.graph.edges import Edge, EdgeType
from probative.core.graph.nodes import EvidenceSpan, NodeBase, Question
from probative.core.graph.nodes import Source as SourceNode
from probative.elicit.types import AnswerKind, Basis, Turn
from probative.ingest import spans as ingest_spans
from probative.ledger.build import new_claim
from probative.ledger.normalise import normalise

BELIEF_TEXT: Final = (
    'The respondent believes this and gave no basis for it: "{answer}" What is it based on?'
)
UNKNOWN_TEXT: Final = 'The respondent did not know the answer to: "{question}"'
DOCUMENT_TEXT: Final = (
    'The respondent points to a document for this: "{answer}" Which document is it?'
)
TAINTED_TEXT: Final = (
    "This answer was given to a question that may have led it, so it is not used as evidence: "
    '"{answer}" Can it be asked again without suggesting an answer?'
)
DENIED_TEXT: Final = (
    'The respondent says this does not match what they know: "{claim}" What is different?'
)
HEADER: Final = "Elicitation session {session}"
ANSWER_PREFIX: Final = "Answer {n} [{kind}; basis {basis}]: "
QUESTION_PREFIX: Final = "Question {n}: "


class Outcome(StrEnum):
    CLAIM = "claim"
    DOCUMENT_QUESTION = "document_question"
    BELIEF_QUESTION = "belief_question"
    UNKNOWN_QUESTION = "unknown_question"
    DENIED_QUESTION = "denied_question"
    NOTHING = "nothing"  # a challenge answer that only records which claim holds
    TAINTED_QUESTION = "tainted_question"  # BiasHunter blocked the question it answered


def outcome(turn: Turn) -> Outcome:
    """What a turn becomes. A pure function of the turn, so the session can be replayed."""
    if turn.template_id == "challenge_contradiction":
        # the contradiction is already a Question; "mine stands" and "theirs stands" decide
        # nothing the graph can hold yet. Only the respondent's own words about context can.
        stated = turn.answer_kind is AnswerKind.AMEND and _states_a_basis(turn)
        return Outcome.CLAIM if stated else Outcome.NOTHING
    if turn.answer_kind is AnswerKind.UNKNOWN:
        # an unknown about a Question that is already open changes nothing: it stays open
        if turn.template_id == "resolve_open_question":
            return Outcome.NOTHING
        return Outcome.UNKNOWN_QUESTION
    if turn.answer_kind is AnswerKind.DENY:
        return Outcome.DENIED_QUESTION
    if turn.basis is Basis.DOCUMENT:
        return Outcome.DOCUMENT_QUESTION
    if _states_a_basis(turn):
        return Outcome.CLAIM
    return Outcome.BELIEF_QUESTION


def _states_a_basis(turn: Turn) -> bool:
    """Only what the respondent saw or was told is evidence. A belief is a Question."""
    return turn.basis in (Basis.OBSERVED, Basis.TOLD)


def words(turn: Turn, proposition: str | None) -> str:
    """The words a turn carries into the transcript. For a `confirm` or a `deny` the
    respondent chose an option, so the words are the proposition they answered, which the
    caller passes from the source claim. Otherwise they are the respondent's own words."""
    if turn.answer_kind in (AnswerKind.CONFIRM, AnswerKind.DENY):
        if proposition is None:
            raise ValueError(f"a {turn.answer_kind.value} answer needs the claim it answered")
        return proposition
    return turn.answer_text


# -- the transcript -----------------------------------------------------------------


def render(session: str, turns: Sequence[tuple[Turn, str]]) -> str:
    """The transcript file: plain lines, no list markers, so normalisation leaves each
    line as written. `turns` pairs a turn with the text its answer line carries."""
    lines = [HEADER.format(session=session), ""]
    for n, (turn, text) in enumerate(turns, start=1):
        basis = turn.basis.value if turn.basis else "none"
        if turn.basis_count is not None:
            basis += f", {turn.basis_count} seen"
        lines.append(QUESTION_PREFIX.format(n=n) + turn.question_text)
        lines.append(
            ANSWER_PREFIX.format(n=n, kind=turn.answer_kind.value, basis=basis)
            + (text or "(no words)")
        )
        lines.append("")
    return "\n".join(lines)


def locate_answers(core: CoreSource, count: int) -> list[tuple[int, int]]:
    """Offsets, in the source's normalised text, of each answer's words. The prefix of an
    answer line is unique per number, so a plain search is exact; a miss is an error."""
    found: list[tuple[int, int]] = []
    for n in range(1, count + 1):
        marker = f"\nAnswer {n} ["
        at = core.text.find(marker)
        if at < 0 or core.text.find(marker, at + 1) >= 0:
            raise ValueError(f"answer {n} is not exactly once in the transcript")
        colon = core.text.index("]: ", at) + 3
        end = core.text.find("\n", colon)
        found.append((colon, len(core.text) if end < 0 else end))
    return found


@dataclass(frozen=True)
class Built:
    nodes: tuple[NodeBase, ...]
    edges: tuple[Edge, ...]
    claims_by_turn: dict[int, str]
    """turn index -> id of the T3 claim it produced."""


def build(
    pairs: Sequence[tuple[Turn, str, str | None]],
    core: CoreSource | None,
    source: SourceNode | None,
    *,
    owner: str,
    now: datetime,
    tainted: frozenset[int] = frozenset(),
) -> Built:
    """Nodes and edges for turns already rendered into `core`. Each tuple is (turn, answer
    text as rendered, the source-claim id a `deny` is about or None). Offsets come from
    `locate_answers`, so a span always re-extracts to the words recorded."""
    where = locate_answers(core, len(pairs)) if core is not None else [(0, 0)] * len(pairs)
    nodes: dict[str, NodeBase] = {}
    edges: dict[str, Edge] = {}
    claims_by_turn: dict[int, str] = {}
    for (turn, text, about), (start, end) in zip(pairs, where, strict=True):
        what = Outcome.TAINTED_QUESTION if turn.index in tainted else outcome(turn)
        if what is Outcome.CLAIM:
            if core is None or source is None:
                raise ValueError("a claim needs the transcript it rests on")
            slice_ = ingest_spans(core, [(start, end)])[0]
            span = EvidenceSpan.make(
                source_ref=source.id,
                start=slice_.start,
                end=slice_.end,
                text=slice_.text,
                locator=slice_.locator,
                owner=owner,
                asserted_at=now,
            )
            claim = new_claim(
                normalise(slice_.text), Tier.T3, _kind(turn, source), owner=owner, now=now
            )
            edge = Edge.make(
                type=EdgeType.EVIDENCED_BY, src=claim.id, dst=span.id, owner=owner, asserted_at=now
            )
            nodes.setdefault(span.id, span)
            nodes.setdefault(claim.id, claim)
            edges.setdefault(edge.id, edge)
            claims_by_turn[turn.index] = claim.id
        elif what is Outcome.TAINTED_QUESTION:
            _question(nodes, TAINTED_TEXT.format(answer=text), "elicitation", owner, now)
        elif what is Outcome.DOCUMENT_QUESTION:
            _question(nodes, DOCUMENT_TEXT.format(answer=text), "gap", owner, now)
        elif what is Outcome.BELIEF_QUESTION:
            _question(nodes, BELIEF_TEXT.format(answer=text), "elicitation", owner, now)
        elif what is Outcome.UNKNOWN_QUESTION:
            _question(
                nodes, UNKNOWN_TEXT.format(question=turn.question_text), "elicitation", owner, now
            )
        elif what is Outcome.DENIED_QUESTION and about is not None:
            q = _question(nodes, DENIED_TEXT.format(claim=text), "elicitation", owner, now)
            edge = Edge.make(
                type=EdgeType.RAISED_ABOUT, src=q.id, dst=about, owner=owner, asserted_at=now
            )
            edges.setdefault(edge.id, edge)
    return Built(
        tuple(nodes[i] for i in sorted(nodes)),
        tuple(edges[i] for i in sorted(edges)),
        claims_by_turn,
    )


def _kind(turn: Turn, source: SourceNode) -> EvidenceKind | None:
    return turn.evidence_kind or source.kind


def _question(
    nodes: dict[str, NodeBase], text: str, raised_by: str, owner: str, now: datetime
) -> Question:
    q = Question.make(text=text, raised_by=raised_by, owner=owner, asserted_at=now)
    nodes.setdefault(q.id, q)
    return q
