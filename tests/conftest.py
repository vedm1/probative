"""Shared test fixtures.

The default suite must pass with **no LLM credentials in the environment**
(S3 / CLAUDE.md § Tests run without an API key). This is enforced here, not
left to developer discipline: every test in the default run gets an
environment with every `*_API_KEY` variable removed, regardless of what the
developer's own shell has exported. `addopts = -m "not live"` already keeps
`live`-marked tests out of the default run; this fixture also leaves their
real credentials untouched (in case someone runs `pytest -m live` directly)
by skipping the scrub for any test carrying the `live` marker.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _no_llm_credentials(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    if request.node.get_closest_marker("live") is None:
        for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
            monkeypatch.delenv(key, raising=False)
    yield
