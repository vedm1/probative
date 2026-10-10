"""`doctor` (PB34): what the MCP server itself sees, as a typed report and a fixed rendering.

A client's shell is not the server's environment: a key exported in one may be absent in the
other, and the server's working directory decides its default root. This reports the server's
view and nothing else. It reads no document, makes no model call, and never prints a key, a
key length or a fragment of one. The rendering is fixed lines filled from `DoctorReport`;
every verdict (`ready`, each credential state) is computed here, none is written by a model
(I4, I5).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel

from probative.config import Settings
from probative.llm.factory import (
    PLUGIN_KEY_ENV,
    CredentialState,
    credential_state,
    key_variable,
    value_state,
)

VENDORS = ("anthropic", "openai", "gemini")
Source = Literal["environment", "dotenv", "plugin", "none"]


class VendorCredential(BaseModel):
    vendor: str
    state: CredentialState
    source: Source


class DoctorReport(BaseModel):
    probative_version: str
    python_version: str
    mcp_version: str
    working_directory: str
    roots: list[str]
    root_warnings: list[str]
    default_out: str
    default_model: str
    default_vendor: str | None  # None: the model string has no `vendor/` prefix
    dotenv: str | None
    dotenv_unreadable: bool
    credentials: list[VendorCredential]
    ready: bool


def _version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "unknown"


def configured_model() -> str:
    """The model `Settings` would pick; a `.env` that cannot be read must not stop a diagnosis."""
    try:
        return Settings().model
    except (OSError, ValueError):
        return str(Settings.model_fields["model"].default)


def _dotenv(cwd: Path) -> tuple[Path | None, Mapping[str, str | None], bool]:
    """The `.env` that `Settings` reads from the working directory: its path, its entries
    (names lower-cased, as `Settings` matches them) and whether it could not be read."""
    file = cwd / ".env"
    if not file.is_file():
        return None, {}, False
    try:
        values = dotenv_values(file)
    except (OSError, ValueError):  # UnicodeDecodeError is a ValueError; the message is not kept
        return file, {}, True
    return file, {name.lower(): value for name, value in values.items()}, False


def _credential(
    vendor: str, environ: Mapping[str, str], dotenv: Mapping[str, str | None]
) -> VendorCredential:
    variable = key_variable(vendor)
    from_env = credential_state(vendor, environ)
    if from_env == "set":
        return VendorCredential(vendor=vendor, state="set", source="environment")
    from_file = value_state(dotenv.get(variable.lower())) if variable else "missing"
    if from_file == "set":
        return VendorCredential(vendor=vendor, state="set", source="dotenv")
    if vendor == "anthropic" and value_state(environ.get(PLUGIN_KEY_ENV)) == "set":
        return VendorCredential(vendor=vendor, state="set", source="plugin")
    placeholder = "placeholder" in (
        from_env,
        from_file,
        value_state(environ.get(PLUGIN_KEY_ENV)) if vendor == "anthropic" else "missing",
    )
    return VendorCredential(
        vendor=vendor, state="placeholder" if placeholder else "missing", source="none"
    )


def _root_warnings(roots: Sequence[Path]) -> list[str]:
    warnings: list[str] = []
    for root in roots:
        if not root.exists():
            warnings.append(f"{root} does not exist")
        if root == Path(root.anchor):
            warnings.append(f"{root} is the filesystem root and is refused: name narrower folders")
        elif root == Path.home().resolve():
            warnings.append(
                f"{root} is your home directory: every file in it can be sent to the LLM "
                "provider; a narrower folder is safer"
            )
    return warnings


def diagnose(
    *,
    environ: Mapping[str, str],
    roots: Sequence[Path],
    default_out: Path,
    cwd: Path,
    model: str,
) -> DoctorReport:
    dotenv_file, entries, unreadable = _dotenv(cwd)
    credentials = [_credential(vendor, environ, entries) for vendor in VENDORS]
    vendor = model.split("/", 1)[0] if "/" in model else None
    states = {c.vendor: c.state for c in credentials}
    # A vendor outside the three known ones (a local model) needs no key we can check; a model
    # with no `vendor/` prefix cannot be routed, so it is not ready.
    key_ok = vendor is not None and states.get(vendor, "set") == "set"
    warnings = _root_warnings([Path(root) for root in roots])
    # a root that does not exist, or that allows everything, is not a usable configuration
    blocked = any("does not exist" in w or "is refused" in w for w in warnings)
    return DoctorReport(
        probative_version=_version("probative"),
        python_version=".".join(str(part) for part in sys.version_info[:3]),
        mcp_version=_version("mcp"),
        working_directory=str(cwd),
        roots=[str(root) for root in roots],
        root_warnings=warnings,
        default_out=str(default_out),
        default_model=model,
        default_vendor=vendor,
        dotenv=str(dotenv_file) if dotenv_file else None,
        dotenv_unreadable=unreadable,
        credentials=credentials,
        ready=key_ok and not blocked and not unreadable,
    )


def render_doctor(report: DoctorReport) -> str:
    lines = [
        "# Probative doctor",
        "",
        f"probative {report.probative_version} · python {report.python_version}"
        f" · mcp {report.mcp_version}",
        f"Working directory: {report.working_directory}",
        "",
        "Allowed roots (the only places the tool reads from):",
        *[f"- {root}" for root in report.roots],
        *[f"  warning: {warning}" for warning in report.root_warnings],
        f"Reports are written to: {report.default_out}",
        "",
        f"Default model: {report.default_model}",
        "Credentials:",
    ]
    for credential in report.credentials:
        suffix = f" (from {credential.source})" if credential.state == "set" else ""
        lines.append(f"- {credential.vendor}: {credential.state}{suffix}")
    if report.dotenv_unreadable:
        lines.append(f".env: {report.dotenv} exists but is unreadable (permissions or encoding)")
    else:
        lines.append(f".env: {report.dotenv or 'none in the working directory'}")
    if report.default_vendor is None:
        lines.append(f"The model {report.default_model!r} has no provider prefix (vendor/model).")
    elif report.default_vendor not in VENDORS:
        lines.append(f"no key check for {report.default_vendor}")
    lines.append("")
    if report.ready:
        lines.append("Ready: yes")
    else:
        lines.append("Ready: no. Run /probative:setup")
    return "\n".join(lines) + "\n"
