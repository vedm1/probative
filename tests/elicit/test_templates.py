"""PB14 types and template data. Key-free."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from probative.elicit.templates import (
    TemplateError,
    families_for,
    fill,
    load_templates,
    load_topics,
    slots,
    topic_question,
)
from probative.elicit.types import (
    AnswerKind,
    Basis,
    Family,
    GainReport,
    RawAnswer,
)


def test_every_template_offers_unknown_and_a_way_to_disagree() -> None:
    # PB14 test 11: template hygiene
    for template in load_templates().values():
        kinds = {o.kind for o in template.options}
        assert AnswerKind.UNKNOWN in kinds, template.id
        if template.kind in ("confirm", "challenge"):
            assert AnswerKind.DENY in kinds, template.id
            assert AnswerKind.AMEND in kinds, template.id


def test_onboarding_templates_are_reconstruct_only_and_state_no_judgement() -> None:
    # I9: onboarding asks what appears decided and what it rests on, never whether it was right
    for template in load_templates().values():
        if "onboarding" in template.modes:
            assert template.family is Family.RECONSTRUCT
            lowered = template.text.casefold()
            for word in ("mistake", "wrong", "should have", "fault", "blame", "right decision"):
                assert word not in lowered
        else:
            assert template.family is Family.DISCOVER
    assert families_for("onboarding") == {Family.RECONSTRUCT}
    assert families_for("solo") == {Family.DISCOVER}


def test_topics_load_and_are_asked_as_written() -> None:
    topics = load_topics()
    assert {"who_is_affected", "recorded_decision"} <= set(topics)
    asked = topic_question(topics["frequency"], index=3)
    assert asked.text == topics["frequency"].question
    assert {o.kind for o in asked.options} == {AnswerKind.OPEN, AnswerKind.UNKNOWN}


def test_fill_requires_exactly_the_templates_slots() -> None:
    template = load_templates()["confirm_source_claim"]
    asked = fill(template, index=0, subject_ref="claim_x", claim="Approvals take 3 days")
    assert "Approvals take 3 days" in asked.text
    assert slots(template.text) == {"claim"}
    with pytest.raises(TemplateError):
        fill(template, index=0, subject_ref="claim_x")
    with pytest.raises(TemplateError):
        fill(template, index=0, subject_ref="claim_x", claim="a", extra="b")


def test_a_slot_value_with_braces_is_kept_verbatim() -> None:
    template = load_templates()["confirm_source_claim"]
    asked = fill(template, index=0, subject_ref="c", claim="uses {curly} words")
    assert "{curly}" in asked.text


def test_raw_answer_rules() -> None:
    with pytest.raises(ValidationError):
        RawAnswer(kind=AnswerKind.OPEN, text="  ")
    with pytest.raises(ValidationError):
        RawAnswer(kind=AnswerKind.UNKNOWN, basis=Basis.OBSERVED)
    with pytest.raises(ValidationError):
        RawAnswer(kind=AnswerKind.OPEN, text="x", basis=Basis.TOLD, basis_count=2)
    with pytest.raises(ValidationError):
        RawAnswer(kind=AnswerKind.OPEN, text="x" * 401, basis=Basis.TOLD)
    ok = RawAnswer(
        kind=AnswerKind.OPEN, text="seen at four clients", basis=Basis.OBSERVED, basis_count=4
    )
    assert ok.basis_count == 4


def test_gain_report_wasted_ignores_an_opened_question() -> None:
    nothing = GainReport(
        new_claims=0, confidence_delta=0, questions_closed=0, contradictions=0, questions_opened=1
    )
    assert nothing.wasted
    assert not GainReport(
        new_claims=1, confidence_delta=0, questions_closed=0, contradictions=0, questions_opened=0
    ).wasted


def test_no_output_model_field_is_numeric_for_a_model_to_fill() -> None:
    # I4: the types a model could be asked to fill carry no number. RawAnswer.basis_count is a
    # respondent's count of what they saw, never a score; PairJudgement-like models are elsewhere.
    for name, field in RawAnswer.model_fields.items():
        if name != "basis_count":
            assert field.annotation not in (float, int, float | None, int | None), name
