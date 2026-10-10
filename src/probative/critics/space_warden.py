"""SpaceWarden — invariant I3 (docs/DESIGN.md §4): problem space and solution
space never mix. A `NeedCandidate` that names a feature, a screen, an
implementation or a technology instead of a customer benefit is blocked
(Olsen p. 39).

Scope, deliberately narrow: this checks *only* solution grammar. It does not
flag a need for being vague, not verb-first, or unmeasurable — those are not
I3. The graph-level rule (a Need may never reference a FeatureIdea) needs
PB10's node types and is not checked here.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from probative.core.candidates import NeedCandidate
from probative.core.critic import Rubric
from probative.critics.llm_judge import DEFAULT_BATCH_SIZE, LLMCritic, Reply
from probative.critics.rubric import load_rubric
from probative.llm import Provider

RUBRIC_PATH = Path(__file__).parent / "rubrics" / "space_warden" / "rubric.yaml"

_PREAMBLE = """\
You are SpaceWarden. Probative keeps the problem space (what customers need, \
as benefits) apart from the solution space (features, screens, technologies). \
A need is a customer benefit: what the customer is trying to achieve, in the \
customer's voice. The candidates are statements a document presents as \
customer needs. Decide only whether each one names the solution instead of \
the benefit. Do not penalise a need for being vague, for not starting with a \
verb, or for lacking a measurable target; those are not your concern. Words a \
customer would use for their own world, such as a settlement, a statement, \
an order or a payout, are not solutions.
"""


class SpaceWarden(LLMCritic):
    candidate_type: ClassVar[type[NeedCandidate]] = NeedCandidate
    preamble: ClassVar[str] = _PREAMBLE

    @classmethod
    def from_builtin_rubric(
        cls,
        provider: Provider,
        *,
        model: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
        reply: Reply = "full",
    ) -> SpaceWarden:
        return cls(
            load_rubric(RUBRIC_PATH), provider, model=model, batch_size=batch_size, reply=reply
        )


def space_warden_rubric() -> Rubric:
    return load_rubric(RUBRIC_PATH)
