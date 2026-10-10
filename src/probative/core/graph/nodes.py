"""Every node type in the evidence graph (docs/DESIGN.md §6.1, plus `Partition`).

Nodes are frozen and their ids are derived from content (`derive_id`), so a
revision is a new node plus a `SUPERSEDES` edge, never an edit (I7). Every node
carries `partition` and `owner` (§6.1, §12). No node holds a bare number: a
number is an `Input` or a `Computed` (I4).

Fields beyond DESIGN's one-line descriptions are PB10's proposals; the phase
that first uses a type may extend it and bump `SCHEMA_VERSION`.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from probative.core.critic import Severity
from probative.core.evidence import EvidenceKind, Locator, SourceFormat, Tier
from probative.core.graph._ids import ID_REGEX, derive_id
from probative.core.graph.values import Computed, Input, Ref, UtcDatetime

_DERIVE = "derive_id"


class NodeBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=ID_REGEX)
    partition: str = Field(default="main", min_length=1)
    owner: str = Field(min_length=1)
    asserted_at: UtcDatetime

    @classmethod
    def type_name(cls) -> str:
        return str(cls.model_fields["type"].default)

    def identity(self) -> Any:
        """What this node *is*; the id is a hash of it. It is the authored
        content: not the id, not `asserted_at` (when it was said is not what was
        said), and not `Computed` values, which are derived from the rest of the
        graph. Were they included, recomputing a confidence would re-id the claim
        and orphan every edge on it. A lifecycle field (`Test.status`) *is*
        content: starting a test is a revision, recorded with `SUPERSEDES`."""
        derived = {n for n, f in type(self).model_fields.items() if f.annotation is Computed}
        return self.model_dump(mode="json", exclude={"id", "asserted_at", *derived})

    @classmethod
    def make(cls, **fields: Any) -> Self:
        """Build a node, deriving its id from the content."""
        return cls.model_validate({"id": "x_000000000000", **fields}, context={_DERIVE: True})

    @model_validator(mode="after")
    def _id_is_derived(self, info: ValidationInfo) -> Self:
        if "type" not in type(self).model_fields:
            raise ValueError(f"{type(self).__name__} has no `type` and cannot be a graph node")
        want = derive_id(self.type_name(), self.partition, self.identity())
        if info.context and info.context.get(_DERIVE):
            object.__setattr__(self, "id", want)
        elif self.id != want:
            raise ValueError(f"id {self.id!r} is not the derived id for this content ({want!r})")
        return self


class GraphLocator(BaseModel):
    """`core.evidence.Locator`, frozen. The ingest `Locator` is mutable, and a
    node's locator must not change after its id was derived."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: int | None = None
    line: int | None = None
    sheet: str | None = None
    cell: str | None = None
    heading_path: tuple[str, ...] | None = None
    issue_key: str | None = None
    field: str | None = None


def _locator_in(v: Any) -> Any:
    return v.model_dump() if isinstance(v, Locator) else v


# -- evidence ---------------------------------------------------------------


class Source(NodeBase):
    """A raw ingested artifact. Holds no text and no absolute path: the file's
    bytes are the source of record, and `graph.json` is portable."""

    type: Literal["source"] = "source"
    ingest_id: str = Field(min_length=1)  # `core.evidence.Source.id`, what `reextract` expects
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    format: SourceFormat
    tier: Tier
    kind: EvidenceKind
    extractor: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    path: str = Field(min_length=1)  # relative to the run's source root

    @field_validator("path")
    @classmethod
    def _relative_and_contained(cls, v: str) -> str:
        parts = v.replace("\\", "/").split("/")
        if (
            "\x00" in v
            or re.match(r"[A-Za-z]:", v)
            or "://" in v
            or "::" in v
            or v.startswith(("/", "\\", "~"))
            or any(p.strip() in ("", ".", "..") for p in parts)
        ):
            raise ValueError(f"source path {v!r} must be a plain relative path inside the run")
        return v

    @model_validator(mode="after")
    def _ingest_id_is_the_one_ingest_derives(self) -> Self:
        if self.ingest_id != f"src_{self.sha256[:16]}":
            raise ValueError(
                "ingest_id must be src_ + the first 16 hex of sha256, as ingest derives it"
            )
        return self


class EvidenceSpan(NodeBase):
    """A located extract: the atom of provenance (I1). `start` and `end` are
    character offsets into the source's normalised text projection (the same
    offsets `core.evidence.EvidenceSpan` uses), not raw file bytes; I1 is checked
    by re-extracting the file and slicing at them."""

    type: Literal["evidence_span"] = "evidence_span"
    source_ref: Ref  # the graph `Source` node
    start: int = Field(ge=0)
    end: int
    text: str
    locator: GraphLocator

    @field_validator("locator", mode="before")
    @classmethod
    def _freeze_locator(cls, v: Any) -> Any:
        return _locator_in(v)

    @model_validator(mode="after")
    def _offsets_match_text(self) -> Self:
        if not (self.start < self.end) or len(self.text) != self.end - self.start:
            raise ValueError(
                f"span ({self.start}, {self.end}) is not coherent with text of length "
                f"{len(self.text)}"
            )
        return self


