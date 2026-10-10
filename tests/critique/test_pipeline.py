from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from probative.core.candidates import CandidateKind
from probative.critique.pipeline import CritiqueOptions, run_critique
from probative.critique.report import DimensionStatus
from probative.critique.roster import ROSTER
from probative.critique.sources import LoadedSource
from probative.critique.verify import verify_numbers
from probative.extract.prompts import (
    FORECAST_PASS,
    PASSES,
    SEGMENT_PASS,
    ConstraintOutput,
    SegmentOutput,
)
from tests.critique._builders import make_source
from tests.critique._scripted import Scripted

DOC = """# Checkout PRD

CLAIM: Conversion drops 12% at the payment step.
CLAIM: FLAG Competitors convert far better than we do.
NEED: Users need a FLAG one-click checkout button.
NEED: Users want to pay without retyping details.
STORY: As a shopper I want to save my card so that I can pay faster.
SEGMENT: Adults aged 25 to 45 who shop online.
FORECAST: Launching this will double repeat purchases.
"""


def _opts(**kw):  # type: ignore[no-untyped-def]
    base = {
        "model": "test/model",
        "jobs": 4,
        "now": lambda: datetime(2026, 1, 1, tzinfo=UTC),
        "clock": lambda: 0.0,
    }
    base.update(kw)
    return CritiqueOptions(**base)


def _run(provider, docs=(DOC,), **kw):  # type: ignore[no-untyped-def]
    loaded = []
    for index, text in enumerate(docs):
        src = make_source(text, name=f"d{index}.md").model_copy(update={"id": f"src_{index:016d}"})
        loaded.append(LoadedSource(src, "detected"))
    return run_critique("subject", loaded, [], provider, _opts(**kw))


def test_the_extraction_passes_write_disjoint_kinds() -> None:
    seen: list[CandidateKind] = []
    for p in [*PASSES, SEGMENT_PASS, FORECAST_PASS]:
        seen.extend(p.fields.values())
    assert len(seen) == len(set(seen))


def test_roster_is_the_seven_critics_in_order() -> None:
    assert [e.rubric_id for e in ROSTER] == [
        "evidence_auditor",
        "space_warden",
        "segment_skeptic",
        "invest",
        "dependency_critic",
        "constraint_critic",
        "red_team",
    ]


def test_end_to_end_small_document() -> None:
    report = _run(Scripted())
    verify_numbers(report)
    by = {d.critic_id: d for d in report.dimensions}
    assert by["space_warden"].status is DimensionStatus.ASSESSED
    assert (by["space_warden"].checked, by["space_warden"].flagged) == (2, 1)
    assert by["space_warden"].blocked is True
    assert by["evidence_auditor"].checked == 2 and by["evidence_auditor"].flagged == 1
    assert by["red_team"].checked == 3  # two claims and one forecast
    assert by["dependency_critic"].status is DimensionStatus.NOT_APPLICABLE
    assert by["constraint_critic"].status is DimensionStatus.NOT_APPLICABLE
    finding = by["space_warden"].findings[0]
    assert finding.quote and finding.locator_label.startswith("line ")
    assert report.totals.block >= 1
    doc = report.documents[0]
    assert doc.candidates["need"] == 2 and doc.candidates["constraint"] == 0
    assert report.is_reference_model is False


def test_no_candidates_means_no_critic_calls() -> None:
    provider = Scripted()
    report = _run(provider, docs=("# Nothing\n\nJust prose here.\n",))
    assert provider.judge_batches == []
    assert all(d.status is DimensionStatus.NOT_APPLICABLE for d in report.dimensions)


def test_sharding_sends_batches_no_larger_than_batch_size() -> None:
    body = "# Many\n\n" + "\n".join(f"CLAIM: Claim number {i} stands." for i in range(7)) + "\n"
    provider = Scripted()
    report = _run(provider, docs=(body,), batch_size=3)
    sizes = sorted(len(b) for b in provider.judge_batches)
    # evidence_auditor: 7 claims -> 3+3+1; red_team: the same 7 -> 3+3+1
    assert sizes == [1, 1, 3, 3, 3, 3]
    assert {d.critic_id: d.checked for d in report.dimensions}["evidence_auditor"] == 7


