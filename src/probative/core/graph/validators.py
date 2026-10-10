"""Deterministic invariant validators: I1, I2 and the shape half of I4.

These judge a graph (or a graph a patch would produce) without a model. They
return `Violation`s rather than raising, so a `Committer` (PB12) can collect
every problem with a proposed patch at once. Ordering is fixed, so the same
graph always yields the same list. Messages name graph ids and source-relative
paths, never the absolute source root.

I1  No orphan claims. A `Claim` has an `EVIDENCED_BY` edge or it is a violation:
    a `Hypothesis` is a different node type, so there is no third category. A
    T4 claim has no span of its own; it is grounded only if it is derived from a
    claim that is. Simulated (T5) evidence is quarantined (DESIGN §5.5): it can
    ground only a T5 claim and no T4 claim can rest on it. Every `EvidenceSpan`
    must re-extract to its recorded text, by its format's own re-extractor.
I2  Every `Hypothesis` has a `TESTED_BY` edge to a complete `Test` whose kill
    criterion was recorded no later than the test started; a test that has run
    says when it started.
I4  Recomputing a `Computed` value is PB11's `FormulaValidator`. Here we check
    only what can be checked without a formula: every named input exists.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from probative.core.evidence import EvidenceSpan as CoreSpan
from probative.core.evidence import (
    IngestError,
    Locator,
    SourceFormat,
    StaleNormalizationError,
    Tier,
)
from probative.core.evidence import Source as CoreSource
from probative.core.graph.edges import EdgeType
from probative.core.graph.graph import Graph
from probative.core.graph.nodes import Claim, EvidenceSpan, Hypothesis, NodeBase, Source, Test
from probative.core.graph.values import Computed
from probative.ingest import reextract
from probative.ingest.confluence import reextract_confluence
from probative.ingest.tracker import reextract_tracker

_TRACKER = {
    SourceFormat.JIRA_CSV,
    SourceFormat.JIRA_HTML,
    SourceFormat.JIRA_XML,
    SourceFormat.ADO_CSV,
}


@dataclass(frozen=True)
class Violation:
    invariant: str
    code: str
    node_id: str
    message: str


def validate_graph(graph: Graph, *, source_root: Path) -> list[Violation]:
    """Every I1, I2 and I4-shape violation in `graph`. `source_root` is the
    directory the graph's `Source.path` values are relative to."""
    found = [
        *_i1_claims(graph),
        *_i1_spans(graph, source_root),
        *_i2(graph),
        *_i4_inputs(graph),
    ]
    return sorted(found, key=lambda v: (v.invariant, v.code, v.node_id))


def unverified_computed(graph: Graph) -> list[tuple[str, str, str]]:
    """`(node_id, field, formula_id)` for every `Computed` value. Until PB11
    registers the formula and recomputes it, none of these is verified."""
    return sorted(
        (node.id, name, value.formula_id)
        for node in graph.nodes.values()
        for name, value in _computed_fields(node)
    )


def _computed_fields(node: NodeBase) -> list[tuple[str, Computed]]:
    return [
        (name, value)
        for name in type(node).model_fields
        if isinstance(value := getattr(node, name), Computed)
    ]


# -- I1: claims ----------------------------------------------------------------


def _i1_claims(graph: Graph) -> list[Violation]:
    claims = [n for n in graph.nodes.values() if isinstance(n, Claim)]
    by_id = {c.id: c for c in claims}
    grounded = {c.id for c in claims if graph.out_edges(c.id, EdgeType.EVIDENCED_BY)}
    changed = True
    while changed:  # a T4 claim is grounded once a non-simulated claim it derives from is
        changed = False
        for c in claims:
            if c.id in grounded or c.tier is not Tier.T4:
                continue
            parents = [by_id.get(e.dst) for e in graph.out_edges(c.id, EdgeType.DERIVED_FROM)]
            if any(p is not None and p.id in grounded and p.tier is not Tier.T5 for p in parents):
                grounded.add(c.id)
                changed = True
    out: list[Violation] = []
    for c in claims:
        if c.id not in grounded:
            if c.tier is Tier.T4 and not graph.out_edges(c.id, EdgeType.DERIVED_FROM):
                out.append(
                    Violation("I1", "I1_T4_LEAF", c.id, "A T4 claim must derive from its parents")
                )
            else:
                out.append(
                    Violation(
                        "I1",
                        "I1_ORPHAN_CLAIM",
                        c.id,
                        "A claim needs evidence, or it is a hypothesis",
                    )
                )
            continue
        for edge in graph.out_edges(c.id, EdgeType.EVIDENCED_BY):
            span = graph.nodes[edge.dst]
            source = graph.nodes.get(span.source_ref) if isinstance(span, EvidenceSpan) else None
            if not isinstance(source, Source):
                continue  # reported against the span (I1_SPAN_UNRESOLVED)
            # a T4 claim may cite any real source, never a simulated one; every
            # other tier must cite a source of its own tier
            bad = source.tier is Tier.T5 if c.tier is Tier.T4 else source.tier is not c.tier
            if bad:
                out.append(
                    Violation(
                        "I1",
                        "I1_TIER_MISMATCH",
                        c.id,
                        f"claim is {c.tier.value} but rests on a {source.tier.value} source",
                    )
                )
                break
    return out


