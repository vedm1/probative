"""The real provider, built from settings (shared by the CLI and the MCP server).

`Settings` reads `.env`, litellm reads `os.environ`, so keys found by `Settings`
are exported (never overriding the environment), and a missing key for a named
vendor fails here, before any call.

A value that is still a literal `${...}` is a placeholder a client failed to expand, not a
key: it counts as missing, so the user sees "no credentials" and not a provider rejection.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

from probative.config import MissingCredentialsError, Settings
from probative.llm.litellm_provider import LiteLLMProvider
from probative.llm.provider import Provider

_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

# The Claude plugin delivers its configured key under this name (PB34), so that an unset
# plugin option can never overwrite a key the user already exports as ANTHROPIC_API_KEY.
PLUGIN_KEY_ENV = "PROBATIVE_PLUGIN_ANTHROPIC_KEY"

CredentialState = Literal["set", "missing", "placeholder"]


def key_variable(vendor: str) -> str | None:
    return _KEYS.get(vendor)


def credential_state(vendor: str, environ: Mapping[str, str] | None = None) -> CredentialState:
    """Is a key for `vendor` present in `environ` (default: the process environment)?"""
    variable = _KEYS.get(vendor)
    if variable is None:
        return "missing"
    return value_state((os.environ if environ is None else environ).get(variable))


def value_state(value: str | None) -> CredentialState:
    text = (value or "").strip()
    if not text:
        return "missing"
    return "placeholder" if text.startswith("${") else "set"


def make_provider(model: str) -> Provider:
    _drop_placeholders()  # an unexpanded `${VAR}` must not shadow a key from `.env`
    settings = Settings()
    for vendor, variable in _KEYS.items():
        secret = settings.credential_for(vendor) if _has(settings, vendor) else None
        if secret is not None:
            os.environ.setdefault(variable, secret.get_secret_value())
    _adopt_plugin_key()
    vendor = model.split("/", 1)[0]
    if vendor in _KEYS and credential_state(vendor) != "set":
        raise MissingCredentialsError(vendor)
    return LiteLLMProvider(num_retries=3, timeout=120.0)


def _drop_placeholders() -> None:
    for variable in (*_KEYS.values(), PLUGIN_KEY_ENV):
        if value_state(os.environ.get(variable)) != "set":
            os.environ.pop(variable, None)


def _adopt_plugin_key() -> None:
    """Use the plugin's configured key only when no real Anthropic key is present."""
    plugin_key = os.environ.get(PLUGIN_KEY_ENV)
    if plugin_key and credential_state("anthropic") != "set":
        os.environ[_KEYS["anthropic"]] = plugin_key


def _has(settings: Settings, vendor: str) -> bool:
    try:
        settings.credential_for(vendor)
    except MissingCredentialsError:
        return False
    return True
