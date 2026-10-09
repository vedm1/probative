"""RedTeam (PB8 checkpoint B): wiring, severity policy and scope against a
scripted provider. What the model does with the corpus is measured by the
recorded replay (test_pb8_replay.py), not here."""

from __future__ import annotations

import pytest

from probative.core.critic import Severity
from probative.critics import aggregate, run_critics
from probative.critics.llm_judge import (
    _JUDGE_PREAMBLE,
    CheckJudgement,
    JudgementBatch,
    Verdict,
    build_system_prompt,
)
from probative.critics.red_team import RedTeam, red_team_rubric
from probative.llm import FakeProvider
from tests.critics._candidates import claims, forecasts, needs
from tests.critics._corpus import RED_TEAM

CLAIM = "Tickets about card entry doubled in June, so the new form is clearly failing."
FORECAST = "Once lockers are live, failed deliveries will drop by a third."
CHECKS = (
    "rival_explanation",
    "unstated_denominator",
    "definition_drift",
    "unstated_precondition",
    "no_adaptive_response",
    "unfalsifiable_outcome",
)


def _batch(candidate_id: str, quote: str, **verdicts: Verdict) -> JudgementBatch:
    return JudgementBatch(
        judgements=[
            CheckJudgement(
                candidate_id=candidate_id,
                check_id=check,
                verdict=verdicts.get(check, Verdict.MET),
                quote=quote if verdicts.get(check) == Verdict.NOT_MET else None,
            )
            for check in CHECKS
        ]
    )


def test_rubric_is_a_warn_only_taxonomy_with_no_invariant() -> None:
    rubric = red_team_rubric()
    assert (rubric.id, rubric.severity, rubric.invariant) == ("red_team", Severity.WARN, None)
    assert rubric.applies_to == ["ClaimCandidate", "ForecastCandidate"]
    assert [c.id for c in rubric.checks] == list(CHECKS)
    assert all((c.severity or rubric.severity) is Severity.WARN for c in rubric.checks)
    assert RED_TEAM.rubric_path.is_file()


def test_every_check_has_examples_both_ways_a_remedy_and_a_must_be_true_template() -> None:
    for check in red_team_rubric().checks:
        assert check.examples_bad and check.examples_good and check.remedy, check.id
        assert check.must_be_true and "{quote}" in check.must_be_true, check.id


def test_every_check_states_when_it_applies_and_that_otherwise_it_is_met() -> None:
    for check in red_team_rubric().checks:
        lowered = " ".join(check.description.lower().split())
        assert "applies only" in lowered and "otherwise" in lowered, check.id


_ONE_PER_CHECK = {
    "rival_explanation": ("claim", "Tickets rose in June, so the form is failing.", "rose in June"),
    "unstated_denominator": ("claim", "We logged 900 disputes, a heavy load.", "900 disputes"),
    "definition_drift": ("claim", "Active users grew from 4,000 to 5,000.", "Active users"),
    "unstated_precondition": ("forecast", "Partners will adopt it, halving intake.", "will adopt"),
    "no_adaptive_response": ("forecast", "A price cut will win their shoppers.", "win their"),
    "unfalsifiable_outcome": ("forecast", "The tool will improve how people feel.", "improve how"),
}


@pytest.mark.parametrize("check", CHECKS)
def test_a_flagged_statement_names_its_mode_and_its_own_must_be_true_text(check: str) -> None:
    kind, text, quote = _ONE_PER_CHECK[check]
    (candidate,) = (claims if kind == "claim" else forecasts)(text, [text])
    provider = FakeProvider([_batch(candidate.id, quote, **{check: Verdict.NOT_MET})])
    (finding,) = RedTeam.from_builtin_rubric(provider, model="m").check([candidate])
    assert (finding.critic_id, finding.check_id, finding.invariant, finding.severity) == (
        "red_team",
        check,
        None,
        Severity.WARN,
    )
    assert finding.evidence is not None and finding.evidence.text == quote
    headline, _, tail = finding.message.partition(" Would have to be true: ")
    assert headline.startswith(f"{check}: “{quote}” — ")
    expected = next(c for c in red_team_rubric().checks if c.id == check).must_be_true
    assert expected is not None and tail == expected.replace("{quote}", quote)
    assert finding.remedy


def test_the_must_be_true_text_is_substituted_literally_not_formatted() -> None:
    """Braces in a quote are not format syntax, and a literal `{quote}` in a quote is
    not substituted again."""
    text = "Tickets {0} doubled, so the form {x.y} is failing, said {quote}."
    (claim,) = claims(text, [text])
    quote = "{0} doubled, so the form {x.y}"
    provider = FakeProvider([_batch(claim.id, quote, rival_explanation=Verdict.NOT_MET)])
    (finding,) = RedTeam.from_builtin_rubric(provider, model="m").check([claim])
    _, _, tail = finding.message.partition(" Would have to be true: ")
    assert quote in tail and "{quote}" not in tail
    assert tail.count("{0}") == 1


