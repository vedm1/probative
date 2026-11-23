"""PB14 tests 1, 4, 7 and the gain rule: answers to graph, the sealed transcript, I1 round trip."""

from __future__ import annotations

from pathlib import Path

import pytest

import probative.formulas  # noqa: F401
from probative.core.evidence import Tier
from probative.core.graph.edges import EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, EvidenceSpan, Question
from probative.core.graph.nodes import Source as SourceNode
from probative.core.graph.validators import validate_graph
from probative.elicit.build import Outcome, outcome
from probative.elicit.gain import measure, should_stop
from probative.elicit.seal import SEAL_DIR, SealError, seal
from probative.elicit.types import AnswerKind, Basis, GainReport
from probative.formulas.validator import FormulaValidator
from tests.elicit._helpers import NOW, OWNER, claims, t1_graph, turn


def do_seal(root: Path, turns, props=None, abouts=None):  # type: ignore[no-untyped-def]
    return seal(
        "s1",
        turns,
        propositions=props or {},
        abouts=abouts or {},
        source_root=root,
        owner=OWNER,
        now=NOW,
    )


def test_outcomes_follow_the_basis_not_a_weight() -> None:
    assert outcome(turn(0, text="four clients", basis=Basis.OBSERVED, count=4)) is Outcome.CLAIM
    assert outcome(turn(0, text="support said so", basis=Basis.TOLD)) is Outcome.CLAIM
    assert (
        outcome(turn(0, text="it is in the spec", basis=Basis.DOCUMENT))
        is Outcome.DOCUMENT_QUESTION
    )
    assert outcome(turn(0, text="seems likely", basis=Basis.BELIEF)) is Outcome.BELIEF_QUESTION
    assert outcome(turn(0, text="seems likely", basis=None)) is Outcome.BELIEF_QUESTION
    assert outcome(turn(0, AnswerKind.UNKNOWN, basis=None)) is Outcome.UNKNOWN_QUESTION
    assert outcome(turn(0, AnswerKind.DENY, basis=None)) is Outcome.DENIED_QUESTION
    resolve = turn(0, AnswerKind.UNKNOWN, basis=None, template="resolve_open_question")
    assert outcome(resolve) is Outcome.NOTHING  # an open Question stays open


def test_an_observed_answer_becomes_a_t3_claim_with_a_span_that_re_extracts(tmp_path: Path) -> None:
    sealed = do_seal(tmp_path, [turn(0, text="Finance leads at four clients", count=4)])
    claim = next(n for n in sealed.nodes if isinstance(n, Claim))
    assert claim.tier is Tier.T3
    assert claim.text == "Finance leads at four clients"
    assert claim.confidence.value is None  # I4: the Committer computes it
    graph = Graph.empty().with_patch(sealed.nodes, sealed.edges)
    graph = FormulaValidator().settle(graph)
    assert validate_graph(graph, source_root=tmp_path) == []  # I1 round trip, tier match
    assert next(c for c in claims(graph)).confidence.value == pytest.approx(0.30)  # one source


def test_a_span_never_contains_question_text(tmp_path: Path) -> None:
    q = "Do you agree that the screen is slow?"
    sealed = do_seal(tmp_path, [turn(0, text="Finance leads at four clients", question=q)])
    for node in sealed.nodes:
        if isinstance(node, EvidenceSpan):
            assert "agree" not in node.text and q not in node.text


def test_the_transcript_is_in_a_dot_directory_so_the_ledger_skips_it(tmp_path: Path) -> None:
    sealed = do_seal(tmp_path, [turn(0, text="Finance leads at four clients")])
    assert sealed.files[0].parent.name == SEAL_DIR
    source = next(n for n in sealed.nodes if isinstance(n, SourceNode))
    assert source.path.startswith(f"{SEAL_DIR}/") and source.tier is Tier.T3


def test_sealing_the_same_turns_twice_is_identical_and_a_changed_file_is_refused(
    tmp_path: Path,
) -> None:
    turns = [turn(0, text="Finance leads at four clients")]
    one, two = do_seal(tmp_path, turns), do_seal(tmp_path, turns)
    assert [n.id for n in one.nodes] == [n.id for n in two.nodes]
    sealed_file = one.files[0]
    sealed_file.write_text(sealed_file.read_text() + "edited\n", encoding="utf-8")
    with pytest.raises(SealError):
        do_seal(tmp_path, turns)


