"""Probative's command-line entry point.

`--version`, `--help` and `critique` (PB9). Every later phase adds a
subcommand here (`onboard`, `ingest`, `run`, ...) — this module stays the thin
interface over `probative.critique` / `probative.core` /
`probative.graph_runtime`, never a place logic accumulates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

import probative.critique as critique_api
from probative import __version__
from probative.config import MissingCredentialsError, Settings
from probative.core.evidence import EvidenceKind, SourceFormat, Tier
from probative.critique.pipeline import (
    DEFAULT_CRITIC_BATCH,
    DEFAULT_JOBS,
    DEFAULT_WINDOW_CHARS,
    CritiqueOptions,
)
from probative.critique.report import ReportIntegrityError
from probative.critique.sources import DEFAULT_MAX_FILES
from probative.llm.factory import make_provider
from probative.render.html import render_html
from probative.render.markdown import render_markdown, render_summary

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


_FORMATS = ("md", "html")
EXIT_INCOMPLETE = 3
EXIT_FAILED = 2

# Shared with the MCP server; the alias keeps the name tests patch.
_make_provider = make_provider


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(EXIT_FAILED)


@app.command()
def critique(
    path: Annotated[Path, typer.Argument(help="A document, an export, or a folder of them.")],
    out: Annotated[Path, typer.Option(help="Where to write the reports.")] = Path("."),
    format: Annotated[str, typer.Option(help="Comma-separated: md, html.")] = "md,html",
    model: Annotated[str | None, typer.Option(help="Model id; default from settings.")] = None,
    jobs: Annotated[int, typer.Option(min=1, help="Concurrent model calls.")] = DEFAULT_JOBS,
    batch_size: Annotated[
        int,
        typer.Option(min=1, help="Candidates per critic call (calibrated at 5; critique uses 2)."),
    ] = DEFAULT_CRITIC_BATCH,
    window_chars: Annotated[
        int, typer.Option(min=1, help="Characters of document per extraction call.")
    ] = DEFAULT_WINDOW_CHARS,
    tier: Annotated[Tier, typer.Option(help="Recorded, never rendered.")] = Tier.T4,
    kind: Annotated[EvidenceKind, typer.Option(help="Recorded, never rendered.")] = (
        EvidenceKind.DOCUMENTARY
    ),
    as_: Annotated[
        str | None,
        typer.Option("--as", help="Force a tracker or Confluence format instead of detecting it."),
    ] = None,
    max_files: Annotated[int, typer.Option(min=1, help="Folder cap.")] = DEFAULT_MAX_FILES,
) -> None:
    """Score a document: quoted findings per dimension, as Markdown and one HTML file."""
    chosen = [part.strip() for part in format.split(",") if part.strip()]
    if not chosen or any(part not in _FORMATS for part in chosen):
        raise _fail(f"--format takes {', '.join(_FORMATS)}; got {format!r}")
    forced: SourceFormat | None = None
    if as_ is not None:
        try:
            forced = SourceFormat(as_)
        except ValueError:
            raise _fail(f"--as {as_!r} is not a known format") from None
    model_id = model or Settings().model
    try:
        provider = _make_provider(model_id)
        run = critique_api.critique(
            path,
            provider,
            CritiqueOptions(
                model=model_id, jobs=jobs, batch_size=batch_size, window_chars=window_chars
            ),
            tier=tier,
            kind=kind,
            forced=forced,
            max_files=max_files,
        )
    except (
        FileNotFoundError,
        critique_api.NoReadableInputError,
        MissingCredentialsError,
        ReportIntegrityError,
        ValueError,
    ) as error:
        raise _fail(str(error)) from error
    except Exception as error:  # a provider outage, a bug: say what, exit 2
        raise _fail(f"{type(error).__name__}: {error}") from error

    report = run.report
    stem = path.resolve().stem if path.is_file() else path.resolve().name
    # render everything before writing anything: a failure leaves no partial output
    rendered: list[tuple[Path, str]] = []
    try:
        if "md" in chosen:
            rendered.append((out / f"{stem}.critique.md", render_markdown(report)))
        if "html" in chosen:
            rendered.append((out / f"{stem}.critique.html", render_html(report)))
        out.mkdir(parents=True, exist_ok=True)
        for target, text in rendered:
            target.write_text(text, encoding="utf-8")
    except Exception as error:
        raise _fail(f"{type(error).__name__}: {error}") from error
    written = [target for target, _ in rendered]
    typer.echo(render_summary(report))
    for target in written:
        typer.echo(f"Full report → {target}")
    if report.incomplete:
        raise typer.Exit(EXIT_INCOMPLETE)


@app.command()
def mcp() -> None:
    """Serve `critique` to an MCP client over stdio (needs `pip install 'probative[mcp]'`)."""
    try:
        from probative.interfaces.mcp_server import serve
    except ModuleNotFoundError as error:
        if error.name is None or not error.name.startswith("mcp"):
            raise
        typer.echo("error: the MCP server needs the extra: pip install 'probative[mcp]'", err=True)
        raise typer.Exit(EXIT_FAILED) from error
    serve()


if __name__ == "__main__":  # pragma: no cover
    app()
