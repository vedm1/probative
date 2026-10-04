"""PB6-p1: `measure(..., detail=True)` adds a per-file `cannot_tell` count.

For a blocking critic `cannot_tell` is a silent pass, and the aggregate counter
cannot say which seeded file slipped through that way. The default output is
unchanged, because PB5's committed `results.json` files are compared against it.
"""

from __future__ import annotations

import re
from typing import Any

from probative.critics.llm_judge import CheckJudgement, Verdict
from probative.critics.space_warden import SpaceWarden
from probative.llm import Message, StructuredResult, TokenUsage
from tests.critics._corpus import SPACE_WARDEN
from tests.critics._measure import measure


class _CannotTell:
    """Answers cannot_tell for every candidate."""

    def complete_structured(
        self, messages: list[Message], *, output_model: type[Any], model: str
    ) -> StructuredResult[Any]:
        ids = re.findall(r'<candidate id="([^"]+)">', messages[-1].content)
        return StructuredResult(
            output=output_model(
                judgements=[
                    CheckJudgement(
                        candidate_id=i, check_id="solution_grammar", verdict=Verdict.CANNOT_TELL
                    )
                    for i in ids
                ]
            ),
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            raw_model=model,
        )


def test_detail_reports_cannot_tell_per_file_and_default_does_not() -> None:
    plain = measure(SPACE_WARDEN, "dev", SpaceWarden.from_builtin_rubric(_CannotTell(), model="m"))
    assert all("cannot_tell" not in row for row in plain["seeded"]["files"])
    assert all("cannot_tell" not in row for row in plain["clean"]["files"])

    detailed = measure(
        SPACE_WARDEN,
        "dev",
        SpaceWarden.from_builtin_rubric(_CannotTell(), model="m"),
        detail=True,
    )
    seeded, clean = detailed["seeded"]["files"], detailed["clean"]["files"]
    assert [row["cannot_tell"] for row in seeded] == [1] * 12  # one defect candidate per file
    assert [row["cannot_tell"] for row in clean] == [5, 5]
    # and a blocking critic that answered cannot_tell to everything caught nothing
    assert detailed["seeded"]["caught"] == 0
    assert detailed["judge_stats"]["cannot_tell"] == 22