def test_each_evidence_kind_is_its_own_source(tmp_path: Path) -> None:
    from probative.core.evidence import EvidenceKind

    sealed = do_seal(
        tmp_path,
        [
            turn(0, text="Four clients", evidence_kind=EvidenceKind.CUSTOMER),
            turn(1, text="Weekly", evidence_kind=EvidenceKind.OPERATIONAL),
        ],
    )
    sources = [n for n in sealed.nodes if isinstance(n, SourceNode)]
    assert {s.kind for s in sources} == {EvidenceKind.CUSTOMER, EvidenceKind.OPERATIONAL}
    assert len(sealed.files) == 2


def test_unknown_and_belief_make_questions_and_no_claim(tmp_path: Path) -> None:
    sealed = do_seal(
        tmp_path,
        [
            turn(0, AnswerKind.UNKNOWN, basis=None, question="How often?"),
            turn(1, text="seems likely", basis=Basis.BELIEF),
        ],
    )
    assert not any(isinstance(n, Claim) for n in sealed.nodes)
    qs = [n for n in sealed.nodes if isinstance(n, Question)]
    assert len(qs) == 2 and all(q.raised_by == "elicitation" for q in qs)
    assert not sealed.files  # a transcript with no claim has nothing to anchor


def test_confirm_uses_the_proposition_and_deny_raises_a_question_about_it(tmp_path: Path) -> None:
    graph = t1_graph(tmp_path / "src", "Approvals take three days")
    source_claim = claims(graph)[0]
    sealed = do_seal(
        tmp_path / "src",
        [
            turn(
                0,
                AnswerKind.CONFIRM,
                basis=Basis.OBSERVED,
                template="confirm_source_claim",
                subject=source_claim.id,
            ),
            turn(
                1,
                AnswerKind.DENY,
                basis=None,
                template="confirm_source_claim",
                subject=source_claim.id,
            ),
        ],
        props={0: source_claim.text, 1: source_claim.text},
        abouts={1: source_claim.id},
    )
    t3 = next(n for n in sealed.nodes if isinstance(n, Claim))
    assert t3.text == source_claim.text and t3.tier is Tier.T3 and t3.id != source_claim.id  # OI40
    denied = next(n for n in sealed.nodes if isinstance(n, Question))
    assert any(e.type is EdgeType.RAISED_ABOUT and e.dst == source_claim.id for e in sealed.edges)
    assert source_claim.text in denied.text


def test_gain_counts_what_an_answer_changed(tmp_path: Path) -> None:
    base = t1_graph(tmp_path / "src", "Approvals take three days")
    sealed = do_seal(tmp_path / "src", [turn(0, text="Finance leads at four clients")])
    after = FormulaValidator().settle(base.with_patch(sealed.nodes, sealed.edges))
    report = measure(base, after)
    assert report.new_claims == 1 and not report.wasted
    again = measure(after, after)
    assert again.wasted and again.new_claims == 0


def test_an_unknown_is_not_gain(tmp_path: Path) -> None:
    base = Graph.empty()
    sealed = do_seal(tmp_path, [turn(0, AnswerKind.UNKNOWN, basis=None)])
    after = base.with_patch(sealed.nodes, sealed.edges)
    report = measure(base, after)
    assert report.questions_opened == 1 and report.wasted  # PB14 mutation: unknown counted as gain


def test_stopping_needs_consecutive_quiet_rounds() -> None:
    quiet = GainReport(
        new_claims=0, confidence_delta=0, questions_closed=0, contradictions=0, questions_opened=0
    )
    busy = GainReport(
        new_claims=1, confidence_delta=0, questions_closed=0, contradictions=0, questions_opened=0
    )
    assert not should_stop([[busy], [quiet]], 2)
    assert should_stop([[busy], [quiet], [quiet, quiet]], 2)
    assert not should_stop([[quiet], [busy, quiet], [quiet]], 2)
    assert should_stop([[quiet], [quiet]], 2)
