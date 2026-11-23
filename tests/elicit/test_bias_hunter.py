"""PB14 test 9: `BiasHunter`. Deterministic checks are measured exactly; judged checks are
exercised here for plumbing only, with a scripted provider (OI50: their real behaviour is
unmeasured until someone records it with a key). Key-free."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from probative.core.critic import Severity
from probative.critics.llm_judge import Verdict
from probative.elicit.bias_hunter import (
    DETERMINISTIC,
    JUDGED,
    RUBRIC_PATH,
    BiasHunter,
    BiasHunterError,
    CheckVerdict,
    ExchangeCandidate,
    ExchangeVerdicts,
)
from probative.elicit.types import AnswerKind, AskedQuestion, Option
from probative.llm import FakeProvider
from tests.elicit._helpers import turn

FIX = RUBRIC_PATH.parent / "fixtures"
LABEL = {
    "confirm": "Yes",
    "deny": "No",
    "amend": "Partly",
    "unknown": "I do not know",
    "open": "I will say",
}


def load(path: Path) -> list[dict]:  # type: ignore[type-arg]
    return json.loads(path.read_text())


def candidate(item: dict) -> ExchangeCandidate:  # type: ignore[type-arg]
    return ExchangeCandidate(
        id=item["id"],
        question=AskedQuestion(
            index=0,
            template_id="t",
            subject_ref="s",
            text=item["text"],
            options=tuple(Option(label=LABEL[k], kind=AnswerKind(k)) for k in item["options"]),
            evidence_kind=None,
        ),
    )


def verdicts(**not_met: bool) -> ExchangeVerdicts:
    return ExchangeVerdicts(
        judgements=[
            CheckVerdict(check_id=c, verdict=Verdict.NOT_MET if not_met.get(c) else Verdict.MET)
            for c in JUDGED
        ]
    )


def seeded(kind: str) -> list[dict]:  # type: ignore[type-arg]
    return [
        i for f in sorted((FIX / "seeded").glob("*.json")) for i in load(f) if kind in i["expect"]
    ]


def test_the_rubric_loads_with_seven_checks_and_the_right_severities() -> None:
    rubric = BiasHunter().rubric
    sev = {c.id: c.severity for c in rubric.checks}
    assert set(sev) == {*DETERMINISTIC, "agreement_skew", *JUDGED}
    assert sev["leading_question"] is Severity.BLOCK and sev["presupposition"] is Severity.BLOCK
    assert (
        sev["no_unknown_option"] is Severity.BLOCK and sev["unbalanced_options"] is Severity.BLOCK
    )
    assert sev["anchoring"] is Severity.WARN and sev["loaded_term"] is Severity.WARN


@pytest.mark.parametrize("check", DETERMINISTIC)
def test_every_seeded_deterministic_defect_is_caught(check: str) -> None:
    items = seeded(check)
    assert len(items) >= 3
    hunter = BiasHunter()
    caught = [
        i["id"] for i in items if check in {f.check_id for f in hunter.check_options(candidate(i))}
    ]
    assert caught == [i["id"] for i in items]  # measured exactly: all of them


def test_nothing_is_raised_on_the_clean_set_by_the_deterministic_checks() -> None:
    clean = load(FIX / "clean" / "clean.json")
    assert len(clean) >= 20
    hunter = BiasHunter()
    assert [f for i in clean for f in hunter.check_options(candidate(i))] == []


def test_the_shipped_templates_pass_the_deterministic_checks() -> None:
    from probative.elicit.templates import load_templates

    hunter = BiasHunter()
    for t in load_templates().values():
        q = AskedQuestion(
            index=0,
            template_id=t.id,
            subject_ref="s",
            text=t.text,
            options=t.options,
            evidence_kind=None,
        )
        assert hunter.check_options(ExchangeCandidate(id=t.id, question=q)) == [], t.id


def test_the_judge_turns_a_not_met_verdict_into_a_finding_with_rubric_words() -> None:
    hunter = BiasHunter(FakeProvider([verdicts(leading_question=True)]), "m")
    found = hunter.check([candidate(load(FIX / "seeded" / "leading_question.json")[0])])
    assert [f.check_id for f in found] == ["leading_question"]
    assert found[0].severity is Severity.BLOCK and BiasHunter.blocked(found)
    assert "steer" in found[0].message  # the rubric's sentence, not the model's


def test_a_question_already_blocked_by_its_options_is_not_judged() -> None:
    hunter = BiasHunter(FakeProvider([]), "m")  # an unexpected judge call would raise
    found = hunter.check([candidate(seeded("no_unknown_option")[0])])
    assert [f.check_id for f in found] == ["no_unknown_option"]


@pytest.mark.parametrize(
    "bad",
    [
        ExchangeVerdicts(judgements=[]),
        ExchangeVerdicts(judgements=[CheckVerdict(check_id="made_up", verdict=Verdict.MET)]),
    ],
)
def test_an_unusable_judge_reply_raises_and_never_passes_a_question(bad: ExchangeVerdicts) -> None:
    hunter = BiasHunter(FakeProvider([bad]), "m")
    with pytest.raises(BiasHunterError):
        hunter.check([candidate(load(FIX / "clean" / "clean.json")[8])])


def test_without_a_provider_a_judged_check_cannot_run() -> None:
    with pytest.raises(BiasHunterError):
        BiasHunter().check([candidate(load(FIX / "clean" / "clean.json")[8])])


def test_agreement_skew_needs_five_proposals_all_confirmed() -> None:
    def proposals(kinds: list[AnswerKind]):  # type: ignore[no-untyped-def]
        return [
            turn(i, k, basis=None, template="confirm_source_claim", subject=f"c{i}")
            for i, k in enumerate(kinds)
        ]

    hunter = BiasHunter()
    assert [f.check_id for f in hunter.check_session(proposals([AnswerKind.CONFIRM] * 5))] == [
        "agreement_skew"
    ]
    assert hunter.check_session(proposals([AnswerKind.CONFIRM] * 4)) == []
    assert hunter.check_session(proposals([AnswerKind.CONFIRM] * 4 + [AnswerKind.DENY])) == []


def test_there_are_at_least_four_judged_seeds_per_judged_check() -> None:
    for check in JUDGED:
        assert len(seeded(check)) >= 4, check
