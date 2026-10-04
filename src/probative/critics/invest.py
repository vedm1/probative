"""INVESTCritic — story quality against the six INVEST properties (Bill Wake,
via Olsen p. 78), blocking only on `testable` (docs/DESIGN.md §13).

It judges a story from its own words alone. A story with no acceptance
criteria written is not "untestable" — that is `cannot_tell`, and
acceptance-criteria capture belongs to PB26. With one sentence of context I
expected `independent`, `estimable` and `small` to be often undecidable. The
recorded runs on the synthetic corpus did not show it (the model used
`cannot_tell` for 14 of 264 judgements, never on a seeded check), which says
more about how signposted the corpus is than about the critic: the stress
split (see PB5's implementation notes) is where undecidable stories are tested.

No INVEST *number* is produced here. `invest_score` (DESIGN §8) is a formula
and waits for PB11; the dimension score is PB3's deterministic
`score_dimension` over these findings.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from probative.core.candidates import StoryCandidate
from probative.core.critic import Rubric
from probative.critics.llm_judge import DEFAULT_BATCH_SIZE, LLMCritic
from probative.critics.rubric import load_rubric
from probative.llm import Provider

RUBRIC_PATH = Path(__file__).parent / "rubrics" / "invest" / "rubric.yaml"

_PREAMBLE = """\
You are INVESTCritic. The candidates are user stories, or statements of who \
wants what, taken from a document. Judge each against the INVEST properties \
(Independent, Negotiable, Valuable, Estimable, Small, Testable) using only \
the story's own words. A story that does not state acceptance criteria is not \
thereby untestable or unestimable: you only see one statement, so say \
cannot_tell when its words do not decide the question. Mark a property \
not_met only when the words themselves show the violation. A leading list \
marker such as "- " is formatting, not content.
"""


class INVESTCritic(LLMCritic):
    candidate_type: ClassVar[type[StoryCandidate]] = StoryCandidate
    preamble: ClassVar[str] = _PREAMBLE

    @classmethod
    def from_builtin_rubric(
        cls, provider: Provider, *, model: str, batch_size: int = DEFAULT_BATCH_SIZE
    ) -> INVESTCritic:
        return cls(load_rubric(RUBRIC_PATH), provider, model=model, batch_size=batch_size)


def invest_rubric() -> Rubric:
    return load_rubric(RUBRIC_PATH)
