"""One valid instance of every node type. Synthetic data only."""

from __future__ import annotations

from datetime import UTC, datetime

from probative.core.critic import Severity
from probative.core.evidence import EvidenceKind, Locator, SourceFormat, Tier
from probative.core.graph.nodes import (
    NODE_CLASSES,
    AcceptanceCriterion,
    Adoption,
    Alternative,
    Backbone,
    Baseline,
    BuildPhase,
    Claim,
    Constraint,
    Decision,
    DeliverySignal,
    Dependency,
    EmpathyEntry,
    Estimate,
    EvidenceSpan,
    FeatureChunk,
    FeatureIdea,
    Finding,
    Hypothesis,
    IncumbentSystem,
    JourneyStage,
    KanoClass,
    Ladder,
    MVPMembership,
    Need,
    NeedHierarchy,
    Node,
    NodeBase,
    Opportunity,
    Partition,
    Persona,
    Postmortem,
    Premortem,
    ProcessModel,
    ProcessStep,
    Question,
    Rating,
    Risk,
    Segment,
    Source,
    Story,
    Test,
    Touchpoint,
    ValueProp,
    Variance,
    Workaround,
)
from probative.core.graph.values import Computed, Input

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
ENV = {"owner": "ved", "asserted_at": T0}


def inp(value: float, unit: str = "count") -> Input:
    return Input(value=value, unit=unit, provenance="elicited")


def conf() -> Computed:
    return Computed(value=0.5, formula_id="confidence.v1", input_ids=[])


def sample_source() -> Source:
    return Source.make(
        sha256="a" * 64,
        ingest_id="src_" + "a" * 16,
        format=SourceFormat.MARKDOWN,
        tier=Tier.T1,
        kind=EvidenceKind.CUSTOMER,
        extractor="markdown",
        extractor_version="md/1",
        path="notes.md",
        **ENV,
    )


def sample_span(source: Source | None = None, text: str = "hello") -> EvidenceSpan:
    src = source or sample_source()
    return EvidenceSpan.make(
        source_ref=src.id, start=0, end=len(text), text=text, locator=Locator(line=1), **ENV
    )


def sample_claim(text: str = "Users wait too long.", tier: Tier = Tier.T1) -> Claim:
    return Claim.make(text=text, tier=tier, confidence=conf(), **ENV)


def sample_test() -> Test:
    return Test.make(
        method="Five interviews",
        cost=inp(2, "person-days"),
        duration=inp(5, "days"),
        kill_criterion="Fewer than 3 of 5 report the problem",
        criterion_recorded_at=T0,
        **ENV,
    )


def sample_hypothesis(statement: str = "Users want faster approvals") -> Hypothesis:
    return Hypothesis.make(statement=statement, tier=Tier.T3, **ENV)


def all_samples() -> dict[str, Node]:
    src = sample_source()
    samples: list[NodeBase] = [
        src,
        sample_span(src),
        sample_claim(),
        Question.make(text="Which is right?", raised_by="contradiction", **ENV),
        sample_hypothesis(),
        sample_test(),
        Decision.make(statement="Go", rationale="Because", **ENV),
        Finding.make(
            critic_id="space_warden",
            check_id="names_feature",
            severity=Severity.BLOCK,
            invariant="I3",
            message="m",
            remedy="r",
            **ENV,
        ),
        Risk.make(text="Slip", likelihood=inp(0.3, "probability"), impact=inp(3, "weeks"), **ENV),
        IncumbentSystem.make(name="Legacy", description="Mainframe", **ENV),
        ProcessModel.make(name="Onboarding", model_kind="as_is", **ENV),
        ProcessStep.make(name="Key in form", actor="clerk", metrics=[inp(12, "minutes")], **ENV),
        Constraint.make(
            text="Retain records for 7 years",
            constraint_kind="regulatory",
            source_doc="policy.pdf",
            locator=Locator(page=3),
            **ENV,
        ),
        Workaround.make(description="Shadow spreadsheet", **ENV),
        Segment.make(name="Claims clerks", description="Back-office staff", **ENV),
        Persona.make(name="Clerk Carla", description="Handles 40 claims", **ENV),
        Adoption.make(stage="early_majority", **ENV),
        Need.make(text="Reduce time to issue a policy", **ENV),
        Ladder.make(description="faster issue -> fewer calls", **ENV),
        NeedHierarchy.make(description="B only after A", **ENV),
        Rating.make(
            dimension="importance",
            value=inp(8, "score"),
            n=inp(12),
            dispersion=inp(1.5, "stdev"),
            tier=Tier.T1,
            evidence_kind=EvidenceKind.CUSTOMER,
            **ENV,
        ),
        Opportunity.make(
            value=Computed(value=15.0, formula_id="ulwick.opportunity.v1", input_ids=[]), **ENV
        ),
        KanoClass.make(classification="must_have", **ENV),
        Alternative.make(name="Spreadsheet", is_incumbent=False, **ENV),
        JourneyStage.make(name="Apply", position=inp(1, "ordinal"), **ENV),
        Touchpoint.make(description="Web form", channel="web", **ENV),
        EmpathyEntry.make(channel="says", text="It takes forever", inferred=False, **ENV),
        ValueProp.make(statement="Issue in minutes", refuses=[], **ENV),
        FeatureIdea.make(text="Auto-fill from prior policy", **ENV),
        FeatureChunk.make(text="Prefill step", **ENV),
        Estimate.make(effort=inp(5, "points"), uncertainty=inp(0.4, "ratio"), **ENV),
        MVPMembership.make(
            in_v1=Computed(value=True, formula_id="mvp.membership.v1", input_ids=[]), **ENV
        ),
        Backbone.make(name="Issue policy", **ENV),
        Story.make(text="As a clerk I can submit a form", **ENV),
        AcceptanceCriterion.make(text="Given a form, when submitted, then a policy exists", **ENV),
        Dependency.make(text="Rating service", dependency_class="system", **ENV),
        Baseline.make(snapshot_hash="b" * 64, gate="G3", **ENV),
        Variance.make(
            change_kind="modified",
            subject_ref="need_aaaaaaaaaaaa",
            baseline_ref="baseline_bbbbbbbbbbbb",
            blast_radius=[],
            severity=Computed(value=1.0, formula_id="variance.severity.v1", input_ids=[]),
            **ENV,
        ),
        BuildPhase.make(name="Phase 1", description="Core", **ENV),
        DeliverySignal.make(source_system="jira", status_text="Done", **ENV),
        Premortem.make(text="It failed because", **ENV),
        Postmortem.make(text="Reconciled", **ENV),
        Partition.make(name="claims", boundary="claims workstream", **ENV),
    ]
    out: dict[str, Node] = {}
    for node in samples:
        assert isinstance(node, tuple(NODE_CLASSES.values()))
        out[node.type] = node  # type: ignore[assignment]
    return out
