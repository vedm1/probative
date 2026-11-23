"""A respondent that replays recorded answers (PB14). For tests and fixtures: it puts no
question to anyone. The terminal respondent is `PB14-p2` (OI49).

An answer is looked up by the question's `subject_ref`, then by a key that occurs in its
text (so a fixture can name a source claim by its words, not by a hash it cannot know),
then the default. Every lookup is recorded in `asked`, so a test can see what was put."""

from __future__ import annotations

from collections.abc import Mapping

from probative.elicit.types import AnswerKind, AskedQuestion, RawAnswer


class ReplayRespondent:
    def __init__(self, answers: Mapping[str, RawAnswer], default: RawAnswer | None = None) -> None:
        self._answers = dict(answers)
        self._default = default or RawAnswer(kind=AnswerKind.UNKNOWN)
        self.asked: list[AskedQuestion] = []

    def answer(self, round_: tuple[AskedQuestion, ...]) -> tuple[RawAnswer, ...]:
        found: list[RawAnswer] = []
        for q in round_:
            self.asked.append(q)
            hit = self._answers.get(q.subject_ref)
            if hit is None:
                hit = next((a for k, a in self._answers.items() if k in q.text), self._default)
            found.append(hit)
        return tuple(found)
