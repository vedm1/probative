"""The real provider, built from settings (shared by the CLI and the MCP server).

`Settings` reads `.env`, litellm reads `os.environ`, so keys found by `Settings`
are exported (never overriding the environment), and a missing key for a named
vendor fails here, before any call.
"""

from __future__ import annotations

import os

from probative.config import MissingCredentialsError, Settings
from probative.llm.litellm_provider import LiteLLMProvider
from probative.llm.provider import Provider

_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def make_provider(model: str) -> Provider:
    settings = Settings()
    for vendor, variable in _KEYS.items():
        secret = settings.credential_for(vendor) if _has(settings, vendor) else None
        if secret is not None:
            os.environ.setdefault(variable, secret.get_secret_value())
    vendor = model.split("/", 1)[0]
    if vendor in _KEYS and not os.environ.get(_KEYS[vendor]):
        raise MissingCredentialsError(vendor)
    return LiteLLMProvider(num_retries=3, timeout=120.0)


def _has(settings: Settings, vendor: str) -> bool:
    try:
        settings.credential_for(vendor)
    except MissingCredentialsError:
        return False
    return True
