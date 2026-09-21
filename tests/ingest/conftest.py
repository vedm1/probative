from __future__ import annotations

from pathlib import Path

import pytest

from tests.ingest._paths import FIXTURES


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