def test_calls_run_concurrently() -> None:
    body = "# Many\n\n" + "\n".join(f"CLAIM: Claim number {i} stands." for i in range(12)) + "\n"
    provider = Scripted(delay=0.02)
    _run(provider, docs=(body,), jobs=6, batch_size=2)
    assert provider.max_in_flight >= 2


def test_report_is_independent_of_completion_order() -> None:
    body = DOC + "\n".join(f"CLAIM: Extra claim {i}, FLAG {i} unsupported." for i in range(9))
    one = _run(Scripted(), docs=(body,), jobs=1, batch_size=2)
    many = _run(Scripted(delay=0.005), docs=(body,), jobs=8, batch_size=2)
    assert one.model_dump(mode="json", exclude={"run"}) == many.model_dump(
        mode="json", exclude={"run"}
    )


def test_a_critic_that_omits_a_judgement_makes_its_dimension_incomplete() -> None:
    report = _run(Scripted(omit_for="BROKEN"), docs=(DOC + "NEED: Users need BROKEN speed.\n",))
    wd = {d.critic_id: d for d in report.dimensions}["space_warden"]
    assert wd.status is DimensionStatus.INCOMPLETE
    assert wd.unjudged >= 1 and wd.clean_rate is None and wd.floor_score is None
    assert report.incomplete is True
    verify_numbers(report)


def test_a_failed_extraction_pass_makes_the_dimension_incomplete() -> None:
    report = _run(Scripted(fail_extraction=SegmentOutput))
    seg = {d.critic_id: d for d in report.dimensions}["segment_skeptic"]
    assert seg.status is DimensionStatus.INCOMPLETE and seg.unextracted == 1
    assert {d.critic_id: d for d in report.dimensions}["space_warden"].status is (
        DimensionStatus.ASSESSED
    )
    assert report.incomplete
    verify_numbers(report)


def test_a_provider_failure_is_not_a_quiet_incomplete() -> None:
    with pytest.raises(RuntimeError, match="provider down"):
        _run(Scripted(explode_on=ConstraintOutput))


def test_two_documents_keep_their_own_identity_and_order() -> None:
    a = "# A\n\nNEED: Users need a FLAG widget.\n"
    b = "# B\n\nNEED: Users want faster sign in.\nNEED: Users need a FLAG dashboard.\n"
    report = _run(Scripted(), docs=(a, b))
    wd = {d.critic_id: d for d in report.dimensions}["space_warden"]
    assert wd.checked == 3 and wd.flagged == 2
    assert [f.source_id for f in wd.findings] == ["src_0000000000000000", "src_0000000000000001"]
    assert [d.counts.block for d in report.documents] == [1, 1]


def test_run_stats_sum_extraction_and_critic_usage() -> None:
    report = _run(Scripted())
    assert report.run.calls > 4 and report.run.input_tokens > 0 and report.run.jobs == 4


def test_extraction_failure_error_is_what_complete_with_repair_raises() -> None:
    with pytest.raises(ValidationError):
        ConstraintOutput.model_validate({"constraints": "bad"})


def test_cannot_tell_verdicts_are_surfaced_not_silently_clean() -> None:
    from probative.critics.llm_judge import (
        CheckJudgement,
        FlaggedBatch,
        FlaggedItem,
        JudgementBatch,
        Verdict,
    )

    class Undecided(Scripted):
        def _judge(self, messages):  # type: ignore[no-untyped-def]
            batch = super()._judge(messages)
            first = batch.judgements[0]
            return JudgementBatch(
                judgements=[
                    CheckJudgement(
                        candidate_id=first.candidate_id,
                        check_id=first.check_id,
                        verdict=Verdict.CANNOT_TELL,
                    ),
                    *batch.judgements[1:],
                ]
            )

        def _flagged(self, messages):  # type: ignore[no-untyped-def]
            batch = super()._flagged(messages)
            first = self._judge_all(messages).judgements[0]
            item = FlaggedItem(
                candidate_id=first.candidate_id,
                check_id=first.check_id,
                verdict=Verdict.CANNOT_TELL,
            )
            return FlaggedBatch(flagged=[item, *batch.flagged], reviewed=batch.reviewed)

    for reply in ("full", "flagged"):
        report = _run(Undecided(), docs=("# D\n\nNEED: Users want faster sign in.\n",), reply=reply)
        wd = {d.critic_id: d for d in report.dimensions}["space_warden"]
        assert wd.cannot_tell >= 1, reply


