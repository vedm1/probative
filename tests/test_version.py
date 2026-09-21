"""`probative --version` prints the packaged version."""

from __future__ import annotations

from typer.testing import CliRunner

from probative import __version__
from probative.cli import app

runner = CliRunner()


def test_version_flag_prints_packaged_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_flag_exits_cleanly() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "probative" in result.stdout.lower()


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])

    # no_args_is_help=True: Click treats a bare invocation as a usage error
    # (exit code 2) but still prints help rather than a bare traceback.
    assert result.exit_code == 2
    assert "usage" in result.stdout.lower()
