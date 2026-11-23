"""The session file (PB14): append-only, hash-chained, resumable.

One JSON line per turn, and one `end_of_round` line after each round's turns. Each
line carries `prev_hash`, the sha256 of the previous line, so an edited, removed or
reordered line is refused. A round is written in one call after the person has
answered, so a crash leaves at most a trailing round with no end marker; `turns()`
drops it and the next `append_round` truncates it away. That round is asked again.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from probative.elicit.types import AskedQuestion, RawAnswer, Turn

GENESIS: Final = "0" * 64
FILE_NAME: Final = "turns.jsonl"


class ChainBrokenError(Exception):
    """A line was edited, removed or reordered, so the session cannot be trusted."""


def _hash(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


class Session:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / FILE_NAME

    # -- reading ----------------------------------------------------------------

    def _read(self) -> tuple[list[Turn], int, str, int]:
        """(turns of complete rounds, byte length of the verified part, last hash, next round)."""
        if not self.path.is_file():
            return [], 0, GENESIS, 0
        raw = self.path.read_bytes().decode("utf-8")
        turns: list[Turn] = []
        pending: list[Turn] = []
        prev = GENESIS
        good_bytes = 0
        offset = 0
        good_prev = GENESIS
        rounds = 0
        lines = raw.split("\n")
        for position, line in enumerate(lines):
            last = position == len(lines) - 1
            if last and not line:
                break  # the file ends with a newline
            consumed = len(line.encode("utf-8")) + (0 if last else 1)
            try:
                data: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                if last:
                    break  # a line cut mid-write is the incomplete round
                raise ChainBrokenError(f"line {position + 1} is not valid JSON") from None
            if data.get("prev_hash") != prev:
                raise ChainBrokenError(f"line {position + 1} does not follow the line before it")
            if "end_of_round" in data:
                if data["end_of_round"] != rounds:
                    raise ChainBrokenError(
                        f"line {position + 1} closes round {data['end_of_round']}"
                    )
                turns.extend(pending)
                pending = []
                rounds += 1
                good_bytes = offset + consumed
                good_prev = _hash(line)
            else:
                pending.append(Turn.model_validate(data))
            prev = _hash(line)
            offset += consumed
        return turns, good_bytes, good_prev, rounds

    def turns(self) -> list[Turn]:
        """The turns of every complete round, with the chain verified."""
        return self._read()[0]

    def rounds(self) -> int:
        return self._read()[3]

    # -- writing ----------------------------------------------------------------

    def append_round(
        self,
        round_: int,
        exchanges: list[tuple[AskedQuestion, RawAnswer]],
        *,
        asked_at: datetime,
    ) -> list[Turn]:
        turns, good_bytes, prev, rounds = self._read()
        if round_ != rounds:
            raise ValueError(f"the next round is {rounds}, not {round_}")
        if not exchanges:
            raise ValueError("a round holds at least one question")
        self.directory.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        made: list[Turn] = []
        index = len(turns)
        for asked, answer in exchanges:
            turn = Turn(
                index=index,
                round=round_,
                template_id=asked.template_id,
                subject_ref=asked.subject_ref,
                question_text=asked.text,
                options=asked.options,
                evidence_kind=asked.evidence_kind,
                answer_kind=answer.kind,
                answer_text=answer.text,
                basis=answer.basis,
                basis_count=answer.basis_count,
                asked_at=asked_at,
                prev_hash=prev,
            )
            line = turn.model_dump_json()
            lines.append(line)
            made.append(turn)
            prev = _hash(line)
            index += 1
        end = json.dumps({"end_of_round": round_, "prev_hash": prev}, sort_keys=True)
        lines.append(end)
        with self.path.open("a+b") as fh:
            fh.truncate(good_bytes)  # a dropped incomplete round is cut away here
            fh.seek(0, 2)
            fh.write(("\n".join(lines) + "\n").encode("utf-8"))
        return made
