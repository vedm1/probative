"""The critics `probative critique` runs, as one named constant.

One entry per critic, one report dimension per entry (no invented grouping).
Keeping the roster as data is what lets PB39 make onboarding-mode exclusion a
configuration (OI22, I9) rather than a prompt request; nothing here enforces
that yet, because there is no mode.

`subjects` is what a dimension counts as "checked". `feeds` is what the critic
is sent, which for `ConstraintCritic` includes stories it traces to. Only
critics that judge each candidate independently are `shardable`: sharding at
`batch_size` boundaries sends the same prompts an unsharded run would, so the
recordings do not move.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from probative.core.candidates import CandidateKind
from probative.critics.base import Critic
from probative.critics.constraint_critic import ConstraintCritic
from probative.critics.dependency_critic import DependencyCritic
from probative.critics.evidence_auditor import EvidenceAuditor
from probative.critics.invest import INVESTCritic
from probative.critics.llm_judge import Reply
from probative.critics.red_team import RedTeam
from probative.critics.segment_skeptic import SegmentSkeptic
from probative.critics.space_warden import SpaceWarden
from probative.llm import Provider

Factory = Callable[[Provider, str, int, Reply], Critic]
K = CandidateKind


@dataclass(frozen=True)
class RosterEntry:
    rubric_id: str
    label: str
    subjects: tuple[CandidateKind, ...]
    feeds: tuple[CandidateKind, ...]
    shardable: bool
    make: Factory


ROSTER: tuple[RosterEntry, ...] = (
    RosterEntry(
        "evidence_auditor",
        "Evidence",
        (K.CLAIM,),
        (K.CLAIM,),
        True,
        lambda p, m, b, r: EvidenceAuditor.from_builtin_rubric(p, model=m, batch_size=b, reply=r),
    ),
    RosterEntry(
        "space_warden",
        "Problem framing",
        (K.NEED,),
        (K.NEED,),
        True,
        lambda p, m, b, r: SpaceWarden.from_builtin_rubric(p, model=m, batch_size=b, reply=r),
    ),
    RosterEntry(
        "segment_skeptic",
        "Segments",
        (K.SEGMENT,),
        (K.SEGMENT,),
        True,
        lambda p, m, b, r: SegmentSkeptic.from_builtin_rubric(p, model=m, batch_size=b, reply=r),
    ),
    RosterEntry(
        "invest",
        "Story quality",
        (K.STORY,),
        (K.STORY,),
        True,
        lambda p, m, b, r: INVESTCritic.from_builtin_rubric(p, model=m, batch_size=b, reply=r),
    ),
    RosterEntry(
        "dependency_critic",
        "Dependencies",
        (K.DEPENDENCY,),
        (K.DEPENDENCY,),
        True,
        lambda p, m, b, r: DependencyCritic.from_builtin_rubric(p, model=m, batch_size=b, reply=r),
    ),
    RosterEntry(
        "constraint_critic",
        "Constraints",
        (K.CONSTRAINT,),
        (K.CONSTRAINT, K.STORY),
        False,
        lambda p, m, b, r: ConstraintCritic.from_builtin_rubric(p, model=m, batch_size=b),
    ),
    RosterEntry(
        "red_team",
        "Stress test: least sure about",
        (K.CLAIM, K.FORECAST),
        (K.CLAIM, K.FORECAST),
        True,
        lambda p, m, b, r: RedTeam.from_builtin_rubric(p, model=m, batch_size=b, reply=r),
    ),
)
