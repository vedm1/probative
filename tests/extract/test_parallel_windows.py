"""`extract_candidates(..., executor=...)` (PB9, lever A): the (window, pass) calls
run concurrently, and the result is exactly what the sequential path returns."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from probative.core.candidates import ExtractionFailedError
from probative.extract import FORECAST_PASS, PASSES, SEGMENT_PASS, extract_candidates
from probative.extract.prompts import ConstraintOutput
from tests.critique._builders import make_source
from tests.critique._scripted import Scripted

ALL_PASSES = [*PASSES, SEGMENT_PASS, FORECAST_PASS]
LINES = [
    "CLAIM: Conversion drops 12% at the payment step.",
    "NEED: Users need to pay without retyping details.",
    "STORY: As a shopper I want to save my card so that I can pay faster.",
    "CONSTRAINT: Card data must be handled under the scheme rules.",
    "DEP: We rely on the payments gateway team.",
    "SEGMENT: Adults aged 25 to 45 who shop online.",
    "FORECAST: Launching this will double repeat purchases.",
]


def _document(copies: int) -> str:
    body = []
    for i in range(copies):
        body.append(f"# Part {i}\n")
        body.extend(f"{line} ({i})" for line in LINES)
        body.append("")
    return "\n".join(body)


def _run(provider, executor=None, max_chars=400):  # type: ignore[no-untyped-def]
    source = make_source(_document(6))
    return extract_candidates(
        source,
        provider,
        model="t/m",
        max_chars_per_call=max_chars,
        passes=ALL_PASSES,
        executor=executor,
    )


def test_executor_result_equals_the_sequential_result() -> None:
    sequential = _run(Scripted())
    with ThreadPoolExecutor(max_workers=8) as pool:
        parallel = _run(Scripted(delay=0.002), pool)
    assert parallel.model_dump() == sequential.model_dump()
    assert len(sequential.candidates()) > 20  # the document really spans several windows


def test_calls_overlap_when_an_executor_is_given() -> None:
    provider = Scripted(delay=0.02)
    with ThreadPoolExecutor(max_workers=8) as pool:
        _run(provider, pool)
    assert provider.max_in_flight >= 2


def test_no_executor_means_no_concurrency() -> None:
    provider = Scripted(delay=0.005)
    _run(provider)
    assert provider.max_in_flight == 1


def test_a_single_worker_executor_does_not_deadlock() -> None:
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert _run(Scripted(), pool).candidates()


def test_a_failed_pass_raises_the_same_error_with_an_executor() -> None:
    with ThreadPoolExecutor(max_workers=4) as pool, pytest.raises(ExtractionFailedError):
        _run(Scripted(fail_extraction=ConstraintOutput), pool)


def test_a_provider_exception_propagates_and_cancels_queued_calls() -> None:
    provider = Scripted(explode_on=ConstraintOutput, delay=0.01)
    with ThreadPoolExecutor(max_workers=1) as pool, pytest.raises(RuntimeError):
        _run(provider, pool)
    assert provider.extraction_calls < 6 * 4 * 2  # not every queued call ran
