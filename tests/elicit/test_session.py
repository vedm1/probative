"""PB14 test 2: the session file is append-only, hash-chained and resumable. Key-free."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from probative.elicit.session import ChainBrokenError, Session
from probative.elicit.types import AnswerKind, AskedQuestion, Basis, Option, RawAnswer

NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
OPTS = (
    Option(label="I will say", kind=AnswerKind.OPEN),
    Option(label="I do not know", kind=AnswerKind.UNKNOWN),
)


def asked(i: int) -> AskedQuestion:
    return AskedQuestion(
        index=i,
        template_id="topic:frequency",
        subject_ref="frequency",
        text=f"q{i}?",
        options=OPTS,
        evidence_kind=None,
    )


def answer(text: str) -> RawAnswer:
    return RawAnswer(kind=AnswerKind.OPEN, text=text, basis=Basis.TOLD)


def write_round(s: Session, rnd: int, first: int, n: int) -> None:
    s.append_round(
        rnd,
        [(asked(first + k), answer(f"a{first + k}")) for k in range(n)],
        asked_at=NOW,
    )


def test_a_round_is_appended_and_read_back(tmp_path: Path) -> None:
    s = Session(tmp_path / "s1")
    write_round(s, 0, 0, 2)
    write_round(s, 1, 2, 1)
    turns = s.turns()
    assert [t.index for t in turns] == [0, 1, 2]
    assert [t.round for t in turns] == [0, 0, 1]
    assert turns[1].prev_hash != turns[0].prev_hash
    assert turns[0].answer_text == "a0"


def test_resume_reads_the_same_turns_in_a_new_object(tmp_path: Path) -> None:
    s = Session(tmp_path / "s1")
    write_round(s, 0, 0, 3)
    again = Session(tmp_path / "s1")
    assert again.turns() == s.turns()
    write_round(again, 1, 3, 1)
    assert len(Session(tmp_path / "s1").turns()) == 4


def test_an_edited_line_breaks_the_chain(tmp_path: Path) -> None:
    s = Session(tmp_path / "s1")
    write_round(s, 0, 0, 2)
    path = s.path
    path.write_text(path.read_text().replace("a0", "b0"), encoding="utf-8")
    with pytest.raises(ChainBrokenError):
        Session(tmp_path / "s1").turns()


def test_a_removed_line_breaks_the_chain(tmp_path: Path) -> None:
    s = Session(tmp_path / "s1")
    write_round(s, 0, 0, 3)
    lines = s.path.read_text().splitlines()
    del lines[1]
    s.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ChainBrokenError):
        Session(tmp_path / "s1").turns()


def test_a_trailing_incomplete_round_is_dropped_on_resume(tmp_path: Path) -> None:
    s = Session(tmp_path / "s1")
    write_round(s, 0, 0, 2)
    complete = s.path.read_text()
    # a crash after two lines of the next round, one of them cut mid-write
    write_round(s, 1, 2, 3)
    lines = s.path.read_text().splitlines()
    s.path.write_text(
        "\n".join(lines[: len(complete.splitlines()) + 1])
        + "\n"
        + lines[len(complete.splitlines()) + 1][:20],
        encoding="utf-8",
    )
    again = Session(tmp_path / "s1")
    assert [t.index for t in again.turns()] == [0, 1]
    write_round(again, 1, 2, 1)  # the dropped round is asked again, cleanly
    assert [t.index for t in Session(tmp_path / "s1").turns()] == [0, 1, 2]


def test_rounds_must_be_numbered_in_order(tmp_path: Path) -> None:
    s = Session(tmp_path / "s1")
    write_round(s, 0, 0, 1)
    with pytest.raises(ValueError):
        write_round(s, 2, 1, 1)
