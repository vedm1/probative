"""`measure` counts what a critic did on a corpus split — proven here with a
scripted provider that plays an oracle, so no key is needed."""

from __future__ import annotations

import re
from typing import Any

from probative.critics.llm_judge import CheckJudgement, Verdict
from probative.critics.space_warden import SpaceWarden
from probative.llm import Message, StructuredResult, TokenUsage
from tests.critics._corpus import SPACE_WARDEN
from tests.critics._measure import measure, measure_mixed, measure_stress


class _Oracle:
    """Flags every candidate whose text contains a feature-ish noun, quoting it."""

    def complete_structured(
        self, messages: list[Message], *, output_model: type[Any], model: str
    ) -> StructuredResult[Any]:
        judgements = []
        for cid, text in re.findall(
            r'<candidate id="([^"]+)">(.*?)</candidate>', messages[-1].content
        ):
            hit = re.search(r"\b(button|dashboard|wishlist|portal)\b", text)
            judgements.append(
                CheckJudgement(
                    candidate_id=cid,
                    check_id="solution_grammar",
                    verdict=Verdict.NOT_MET if hit else Verdict.MET,
                    quote=hit.group(0) if hit else None,
                )
            )
        return StructuredResult(
            output=output_model(judgements=judgements),
            usage=TokenUsage(input_tokens=5, output_tokens=2),
            raw_model=model,
        )


def test_measure_counts_catches_false_positives_and_usage() -> None:
    critic = SpaceWarden.from_builtin_rubric(_Oracle(), model="m")
    result = measure(SPACE_WARDEN, "dev", critic)

    assert result["critic"] == "space_warden" and result["split"] == "dev"
    seeded = result["seeded"]
    assert seeded["n"] == 12
    # The dev defects naming a wishlist / button / dashboard-like noun are caught; the rest are not.
    assert 0 < seeded["caught"] < 12
    assert seeded["caught"] == seeded["caught_intended"]  # one check, so the two readings agree
    assert seeded["per_check"]["solution_grammar"]["n"] == 12
    assert result["clean"]["candidates"] == 10
    assert result["clean"]["flagged_candidates"] == 0
    assert result["judge_stats"]["calls"] == 14  # one call per fixture file: 12 defect + 2 clean
    assert result["judge_stats"]["duplicates"] == 0
    assert result["judge_stats"]["usage"] == {"input_tokens": 70, "output_tokens": 28}


def test_measure_stress_compares_the_fired_set_to_the_expected_one() -> None:
    critic = SpaceWarden.from_builtin_rubric(_Oracle(), model="m")
    result = measure_stress(SPACE_WARDEN, critic)
    assert result["n"] == 10
    rows = {r["file"]: r for r in result["files"]}
    # The oracle only knows button/dashboard/wishlist/portal, so it fires on no stress case:
    # right where nothing should fire, wrong where something should.
    assert rows["negated_app.json"]["as_expected"] is True
    assert rows["sso_named.json"]["as_expected"] is False
    assert rows["sso_named.json"]["expect_fired"] == ["solution_grammar"]
    assert rows["sso_named.json"]["fired"] == []
    assert result["as_expected"] == 6  # the six cases that expect silence


def test_measure_mixed_judges_every_split_together_in_the_critics_batch_size() -> None:
    critic = SpaceWarden.from_builtin_rubric(_Oracle(), model="m")
    result = measure_mixed(SPACE_WARDEN, critic)
    assert result["candidates"] == 24 + 20  # 24 defects, 20 clean, across both splits
    assert result["seeded"]["n"] == 24 and result["clean"]["candidates"] == 20
    assert 0 < result["seeded"]["caught"] < 24
    assert result["clean"]["flagged_candidates"] == 0
    # 44 candidates at the default batch size of 5 -> 9 calls
    assert result["judge_stats"]["calls"] == 9


def test_a_tolerated_check_firing_is_still_as_expected_but_an_unlisted_one_is_not() -> None:
    from tests.critics._corpus import INVEST

    class _Fires:
        def __init__(self, check: str) -> None:
            self.check = check

        def complete_structured(
            self, messages: list[Message], *, output_model: type[Any], model: str
        ) -> StructuredResult[Any]:
            from probative.critics.invest import invest_rubric

            ids = re.findall(r'<candidate id="([^"]+)">', messages[-1].content)
            judgements = [
                CheckJudgement(
                    candidate_id=cid,
                    check_id=c.id,
                    verdict=Verdict.NOT_MET if c.id == self.check else Verdict.MET,
                    quote=None,
                )
                for cid in ids
                for c in invest_rubric().checks
            ]
            return StructuredResult(
                output=output_model(judgements=judgements),
                usage=TokenUsage(input_tokens=1, output_tokens=1),
                raw_model=model,
            )

    from probative.critics.invest import INVESTCritic

    def row(check: str) -> dict[str, Any]:
        critic = INVESTCritic.from_builtin_rubric(_Fires(check), model="m")
        rows = {r["file"]: r for r in measure_stress(INVEST, critic)["files"]}
        return rows["oauth_users_world.json"]

    assert row("negotiable")["allow_also"] == ["negotiable"]
    assert row("negotiable")["as_expected"] is True  # tolerated
    assert row("small")["as_expected"] is False  # not listed
