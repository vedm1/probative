from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

import probative.cli as cli
from probative.critique.report import ReportIntegrityError
from tests.critique._scripted import Scripted

runner = CliRunner()

PRD = """# PRD

CLAIM: Conversion drops 12% at the payment step.
NEED: Users need a FLAG one-click checkout button.
NEED: Users want to pay without retyping details.
"""


@pytest.fixture
def prd(tmp_path: Path) -> Path:
    path = tmp_path / "checkout.md"
    path.write_text(PRD, encoding="utf-8")
    return path


def _use(monkeypatch: pytest.MonkeyPatch, provider: Scripted) -> None:
    monkeypatch.setattr(cli, "_make_provider", lambda model: provider)


def test_writes_both_reports_and_prints_the_summary(
    prd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, Scripted())
    out = tmp_path / "out"
    result = runner.invoke(cli.app, ["critique", str(prd), "--out", str(out), "--model", "t/m"])
    assert result.exit_code == 0, result.output
    assert (
        (out / "checkout.critique.md").read_text().startswith("# Probative critique: checkout.md")
    )
    assert "<!doctype html>" in (out / "checkout.critique.html").read_text()
    assert "| Dimension |" in result.stdout
    assert "checkout.critique.html" in result.stdout


def test_format_selects_outputs(prd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, Scripted())
    out = tmp_path / "o"
    result = runner.invoke(cli.app, ["critique", str(prd), "--out", str(out), "--format", "md"])
    assert result.exit_code == 0
    assert [p.name for p in out.iterdir()] == ["checkout.critique.md"]


def test_bad_format_is_a_usage_error(prd: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, Scripted())
    result = runner.invoke(cli.app, ["critique", str(prd), "--format", "pdf"])
    assert result.exit_code == 2


def test_folder_input_names_outputs_after_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, Scripted())
    folder = tmp_path / "specs"
    folder.mkdir()
    (folder / "a.md").write_text(PRD, encoding="utf-8")
    (folder / "b.md").write_text(PRD.replace("PRD", "Other"), encoding="utf-8")
    result = runner.invoke(cli.app, ["critique", str(folder), "--out", str(tmp_path / "o")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "o" / "specs.critique.md").exists()


def test_missing_path_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, Scripted())
    result = runner.invoke(cli.app, ["critique", str(tmp_path / "nope.md")])
    assert result.exit_code == 2 and "nope.md" in result.stderr


def test_nothing_readable_exits_2_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, Scripted())
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    result = runner.invoke(cli.app, ["critique", str(empty), "--out", str(tmp_path / "o")])
    assert result.exit_code == 2
    assert "empty" in result.stderr.lower() and not (tmp_path / "o").exists()


def test_an_incomplete_assessment_exits_3_but_still_writes_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "x.md"
    path.write_text(PRD + "NEED: Users need BROKEN speed.\n", encoding="utf-8")
    _use(monkeypatch, Scripted(omit_for="BROKEN"))
    result = runner.invoke(cli.app, ["critique", str(path), "--out", str(tmp_path / "o")])
    assert result.exit_code == 3
    assert "INCOMPLETE" in (tmp_path / "o" / "x.critique.md").read_text()


def test_a_provider_failure_exits_2_without_writing(
    prd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from probative.extract.prompts import ConstraintOutput

    _use(monkeypatch, Scripted(explode_on=ConstraintOutput))
    result = runner.invoke(cli.app, ["critique", str(prd), "--out", str(tmp_path / "o")])
    assert result.exit_code == 2 and "provider down" in result.stderr
    assert not (tmp_path / "o").exists()


def test_an_integrity_failure_writes_nothing(
    prd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, Scripted())

    def boom(*a: object, **k: object) -> None:
        raise ReportIntegrityError("quote does not match")

    monkeypatch.setattr("probative.critique.verify_report", boom)
    result = runner.invoke(cli.app, ["critique", str(prd), "--out", str(tmp_path / "o")])
    assert result.exit_code == 2 and "quote does not match" in result.stderr
    assert not (tmp_path / "o").exists()


def test_as_must_name_a_forcible_format(prd: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, Scripted())
    result = runner.invoke(cli.app, ["critique", str(prd), "--as", "markdown"])
    assert result.exit_code == 2 and "--as" in result.stderr


def test_missing_credentials_exit_2_before_any_call(
    prd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    result = runner.invoke(
        cli.app, ["critique", str(prd), "--model", "anthropic/claude-sonnet-5", "--out", "o"]
    )
    assert result.exit_code == 2 and "anthropic" in result.stderr and "API_KEY" in result.stderr


def test_dotenv_keys_reach_the_environment_for_litellm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        cli._make_provider("anthropic/claude-sonnet-5")
        assert os.environ["ANTHROPIC_API_KEY"] == "sk-from-dotenv"
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_as_on_a_folder_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, Scripted())
    folder = tmp_path / "f"
    folder.mkdir()
    (folder / "a.md").write_text(PRD, encoding="utf-8")
    result = runner.invoke(cli.app, ["critique", str(folder), "--as", "jira_csv"])
    assert result.exit_code == 2 and "single file" in result.stderr


def test_a_render_failure_leaves_no_partial_output(
    prd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, Scripted())

    def boom(report: object) -> str:
        raise RuntimeError("render failed")

    monkeypatch.setattr(cli, "render_html", boom)
    result = runner.invoke(cli.app, ["critique", str(prd), "--out", str(tmp_path / "o")])
    assert result.exit_code == 2
    assert not (tmp_path / "o").exists()


def test_batch_size_and_window_chars_reach_the_pipeline(
    prd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    real = cli.critique_api.critique

    def spy(path, provider, options, **kw):  # type: ignore[no-untyped-def]
        seen["options"] = options
        return real(path, provider, options, **kw)

    monkeypatch.setattr(cli.critique_api, "critique", spy)
    _use(monkeypatch, Scripted())
    result = runner.invoke(
        cli.app,
        [
            "critique",
            str(prd),
            "--out",
            str(tmp_path / "o"),
            "--batch-size",
            "2",
            "--window-chars",
            "5000",
            "--jobs",
            "32",
        ],
    )
    assert result.exit_code == 0, result.output
    options = seen["options"]
    assert (options.batch_size, options.window_chars, options.jobs) == (2, 5000, 32)  # type: ignore[attr-defined]


def test_defaults_are_unchanged_when_the_flags_are_absent(
    prd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    real = cli.critique_api.critique

    def spy(path, provider, options, **kw):  # type: ignore[no-untyped-def]
        seen["options"] = options
        return real(path, provider, options, **kw)

    monkeypatch.setattr(cli.critique_api, "critique", spy)
    _use(monkeypatch, Scripted())
    runner.invoke(cli.app, ["critique", str(prd), "--out", str(tmp_path / "o")])
    options = seen["options"]
    assert (options.batch_size, options.window_chars, options.jobs) == (2, 10_000, 32)  # type: ignore[attr-defined]


def test_nonpositive_batch_size_is_a_usage_error(
    prd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, Scripted())
    assert runner.invoke(cli.app, ["critique", str(prd), "--batch-size", "0"]).exit_code == 2
    assert runner.invoke(cli.app, ["critique", str(prd), "--window-chars", "0"]).exit_code == 2
