"""PB8 checkpoint A: the opt-in forecast extraction pass. The default passes are
untouched (PB4's recordings are keyed by prompt hash), forecasts come only when
a caller asks, and a forecast quote resolves exactly like any other."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from probative.core.candidates import (
    Candidate,
    CandidateKind,
    ExtractionResult,
    ForecastCandidate,
    RejectReason,
    candidate_id,
)
from probative.core.evidence import EvidenceSpan, Locator
from probative.extract import extract_candidates
from probative.extract.prompts import (
    CONSTRAINT_PROMPT,
    FORECAST_PASS,
    GENERAL_PROMPT,
    PASSES,
    SEGMENT_PASS,
    ConstraintOutput,
    ForecastOutput,
    GeneralOutput,
    RawQuote,
)
from probative.llm import FakeProvider, Message, StructuredResult, TokenUsage
from tests.extract._helpers import make_source

TEXT = (
    "# Billing PRD\n"
    "Once reminders ship, late payments will fall by half within a quarter.\n"
    "We will build reminders in Q3.\n"
    "Invoices must be sent within 24 hours.\n"
    "Customers will pay faster because they get a nudge.\n"
)
FORECAST_A = "Once reminders ship, late payments will fall by half within a quarter."
FORECAST_B = "Customers will pay faster because they get a nudge."
PLAN = "We will build reminders in Q3."


def _fc(*quotes: str) -> ForecastOutput:
    return ForecastOutput(forecasts=[RawQuote(quote=q) for q in quotes])


class _Calls:
    def __init__(self, outputs: list[Any]) -> None:
        self.inner = FakeProvider(outputs, usage=TokenUsage(input_tokens=10, output_tokens=2))
        self.calls: list[list[Message]] = []

    def complete_structured(
        self, messages: list[Message], *, output_model: type[Any], model: str
    ) -> StructuredResult[Any]:
        self.calls.append(messages)
        return self.inner.complete_structured(messages, output_model=output_model, model=model)


def _span(start: int = 0, end: int = 5, text: str = "hello") -> EvidenceSpan:
    return EvidenceSpan(source_id="src_a", start=start, end=end, text=text, locator=Locator())


def test_default_prompts_are_byte_identical_to_pb4s() -> None:
    assert (
        hashlib.sha256(GENERAL_PROMPT.encode()).hexdigest()
        == "a5b2b3a95e5107d5d7081d0a163cc862eb157e333021f6cb15cc0b791c2b59af"
    )
    assert (
        hashlib.sha256(CONSTRAINT_PROMPT.encode()).hexdigest()
        == "8c556df766b710dbe61c26290b08fdada4d4d94b10cf858cf0552433a9c39542"
    )
    assert [p.name for p in PASSES] == ["general", "constraint"]
    assert FORECAST_PASS not in PASSES and FORECAST_PASS is not SEGMENT_PASS


def test_forecast_candidate_id_is_derived_and_prefixed() -> None:
    span = _span()
    candidate = ForecastCandidate(id=candidate_id(CandidateKind.FORECAST, span), evidence=span)
    assert candidate.id.startswith("cand_forecast_")
    with pytest.raises(ValidationError, match="derived id"):
        ForecastCandidate(id="cand_forecast_handwritten", evidence=span)


def test_forecast_candidate_is_in_the_union_and_the_result() -> None:
    adapter: TypeAdapter[Candidate] = TypeAdapter(Candidate)
    span = _span(10, 15)
    forecast = ForecastCandidate(id=candidate_id(CandidateKind.FORECAST, span), evidence=span)
    assert adapter.validate_json(adapter.dump_json(forecast)) == forecast
    result = ExtractionResult(source_id="src_a", forecasts=[forecast])
    assert [c.kind for c in result.candidates()] == [CandidateKind.FORECAST]
    assert ExtractionResult(source_id="src_a").forecasts == []


def test_forecasts_are_not_asked_for_by_default() -> None:
    provider = _Calls([GeneralOutput(), ConstraintOutput()])
    result = extract_candidates(make_source(TEXT), provider, model="m")
    assert len(provider.calls) == 2
    assert result.forecasts == []


def test_opt_in_pass_yields_located_forecasts() -> None:
    source = make_source(TEXT)
    provider = _Calls([GeneralOutput(), ConstraintOutput(), _fc(FORECAST_A, FORECAST_B)])
    result = extract_candidates(source, provider, model="m", passes=[*PASSES, FORECAST_PASS])
    assert [c.text for c in result.forecasts] == [FORECAST_A, FORECAST_B]
    assert all(c.kind is CandidateKind.FORECAST for c in result.forecasts)
    for forecast in result.forecasts:
        ev = forecast.evidence  # sliced from the source, never from the model (I1)
        assert source.text[ev.start : ev.end] == ev.text
    assert result.usage == TokenUsage(input_tokens=30, output_tokens=6)


def test_a_forecast_the_document_does_not_contain_is_rejected_not_believed() -> None:
    provider = _Calls([_fc("Revenue will triple next year.", FORECAST_A)])
    result = extract_candidates(make_source(TEXT), provider, model="m", passes=[FORECAST_PASS])
    assert [c.text for c in result.forecasts] == [FORECAST_A]
    assert [(r.kind, r.reason) for r in result.rejected] == [
        (CandidateKind.FORECAST, RejectReason.NOT_FOUND)
    ]


def test_forecast_and_segment_passes_do_not_share_claims() -> None:
    """The same sentence may be a claim and a forecast; kinds are tracked apart."""
    provider = _Calls([GeneralOutput(claims=[RawQuote(quote=FORECAST_A)]), _fc(FORECAST_A)])
    result = extract_candidates(
        make_source(TEXT), provider, model="m", passes=[PASSES[0], FORECAST_PASS]
    )
    assert [c.text for c in result.claims] == [FORECAST_A]
    assert [c.text for c in result.forecasts] == [FORECAST_A]


def test_the_forecast_prompt_excludes_plans_requirements_targets_and_facts() -> None:
    prompt = FORECAST_PASS.system_prompt.lower()
    assert "<document>" in prompt and "data" in prompt
    for word in ("plan", "requirement", "target", "own knowledge"):
        assert word in prompt, word
    assert FORECAST_A not in FORECAST_PASS.system_prompt  # no fixture text in the prompt
    assert PLAN not in FORECAST_PASS.system_prompt


def test_forecast_output_model_has_no_room_for_a_score() -> None:
    assert set(ForecastOutput.model_fields) == {"forecasts"}