def test_a_provider_failure_cancels_queued_work() -> None:
    provider = Scripted(explode_on=ConstraintOutput, delay=0.01)
    docs = tuple(f"# D{i}\n\nNEED: Users need thing {i}.\n" for i in range(12))
    with pytest.raises(RuntimeError):
        _run(provider, docs=docs, jobs=1)
    assert provider.extraction_calls < 12 * 4  # not every queued extraction ran


def test_verify_numbers_rejects_a_wrong_checked_count() -> None:
    from probative.critique.report import ReportIntegrityError
    from probative.critique.verify import verify_numbers

    report = _run(Scripted())
    dim = report.dimensions[1].model_copy(update={"checked": report.dimensions[1].checked + 1})
    dims = [*report.dimensions[:1], dim, *report.dimensions[2:]]
    with pytest.raises(ReportIntegrityError, match="checked"):
        verify_numbers(report.model_copy(update={"dimensions": dims}))


def _multi_window_doc(parts: int) -> str:
    body = []
    for i in range(parts):
        body.append(f"# Part {i}\n")
        body.append(f"CLAIM: Conversion drops {i + 5}% at step {i}.")
        body.append(f"NEED: Users want to pay without retyping details {i}.")
        body.append("Filler sentence one. Filler sentence two. " * 4)
        body.append("")
    return "\n".join(body)


def test_windows_of_one_document_are_extracted_concurrently() -> None:
    provider = Scripted(delay=0.02)
    report = _run(provider, docs=(_multi_window_doc(8),), jobs=16, window_chars=400)
    # four passes only could be 4 in flight; more means windows overlap too
    assert provider.max_in_flight > 4
    assert provider.extraction_calls > 4 * 3
    assert {d.critic_id: d for d in report.dimensions}["space_warden"].checked == 8


def test_window_size_does_not_change_which_candidates_are_found() -> None:
    doc = _multi_window_doc(6)
    small = _run(Scripted(), docs=(doc,), window_chars=300)
    big = _run(Scripted(), docs=(doc,), window_chars=60_000)
    assert [d.checked for d in small.dimensions] == [d.checked for d in big.dimensions]
    one = _run(Scripted(delay=0.003), docs=(doc,), jobs=1, window_chars=300)
    many = _run(Scripted(delay=0.003), docs=(doc,), jobs=12, window_chars=300)
    assert one.model_dump(mode="json", exclude={"run"}) == many.model_dump(
        mode="json", exclude={"run"}
    )


def test_flagged_and_full_replies_give_the_same_report() -> None:
    doc = DOC + "\n".join(f"CLAIM: Extra claim {i}, FLAG {i} unsupported." for i in range(7))
    full = _run(Scripted(), docs=(doc,), reply="full", batch_size=3)
    flagged = _run(Scripted(), docs=(doc,), reply="flagged", batch_size=3)
    assert full.run.reply == "full" and flagged.run.reply == "flagged"
    assert full.model_dump(mode="json", exclude={"run"}) == flagged.model_dump(
        mode="json", exclude={"run"}
    )


def test_the_report_names_the_reply_mode_it_ran_with() -> None:
    from probative.render.markdown import render_markdown

    flagged = _run(Scripted(), reply="flagged")
    full = _run(Scripted(), reply="full")
    assert "critics reply with flagged items only" in render_markdown(flagged)
    assert "critics reply with a verdict per check" in render_markdown(full)
