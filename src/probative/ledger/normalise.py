"""One rule for when two statements are the same statement (PB13, D7).

Equal normalised text means one `Claim` node. Case and punctuation are kept:
dropping them would merge statements a reader would call different. Paraphrase
is not handled here (OI41).
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_MARKER = re.compile(r"^(?:[-*•]|\d+[.)])\s+")


def normalise(text: str) -> str:
    folded = _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()
    return _MARKER.sub("", folded, count=1)
