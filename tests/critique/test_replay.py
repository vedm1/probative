"""Replays committed full-run recordings through the real `LiteLLMProvider` parse
path (no key, no network) and pins what each case produced. Skipped per case
until a developer has recorded it (S3); the phase's gating check G2 is not met
until these run, not skip. `test_long_run_met_the_sixty_second_gate` pins the
wall-clock the recording took (G1): it is a recorded fact, not a CI timing.
"""

from __future__ import annotations

import json
from html import escape as html_escape
from pathlib import Path
from typing import Any

import pytest

from probative.critique import CritiqueOptions, CritiqueRun, critique
from probative.critique.pipeline import DEFAULT_CRITIC_BATCH, DEFAULT_JOBS, DEFAULT_WINDOW_CHARS
from probative.llm import LiteLLMProvider
from probative.render.html import render_html
from probative.render.markdown import md as md_escape
from probative.render.markdown import render_markdown
from tests._recording import replay
from tests.critique._cases import CASE_NAMES, RECORDINGS, case_path, rerecord_hint


def _results(case: str) -> dict[str, Any] | None:
    path = RECORDINGS / case / "results.json"
    return json.loads(path.read_text()) if path.exists() else None


def _replay_run(case: str, tmp_path: Path, results: dict[str, Any]) -> CritiqueRun:
    provider = LiteLLMProvider(completion_fn=replay(RECORDINGS / case, rerecord_hint(case)))
    return critique(
        case_path(case, tmp_path),
        provider,
        CritiqueOptions(
            model=results["model"],
            jobs=results["jobs"],
            reply=results.get("reply", "full"),  # recordings before `reply` was recorded
            batch_size=results.get("batch_size", 5),
            window_chars=results.get("window_chars", 10_000),
        ),
    )


@pytest.mark.parametrize("case", CASE_NAMES)
def test_replayed_run_equals_the_recorded_one(case: str, tmp_path: Path) -> None:
    results = _results(case)
    if results is None:
        pytest.skip(rerecord_hint(case))
    run = _replay_run(case, tmp_path, results)
    report = run.report
    assert report.incomplete is results["incomplete"]
    assert report.totals.model_dump() == results["totals"]
    for dim in report.dimensions:
        recorded = results["dimensions"][dim.critic_id]
        assert (dim.status.value, dim.checked, dim.flagged) == (
            recorded["status"],
            recorded["checked"],
            recorded["flagged"],
        )
        assert dim.counts.model_dump() == recorded["counts"]
    assert report.run.input_tokens == results["input_tokens"]


@pytest.mark.parametrize("case", CASE_NAMES)
def test_every_finding_has_a_verified_quote_and_a_locator(case: str, tmp_path: Path) -> None:
    results = _results(case)
    if results is None:
        pytest.skip(rerecord_hint(case))
    run = _replay_run(case, tmp_path, results)  # `critique` already verified the report
    for dim in run.report.dimensions:
        for f in dim.findings:
            source = run.sources[f.source_id]
            assert source.text[f.start : f.end] == f.quote
            assert f.locator_label != "location unknown"


@pytest.mark.parametrize("case", CASE_NAMES)
def test_both_renderers_produce_the_recorded_run(case: str, tmp_path: Path) -> None:
    results = _results(case)
    if results is None:
        pytest.skip(rerecord_hint(case))
    report = _replay_run(case, tmp_path, results).report
    md, page = render_markdown(report), render_html(report)
    for dim in report.dimensions:
        for f in dim.findings:
            assert md_escape(f.locator_label) in md
            assert html_escape(f.locator_label) in page


def test_folder_case_reads_three_formats(tmp_path: Path) -> None:
    results = _results("folder")
    if results is None:
        pytest.skip(rerecord_hint("folder"))
    run = _replay_run("folder", tmp_path, results)
    assert sorted(d.format.value for d in run.report.documents) == [
        "confluence_word",
        "jira_csv",
        "markdown",
    ]


# G1' asked for under 60 s. `long` (recorded at the default settings) took 64.8 s; the owner
# accepted that. The target is NOT met; this ceiling is the accepted figure, so a re-recording
# that is slower than what was accepted fails.
G1_TARGET_SECONDS = 60
G1_ACCEPTED_CEILING_SECONDS = 65


def test_long_run_is_within_the_accepted_ceiling_and_is_not_claimed_as_meeting_the_target() -> None:
    results = _results("long")
    if results is None:
        pytest.skip(rerecord_hint("long"))
    assert results["documents"][0]["pages"] == 30
    assert (results["jobs"], results["batch_size"], results["window_chars"]) == (
        DEFAULT_JOBS,
        DEFAULT_CRITIC_BATCH,
        DEFAULT_WINDOW_CHARS,
    ), "the gate case must be recorded at the default settings"
    assert results["wall_seconds"] <= G1_ACCEPTED_CEILING_SECONDS
    if results["wall_seconds"] >= G1_TARGET_SECONDS:
        pytest.xfail(
            f"G1' target {G1_TARGET_SECONDS} s not met: recorded {results['wall_seconds']} s, "
            f"accepted by the owner up to {G1_ACCEPTED_CEILING_SECONDS} s. See OI27 (a)."
        )


@pytest.mark.parametrize("case", ["long_b5j16", "long_j32"])
def test_experiment_runs_are_recorded_facts(case: str) -> None:
    """The same document at earlier settings (16 jobs and batch 5; 32 jobs and batch 5):
    kept to show what batch size 2 bought. Reported, never gating."""
    results = _results(case)
    if results is None:
        pytest.skip(rerecord_hint(case))
    expected = {"long_b5j16": (16, 5), "long_j32": (32, 5)}[case]
    assert (results["jobs"], results.get("batch_size", 5)) == expected
    assert results["wall_seconds"] > G1_ACCEPTED_CEILING_SECONDS  # why batch 2 became the default
