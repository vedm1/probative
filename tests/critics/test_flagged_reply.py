"""`LLMCritic(reply="flagged")` (PB9, lever B): the model returns only the pairs that
are not met, plus how many candidates it reviewed. Same findings as the full reply;
completeness is guarded by the reviewed count instead of a verdict per pair."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from probative.core.candidates import CandidateKind as K
from probative.core.candidates import ClaimCandidate, candidate_id
from probative.core.critic import Severity
from probative.critics.evidence_auditor import EvidenceAuditor
from probative.critics.llm_judge import (
    CheckJudgement,
    CriticJudgementError,
    FlaggedBatch,
    FlaggedItem,
    JudgementBatch,
    LLMCritic,
    Verdict,
    build_system_prompt,
    build_user_message,
)
from probative.llm import FakeProvider
from tests.critique._builders import make_source, span_of

TEXT = (
    "# Claims\n\n"
    "Conversion drops 12% at the payment step.\n"
    "Competitors convert far better than we do.\n"
    "The checkout page loads in two seconds.\n"
)
SOURCE = make_source(TEXT)


def _claim(phrase: str) -> ClaimCandidate:
    span = span_of(SOURCE, phrase)
    return ClaimCandidate(id=candidate_id(K.CLAIM, span), evidence=span)


A = _claim("Conversion drops 12% at the payment step.")
B = _claim("Competitors convert far better than we do.")
C = _claim("The checkout page loads in two seconds.")
CHECKS = ["unsourced_statistic", "basis_overreach", "unsourced_assertion"]


def _critic(outputs, reply="flagged", **kw):  # type: ignore[no-untyped-def]
    return EvidenceAuditor.from_builtin_rubric(
        FakeProvider(outputs), model="t/m", reply=reply, **kw
    )


def _full(not_met: dict[tuple[str, str], str]) -> JudgementBatch:
    rows = []
    for c in (A, B, C):
        for check in CHECKS:
            quote = not_met.get((c.id, check))
            rows.append(
                CheckJudgement(
                    candidate_id=c.id,
                    check_id=check,
                    verdict=Verdict.NOT_MET if quote else Verdict.MET,
                    quote=quote,
                )
            )
    return JudgementBatch(judgements=rows)


def _flagged(not_met: dict[tuple[str, str], str], reviewed: int = 3) -> FlaggedBatch:
    return FlaggedBatch(
        flagged=[
            FlaggedItem(candidate_id=cid, check_id=check, verdict=Verdict.NOT_MET, quote=quote)
            for (cid, check), quote in not_met.items()
        ],
        reviewed=reviewed,
    )


FLAGS = {(A.id, "unsourced_statistic"): "12%", (B.id, "unsourced_assertion"): "far better"}


def test_default_reply_is_full() -> None:
    critic = EvidenceAuditor.from_builtin_rubric(FakeProvider([]), model="t/m")
    assert critic.reply == "full"


def test_unknown_reply_is_rejected() -> None:
    with pytest.raises(ValueError, match="reply"):
        _critic([], reply="terse")


def test_flagged_reply_gives_the_same_findings_as_the_full_reply() -> None:
    full = _critic([_full(FLAGS)], reply="full").check([A, B, C])
    flagged = _critic([_flagged(FLAGS)]).check([A, B, C])
    assert [f.model_dump() for f in flagged] == [f.model_dump() for f in full]
    assert len(flagged) == 2 and all(f.evidence is not None for f in flagged)


def test_nothing_flagged_is_all_met_when_the_count_matches() -> None:
    critic = _critic([_flagged({})])
    assert critic.check([A, B, C]) == []
    assert critic.stats.met == 9 and critic.stats.implied_met == 9


def test_a_wrong_reviewed_count_is_asked_again_and_accepted_once_it_matches() -> None:
    critic = _critic([_flagged({}, reviewed=2), _flagged(FLAGS, reviewed=3)])
    findings = critic.check([A, B, C])
    assert len(findings) == 2 and critic.stats.recounted == 1


def test_flags_in_a_miscounted_reply_are_kept_not_dropped() -> None:
    first = _flagged({(A.id, "unsourced_statistic"): "12%"}, reviewed=1)
    critic = _critic([first, _flagged({}, reviewed=3)])
    assert [f.check_id for f in critic.check([A, B, C])] == ["unsourced_statistic"]


def test_two_wrong_counts_fail_closed() -> None:
    critic = _critic([_flagged({}, reviewed=2), _flagged({}, reviewed=2)])
    with pytest.raises(CriticJudgementError, match="reviewed"):
        critic.check([A, B, C])


def test_cannot_tell_is_counted_and_makes_no_finding() -> None:
    item = FlaggedItem(
        candidate_id=A.id, check_id="unsourced_statistic", verdict=Verdict.CANNOT_TELL
    )
    critic = _critic([FlaggedBatch(flagged=[item], reviewed=3)])
    assert critic.check([A, B, C]) == []
    assert critic.stats.cannot_tell == 1 and critic.stats.met == 8


def _mangled() -> FlaggedBatch:
    return FlaggedBatch(
        flagged=[
            FlaggedItem(
                candidate_id="c1",
                check_id="unsourced_statistic",
                verdict=Verdict.NOT_MET,
                quote="12%",
            ),
        ],
        reviewed=3,
    )


def test_a_flag_under_an_unknown_id_is_a_miscount_not_a_quiet_pass() -> None:
    """In full mode a mangled id leaves the pair missing, which is re-asked and then raises;
    in flagged mode it must not become an implied `met`."""
    critic = _critic([_mangled(), _flagged(FLAGS)])
    findings = critic.check([A, B, C])
    assert len(findings) == 2 and critic.stats.unknown_ids == 1 and critic.stats.recounted == 1


def test_a_second_unknown_id_fails_closed() -> None:
    critic = _critic([_mangled(), _mangled()])
    with pytest.raises(CriticJudgementError, match="unknown"):
        critic.check([A, B, C])


def test_an_unknown_check_id_is_treated_the_same_way() -> None:
    bad = FlaggedBatch(
        flagged=[
            FlaggedItem(
                candidate_id=A.id, check_id="no_such_check", verdict=Verdict.NOT_MET, quote="x"
            )
        ],
        reviewed=3,
    )
    with pytest.raises(CriticJudgementError):
        _critic([bad, bad]).check([A, B, C])


def test_an_unresolvable_quote_falls_back_to_the_candidates_own_span() -> None:
    flags = {(A.id, "unsourced_statistic"): "not in the text"}
    (finding,) = _critic([_flagged(flags)]).check([A, B, C])
    assert finding.evidence == A.evidence


def test_a_duplicate_flag_is_one_finding() -> None:
    twice = FlaggedBatch(
        flagged=[
            FlaggedItem(
                candidate_id=A.id,
                check_id="unsourced_statistic",
                verdict=Verdict.NOT_MET,
                quote="12%",
            ),
            FlaggedItem(
                candidate_id=A.id,
                check_id="unsourced_statistic",
                verdict=Verdict.NOT_MET,
                quote="12%",
            ),
        ],
        reviewed=3,
    )
    critic = _critic([twice])
    assert len(critic.check([A, B, C])) == 1 and critic.stats.duplicates == 1


def test_a_reply_that_omits_the_reviewed_count_is_malformed() -> None:
    with pytest.raises(ValidationError):
        FlaggedBatch.model_validate({"flagged": []})


def test_the_flagged_system_prompt_extends_the_full_one_and_the_user_message_is_unchanged() -> None:
    critic = _critic([_flagged({})])
    full_prompt = build_system_prompt(critic.rubric, critic.preamble, critic.judge_preamble)
    flagged_prompt = critic.system_prompt()
    assert flagged_prompt.startswith(full_prompt)
    assert "do NOT return a judgement for a (candidate, check) pair that is met" in flagged_prompt
    full_critic = _critic([_full({})], reply="full")
    assert full_critic.system_prompt() == full_prompt
    assert build_user_message([A, B]).startswith("<candidates>")


def test_every_llm_critic_accepts_reply() -> None:
    from probative.critics.dependency_critic import DependencyCritic
    from probative.critics.invest import INVESTCritic
    from probative.critics.red_team import RedTeam
    from probative.critics.segment_skeptic import SegmentSkeptic
    from probative.critics.space_warden import SpaceWarden

    for cls in (
        SpaceWarden,
        INVESTCritic,
        EvidenceAuditor,
        SegmentSkeptic,
        DependencyCritic,
        RedTeam,
    ):
        critic = cls.from_builtin_rubric(FakeProvider([]), model="t/m", reply="flagged")
        assert isinstance(critic, LLMCritic) and critic.reply == "flagged"
        assert Severity  # keep import used
