"""Checkpoint-B review findings for the I5 mechanism (B1, B2, S6, S7, N1)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from probative.core.projection import blank_strings, prose_runs, unprojected


class Mode(StrEnum):
    FAST = "fast"


class Doc(BaseModel):
    title: str
    reply: str
    detail: str
    mode: Mode
    tally: dict[str, int]


DOC = Doc(title="T", reply="flagged", detail="d", mode=Mode.FAST, tally={"warn": 1, "claim": 2})
LABELS = frozenset({"Findings", "Verdict per check"})


# -- B1: branches keyed on string equality or truthiness are reached ----------------------------


def _render(d: Doc) -> str:
    lines = [f"# {d.title}"]
    lines.append("Flagged items only" if d.reply == "flagged" else "Verdict per check")
    if d.detail:
        lines.append("More detail below")
    return "\n".join(lines)


def test_a_truthiness_branch_is_reached_because_blanks_are_not_empty() -> None:
    assert "More detail below" in unprojected(_render, DOC, LABELS)


def test_a_branch_keyed_on_a_closed_vocabulary_field_is_reached_when_that_field_is_kept() -> None:
    assert "Flagged items only" not in unprojected(_render, DOC, LABELS)  # unreachable blanked
    assert "Flagged items only" in unprojected(_render, DOC, LABELS, keep=frozenset({"reply"}))


def test_keep_leaves_only_the_named_fields_unblanked() -> None:
    b = blank_strings(DOC, keep=frozenset({"reply"}))
    assert (b.reply, b.title, b.detail) == ("flagged", "0", "0")


# -- B2: a stray end tag cannot blind the HTML reader -------------------------------------------


def test_a_stray_end_style_tag_does_not_hide_later_text() -> None:
    runs = prose_runs("<p>a</p></style><p>Totally free sentence</p>", html=True)
    assert "Totally free sentence" in runs and any("stray" in r for r in runs)


def test_a_stray_end_script_tag_does_not_hide_later_text() -> None:
    runs = prose_runs("</script><p>Totally free sentence</p>", html=True)
    assert "Totally free sentence" in runs and any("stray" in r for r in runs)


def test_an_unclosed_script_is_reported() -> None:
    runs = prose_runs("<p>a</p><script>var x = 1;", html=True)
    assert any("unclosed" in r for r in runs)


def test_balanced_script_and_style_are_still_skipped() -> None:
    assert prose_runs("<style>a{}</style><script>x()</script><p>Hi</p>", html=True) == ["Hi"]


# -- S6: a dict key cannot mask template words --------------------------------------------------


def test_template_words_equal_to_a_data_key_are_still_prose() -> None:
    def render(d: Doc) -> str:
        return "Findings warn"  # `warn` is a key of d.tally

    assert unprojected(render, DOC, frozenset({"Findings"})) == ["Findings warn"]


def test_keys_still_render_as_data() -> None:
    def render(d: Doc) -> str:
        return " ".join(f"{k}: {v}" for k, v in sorted(d.tally.items()))

    assert unprojected(render, DOC, frozenset()) == []


# -- S7: more attributes, and symbol verdicts ---------------------------------------------------


def test_every_text_bearing_attribute_is_read() -> None:
    for attr in ("value", "aria-valuetext", "aria-roledescription", "data-note", "summary", "abbr"):
        runs = prose_runs(f'<div {attr}="Free sentence"></div>', html=True)
        assert runs == ["Free sentence"], attr


def test_structural_attributes_are_not_prose() -> None:
    page = (
        '<a href="#section-1" class="btn x" id="top" role="group" lang="en">'
        '<meta content="a b"></a>'
    )
    assert prose_runs(page, html=True) == []


def test_emoji_and_symbol_verdicts_are_runs() -> None:
    assert prose_runs("<p>✅ 🚀</p>", html=True) == ["✅ 🚀"]
    assert prose_runs("| ✅ |\n", html=False) == ["✅"]


def test_plain_glyphs_and_rules_are_still_not_prose() -> None:
    assert prose_runs("| — | ▓▓▓░░ | • |\n|---|---|", html=False) == []


# -- N1: an enum's value is data, whatever its spelling -----------------------------------------


def test_an_enum_value_printed_as_is_is_data() -> None:
    def render(d: Doc) -> str:
        return f"{d.mode.value}"

    assert unprojected(render, DOC, frozenset()) == []
