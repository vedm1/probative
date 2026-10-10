"""Derived ids. An id says what a thing *is*; it is never authored."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ID_PATTERN = re.compile(r"^[a-z][a-z_]*_[0-9a-f]{12}$")
ID_REGEX = ID_PATTERN.pattern


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def derive_id(prefix: str, partition: str, identity: Any) -> str:
    digest = hashlib.sha256(
        f"{prefix}\x00{partition}\x00{canonical_json(identity)}".encode()
    ).hexdigest()
    return f"{prefix}_{digest[:12]}"