# -- I1: spans ---------------------------------------------------------------


def _reextractor(fmt: SourceFormat) -> Callable[[CoreSource, CoreSpan], str]:
    if fmt in _TRACKER:
        return reextract_tracker
    if fmt is SourceFormat.CONFLUENCE_WORD:
        return reextract_confluence
    return reextract


def _i1_spans(graph: Graph, source_root: Path) -> list[Violation]:
    by_source: dict[str, list[EvidenceSpan]] = {}
    out: list[Violation] = []
    for node in graph.nodes.values():
        if isinstance(node, EvidenceSpan):
            by_source.setdefault(node.source_ref, []).append(node)
    root = source_root.resolve()
    for ref, spans in sorted(by_source.items()):
        source = graph.nodes.get(ref)

        def fail(code: str, why: str, *, _spans: list[EvidenceSpan] = spans) -> None:
            out.extend(Violation("I1", code, s.id, why) for s in _spans)

        if not isinstance(source, Source):
            fail("I1_SPAN_UNRESOLVED", f"source {ref} is not a Source in the graph")
            continue
        try:
            path = (root / source.path).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                fail(
                    "I1_SPAN_UNRESOLVED", f"source file {source.path} is not under the source root"
                )
                continue
            recorded_bytes = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            fail("I1_SPAN_UNRESOLVED", f"source file {source.path} cannot be read")
            continue
        if recorded_bytes != source.sha256:
            fail("I1_SOURCE_CHANGED", f"{source.path} no longer has the recorded bytes")
            continue
        core = CoreSource(
            id=source.ingest_id,
            path=path,
            sha256=source.sha256,
            format=source.format,
            tier=source.tier,
            kind=source.kind,
            ingested_at=source.asserted_at,
            extractor=source.extractor,
            extractor_version=source.extractor_version,
            text="",
            locator_regions=[],
        )
        lo, hi = min(s.start for s in spans), max(s.end for s in spans)
        try:  # one re-extraction per source: the hull covers every span
            fresh = _reextractor(source.format)(
                core, CoreSpan(source_id=core.id, start=lo, end=hi, text="", locator=Locator())
            )
        except StaleNormalizationError:
            fail(
                "I1_STALE_NORMALISATION", f"normalisation of {source.path} changed since ingestion"
            )
            continue
        except (IngestError, OSError) as err:
            fail(
                "I1_SPAN_UNRESOLVED", f"{source.path} cannot be re-extracted ({type(err).__name__})"
            )
            continue
        for s in spans:
            if fresh[s.start - lo : s.end - lo] != s.text:
                out.append(
                    Violation(
                        "I1", "I1_SPAN_MISMATCH", s.id, "re-extraction does not reproduce the text"
                    )
                )
    return out


# -- I2 ----------------------------------------------------------------------


def _is_blank(text: str) -> bool:
    """Nothing a reader can see: whitespace, zero-width and other format characters."""
    return all(ch.isspace() or unicodedata.category(ch) in {"Cf", "Cc", "Zs"} for ch in text)


def _i2(graph: Graph) -> list[Violation]:
    out: list[Violation] = []
    for node in graph.nodes.values():
        if isinstance(node, Hypothesis) and not graph.out_edges(node.id, EdgeType.TESTED_BY):
            out.append(Violation("I2", "I2_NO_TEST", node.id, "A hypothesis needs a test"))
        elif isinstance(node, Test):
            missing = [
                label
                for label, bad in (
                    ("method", _is_blank(node.method)),
                    ("kill criterion", _is_blank(node.kill_criterion)),
                    ("cost", node.cost.value < 0),
                    ("duration", node.duration.value <= 0),
                    ("start time", node.status != "planned" and node.started_at is None),
                )
                if bad
            ]
            if missing:
                out.append(
                    Violation(
                        "I2",
                        "I2_TEST_INCOMPLETE",
                        node.id,
                        f"A test states its method, cost, duration and kill criterion: {missing}",
                    )
                )
            if node.started_at is not None and node.criterion_recorded_at > node.started_at:
                out.append(
                    Violation(
                        "I2",
                        "I2_CRITERION_AFTER_START",
                        node.id,
                        "The kill criterion was recorded after the test started",
                    )
                )
    return out


# -- I4 (shape) --------------------------------------------------------------


def _i4_inputs(graph: Graph) -> list[Violation]:
    return [
        Violation(
            "I4", "I4_DANGLING_INPUT", node.id, f"{name} names {ref}, which is not in the graph"
        )
        for node in graph.nodes.values()
        for name, value in _computed_fields(node)
        for ref in value.input_ids
        if ref not in graph.nodes
    ]
