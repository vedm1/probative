"""Choose the next questions (PB14, D3). Deterministic, no model, nothing authored.

Priority, highest first:
1. an open contradiction `Question` between a claim of the respondent's (T3) and another claim
2. an open `elicitation` `Question`
3. a topic not yet asked
4. a T1 claim not yet asked, lowest confidence first, as a `confirm` proposition

A `gap` Question (a source nobody could classify, OI42) is never asked here: an answer in
free text would not classify it. The `Elicitor` never proposes to confirm a claim that is
already T3 (OI46). A candidate is a plan, not a filled question: the agent fills it and
`BiasHunter` judges the filled text before a person sees it.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field

from probative.core.evidence import EvidenceKind, Tier
from probative.core.graph.edges import EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, Question
from probative.elicit.templates import families_for, load_templates, load_topics
from probative.elicit.types import Family
from probative.ledger.contradict import content_tokens, where


@dataclass(frozen=True)
class Plan:
    template_id: str  # a template id, or "topic:<id>"
    subject_ref: str
    slots: dict[str, str] = field(default_factory=dict)
    evidence_kind: EvidenceKind | None = None


def _confidence(claim: Claim) -> float:
    value = claim.confidence.value
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def select(
    graph: Graph,
    *,
    mode: str,
    asked: Collection[str],
    topic: str = "general",
    limit: int = 12,
) -> list[Plan]:
    """Plans in priority order. `asked` holds the subject refs already put to the person."""
    families = families_for(mode)
    templates = load_templates()
    plans: list[Plan] = []
    current = list(graph.current())

    def usable(template_id: str) -> bool:
        t = templates[template_id]
        return t.family in families and (mode in t.modes)

    if Family.DISCOVER in families:
        for node in sorted(current, key=lambda n: n.id):
            if not isinstance(node, Question) or node.status != "open" or node.id in asked:
                continue
            if node.raised_by == "contradiction" and usable("challenge_contradiction"):
                plan = _challenge(graph, node)
                if plan:
                    plans.append(plan)
        for node in sorted(current, key=lambda n: n.id):
            if (
                isinstance(node, Question)
                and node.status == "open"
                and node.raised_by == "elicitation"
                and node.id not in asked
                and usable("resolve_open_question")
            ):
                plans.append(
                    Plan(
                        "resolve_open_question",
                        node.id,
                        {"question": node.text},
                        EvidenceKind.CUSTOMER,
                    )
                )
    for topic_id, t in load_topics().items():
        if t.family in families and topic_id not in asked:
            plans.append(Plan(f"topic:{topic_id}", topic_id, {}, t.evidence_kind))
    confirm_id = (
        "confirm_source_claim" if Family.DISCOVER in families else "reconstruct_recorded_item"
    )
    if usable(confirm_id):
        wanted = content_tokens(topic) if topic != "general" else frozenset()
        t3_texts = {n.text for n in current if isinstance(n, Claim) and n.tier is Tier.T3}
        candidates = [
            n
            for n in current
            if isinstance(n, Claim)
            and n.tier is Tier.T1
            and n.id not in asked
            and n.text not in t3_texts
            and (not wanted or wanted & content_tokens(n.text))
        ]
        for claim in sorted(candidates, key=lambda c: (_confidence(c), c.id)):
            plans.append(
                Plan(
                    confirm_id,
                    claim.id,
                    {"claim": claim.text},
                    claim.evidence_kind or EvidenceKind.CUSTOMER,
                )
            )
    return plans[:limit]


def _challenge(graph: Graph, question: Question) -> Plan | None:
    about = [
        graph.nodes[e.dst]
        for e in graph.out_edges(question.id, EdgeType.RAISED_ABOUT)
        if isinstance(graph.nodes.get(e.dst), Claim)
    ]
    mine = [c for c in about if isinstance(c, Claim) and c.tier is Tier.T3]
    theirs = [c for c in about if isinstance(c, Claim) and c.tier is not Tier.T3]
    if len(mine) != 1 or len(theirs) != 1:
        return None  # only a respondent's own claim can be put to them
    return Plan(
        "challenge_contradiction",
        question.id,
        {"mine": mine[0].text, "theirs": theirs[0].text, "where": where(graph, theirs[0])},
        mine[0].evidence_kind or EvidenceKind.CUSTOMER,
    )
