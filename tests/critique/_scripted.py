"""A thread-safe, content-keyed provider for pipeline tests (no key, no network).

It answers from what the prompt contains, not from call order, so concurrent
callers get stable answers. Document lines such as `NEED: Users need X` become
extraction quotes (the text after the prefix); a candidate whose text contains
FLAG is judged not_met on the rubric's first check, anything else met.
"""

from __future__ import annotations

import re
import threading
import time
import zlib
from typing import Any

from pydantic import BaseModel

from probative.critics.llm_judge import (
    CheckJudgement,
    FlaggedBatch,
    FlaggedItem,
    JudgementBatch,
    Verdict,
)
from probative.extract.prompts import (
    ConstraintOutput,
    ForecastOutput,
    GeneralOutput,
    RawQuote,
    SegmentOutput,
)
from probative.llm import Message, StructuredResult, TokenUsage

_PREFIXES = {
    "CLAIM": ("claims", GeneralOutput),
    "NEED": ("needs", GeneralOutput),
    "STORY": ("stories", GeneralOutput),
    "DEP": ("dependencies", GeneralOutput),
    "CONSTRAINT": ("constraints", ConstraintOutput),
    "SEGMENT": ("segments", SegmentOutput),
    "FORECAST": ("forecasts", ForecastOutput),
}


class Scripted:
    def __init__(
        self,
        *,
        delay: float = 0.0,
        omit_for: str | None = None,
        fail_extraction: type[BaseModel] | None = None,
        explode_on: type[BaseModel] | None = None,
    ) -> None:
        self.delay = delay
        self.omit_for = omit_for
        self.fail_extraction = fail_extraction
        self.explode_on = explode_on
        self.lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0
        self.judge_batches: list[list[str]] = []
        self.extraction_calls = 0

    def complete_structured(
        self, messages: list[Message], *, output_model: type[Any], model: str
    ) -> StructuredResult[Any]:
        with self.lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            user = messages[-1].content
            if self.delay:
                time.sleep(self.delay * (1 + zlib.crc32(user.encode()) % 3))
            if self.explode_on is not None and output_model is self.explode_on:
                raise RuntimeError("provider down")
            output = self._answer(messages, output_model)
            return StructuredResult(
                output=output, usage=TokenUsage(input_tokens=10, output_tokens=5), raw_model=model
            )
        finally:
            with self.lock:
                self.in_flight -= 1

    def _answer(self, messages: list[Message], output_model: type[Any]) -> BaseModel:
        if output_model is FlaggedBatch:
            return self._flagged(messages)
        if output_model is JudgementBatch:
            return self._judge(messages)
        if output_model in (GeneralOutput, ConstraintOutput, SegmentOutput, ForecastOutput):
            with self.lock:
                self.extraction_calls += 1
            if self.fail_extraction is output_model:
                return output_model.model_validate({next(iter(output_model.model_fields)): "bad"})
            return self._extract(messages[-1].content, output_model)
        raise AssertionError(f"Scripted cannot answer {output_model.__name__}")

    def _extract(self, user: str, output_model: type[Any]) -> BaseModel:
        document = user.split("<document>\n", 1)[1].rsplit("\n</document>", 1)[0]
        found: dict[str, list[RawQuote]] = {}
        for line in document.splitlines():
            prefix, _, rest = line.partition(": ")
            if prefix in _PREFIXES and _PREFIXES[prefix][1] is output_model:
                found.setdefault(_PREFIXES[prefix][0], []).append(RawQuote(quote=rest))
        return output_model.model_validate(
            {k: [q.model_dump() for q in v] for k, v in found.items()}
        )

    def _judge(self, messages: list[Message]) -> JudgementBatch:
        return self._judge_all(messages, omit=True)

    def _judge_all(self, messages: list[Message], omit: bool = False) -> JudgementBatch:
        system, user = messages[0].content, messages[-1].content
        checks = re.findall(r"^\[(\w+)\] ", system, flags=re.MULTILINE)
        cands = re.findall(r'<candidate id="([^"]+)">(.*?)</candidate>', user, flags=re.DOTALL)
        with self.lock:
            self.judge_batches.append([cid for cid, _ in cands])
        out: list[CheckJudgement] = []
        for cid, text in cands:
            if omit and self.omit_for and self.omit_for in text:
                continue
            for index, check in enumerate(checks):
                flagged = "FLAG" in text and index == 0
                out.append(
                    CheckJudgement(
                        candidate_id=cid,
                        check_id=check,
                        verdict=Verdict.NOT_MET if flagged else Verdict.MET,
                        quote=text if flagged else None,
                    )
                )
        return JudgementBatch(judgements=out)

    def _flagged(self, messages: list[Message]) -> FlaggedBatch:
        """The flagged reply, derived from the full one so both modes agree."""
        batch = self._judge_all(messages)
        cands = re.findall(r'<candidate id="([^"]+)">', messages[-1].content)
        items = [
            FlaggedItem(
                candidate_id=j.candidate_id,
                check_id=j.check_id,
                verdict=j.verdict,
                quote=j.quote,
            )
            for j in batch.judgements
            if j.verdict is not Verdict.MET
        ]
        reviewed = len(cands)
        if self.omit_for and self.omit_for in messages[-1].content:
            reviewed -= 1  # the model skipped a candidate: the guard is the count
        return FlaggedBatch(flagged=items, reviewed=reviewed)
