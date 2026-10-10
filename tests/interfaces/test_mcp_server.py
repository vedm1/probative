"""PB33: the MCP server over `critique`. No key, no network: an in-memory client
against a server built with a scripted provider, plus one subprocess smoke test
that never reaches a model."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp.client import Client
from mcp.types import CallToolResult

import probative.cli as cli
from probative.config import MissingCredentialsError
from probative.critique import CritiqueOptions, critique
from probative.interfaces.mcp_server import MAX_CONTENT_BYTES, ROOTS_ENV, build_server
from probative.llm import LiteLLMProvider, Provider
from probative.render.markdown import md as md_escape
from probative.render.markdown import render_summary
from tests._recording import replay
from tests.critique._cases import RECORDINGS, case_path, rerecord_hint
from tests.critique._scripted import Scripted

PRD = """# PRD

CLAIM: Conversion drops 12% at the payment step.
NEED: Users need a FLAG one-click checkout button.
NEED: Users want to pay without retyping details.
"""


def _text(result: CallToolResult) -> str:
    return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")


def _table(text: str) -> str:
    """The dimension table: everything in it is computed, none of it is wall-clock."""
    start = text.index("| Dimension")
    end = text.find("\n\n", start)
    return text[start : end if end != -1 else len(text)].rstrip("\n")


def _call(
    server: Any, arguments: dict[str, Any], *, progress: list[float] | None = None
) -> CallToolResult:
    async def go() -> CallToolResult:
        async def on_progress(value: float, total: float | None, message: str | None) -> None:
            assert total is None  # no total is computed anywhere, so none is invented
            assert progress is not None
            progress.append(value)

        async with Client(server) as client:
            return await client.call_tool(
                "critique",
                arguments,
                progress_callback=on_progress if progress is not None else None,
            )

    return asyncio.run(go())


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "root"
    path.mkdir()
    return path


@pytest.fixture
def prd(root: Path) -> Path:
    path = root / "checkout.md"
    path.write_text(PRD, encoding="utf-8")
    return path


def _server(root: Path, provider: Provider | None = None, **kw: Any) -> Any:
    chosen = provider or Scripted()
    return build_server(lambda model: chosen, roots=[root], default_out=root / "reports", **kw)


def test_the_server_lists_critique_and_doctor_with_the_documented_arguments(root: Path) -> None:
    async def go() -> Any:
        async with Client(_server(root)) as client:
            return (await client.list_tools()).tools

    tools = asyncio.run(go())
    assert [t.name for t in tools] == ["critique", "doctor"]  # PB34 added `doctor`
    props = set(tools[0].input_schema["properties"])
    assert props == {"path", "content", "filename", "encoding", "source_format", "format", "out"}
    assert not {"model", "jobs", "batch_size", "tier", "kind"} & props


def test_a_path_call_returns_the_summary_and_the_files(prd: Path, root: Path) -> None:
    result = _call(_server(root), {"path": str(prd)})
    assert not result.is_error
    text = _text(result)
    assert text.startswith("# Probative critique: checkout.md")
    md = root / "reports" / "checkout.critique.md"
    html = root / "reports" / "checkout.critique.html"
    assert f"Full report → {md}" in text and f"Full report → {html}" in text
    assert md.read_text().startswith("# Probative critique: checkout.md")
    assert "<!doctype html>" in html.read_text()


def test_the_result_matches_the_cli_run_on_the_same_input(
    prd: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    monkeypatch.setattr(cli, "_make_provider", lambda model: Scripted())
    out = root / "cli"
    cli_result = CliRunner().invoke(cli.app, ["critique", str(prd), "--out", str(out)])
    assert cli_result.exit_code == 0, cli_result.output
    mcp_text = _text(_call(_server(root), {"path": str(prd)}))
    assert _table(mcp_text) == _table(cli_result.stdout)
    for name in ("checkout.critique.md", "checkout.critique.html"):
        mine = (root / "reports" / name).read_text()
        theirs = (out / name).read_text()
        # only the wall-clock and generation timestamp may differ between two runs
        assert len(mine) == pytest.approx(len(theirs), abs=80)  # sanity only; the table is exact
    assert _table((root / "reports" / "checkout.critique.md").read_text()) == _table(
        (out / "checkout.critique.md").read_text()
    )


def test_format_selects_outputs(prd: Path, root: Path) -> None:
    _call(_server(root), {"path": str(prd), "format": "md"})
    assert (root / "reports" / "checkout.critique.md").exists()
    assert not (root / "reports" / "checkout.critique.html").exists()


def test_inline_text_content(root: Path) -> None:
    result = _call(_server(root), {"content": PRD, "filename": "inline.md"})
    assert not result.is_error
    assert "Probative critique: inline.md" in _text(result)
    assert (root / "reports" / "inline.critique.md").exists()


def test_inline_base64_docx(root: Path, tmp_path: Path) -> None:
    import docx

    document = docx.Document()
    for line in PRD.splitlines():
        document.add_paragraph(line)
    path = tmp_path / "x.docx"
    document.save(str(path))
    result = _call(
        _server(root),
        {
            "content": base64.b64encode(path.read_bytes()).decode(),
            "filename": "spec.docx",
            "encoding": "base64",
        },
    )
    assert not result.is_error, _text(result)
    assert "Probative critique: spec.docx" in _text(result)


def test_inline_temp_dir_is_removed_and_never_named(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    made: list[str] = []
    real = tempfile.mkdtemp

    def spy(*args: Any, **kwargs: Any) -> str:
        made.append(real(*args, **kwargs))
        return made[-1]

    monkeypatch.setattr(tempfile, "mkdtemp", spy)
    ok = _call(_server(root), {"content": PRD, "filename": "inline.md"})
    bad = _call(_server(root), {"content": "x", "filename": "notes.exe"})
    assert len(made) == 2 and not any(Path(d).exists() for d in made)
    assert not any(d in _text(r) for d in made for r in (ok, bad))


def test_a_folder_containing_a_symlink_out_of_the_root_is_refused(
    root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "secret.md"
    outside.write_text("CLAIM: the secret outside the root.\n")
    docs = root / "docs"
    docs.mkdir()
    (docs / "ok.md").write_text(PRD)
    (docs / "leak.md").symlink_to(outside)
    provider = Scripted()
    result = _call(_server(root, provider), {"path": str(docs)})
    assert result.is_error and "outside" in _text(result)
    assert provider.judge_batches == []  # nothing was sent to the model


def test_a_report_target_that_is_a_symlink_is_refused(
    prd: Path, root: Path, tmp_path: Path
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("ORIGINAL")
    reports = root / "reports"
    reports.mkdir()
    (reports / "checkout.critique.md").symlink_to(victim)
    result = _call(_server(root), {"path": str(prd)})
    assert result.is_error
    assert victim.read_text() == "ORIGINAL"


def test_an_out_that_is_a_file_is_a_clean_error(prd: Path, root: Path) -> None:
    blocker = root / "file.txt"
    blocker.write_text("x")
    result = _call(_server(root), {"path": str(prd), "out": str(blocker)})
    assert result.is_error and "Traceback" not in _text(result)


def test_unexpected_errors_do_not_echo_their_message(prd: Path, root: Path) -> None:
    marker = "-".join(
        ["not", "a", "real", "credential"]
    )  # built at runtime: nothing key-shaped in source

    class Leaky:
        def complete_structured(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(f"provider rejected the request: {marker}")

    result = _call(_server(root, Leaky()), {"path": str(prd)})  # type: ignore[arg-type]
    assert result.is_error
    assert marker not in _text(result) and "RuntimeError" in _text(result)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"path": "a.md", "content": "x", "filename": "a.md"},
        {"content": "x"},
        {"content": "x", "filename": ".hidden"},
        {"content": "x", "filename": "a.md", "encoding": "rot13"},
        {"content": "!!!notbase64", "filename": "a.docx", "encoding": "base64"},
        {"content": "x", "filename": "a.md", "format": "pdf"},
        {"content": "x", "filename": "a.md", "source_format": "nonsense"},
        {"content": "x", "filename": "a.exe"},
    ],
)
def test_bad_arguments_are_tool_errors_that_write_nothing(
    root: Path, arguments: dict[str, Any]
) -> None:
    result = _call(_server(root), arguments)
    assert result.is_error
    assert "Traceback" not in _text(result)
    assert not (root / "reports").exists()


def test_a_traversal_filename_is_reduced_to_its_basename(root: Path) -> None:
    result = _call(_server(root), {"content": PRD, "filename": "../../escape.md"})
    assert not result.is_error
    assert (root / "reports" / "escape.critique.md").exists()
    assert (
        not (root.parent / "escape.md").exists() and not (root.parent.parent / "escape.md").exists()
    )


def test_oversize_content_is_refused(root: Path) -> None:
    big = base64.b64encode(b"x" * (MAX_CONTENT_BYTES + 1)).decode()
    result = _call(_server(root), {"content": big, "filename": "big.pdf", "encoding": "base64"})
    assert result.is_error and "20 MB" in _text(result)


def test_paths_outside_the_roots_are_refused(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.md"
    outside.write_text(PRD)
    for bad in (str(outside), str(root / ".." / "secret.md"), "/etc/passwd"):
        result = _call(_server(root), {"path": bad})
        assert result.is_error and "outside" in _text(result)


def test_a_symlink_escaping_the_root_is_refused(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.md"
    outside.write_text(PRD)
    link = root / "link.md"
    link.symlink_to(outside)
    result = _call(_server(root), {"path": str(link)})
    assert result.is_error and "outside" in _text(result)


def test_an_out_directory_outside_the_roots_is_refused(
    prd: Path, root: Path, tmp_path: Path
) -> None:
    result = _call(_server(root), {"path": str(prd), "out": str(tmp_path / "elsewhere")})
    assert result.is_error and "outside" in _text(result)
    assert not (tmp_path / "elsewhere").exists()


def test_an_allowed_out_directory_is_used(prd: Path, root: Path) -> None:
    result = _call(_server(root), {"path": str(prd), "out": str(root / "mine")})
    assert not result.is_error
    assert (root / "mine" / "checkout.critique.md").exists()


def test_a_missing_file_is_a_tool_error(root: Path) -> None:
    result = _call(_server(root), {"path": str(root / "nope.md")})
    assert result.is_error and "nope.md" in _text(result)


def test_an_incomplete_run_is_an_error_that_still_carries_the_summary(
    prd: Path, root: Path
) -> None:
    from probative.extract.prompts import SegmentOutput

    result = _call(_server(root, Scripted(fail_extraction=SegmentOutput)), {"path": str(prd)})
    assert result.is_error
    text = _text(result)
    assert "| Dimension |" in text and "incomplete" in text.lower()


def test_a_missing_key_names_the_vendor_and_never_a_secret(prd: Path, root: Path) -> None:
    def factory(model: str) -> Provider:
        raise MissingCredentialsError("anthropic")

    server = build_server(factory, roots=[root], default_out=root / "reports")
    result = _call(server, {"path": str(prd)})
    assert result.is_error and "anthropic" in _text(result)


def test_progress_is_monotonic_and_ends_at_the_reported_call_count(prd: Path, root: Path) -> None:
    ticks: list[float] = []
    result = _call(_server(root), {"path": str(prd)}, progress=ticks)
    assert not result.is_error
    assert ticks == sorted(ticks) and len(set(ticks)) == len(ticks) and ticks
    calls = int(_text(result).split(" successful model calls")[0].rsplit(" ", 1)[-1])
    assert ticks[-1] == calls


def test_the_recorded_payments_case_replays_through_the_tool(root: Path) -> None:
    results = json.loads((RECORDINGS / "payments" / "results.json").read_text())
    options = CritiqueOptions(
        model=results["model"],
        jobs=results["jobs"],
        reply=results["reply"],
        batch_size=results.get("batch_size", 5),
    )

    def provider() -> Provider:
        return LiteLLMProvider(
            completion_fn=replay(RECORDINGS / "payments", rerecord_hint("payments"))
        )

    prd = case_path("payments", root)
    server = build_server(
        lambda model: provider(),
        roots=[prd.parent.resolve(), root],
        default_out=root / "reports",
        base_options=options,
    )
    result = _call(server, {"path": str(prd), "out": str(root / "o")})
    assert not result.is_error, _text(result)
    direct = critique(prd, provider(), options)
    assert _table(_text(result)) == _table(render_summary(direct.report))
    assert (root / "o" / "prd_payments.critique.md").exists()


def _stdio_env(root: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env[ROOTS_ENV] = str(root)
    return env


def test_probative_mcp_serves_over_stdio_with_no_credentials(tmp_path: Path) -> None:
    from mcp.client.stdio import StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from probative.cli import app; app()", "mcp"],
        env=_stdio_env(tmp_path),
        cwd=tmp_path,
    )

    async def go() -> list[str]:
        async with Client(params) as client:
            return [t.name for t in (await client.list_tools()).tools]

    assert asyncio.run(go()) == ["critique", "doctor"]


def test_stdout_carries_only_json_rpc(tmp_path: Path) -> None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"},
        },
    }
    done = subprocess.run(
        [sys.executable, "-c", "from probative.cli import app; app()", "mcp"],
        input=json.dumps(initialize) + "\n",
        capture_output=True,
        text=True,
        env=_stdio_env(tmp_path),
        cwd=tmp_path,
        timeout=60,
    )
    lines = [line for line in done.stdout.splitlines() if line.strip()]  # initialize only
    assert lines, done.stderr
    assert all(json.loads(line)["jsonrpc"] == "2.0" for line in lines)


def test_roots_come_from_the_environment_else_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from probative.interfaces.mcp_server import roots_from_env

    a, b = tmp_path / "a", tmp_path / "b"
    assert roots_from_env({ROOTS_ENV: f"{a}{os.pathsep}{b}"}) == [a.resolve(), b.resolve()]
    monkeypatch.chdir(tmp_path)
    assert roots_from_env({}) == [tmp_path.resolve()]


def test_a_missing_extra_prints_an_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    for name in [
        n
        for n in sys.modules
        if n == "mcp" or n.startswith(("mcp.", "probative.interfaces.mcp_server"))
    ]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "mcp", None)
    result = CliRunner().invoke(cli.app, ["mcp"])
    assert result.exit_code == cli.EXIT_FAILED
    assert "probative[mcp]" in result.output


# --- gaps recorded in OI28 ---------------------------------------------------------------


def test_the_run_reads_a_snapshot_not_the_original_path(
    prd: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import probative.interfaces.mcp_server as module

    seen: list[tuple[Path, str]] = []
    real = module.critique

    def spy(target: Path, *args: Any, **kwargs: Any) -> Any:
        seen.append((target, target.read_text()))
        return real(target, *args, **kwargs)

    monkeypatch.setattr(module, "critique", spy)
    _call(_server(root), {"path": str(prd)})
    ((target, text),) = seen
    assert (
        target != prd
        and not target.is_relative_to(root)
        and text == PRD
        and target.name == prd.name
    )
    assert not target.exists()  # and the snapshot is gone afterwards


def test_snapshot_refuses_a_file_that_became_a_symlink_out_of_the_root(
    root: Path, tmp_path: Path
) -> None:
    from probative.interfaces.mcp_server import snapshot

    outside = tmp_path / "secret.md"
    outside.write_text("secret")
    link = root / "swapped.md"
    link.symlink_to(outside)
    with pytest.raises(Exception, match="outside"):
        snapshot(link, [root.resolve()], tmp_path / "dest")


def test_skipped_files_keep_their_real_name_in_the_report(root: Path) -> None:
    docs = root / "docs"
    docs.mkdir()
    (docs / "ok.md").write_text(PRD)
    (docs / "image.png").write_bytes(b"\x89PNG")
    text = _text(_call(_server(root), {"path": str(docs)}))
    md = (root / "reports" / "docs.critique.md").read_text()
    assert md_escape(str(docs / "image.png")) in md
    assert "probative-mcp" not in md and "probative-mcp" not in text


def test_a_cancelled_call_stops_spending_and_cleans_up(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic: no sleep decides the outcome. A gate holds the model calls, the test waits
    for the server's own cancel flag to be set (the flag is captured, not timed), then releases
    the gate and asserts that no call began after the cancellation and the temp dir is gone."""
    import tempfile
    import threading
    import types

    from probative.extract.prompts import PASSES
    from probative.interfaces import mcp_server

    body = "# Many\n\n" + "\n".join(f"CLAIM: Claim number {i} stands." for i in range(40)) + "\n"
    (root / "many.md").write_text(body)

    flags: list[threading.Event] = []

    class RecordingEvent(threading.Event):
        def __init__(self) -> None:
            super().__init__()
            flags.append(self)

    # the server creates its cancel flag with `threading.Event()`; capture it
    monkeypatch.setattr(
        mcp_server,
        "threading",
        types.SimpleNamespace(Event=RecordingEvent, Lock=threading.Lock),
    )

    gate = threading.Event()
    started = threading.Event()
    lock = threading.Lock()

    class Gated(Scripted):
        entered = 0
        after_cancel = 0

        def complete_structured(self, *args: Any, **kwargs: Any) -> Any:
            with lock:
                type(self).entered += 1
                if flags and flags[0].is_set():
                    type(self).after_cancel += 1
                if type(self).entered >= len(PASSES):
                    started.set()
            gate.wait(timeout=30)  # a failing test must not hang
            return super().complete_structured(*args, **kwargs)

    provider = Gated()
    made: list[str] = []
    real = tempfile.mkdtemp
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: made.append(real(*a, **k)) or made[-1])

    async def until(condition: Any, what: str) -> None:
        for _ in range(500):  # a deadline, never an expected duration
            if condition():
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f"timed out waiting for {what}")

    async def go() -> None:
        async with Client(_server(root, provider)) as client:
            call = asyncio.create_task(
                client.call_tool("critique", {"path": str(root / "many.md")})
            )
            try:
                await until(started.is_set, "the extraction calls to reach the gate")
                call.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await call
                await until(lambda: bool(flags) and flags[0].is_set(), "the server's cancel flag")
            finally:
                gate.set()
            await until(
                lambda: bool(made) and not any(Path(d).exists() for d in made),
                "the run to finish and remove its temp dir",
            )

    asyncio.run(go())
    assert Gated.entered >= len(PASSES)  # the run really was spending
    assert Gated.after_cancel == 0  # and nothing began once the cancellation was seen


