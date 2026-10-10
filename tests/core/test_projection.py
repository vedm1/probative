"""I5: an artifact is a projection. The mechanism, on toy models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from probative.core.projection import blank_strings, normalise_run, prose_runs, unprojected


class Colour(StrEnum):
    RED = "red"


class Row(BaseModel):
    name: str
    n: int


class Doc(BaseModel):
    title: str
    colour: Colour
    rows: list[Row]
    tally: dict[str, int]
    note: str | None = None


DOC = Doc(
    title="Quarterly",
    colour=Colour.RED,
    rows=[Row(name="alpha", n=3), Row(name="beta", n=4)],
    tally={"claim": 2},
    note="hello",
)
LABELS = frozenset({"title", "rows", "# rows", "total", "# total"})


def test_blank_strings_blanks_every_string_leaf_and_nothing_else() -> None:
    b = blank_strings(DOC)
    assert b.title == "0" and b.note == "0" and [r.name for r in b.rows] == ["0", "0"]
    assert b.colour is Colour.RED  # enums are labels, not data
    assert [r.n for r in b.rows] == [3, 4]  # numbers are untouched
    assert list(b.tally) == ["0"] and b.tally["0"] == 2  # data keys become placeholders
    assert DOC.title == "Quarterly"  # the original is untouched


def test_normalise_run_collapses_digits_whitespace_and_edge_punctuation() -> None:
    assert normalise_run("  1 of 2 (50%) ") == "# of # (#%"
    assert normalise_run("3.5s") == "#s"
    assert normalise_run("— total:") == "total"
    assert normalise_run("a   b") == "a b"


def test_a_projection_that_only_uses_labels_and_model_fields_is_clean() -> None:
    def render(d: Doc) -> str:
        rows = "\n".join(f"| {r.name} | {r.n} |" for r in d.rows)
        return f"# {d.title}\n\n| rows | total |\n|---|---:|\n{rows}\n"

    assert unprojected(render, DOC, LABELS) == []


def test_prose_the_model_does_not_contain_is_found() -> None:
    def render(d: Doc) -> str:
        return f"# {d.title}\n\nThis quarter was our best ever.\n"

    assert unprojected(render, DOC, LABELS) == ["This quarter was our best ever"]


def test_a_model_string_cannot_hide_prose_by_matching_a_label() -> None:
    # the renderer says "total" itself, but blanking removes model strings, so
    # the only way "total" can appear is from the template; it is a label here
    def render(d: Doc) -> str:
        return f"{d.title} total"

    assert unprojected(render, DOC, LABELS) == []
    assert unprojected(render, DOC, frozenset()) == ["# total"]


def test_dict_keys_are_data_and_are_allowed() -> None:
    def render(d: Doc) -> str:
        return " ".join(f"{k}: {v}" for k, v in d.tally.items())

    assert unprojected(render, DOC, frozenset()) == []


def test_numbers_and_glyphs_alone_are_not_prose() -> None:
    assert prose_runs("| 12 | 3.5 | — | ▓▓▓░░ | • |\n|---|---:|", html=False) == []


def test_markdown_syntax_is_not_prose() -> None:
    runs = prose_runs("# **Heading**\n\n- `code` and \\*escaped\\*\n\n> quote\n", html=False)
    assert runs == ["Heading", "code and *escaped*", "quote"] or runs == [
        "Heading",
        "code and escaped",
        "quote",
    ]


def test_table_cells_are_separate_runs() -> None:
    assert prose_runs("| Block | Warn |\n|---|---|\n", html=False) == ["Block", "Warn"]


def test_middle_dot_separates_runs() -> None:
    assert prose_runs("3 input tokens · 4 output tokens", html=False) == [
        "# input tokens",
        "# output tokens",
    ]


def test_html_text_is_read_and_script_and_style_are_not() -> None:
    page = (
        "<style>.a{content:'secret prose'}</style><script>var s='more prose';</script>"
        "<p>Hello <b>world</b></p>"
    )
    assert prose_runs(page, html=True) == ["Hello", "world"]


def test_html_attribute_prose_is_read() -> None:
    page = '<div role="group" aria-label="Filter by severity" title="Tip" class="x"></div>'
    assert prose_runs(page, html=True) == ["Filter by severity", "Tip"]


def test_html_entities_are_decoded() -> None:
    assert prose_runs("<p>Fish &amp; chips</p>", html=True) == ["Fish & chips"]


def test_prose_hidden_in_an_html_attribute_is_found() -> None:
    def render(d: Doc) -> str:
        return f'<h1>{d.title}</h1><div aria-label="Our best quarter ever"></div>'

    assert unprojected(render, DOC, LABELS, html=True) == ["Our best quarter ever"]