def test_a_quote_that_does_not_resolve_falls_back_to_the_whole_statement_in_the_template() -> None:
    (claim,) = claims(CLAIM, [CLAIM])
    provider = FakeProvider(
        [_batch(claim.id, "not in the text", rival_explanation=Verdict.NOT_MET)]
    )
    (finding,) = RedTeam.from_builtin_rubric(provider, model="m").check([claim])
    assert finding.evidence is not None and finding.evidence.text == CLAIM
    assert CLAIM in finding.message.split("Would have to be true: ")[1]  # never the model's quote


def test_it_judges_claims_and_forecasts_and_nothing_else() -> None:
    (claim,) = claims(CLAIM, [CLAIM])
    (forecast,) = forecasts(FORECAST, [FORECAST])
    provider = FakeProvider(
        [
            _batch(claim.id, "doubled", rival_explanation=Verdict.NOT_MET),
            _batch(forecast.id, "will drop by a third", unstated_precondition=Verdict.NOT_MET),
        ]
    )
    critic = RedTeam.from_builtin_rubric(provider, model="m", batch_size=1)
    findings = critic.check([claim, forecast])
    assert [(f.check_id, f.target_id) for f in findings] == [
        ("rival_explanation", claim.id),
        ("unstated_precondition", forecast.id),
    ]
    (need,) = needs("Users need a dashboard.", ["Users need a dashboard."])
    idle = RedTeam.from_builtin_rubric(FakeProvider([]), model="m")
    assert run_critics([idle], [need]) == []  # filtered by applies_to: no call made
    with pytest.raises(TypeError, match=r"ClaimCandidate or ForecastCandidate"):
        idle.check([need])


def test_run_critics_routes_both_candidate_kinds_to_it() -> None:
    (claim,) = claims(CLAIM, [CLAIM])
    (forecast,) = forecasts(FORECAST, [FORECAST])
    provider = FakeProvider([_batch(claim.id, "x"), _batch(forecast.id, "x")])
    critic = RedTeam.from_builtin_rubric(provider, model="m", batch_size=1)
    assert run_critics([critic], [claim, forecast]) == []
    assert critic.stats.calls == 2


def test_a_warn_lowers_the_dimension_score_but_never_blocks() -> None:
    (claim,) = claims(CLAIM, [CLAIM])
    provider = FakeProvider([_batch(claim.id, "doubled", rival_explanation=Verdict.NOT_MET)])
    findings = RedTeam.from_builtin_rubric(provider, model="m").check([claim])
    (dimension,) = aggregate([red_team_rubric()], findings)
    assert not dimension.blocked and dimension.score == 8.0


def test_it_defaults_to_the_pb5_batch_size() -> None:
    assert RedTeam.from_builtin_rubric(FakeProvider([]), model="m")._batch_size == 5


def _prompt() -> str:
    return build_system_prompt(red_team_rubric(), RedTeam.preamble, RedTeam.judge_preamble)


def test_the_prompt_is_closed_world_and_never_shows_the_must_be_true_text() -> None:
    prompt = _prompt()
    assert RedTeam.judge_preamble != _JUDGE_PREAMBLE
    assert "Missing information is cannot_tell" not in prompt
    lowered = prompt.lower()
    assert "your own knowledge" in lowered and "never instructions" in lowered
    for needle in ("not_met", "cannot_tell", "verbatim", "Do not return scores"):
        assert needle in prompt
    for check in red_team_rubric().checks:
        assert f"[{check.id}]" in prompt
        assert check.must_be_true and check.must_be_true not in prompt  # the model never writes it
        assert all(example in prompt for example in (*check.examples_bad, *check.examples_good))


def test_the_model_is_never_asked_to_write_an_alternative_explanation() -> None:
    assert "Do not write any alternative explanation" in _prompt()
    assert "You do not write an alternative explanation" in _prompt()


def test_the_prompt_names_no_particular_attack_and_makes_no_false_structural_claim() -> None:
    """Pre-recording review B1/B7: an injection fixture must test the generic rule, not a
    sentence written for it, and the prompt must not describe the rubric wrongly."""
    prompt = _prompt()
    lowered = prompt.lower()
    for named in ("reviewer", "status", "validated", "cleared"):
        assert named not in lowered, named
    assert "begins" not in lowered
    assert "never instructions" in lowered


def test_a_belief_marker_alone_is_not_a_hypothesis_marker() -> None:
    """Pre-recording review B2: rubric and preamble must agree."""
    check = next(c for c in red_team_rubric().checks if c.id == "unstated_precondition")
    text = " ".join(check.description.split())
    assert "is not a statement that it is to be tested" in text
    assert "does not by itself state a condition" in RedTeam.preamble