class Claim(NodeBase):
    """An assertion. Its `basis` is not a field: it is the node's outgoing
    `EVIDENCED_BY` / `DERIVED_FROM` edges, so there is one record of it. A
    `Hypothesis` is a different node type, not a flavour of `Claim`."""

    type: Literal["claim"] = "claim"
    text: str = Field(min_length=1)
    tier: Tier
    evidence_kind: EvidenceKind | None = None
    confidence: Computed  # never authored (§5.3)


class Question(NodeBase):
    type: Literal["question"] = "question"
    text: str = Field(min_length=1)
    status: Literal["open", "resolved"] = "open"
    raised_by: Literal["contradiction", "gap", "elicitation"]


# -- process ----------------------------------------------------------------


class Hypothesis(NodeBase):
    type: Literal["hypothesis"] = "hypothesis"
    statement: str = Field(min_length=1)
    tier: Tier
    status: Literal["untested", "testing", "supported", "killed"] = "untested"


class Test(NodeBase):
    type: Literal["test"] = "test"
    method: str
    cost: Input
    duration: Input
    kill_criterion: str  # written before the test runs (I2)
    criterion_recorded_at: UtcDatetime
    started_at: UtcDatetime | None = None
    status: Literal["planned", "running", "passed", "killed"] = "planned"


class Decision(NodeBase):
    type: Literal["decision"] = "decision"
    statement: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    gate: str | None = None


class Finding(NodeBase):
    """A critic's finding, shape-compatible with `core.critic.Finding`."""

    type: Literal["finding"] = "finding"
    critic_id: str = Field(min_length=1)
    check_id: str = Field(min_length=1)
    severity: Severity
    invariant: str | None = None
    message: str
    remedy: str
    target_id: str | None = None


class Risk(NodeBase):
    type: Literal["risk"] = "risk"
    text: str = Field(min_length=1)
    likelihood: Input
    impact: Input


# -- current state (brownfield) ---------------------------------------------


class IncumbentSystem(NodeBase):
    type: Literal["incumbent_system"] = "incumbent_system"
    name: str = Field(min_length=1)
    description: str = ""


class ProcessModel(NodeBase):
    type: Literal["process_model"] = "process_model"
    name: str = Field(min_length=1)
    model_kind: Literal["as_is", "to_be"]


class ProcessStep(NodeBase):
    type: Literal["process_step"] = "process_step"
    name: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    system: str | None = None
    pain: str | None = None
    metrics: tuple[Input, ...] = ()


class Constraint(NodeBase):
    """Regulatory, contractual or policy obligation. Always sourced (I8): a
    document and a locator, never an inference."""

    type: Literal["constraint"] = "constraint"
    text: str = Field(min_length=1)
    constraint_kind: Literal["regulatory", "contractual", "policy"]
    source_doc: str = Field(min_length=1)
    locator: GraphLocator

    @field_validator("locator", mode="before")
    @classmethod
    def _freeze_locator(cls, v: Any) -> Any:
        return _locator_in(v)


class Workaround(NodeBase):
    type: Literal["workaround"] = "workaround"
    description: str = Field(min_length=1)


# -- problem space ----------------------------------------------------------


class Segment(NodeBase):
    type: Literal["segment"] = "segment"
    name: str = Field(min_length=1)
    description: str = ""


class Persona(NodeBase):
    type: Literal["persona"] = "persona"
    name: str = Field(min_length=1)
    description: str = ""


class Adoption(NodeBase):
    type: Literal["adoption"] = "adoption"
    stage: Literal["innovators", "early_adopters", "early_majority", "late_majority", "laggards"]


class Need(NodeBase):
    """A customer benefit, verb-first, in the customer's voice (I3)."""

    type: Literal["need"] = "need"
    text: str = Field(min_length=1)


class Ladder(NodeBase):
    type: Literal["ladder"] = "ladder"
    description: str = Field(min_length=1)


class NeedHierarchy(NodeBase):
    type: Literal["need_hierarchy"] = "need_hierarchy"
    description: str = Field(min_length=1)


class Rating(NodeBase):
    type: Literal["rating"] = "rating"
    dimension: Literal["importance", "satisfaction"]
    value: Input
    n: Input
    dispersion: Input
    tier: Tier
    evidence_kind: EvidenceKind


class Opportunity(NodeBase):
    """Computed, never authored."""

    type: Literal["opportunity"] = "opportunity"
    value: Computed


class KanoClass(NodeBase):
    type: Literal["kano_class"] = "kano_class"
    classification: Literal["must_have", "performance", "delighter", "indifferent", "reverse"]


class Alternative(NodeBase):
    type: Literal["alternative"] = "alternative"
    name: str = Field(min_length=1)
    is_incumbent: bool = False


class JourneyStage(NodeBase):
    type: Literal["journey_stage"] = "journey_stage"
    name: str = Field(min_length=1)
    position: Input


