"""Probative's command-line entry point.

PB0 ships only `--version` and `--help`. Every later phase adds a
subcommand here (`critique`, `onboard`, `ingest`, `run`, ...) — this module
stays the thin interface over `probative.core` / `probative.graph_runtime`,
never a place logic accumulates.
"""

from __future__ import annotations

import typer

from probative import __version__

app = typer.Typer(
    name="probative",
    help="Evidence-grounded product discovery. Every claim cites its source "
    "or is labelled a hypothesis with a test attached.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"probative {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed version and exit.",
    ),
) -> None:
    """Probative."""


if __name__ == "__main__":  # pragma: no cover
    app()
