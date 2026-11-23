"""PB14: deterministic question selection. Key-free, no model."""

from __future__ import annotations

from pathlib import Path

from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Question
from probative.elicit.select import select
from tests.elicit._helpers import NOW, OWNER, claims, t1_graph


def with_question(graph: Graph, text: str, raised_by: str) -> tuple[Graph, str]:
    q = Question.make(text=text, raised_by=raised_by, owner=OWNER, asserted_at=NOW)
    return graph.with_patch(nodes=[q]), q.id


def test_topics_come_before_source_claims_and_each_is_planned_once(tmp_path: Path) -> None:
    graph = t1_graph(tmp_path, "Approvals take three days")
    plans = select(graph, mode="solo", asked=set())
    refs = [p.template_id for p in plans]
    assert refs[:4] == [
        f"topic:{t}"
        for t in ("who_is_affected", "current_workaround", "frequency", "known_constraint")
    ]
    assert refs[4] == "confirm_source_claim"
    again = select(graph, mode="solo", asked={"who_is_affected"})
    assert "topic:who_is_affected" not in [p.template_id for p in again]


def test_an_open_elicitation_question_is_asked_before_a_topic(tmp_path: Path) -> None:
    graph, qid = with_question(
        t1_graph(tmp_path, "Approvals take three days"), "How often?", "elicitation"
    )
    first = select(graph, mode="solo", asked=set())[0]
    assert first.template_id == "resolve_open_question" and first.subject_ref == qid


def test_a_gap_question_is_never_asked(tmp_path: Path) -> None:
    # OI42: a free-text answer would not classify a source
    graph, qid = with_question(
        t1_graph(tmp_path, "Approvals take three days"), "Which tier is it?", "gap"
    )
    assert qid not in [p.subject_ref for p in select(graph, mode="solo", asked=set())]


def test_a_source_claim_already_held_at_t3_is_not_proposed_again(tmp_path: Path) -> None:
    from probative.core.evidence import Tier
    from probative.core.graph.nodes import Claim
    from probative.ledger.build import new_claim

    graph = t1_graph(tmp_path, "Approvals take three days")
    t3 = new_claim(
        "Approvals take three days", Tier.T3, claims(graph)[0].evidence_kind, owner=OWNER, now=NOW
    )
    held = graph.with_patch(nodes=[t3])
    assert isinstance(t3, Claim)
    assert "confirm_source_claim" not in [
        p.template_id for p in select(held, mode="solo", asked=set())
    ]


def test_onboarding_plans_reconstruct_templates_only(tmp_path: Path) -> None:
    graph, _ = with_question(
        t1_graph(tmp_path, "Approvals take three days"), "How often?", "elicitation"
    )
    plans = select(graph, mode="onboarding", asked=set())
    assert [p.template_id for p in plans] == [
        "topic:recorded_decision",
        "reconstruct_recorded_item",
    ]


def test_a_topic_label_limits_which_source_claims_are_proposed(tmp_path: Path) -> None:
    graph = t1_graph(tmp_path, "Approvals take three days", "Refunds are handled by hand")
    plans = select(graph, mode="solo", asked=set(), topic="refunds")
    slots = [p.slots.get("claim") for p in plans if p.template_id == "confirm_source_claim"]
    assert slots == ["Refunds are handled by hand"]
