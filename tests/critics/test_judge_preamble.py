"""PB6-p1: `judge_preamble`, the verdict semantics a critic may override.

PB5's generic preamble says "missing information is cannot_tell, never
not_met" — right for INVEST (judge only what the words show), wrong for a
provenance auditor, where the absence of a stated basis *is* the violation.
The hook defaults to PB5's text byte-for-byte, so PB5's recordings (keyed by
prompt hash) and held-out numbers are untouched.
"""

from __future__ import annotations

import hashlib
from typing import ClassVar

from probative.core.candidates import NeedCandidate
from probative.critics.invest import INVESTCritic, invest_rubric
from probative.critics.llm_judge import (
    _JUDGE_PREAMBLE,
    CheckJudgement,
    JudgementBatch,
    LLMCritic,
    Verdict,
    build_system_prompt,
)
from probative.critics.space_warden import SpaceWarden, space_warden_rubric
from probative.llm import FakeProvider
from tests.critics._candidates import needs
from tests.critics.test_llm_judge import DOC, Q1, _rubric

# Captured from PB5 (commit 34a420e) before this hook existed.
PB5_SPACE_WARDEN_PROMPT_SHA = "67d67e533dbb53d8c588c4834fadbf747d314fa0c9108a1fe9f4d13928632c88"
PB5_INVEST_PROMPT_SHA = "6b4cb1a2b4a36252913341ecc7547e5b6d325271709beb398bafd5f4323f98fd"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_pb5_critics_prompts_are_byte_identical_to_before_the_hook() -> None:
    assert _sha(build_system_prompt(space_warden_rubric(), SpaceWarden.preamble)) == (
        PB5_SPACE_WARDEN_PROMPT_SHA
    )
    assert _sha(build_system_prompt(invest_rubric(), INVESTCritic.preamble)) == (
        PB5_INVEST_PROMPT_SHA
    )


def test_pb5s_critics_inherit_the_default_judge_preamble_unchanged() -> None:
    assert SpaceWarden.judge_preamble is _JUDGE_PREAMBLE
    assert INVESTCritic.judge_preamble is _JUDGE_PREAMBLE


def test_an_overriding_judge_preamble_replaces_the_generic_one() -> None:
    prompt = build_system_prompt(_rubric(), "PREAMBLE-TEXT", judge_preamble="MY-VERDICT-RULES")
    assert prompt.startswith("MY-VERDICT-RULES")
    assert "Missing information is cannot_tell" not in prompt
    assert "PREAMBLE-TEXT" in prompt and "Names a feature" in prompt  # rubric still rendered


def test_a_critic_class_override_reaches_the_system_message() -> None:
    class _Closed(LLMCritic):
        candidate_type: ClassVar[type[NeedCandidate]] = NeedCandidate
        preamble: ClassVar[str] = "PREAMBLE-TEXT"
        judge_preamble: ClassVar[str] = "CLOSED-WORLD-RULES"

    (cand,) = needs(DOC, [Q1])
    seen: list[str] = []

    class _Spy(FakeProvider):
        def complete_structured(self, messages, **kwargs):  # type: ignore[no-untyped-def, override]
            seen.append(messages[0].content)
            return super().complete_structured(messages, **kwargs)

    batch = JudgementBatch(
        judgements=[
            CheckJudgement(candidate_id=cand.id, check_id=check, verdict=Verdict.MET)
            for check in ("c1", "c2")
        ]
    )
    _Closed(_rubric(), _Spy([batch]), model="m").check([cand])
    assert seen[0].startswith("CLOSED-WORLD-RULES")
