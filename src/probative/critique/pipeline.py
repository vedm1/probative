"""One critique run: extract, judge, collate, build the report (PB9).

Concurrency lives here, not in the critic framework (PB3's `run_critics` stays
sequential; true fan-out is PB12's). Extraction runs one task per (source, pass).
Judging runs one task per shard of at most `batch_size` candidates, each with
its own critic instance (the critics' `stats` are not thread-safe), and the
relational `ConstraintCritic` once. Results are collated in a fixed order, so a
report never depends on which call finished first.

Failure policy, fail closed: a critic that cannot judge a shard, or an
extraction pass that fails after its repair retry, makes the dimensions it feeds
`incomplete` (no rate, no floor, exit code 3). Any other exception, such as a
provider outage, propagates: an all-incomplete report would read as a result.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from probative import __version__
from probative.config import REFERENCE_MODEL
from probative.core.candidates import (
    Candidate,
    CandidateKind,
    ExtractionFailedError,
    ExtractionResult,
)
from probative.core.critic import Finding
from probative.core.evidence import Source
from probative.critics.llm_judge import (
    CriticJudgementError,
    Reply,
    first_sentence,
)
from probative.critique.report import (
    CritiqueReport,
    DimensionResult,
    DocumentSummary,
    ReportFinding,
    RunStats,
    SeverityCounts,
    SkippedFile,
    report_finding,
)
from probative.critique.roster import ROSTER, RosterEntry
from probative.critique.scoring import assess_dimension, severity_counts
from probative.critique.sources import LoadedSource
from probative.extract import FORECAST_PASS, PASSES, SEGMENT_PASS, extract_candidates
from probative.extract.chunking import chunk_windows
from probative.extract.prompts import ExtractionPass
from probative.llm import Provider, TokenUsage

CRITIQUE_PASSES: tuple[ExtractionPass, ...] = (*PASSES, SEGMENT_PASS, FORECAST_PASS)
# ~10k characters: a window's reply is then ~1k tokens, so the windows of one document
# (and the four passes over each) are generated in parallel instead of as one long call.
DEFAULT_WINDOW_CHARS = 10_000
# Measured on the 30-page gate document (PROBATIVE_PHASE_SPECS.md PB9): 32 concurrent calls and
# critic batches of 2 took 64.8 s, against 91.1 s at 16 and 5. The critics were calibrated at
# batch 5; batch 2 judges the same candidates with fewer per call and is unmeasured on the corpora.
DEFAULT_JOBS = 32
DEFAULT_CRITIC_BATCH = 2
_MAX_OUTER_THREADS = 64


@dataclass(frozen=True)
class CritiqueOptions:
    model: str
    jobs: int = DEFAULT_JOBS
    window_chars: int = DEFAULT_WINDOW_CHARS
    # "flagged" because every critic passed the pre-registered rule on held-out
    # (tests/critics/_flagged.py; enforced by test_the_default_reply_follows_the_calibration).
    reply: Reply = "flagged"
    batch_size: int = DEFAULT_CRITIC_BATCH
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    clock: Callable[[], float] = time.monotonic
    tool_version: str = __version__


@dataclass
class _Extracted:
    results: list[ExtractionResult] = field(default_factory=list)
    failed: list[ExtractionPass] = field(default_factory=list)
    calls: int = 0


def _extract(
    source: Source,
    extraction_pass: ExtractionPass,
    provider: Provider,
    model: str,
    window_chars: int,
    executor: Executor,
) -> tuple[ExtractionResult | None, int]:
    try:
        result = extract_candidates(
            source,
            provider,
            model=model,
            max_chars_per_call=window_chars,
            passes=[extraction_pass],
            executor=executor,
        )
    except ExtractionFailedError:
        return None, 0
    return result, len(chunk_windows(source, max_chars=window_chars))


def _merge(source_id: str, results: Sequence[ExtractionResult]) -> ExtractionResult:
    """The passes write disjoint kinds, so merging is concatenation, then sorted."""

    def span_key(c: Any) -> tuple[int, int]:
        return (c.evidence.start, c.evidence.end)

    def cat(attr: str) -> list[Any]:
        return sorted((c for r in results for c in getattr(r, attr)), key=span_key)

    return ExtractionResult(
        source_id=source_id,
        claims=cat("claims"),
        needs=cat("needs"),
        stories=cat("stories"),
        constraints=cat("constraints"),
        dependencies=cat("dependencies"),
        segments=cat("segments"),
        forecasts=cat("forecasts"),
        rejected=[q for r in results for q in r.rejected],
        usage=TokenUsage(
            input_tokens=sum(r.usage.input_tokens for r in results),
            output_tokens=sum(r.usage.output_tokens for r in results),
        ),
    )


def _pool(
    entry: RosterEntry, extractions: Sequence[ExtractionResult], order: dict[str, int]
) -> list[Candidate]:
    pooled = [c for e in extractions for c in e.candidates() if c.kind in entry.feeds]
    return sorted(
        pooled,
        key=lambda c: (order[c.evidence.source_id], c.evidence.start, c.evidence.end, c.kind.value),
    )


@dataclass
class _Judged:
    findings: list[Finding] = field(default_factory=list)
    unjudged: int = 0
    calls: int = 0
    cannot_tell: int = 0
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(input_tokens=0, output_tokens=0))


def _judge(
    entry: RosterEntry,
    candidates: Sequence[Candidate],
    provider: Provider,
    options: CritiqueOptions,
) -> _Judged:
    critic = entry.make(provider, options.model, options.batch_size, options.reply)
    unit = [c for c in candidates if c.kind in entry.subjects]
    out = _Judged()
    try:
        out.findings = critic.check(candidates)
    except CriticJudgementError as error:
        out.findings = list(error.partial_findings)
        out.unjudged = max(1, len(unit))
    stats = getattr(critic, "stats", None)
    if stats is not None:
        out.calls = stats.calls
        out.cannot_tell = getattr(stats, "cannot_tell", 0)
        out.usage = stats.usage
    return out


def _pages(source: Source) -> int | None:
    pages = [r.locator.page for r in source.locator_regions if r.locator.page is not None]
    return max(pages) if pages else None


def run_critique(
    subject: str,
    loaded: Sequence[LoadedSource],
    skipped: Sequence[SkippedFile],
    provider: Provider,
    options: CritiqueOptions,
) -> CritiqueReport:
    started = options.clock()
    sources = {item.source.id: item.source for item in loaded}
    order = {item.source.id: index for index, item in enumerate(loaded)}
    jobs = max(1, options.jobs)

    # `pool` makes the model calls. `outer` only runs the per-(source, pass) calls to
    # `extract_candidates`, which block on `pool` for their windows: keeping them on a
    # separate pool is what stops a waiting task from occupying the worker it waits on.
    outer = ThreadPoolExecutor(max_workers=min(_MAX_OUTER_THREADS, max(1, len(loaded) * 4)))
    with outer, ThreadPoolExecutor(max_workers=jobs) as pool:
        try:
            extraction_futures = [
                (
                    item.source,
                    p,
                    outer.submit(
                        _extract,
                        item.source,
                        p,
                        provider,
                        options.model,
                        options.window_chars,
                        pool,
                    ),
                )
                for item in loaded
                for p in CRITIQUE_PASSES
            ]
            per_source: dict[str, _Extracted] = {sid: _Extracted() for sid in sources}
            for source, extraction_pass, future in extraction_futures:
                result, windows = future.result()
                bucket = per_source[source.id]
                if result is None:
                    bucket.failed.append(extraction_pass)
                else:
                    bucket.results.append(result)
                    bucket.calls += windows
            extractions = [_merge(sid, bucket.results) for sid, bucket in per_source.items()]

            tasks: list[tuple[RosterEntry, list[list[Candidate]]]] = []
            for entry in ROSTER:
                pooled = _pool(entry, extractions, order)
                if not any(c.kind in entry.subjects for c in pooled):
                    tasks.append((entry, []))
                elif entry.shardable:
                    size = options.batch_size
                    tasks.append(
                        (entry, [pooled[i : i + size] for i in range(0, len(pooled), size)])
                    )
                else:
                    tasks.append((entry, [pooled]))
            judge_futures = [
                (entry, shard, pool.submit(_judge, entry, shard, provider, options))
                for entry, shards in tasks
                for shard in shards
            ]
            judged: dict[str, list[_Judged]] = {e.rubric_id: [] for e in ROSTER}
            for entry, _shard, judge_future in judge_futures:
                judged[entry.rubric_id].append(judge_future.result())
        except BaseException:
            # a provider outage must not wait for every queued call to run first
            outer.shutdown(wait=False, cancel_futures=True)
            pool.shutdown(wait=False, cancel_futures=True)
            raise

    candidate_counts = {
        e.source_id: {kind.value: len(getattr(e, _ATTR[kind])) for kind in CandidateKind}
        for e in extractions
    }
    total_subjects = {
        entry.rubric_id: sum(
            counts[k.value] for counts in candidate_counts.values() for k in entry.subjects
        )
        for entry in ROSTER
    }

    dimensions: list[DimensionResult] = []
    for entry in ROSTER:
        results = judged[entry.rubric_id]
        findings = sorted(
            (f for r in results for f in r.findings),
            key=lambda f: _finding_key(f, order),
        )
        critic = entry.make(provider, options.model, options.batch_size, options.reply)
        headlines = {c.id: first_sentence(c.description) for c in critic.rubric.checks}
        rendered: list[ReportFinding] = [
            report_finding(
                f,
                sources[f.evidence.source_id],  # type: ignore[union-attr]
                headline=headlines.get(f.check_id),
            )
            for f in findings
        ]
        failed_feeds = sum(
            1
            for bucket in per_source.values()
            for p in bucket.failed
            if set(p.fields.values()) & set(entry.feeds)
        )
        dimensions.append(
            assess_dimension(
                critic.rubric,
                entry.label,
                checked=total_subjects[entry.rubric_id],
                findings=findings,
                rendered=rendered,
                unjudged=sum(r.unjudged for r in results),
                unextracted=failed_feeds,
                cannot_tell=sum(r.cannot_tell for r in results),
            )
        )

    every = [f for d in dimensions for f in d.findings]
    documents = []
    for item in loaded:
        source = item.source
        rejected = Counter(
            q.reason.value for e in extractions if e.source_id == source.id for q in e.rejected
        )
        documents.append(
            DocumentSummary(
                source_id=source.id,
                file_name=source.path.name,
                format=source.format,
                format_choice=item.format_choice,
                sha256=source.sha256,
                chars=len(source.text),
                pages=_pages(source),
                tier=source.tier.value,
                kind=source.kind.value,
                candidates=candidate_counts[source.id],
                rejected=dict(sorted(rejected.items())),
                counts=severity_counts([f for f in every if f.source_id == source.id]),
            )
        )

    calls = sum(b.calls for b in per_source.values()) + sum(
        r.calls for rs in judged.values() for r in rs
    )
    input_tokens = sum(e.usage.input_tokens for e in extractions) + sum(
        r.usage.input_tokens for rs in judged.values() for r in rs
    )
    output_tokens = sum(e.usage.output_tokens for e in extractions) + sum(
        r.usage.output_tokens for rs in judged.values() for r in rs
    )
    return CritiqueReport(
        generated_at=options.now(),
        tool_version=options.tool_version,
        model=options.model,
        is_reference_model=options.model == REFERENCE_MODEL,
        subject=subject,
        documents=documents,
        dimensions=dimensions,
        totals=severity_counts(every) if every else SeverityCounts(),
        skipped=list(skipped),
        run=RunStats(
            calls=calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            wall_seconds=round(options.clock() - started, 3),
            jobs=jobs,
            reply=options.reply,
        ),
    )


_ATTR = {
    CandidateKind.CLAIM: "claims",
    CandidateKind.NEED: "needs",
    CandidateKind.STORY: "stories",
    CandidateKind.CONSTRAINT: "constraints",
    CandidateKind.DEPENDENCY: "dependencies",
    CandidateKind.SEGMENT: "segments",
    CandidateKind.FORECAST: "forecasts",
}


def _finding_key(finding: Finding, order: dict[str, int]) -> tuple[int, int, int, str, str]:
    ev = finding.evidence
    if ev is None:
        return (0, 0, 0, finding.check_id, finding.target_id or "")
    return (order.get(ev.source_id, 0), ev.start, ev.end, finding.check_id, finding.target_id or "")