class Touchpoint(NodeBase):
    type: Literal["touchpoint"] = "touchpoint"
    description: str = Field(min_length=1)
    channel: str = ""


class EmpathyEntry(NodeBase):
    type: Literal["empathy_entry"] = "empathy_entry"
    channel: Literal["says", "thinks", "does", "feels"]
    text: str = Field(min_length=1)
    inferred: bool


# -- solution space ---------------------------------------------------------


class ValueProp(NodeBase):
    type: Literal["value_prop"] = "value_prop"
    statement: str = Field(min_length=1)
    refuses: tuple[Ref, ...] = ()  # Need ids deliberately not served


class FeatureIdea(NodeBase):
    """May reference a `Need` (via ADDRESSES); a `Need` may never reference it (I3)."""

    type: Literal["feature_idea"] = "feature_idea"
    text: str = Field(min_length=1)


class FeatureChunk(NodeBase):
    type: Literal["feature_chunk"] = "feature_chunk"
    text: str = Field(min_length=1)


class Estimate(NodeBase):
    type: Literal["estimate"] = "estimate"
    effort: Input
    uncertainty: Input


class MVPMembership(NodeBase):
    type: Literal["mvp_membership"] = "mvp_membership"
    in_v1: Computed


class Backbone(NodeBase):
    type: Literal["backbone"] = "backbone"
    name: str = Field(min_length=1)


class Story(NodeBase):
    type: Literal["story"] = "story"
    text: str = Field(min_length=1)


class AcceptanceCriterion(NodeBase):
    type: Literal["acceptance_criterion"] = "acceptance_criterion"
    text: str = Field(min_length=1)


# -- continuity -------------------------------------------------------------


class Dependency(NodeBase):
    type: Literal["dependency"] = "dependency"
    text: str = Field(min_length=1)
    dependency_class: Literal["team", "system", "vendor", "data", "legal", "migration"]
    owner_ref: str | None = None


class Baseline(NodeBase):
    """Immutable, content-addressed snapshot (I7). Computing it is PB27."""

    type: Literal["baseline"] = "baseline"
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate: str = Field(min_length=1)


class Variance(NodeBase):
    type: Literal["variance"] = "variance"
    change_kind: Literal["added", "removed", "modified", "reprioritised", "unsupported"]
    subject_ref: Ref
    baseline_ref: Ref
    blast_radius: tuple[Ref, ...] = ()
    severity: Computed
    rationale: str | None = None


class BuildPhase(NodeBase):
    type: Literal["build_phase"] = "build_phase"
    name: str = Field(min_length=1)
    description: str = ""


class DeliverySignal(NodeBase):
    type: Literal["delivery_signal"] = "delivery_signal"
    source_system: str = Field(min_length=1)
    status_text: str = Field(min_length=1)


class Premortem(NodeBase):
    type: Literal["premortem"] = "premortem"
    text: str = Field(min_length=1)


class Postmortem(NodeBase):
    type: Literal["postmortem"] = "postmortem"
    text: str = Field(min_length=1)


# -- federation -------------------------------------------------------------


class Partition(NodeBase):
    """Named scope area with a declared boundary (§12.2). `CLAIMED_BY` targets it."""

    type: Literal["partition"] = "partition"
    name: str = Field(min_length=1)
    boundary: str = ""


Node = Annotated[
    Source
    | EvidenceSpan
    | Claim
    | Question
    | Hypothesis
    | Test
    | Decision
    | Finding
    | Risk
    | IncumbentSystem
    | ProcessModel
    | ProcessStep
    | Constraint
    | Workaround
    | Segment
    | Persona
    | Adoption
    | Need
    | Ladder
    | NeedHierarchy
    | Rating
    | Opportunity
    | KanoClass
    | Alternative
    | JourneyStage
    | Touchpoint
    | EmpathyEntry
    | ValueProp
    | FeatureIdea
    | FeatureChunk
    | Estimate
    | MVPMembership
    | Backbone
    | Story
    | AcceptanceCriterion
    | Dependency
    | Baseline
    | Variance
    | BuildPhase
    | DeliverySignal
    | Premortem
    | Postmortem
    | Partition,
    Field(discriminator="type"),
]

NODE_CLASSES: dict[str, type[NodeBase]] = {
    cls.type_name(): cls
    for cls in (
        Source, EvidenceSpan, Claim, Question, Hypothesis, Test, Decision, Finding, Risk,
        IncumbentSystem, ProcessModel, ProcessStep, Constraint, Workaround, Segment, Persona,
        Adoption, Need, Ladder, NeedHierarchy, Rating, Opportunity, KanoClass, Alternative,
        JourneyStage, Touchpoint, EmpathyEntry, ValueProp, FeatureIdea, FeatureChunk, Estimate,
        MVPMembership, Backbone, Story, AcceptanceCriterion, Dependency, Baseline, Variance,
        BuildPhase, DeliverySignal, Premortem, Postmortem, Partition,
    )
}  # fmt: skip
