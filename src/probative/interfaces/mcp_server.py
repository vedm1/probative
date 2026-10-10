"""`probative mcp` (PB33): `critique` as an MCP tool over stdio.

Thin by construction: the tool resolves its input, calls `probative.critique.critique`
(which verifies the report against the source bytes before anything renders) and returns
the CLI's own text, `render_summary(report)` plus the files written. No prose is added here
and no number is produced here (I4, I5).

Two things are specific to being driven by a model rather than a person:

* `path` and `out` must resolve inside the allowed roots (`PROBATIVE_MCP_ROOTS`, default the
  server's working directory), so a prompt-injected document cannot steer the agent into
  sending an arbitrary local file to the LLM provider.
* Progress is a count of completed model calls with no total: no total is computed anywhere.

On stdio, stdout is the protocol channel; nothing in this module prints to it.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import shutil
import tempfile
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import anyio
import anyio.from_thread
import anyio.lowlevel
import anyio.to_thread
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

from probative.config import MissingCredentialsError, Settings
from probative.core.evidence import SourceFormat
from probative.critique import (
    CritiqueOptions,
    NoReadableInputError,
    ReportIntegrityError,
    critique,
)
from probative.llm import Message, Provider, StructuredResult
from probative.llm.types import OutputT
from probative.render.html import render_html
from probative.render.markdown import render_markdown, render_summary

ROOTS_ENV = "PROBATIVE_MCP_ROOTS"
MAX_CONTENT_BYTES = 20 * 1024 * 1024
_FORMATS = ("md", "html")
REPORTS_DIRNAME = "probative-reports"

logger = logging.getLogger(__name__)
ProviderFactory = Callable[[str], Provider]


def roots_from_env(environ: dict[str, str] | None = None) -> list[Path]:
    """Allowed roots: `PROBATIVE_MCP_ROOTS` (os.pathsep-separated), else the working directory."""
    raw = (os.environ if environ is None else environ).get(ROOTS_ENV, "")
    parts = [part for part in raw.split(os.pathsep) if part.strip()]
    return [Path(part).expanduser().resolve() for part in parts] or [Path.cwd().resolve()]


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _inside(path: Path, roots: Sequence[Path]) -> bool:
    """Is `path` (already resolved) under a root? A textual check first, then a filesystem
    check on its nearest existing ancestors, so letter case on a case-insensitive filesystem
    cannot cause a false refusal (an ancestor either is a root or it is not)."""
    if any(path.is_relative_to(root) for root in roots):
        return True
    return any(_same_file(ancestor, root) for ancestor in (path, *path.parents) for root in roots)


def validate_roots(roots: Sequence[Path]) -> list[Path]:
    """Refuse a root that allows everything; warn about one that nearly does."""
    resolved = [root.resolve() for root in roots]
    for root in resolved:
        if root == Path(root.anchor):
            raise ValueError(
                f"{ROOTS_ENV} contains the filesystem root {str(root)!r}; name the folders the "
                "tool may read from instead"
            )
        if root == Path.home().resolve():
            logger.warning(
                "%s contains your home directory %s: every file in it can be sent to the "
                "LLM provider; a narrower folder is safer",
                ROOTS_ENV,
                root,
            )
    return resolved


class RunCancelled(Exception):
    """The client went away; the run stops spending at its next model call."""


def snapshot(source: Path, roots: Sequence[Path], dest: Path) -> Path:
    """Copy `source` (a file, or a folder's non-hidden files) into `dest` and return the copy.

    Each file's resolved path must lie inside a root and is opened without following a final
    symlink, so what the run reads is exactly what was checked: a link swapped in afterwards
    cannot redirect it. Returns the copied file or folder, named as the original."""
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / source.name
    if source.is_file():
        _copy_checked(source, roots, target)
        return target
    target.mkdir()
    for folder, directories, files in os.walk(source, followlinks=False):
        directories[:] = sorted(d for d in directories if not d.startswith("."))
        for name in sorted(files):
            if name.startswith("."):
                continue
            found = Path(folder) / name
            _copy_checked(found, roots, target / found.relative_to(source))
    return target


def _copy_checked(found: Path, roots: Sequence[Path], to: Path) -> None:
    resolved = found.resolve()
    if not _inside(resolved, roots):
        raise ToolError(f"{found.name!r} resolves outside the allowed roots")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as error:
        raise ToolError(f"{found.name!r} could not be read safely") from error
    with os.fdopen(descriptor, "rb") as stream:
        data = stream.read()
    to.parent.mkdir(parents=True, exist_ok=True)
    to.write_bytes(data)


class ProgressProvider:
    """Counts completed model calls and reports each one; once cancelled, makes no more."""

    def __init__(
        self,
        inner: Provider,
        report: Callable[[int], None],
        cancelled: threading.Event | None = None,
    ) -> None:
        self._inner = inner
        self._report = report
        self._cancelled = cancelled or threading.Event()
        self._lock = threading.Lock()
        self._done = 0

    def complete_structured(
        self, messages: list[Message], *, output_model: type[OutputT], model: str
    ) -> StructuredResult[OutputT]:
        if self._cancelled.is_set():
            raise RunCancelled
        result = self._inner.complete_structured(messages, output_model=output_model, model=model)
        with self._lock:
            self._done += 1
            count = self._done
        self._report(count)  # outside the lock: a slow client must not serialise the workers
        return result


class _Request(BaseModel):
    """A validated critique request (everything the tool accepts, checked)."""

    path: Path | None
    content: bytes | None
    filename: str | None
    forced: SourceFormat | None
    formats: list[str]
    out: Path


def _parse_formats(raw: str) -> list[str]:
    chosen = [part.strip() for part in raw.split(",") if part.strip()]
    if not chosen or any(part not in _FORMATS for part in chosen):
        raise ToolError(f"format takes {', '.join(_FORMATS)}; got {raw!r}")
    return chosen


def _decode(content: str, encoding: str) -> bytes:
    limit = MAX_CONTENT_BYTES * 4 // 3 + 4 if encoding == "base64" else MAX_CONTENT_BYTES
    if len(content) > limit:  # before any decode or encode allocates a second copy
        raise ToolError("content is over the 20 MB limit")
    if encoding == "text":
        data = content.encode("utf-8")
    elif encoding == "base64":
        try:
            data = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError):
            raise ToolError("content is not valid base64") from None
    else:
        raise ToolError(f"encoding takes text or base64; got {encoding!r}")
    if len(data) > MAX_CONTENT_BYTES:
        raise ToolError("content is over the 20 MB limit")
    return data


def _safe_filename(raw: str) -> str:
    name = Path(raw.replace("\\", "/")).name
    if not name or name.startswith(".") or name in {".", ".."}:
        raise ToolError(f"filename {raw!r} is not a usable file name")
    return name


def build_server(
    provider_factory: ProviderFactory,
    *,
    roots: Sequence[Path],
    default_out: Path,
    base_options: CritiqueOptions | None = None,
) -> MCPServer:
    """The MCP server. `provider_factory(model)` builds the provider per call, so a missing
    key is a tool error at the moment it matters, never a startup failure."""
    resolved_roots = validate_roots(roots)
    server = MCPServer(
        "probative",
        instructions=(
            "Probative scores a product document (PRD, spec, Jira/ADO export, Confluence page) "
            "and returns findings that each quote the source. Call `critique` with a `path` "
            "or with inline `content` and `filename`; a run takes 30 to 65 seconds."
        ),
    )

    def resolve_inside(raw: str, what: str) -> Path:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            # a relative name belongs to whichever root holds it (else the first root)
            held = [root / path for root in resolved_roots if (root / path).exists()]
            path = held[0] if held else resolved_roots[0] / path
        path = path.resolve()
        if not _inside(path, resolved_roots):
            raise ToolError(f"{what} {raw!r} is outside the allowed roots")
        return path

    def validate(
        path: str | None,
        content: str | None,
        filename: str | None,
        encoding: str,
        source_format: str | None,
        format: str,
        out: str | None,
    ) -> tuple[_Request, bytes | None]:
        if (path is None) == (content is None):
            raise ToolError("give exactly one of `path` or `content`")
        if content is not None and filename is None:
            raise ToolError("`content` needs a `filename` (its extension picks the format)")
        formats = _parse_formats(format)
        forced: SourceFormat | None = None
        if source_format is not None:
            try:
                forced = SourceFormat(source_format)
            except ValueError:
                raise ToolError(f"source_format {source_format!r} is not a known format") from None
        out_dir = resolve_inside(out, "out") if out is not None else default_out.resolve()
        if not _inside(out_dir, resolved_roots):
            raise ToolError(f"out {str(out_dir)!r} is outside the allowed roots")
        data: bytes | None = None
        name: str | None = None
        if content is not None:
            assert filename is not None
            name = _safe_filename(filename)
            data = _decode(content, encoding)
        return (
            _Request(
                path=resolve_inside(path, "path") if path is not None else None,
                content=None,
                filename=name,
                forced=forced,
                formats=formats,
                out=out_dir,
            ),
            data,
        )

    @server.tool(name="critique")
    async def critique_tool(
        ctx: Context,
        path: str | None = None,
        content: str | None = None,
        filename: str | None = None,
        encoding: Literal["text", "base64"] = "text",
        source_format: str | None = None,
        format: str = "md,html",
        out: str | None = None,
    ) -> str:
        """Score a product document (PRD, spec, Jira/ADO export, Confluence page, folder).

        Pass `path` (inside the allowed roots) or inline `content` with a `filename` whose
        extension picks the format (`encoding="base64"` for pdf/docx/xlsx). Returns the
        per-dimension summary and the paths of the Markdown and HTML reports; every finding
        in them quotes the source. Takes 30 to 65 seconds.
        """
        try:
            request, data = validate(path, content, filename, encoding, source_format, format, out)
        except ToolError:
            raise
        loop_progress = _progress_sender(ctx)
        workdir = Path(tempfile.mkdtemp(prefix="probative-mcp-"))
        cancel = threading.Event()
        handed_over = False
        shown = request.path if request.path is not None else request.filename
        target = workdir
        try:
            if data is not None:
                assert request.filename is not None
                target = workdir / request.filename
                target.write_bytes(data)
            else:
                assert request.path is not None
                target = snapshot(request.path, resolved_roots, workdir)  # read once, checked
            handed_over = True
            # The run owns `workdir` from here and removes it when it ends. If the client goes
            # away the call is abandoned and `cancel` stops the run at its next model call.
            summary = await anyio.to_thread.run_sync(
                _run,
                target,
                request,
                _Context(loop_progress, provider_factory, base_options, cancel, workdir, shown),
                abandon_on_cancel=True,
            )
        except ToolError:
            raise
        except (
            FileNotFoundError,
            NoReadableInputError,
            MissingCredentialsError,
            ReportIntegrityError,
            ValueError,
        ) as error:
            message = str(error).replace(str(target), str(shown))
            raise ToolError(message.replace(str(workdir), "upload")) from error
        except Exception as error:
            # A provider's message can carry a key fragment or a response body: the class name
            # goes to the model, the detail to the server's stderr.
            logger.error("critique failed: %s: %s", type(error).__name__, error)
            raise ToolError(
                f"{type(error).__name__}: the run failed; details are in the server log"
            ) from error
        finally:
            cancel.set()  # a finished run ignores it; an abandoned one stops spending
            if not handed_over:
                shutil.rmtree(workdir, ignore_errors=True)
        text, incomplete = summary
        if incomplete:
            raise ToolError(text)
        return text

    return server


def _progress_sender(ctx: Context) -> Callable[[int], None]:
    """A thread-safe `count -> None`; a client that cannot take progress is ignored."""

    # Ticks come from the pipeline's own pool threads, which anyio does not know:
    # the loop is named explicitly.
    token = anyio.lowlevel.current_token()

    def send(count: int) -> None:
        try:
            anyio.from_thread.run(
                ctx.report_progress,
                float(count),
                None,
                f"model calls completed: {count}",
                token=token,
            )
        except Exception:
            return

    return send


@dataclass(frozen=True)
class _Context:
    progress: Callable[[int], None]
    provider_factory: ProviderFactory
    base_options: CritiqueOptions | None
    cancel: threading.Event
    workdir: Path
    shown: Path | str | None


def _run(target: Path, request: _Request, context: _Context) -> tuple[str, bool]:
    try:
        return _run_unowned(target, request, context)
    finally:
        shutil.rmtree(context.workdir, ignore_errors=True)


def _run_unowned(target: Path, request: _Request, context: _Context) -> tuple[str, bool]:
    options = context.base_options or CritiqueOptions(model=Settings().model)
    provider = ProgressProvider(
        context.provider_factory(options.model), context.progress, context.cancel
    )
    run = critique(target, provider, options, forced=request.forced)
    report = run.report
    # skipped paths name the temporary copy; the report should name what the user pointed at
    shown = str(context.shown)
    report = report.model_copy(
        update={
            "skipped": [
                s.model_copy(update={"path": shown + s.path[len(str(target)) :]})
                if s.path.startswith(str(target))
                else s
                for s in report.skipped
            ]
        }
    )
    stem = request.filename and Path(request.filename).stem
    stem = stem or (target.stem if target.is_file() else target.name)
    rendered: list[tuple[Path, str]] = []
    if "md" in request.formats:
        rendered.append((request.out / f"{stem}.critique.md", render_markdown(report)))
    if "html" in request.formats:
        rendered.append((request.out / f"{stem}.critique.html", render_html(report)))
    request.out.mkdir(parents=True, exist_ok=True)
    for file, _ in rendered:
        if file.is_symlink():
            raise ToolError(f"{file.name} in the output folder is a symlink; refusing to write")
    for file, text in rendered:
        _write_atomically(file, text)
    lines = [render_summary(report).rstrip("\n"), ""]
    lines += [f"Full report → {file}" for file, _ in rendered]
    return "\n".join(lines) + "\n", report.incomplete


def _write_atomically(file: Path, text: str) -> None:
    """Replace `file` itself (never what a link at that name points to)."""
    handle, temp_name = tempfile.mkstemp(dir=file.parent, prefix=".probative-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temp_name, file)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def serve() -> None:
    """Run the server on stdio, from the environment (the real provider, `PROBATIVE_MCP_ROOTS`)."""
    from probative.llm.factory import make_provider

    roots = validate_roots(roots_from_env())
    server = build_server(make_provider, roots=roots, default_out=roots[0] / REPORTS_DIRNAME)
    server.run("stdio")


__all__: list[Any] = [
    "MAX_CONTENT_BYTES",
    "ProgressProvider",
    "RunCancelled",
    "build_server",
    "roots_from_env",
    "serve",
    "snapshot",
    "validate_roots",
]
