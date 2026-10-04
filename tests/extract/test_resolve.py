"""Quote -> span resolution (extract/resolve.py). The model's quote is only a
search key: the recorded span text always comes from `source.text`."""

from __future__ import annotations

from probative.core.candidates import RejectReason
from probative.core.evidence import EvidenceSpan, Locator
from probative.extract.resolve import resolve_quote
from tests.extract._helpers import make_source

TEXT = (
    "Intro line.\n"
    "Users need to see where their money went.\n"
    "The line  with   odd\nwhitespace stays.\n"
    "Repeated sentence here. Middle. Repeated sentence here. End. Repeated sentence here.\n"
)


def _resolve(
    quote: str,
    *,
    claimed: set[tuple[int, int]] | None = None,
    window: tuple[int, int] | None = None,
    max_quote_chars: int = 500,
    text: str = TEXT,
) -> EvidenceSpan | RejectReason:
    source = make_source(text)
    return resolve_quote(
        source,
        quote,
        window=window or (0, len(text)),
        claimed=claimed if claimed is not None else set(),
        max_quote_chars=max_quote_chars,
    )


def test_exact_match_gives_offsets_and_source_text() -> None:
    result = _resolve("Users need to see where their money went.")
    assert isinstance(result, EvidenceSpan)
    assert TEXT[result.start : result.end] == result.text
    assert result.text == "Users need to see where their money went."
    assert result.source_id == "src_test"


def test_surrounding_whitespace_in_the_quote_is_trimmed() -> None:
    result = _resolve("  Intro line.\n")
    assert isinstance(result, EvidenceSpan)
    assert result.text == "Intro line."


def test_whitespace_variance_resolves_and_returns_the_sources_text() -> None:
    result = _resolve("The line with odd whitespace stays.")
    assert isinstance(result, EvidenceSpan)
    assert result.text == "The line  with   odd\nwhitespace stays."
    assert TEXT[result.start : result.end] == result.text


def test_paraphrase_is_not_found() -> None:
    assert _resolve("Users want to know where money went.") is RejectReason.NOT_FOUND


def test_curly_quote_variance_is_not_found() -> None:
    text = 'She said "yes" to it.'
    assert _resolve("She said “yes” to it.", text=text) is RejectReason.NOT_FOUND


def test_model_imagined_obligation_is_not_found() -> None:
    """I8 unit guard: an obligation that is in the model's head, not the
    document, can never become a candidate."""
    assert _resolve("GDPR Art. 17 applies to this system.") is RejectReason.NOT_FOUND


def test_empty_and_whitespace_only_are_rejected() -> None:
    assert _resolve("") is RejectReason.EMPTY
    assert _resolve("   \n\t ") is RejectReason.EMPTY


def test_over_long_quote_is_rejected_even_if_it_exists() -> None:
    assert _resolve(TEXT.strip(), max_quote_chars=20) is RejectReason.TOO_LONG


def test_repeated_quote_takes_successive_occurrences_then_duplicate() -> None:
    claimed: set[tuple[int, int]] = set()
    spans = []
    for _ in range(3):
        result = _resolve("Repeated sentence here.", claimed=claimed)
        assert isinstance(result, EvidenceSpan)
        claimed.add((result.start, result.end))
        spans.append(result)
    assert [s.start for s in spans] == sorted({s.start for s in spans})
    assert len({s.start for s in spans}) == 3
    assert _resolve("Repeated sentence here.", claimed=claimed) is RejectReason.DUPLICATE


def test_window_restricts_the_search() -> None:
    first = TEXT.index("Repeated sentence here.")
    second = TEXT.index("Repeated sentence here.", first + 1)
    result = _resolve("Repeated sentence here.", window=(second, len(TEXT)))
    assert isinstance(result, EvidenceSpan)
    assert result.start == second
    assert _resolve("Intro line.", window=(second, len(TEXT))) is RejectReason.NOT_FOUND


def test_locator_comes_from_the_region_of_the_first_character() -> None:
    text = "alpha beta\ngamma delta\n"
    regions = [
        (0, 11, Locator(page=1)),
        (11, len(text), Locator(page=2)),
    ]
    source = make_source(text, regions=regions)
    result = resolve_quote(
        source, "beta\ngamma", window=(0, len(text)), claimed=set(), max_quote_chars=500
    )
    assert isinstance(result, EvidenceSpan)
    assert result.locator.page == 1


# --- hardening from the PB4 independent review -------------------------------


def test_whitespace_fallback_never_bridges_a_blank_line() -> None:
    text = "## Needs\n\nUsers need a dashboard.\n\nOther heading\n\nFinance struggles."
    assert _resolve("Needs Users need a dashboard.", text=text) is RejectReason.NOT_FOUND
    stitched = "Users need a dashboard. Other heading Finance struggles."
    assert _resolve(stitched, text=text) is RejectReason.NOT_FOUND


def test_whitespace_fallback_may_bridge_a_single_line_wrap() -> None:
    text = "Users need to see\nwhere their money went.\n"
    result = _resolve("Users need to see where their money went.", text=text)
    assert isinstance(result, EvidenceSpan)
    assert result.text == "Users need to see\nwhere their money went."


def test_fallback_span_longer_than_the_limit_is_too_long() -> None:
    text = "a" + " " * 5000 + "b"
    assert _resolve("a b", text=text, max_quote_chars=500) is RejectReason.TOO_LONG


def test_quote_must_start_and_end_on_word_boundaries() -> None:
    assert _resolve("art", text="a start here") is RejectReason.NOT_FOUND
    assert _resolve("cat sat", text="a concat  sat here") is RejectReason.NOT_FOUND
    ok = _resolve("start", text="a start here")
    assert isinstance(ok, EvidenceSpan)


def test_punctuation_only_quote_has_nothing_to_quote() -> None:
    assert _resolve(".", text="Hello. World.") is RejectReason.EMPTY
    assert _resolve("--", text="a -- b") is RejectReason.EMPTY
