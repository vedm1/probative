"""Measurement of ConstraintCritic over `TraceCorpus` (PB7).

Counts are per *constraint*, because a document mixes traced and untraced ones
and both kinds of error matter: an untraced constraint that is passed (a false
trace: the dangerous one for a blocking critic) and a traced constraint that is
flagged (a false block)."""

from __future__ import annotations

from typing import Any

from probative.critics.constraint_critic import ConstraintCritic
from tests.critics._candidates import load_fixture
from tests.critics._trace_corpus import TraceCorpus, TraceDoc, parse_trace_doc


def _stats(critic: ConstraintCritic) -> dict[str, Any]:
    stats = critic.stats
    return {
        "calls": stats.calls,
        "usage": stats.usage.model_dump(),
        "traced": stats.traced,
        "untraced": stats.untraced,
        "missing": stats.missing,
        "unknown_ids": stats.unknown_ids,
        "unverified_links": stats.unverified_links,
        "no_story_docs": stats.no_story_docs,
    }


def _run(critic: ConstraintCritic, doc: TraceDoc) -> tuple[set[str], int]:
    result = critic.check_with_traces(doc.candidates)
    return {str(f.target_id) for f in result.findings}, len(result.links)


def measure_trace(corpus: TraceCorpus, split: str, critic: ConstraintCritic) -> dict[str, Any]:
    seeded: list[dict[str, Any]] = []
    for path in corpus.files("seeded", split):
        doc = parse_trace_doc(path)
        flagged, links = _run(critic, doc)
        expected = doc.expect_untraced
        seeded.append(
            {
                "file": path.name,
                "kind": load_fixture(path)["kind"],
                "constraints": len(doc.constraints),
                "expect_untraced": len(expected),
                "caught": len(flagged & expected),
                "caught_all": expected <= flagged,
                "flagged_traced": len(flagged - expected),  # false blocks inside a seeded doc
                "links": links,
            }
        )
    clean: list[dict[str, Any]] = []
    for path in corpus.files("clean", split):
        doc = parse_trace_doc(path)
        flagged, links = _run(critic, doc)
        clean.append(
            {
                "file": path.name,
                "constraints": len(doc.constraints),
                "flagged_constraints": len(flagged),
                "links": links,
            }
        )
    return {
        "critic": critic.rubric.id,
        "split": split,
        "seeded": {
            "documents": len(seeded),
            "documents_caught_all": sum(r["caught_all"] for r in seeded),
            "untraced_constraints": sum(r["expect_untraced"] for r in seeded),
            "caught": sum(r["caught"] for r in seeded),
            "traced_constraints": sum(r["constraints"] - r["expect_untraced"] for r in seeded),
            "flagged_traced": sum(r["flagged_traced"] for r in seeded),
            "files": seeded,
        },
        "clean": {
            "documents": len(clean),
            "constraints": sum(r["constraints"] for r in clean),
            "flagged_constraints": sum(r["flagged_constraints"] for r in clean),
            "files": clean,
        },
        "judge_stats": _stats(critic),
    }


def measure_trace_stress(corpus: TraceCorpus, critic: ConstraintCritic) -> dict[str, Any]:
    """Hard cases: every `expect_untraced` constraint flagged, and nothing outside
    `expect_untraced` plus `allow_also_untraced`. Reported, never gating, never
    tuned on. 'As expected' is lenient by design: a case labelled defensible either
    way allows the flag without requiring it."""
    rows: list[dict[str, Any]] = []
    for path in corpus.stress_files():
        data = load_fixture(path)
        doc = parse_trace_doc(path)
        flagged, links = _run(critic, doc)
        by_id = {c.id: c.evidence.text for c in doc.constraints}
        rows.append(
            {
                "file": path.name,
                "expect_untraced": sorted(by_id[i] for i in doc.expect_untraced),
                "allow_also_untraced": sorted(by_id[i] for i in doc.allow_untraced),
                "flagged": sorted(by_id[i] for i in flagged),
                "links": links,
                "as_expected": doc.expect_untraced
                <= flagged
                <= doc.expect_untraced | doc.allow_untraced,
                "why": data["why"],
            }
        )
    return {
        "critic": critic.rubric.id,
        "n": len(rows),
        "as_expected": sum(r["as_expected"] for r in rows),
        "files": rows,
        "judge_stats": _stats(critic),
    }