def test_the_filesystem_root_is_refused_and_the_home_directory_is_warned_about(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from probative.interfaces.mcp_server import validate_roots

    with pytest.raises(ValueError, match="filesystem root"):
        validate_roots([Path("/")])
    with caplog.at_level("WARNING"):
        validate_roots([Path.home()])
    assert "home directory" in caplog.text


def test_a_relative_path_resolves_against_whichever_root_holds_it(tmp_path: Path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (second / "spec.md").write_text(PRD)
    server = build_server(lambda m: Scripted(), roots=[first, second], default_out=first / "r")
    result = _call(server, {"path": "spec.md"})
    assert not result.is_error, _text(result)


def test_the_root_check_ignores_letter_case_on_a_case_insensitive_filesystem(
    root: Path,
) -> None:
    swapped = Path(str(root).replace("root", "ROOT"))
    if not swapped.exists():
        pytest.skip("case-sensitive filesystem")
    (root / "a.md").write_text(PRD)
    assert not _call(_server(root), {"path": str(swapped / "a.md")}).is_error


def test_oversize_content_is_refused_before_it_is_decoded(root: Path) -> None:
    result = _call(
        _server(root),
        {
            "content": "A" * (MAX_CONTENT_BYTES * 4 // 3 + 8),
            "filename": "x.pdf",
            "encoding": "base64",
        },
    )
    assert result.is_error and "20 MB" in _text(result)


def test_stdout_stays_json_rpc_through_a_live_run(tmp_path: Path) -> None:
    """A real tool call with progress over stdio: any stray stdout line breaks the client."""
    from mcp.client.stdio import StdioServerParameters

    (tmp_path / "doc.md").write_text(PRD)
    repo = Path(__file__).resolve().parents[2]
    script = "\n".join(
        [
            "import sys",
            f"sys.path.insert(0, {str(repo)!r})",
            "from pathlib import Path",
            "from probative.interfaces.mcp_server import build_server",
            "from tests.critique._scripted import Scripted",
            "r = Path.cwd()",
            "build_server(lambda m: Scripted(), roots=[r], default_out=r / 'o').run('stdio')",
        ]
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", script],
        env=_stdio_env(tmp_path),
        cwd=tmp_path,
    )
    problems: list[Any] = []
    ticks: list[float] = []

    async def go() -> str:
        async def handler(message: Any) -> None:
            if isinstance(message, Exception):
                problems.append(message)

        async def on_progress(value: float, total: float | None, message: str | None) -> None:
            ticks.append(value)

        async with Client(params, message_handler=handler) as client:
            result = await client.call_tool(
                "critique", {"path": str(tmp_path / "doc.md")}, progress_callback=on_progress
            )
            return _text(result)

    text = asyncio.run(go())
    assert text.startswith("# Probative critique: doc.md") and ticks and not problems
