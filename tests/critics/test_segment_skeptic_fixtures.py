"""The S2 fixture gate for SegmentSkeptic, wired end to end with an ORACLE
provider that answers from each fixture file's own label.

This proves the plumbing only: that the rubric's globs find the corpus, that
every fixture parses to candidates, that a labelled check yields a finding on
exactly its defect and nothing on a clean file, and that the gate fails when the
critic misses. It measures nothing about a model. The model's behaviour is the
recorded replay (test_pb6_replay.py)."""

from __future__ import annotations

import re
from typing import Any

import pytest

from probative.critics.llm_judge import CheckJudgement, JudgementBatch, Verdict
from probative.critics.segment_skeptic import SegmentSkeptic
from probative.critics.testing import assert_rubric_fixtures
from probative.llm import Message, StructuredResult, TokenUsage
from tests.critics._candidates import load_fixture
from tests.critics._corpus import SEGMENT_SKEPTIC as CORPUS
from tests.critics._corpus import SPLITS

_ID = re.compile(r'<candidate id="([^"]+)">')


class OracleProvider:
    """Judges `not_met` on the labelled check of a labelled candidate, `met` otherwise.
    `blind=True` never flags anything: the critic that misses every defect."""

    def __init__(self, labels: dict[str, str], *, blind: bool = False) -> None:
        self.labels = labels
        self.blind = blind

    def complete_structured(
        self, messages: list[Message], *, output_model: type[Any], model: str
    ) -> StructuredResult[Any]:
        ids = _ID.findall(messages[-1].content)
        batch = JudgementBatch(
            judgements=[
                CheckJudgement(
                    candidate_id=cid,
                    check_id=check.id,
                    verdict=(
                        Verdict.NOT_MET
                        if not self.blind and self.labels.get(cid) == check.id
                        else Verdict.MET
                    ),
                )
                for cid in ids
                for check in CORPUS.rubric.checks
            ]
        )
        return StructuredResult(
            output=batch, usage=TokenUsage(input_tokens=1, output_tokens=1), raw_model=model
        )


def _labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    for split in SPLITS:
        for path in CORPUS.files("seeded", split):
            (candidate,) = CORPUS.parse(path)
            labels[candidate.id] = load_fixture(path)["check"]  # type: ignore[attr-defined]
    return labels


def test_the_gate_passes_with_an_oracle_critic() -> None:
    critic = SegmentSkeptic.from_builtin_rubric(OracleProvider(_labels()), model="m")
    assert_rubric_fixtures(critic, CORPUS.rubric_path, CORPUS.parse)


def test_the_gate_fails_for_a_critic_that_misses_defects() -> None:
    critic = SegmentSkeptic.from_builtin_rubric(OracleProvider(_labels(), blind=True), model="m")
    with pytest.raises(AssertionError, match="seeded-defect"):
        assert_rubric_fixtures(critic, CORPUS.rubric_path, CORPUS.parse)


def test_each_defect_fires_exactly_its_labelled_check() -> None:
    critic = SegmentSkeptic.from_builtin_rubric(OracleProvider(_labels()), model="m")
    for split in SPLITS:
        for path in CORPUS.files("seeded", split):
            fired = {f.check_id for f in critic.check(CORPUS.parse(path))}
            assert fired == {load_fixture(path)["check"]}, path.name


def test_seeded_severities_follow_the_check() -> None:
    critic = SegmentSkeptic.from_builtin_rubric(OracleProvider(_labels()), model="m")
    for path in CORPUS.files("seeded", "dev"):
        (finding,) = critic.check(CORPUS.parse(path))
        expected = "block" if finding.check_id == "demographic_only" else "warn"
        assert finding.severity.value == expected, path.name
