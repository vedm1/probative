"""I5: every artifact is a projection. How that is checked.

A renderer has no free-text slot if everything it prints is either a field of
the model it was given or a fixed label. `unprojected` makes that testable: it
replaces every string in the model with a non-word sentinel, renders, and
returns whatever *text* is left. What is left can only have come from the
template, so each piece must be in a reviewed allowlist of labels; a sentence
added to a renderer then fails until someone adds it to that list, where a
reviewer sees it.

Choices that decide what the check can see:

* Strings become `"0"`, not `""`, so a branch guarded by `if text:` is taken.
* A branch guarded by *equality* on a string (`reply == "flagged"`) is not
  reached by a sentinel. Name such fields in `keep` and they are left as they
  are; render a model per value to reach each branch.
* Mapping keys are data (a count by kind, say). Each distinct key becomes a
  digit placeholder, so it renders as a number and cannot mask a template word.
  Field names are not keys.
* An enum's value printed as-is is data; an enum mapped to a label is template.

Limits, by design: it sees the branches the models you pass exercise; it
checks words and symbols, not numbers (numbers are I4's: `critique.verify`);
it reads rendered text and text-bearing HTML attributes, not CSS or script
bodies, which the HTML renderer pins by hash.

The blanked copy is rebuilt through the model's own validation, so this works
for report-shaped models whose integrity checks live in a builder. A model with
pattern-constrained strings (graph nodes) cannot be blanked this way.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from enum import Enum
from html.parser import HTMLParser
from typing import Any

from pydantic import BaseModel

BLANK = "0"

_DIGITS = re.compile(r"\d[\d.,]*")
_EDGE = " \t\n:;,.·•—–-()[]{}“”\"'…"  # noqa: RUF001
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_SYMBOL_BLOCKS = ((0x2600, 0x27BF), (0x1F000, 0x1FAFF))  # misc symbols, dingbats, emoji
# Attributes that are structure or machine tokens. Every other attribute is read as text.
_NOT_TEXT = frozenset(
    {
        "class", "id", "role", "type", "href", "src", "lang", "charset", "name", "rel", "for",
        "tabindex", "hidden", "open", "style", "width", "height", "viewbox", "d", "fill",
        "stroke", "x", "y", "cx", "cy", "r", "xmlns", "target", "colspan", "rowspan", "scope",
        "aria-hidden", "aria-expanded", "aria-controls", "aria-labelledby", "aria-describedby",
        "aria-live", "aria-pressed", "aria-selected", "aria-current", "http-equiv",
    }
)  # fmt: skip


class _Map(dict[str, Any]):
    """A real mapping in the model, as opposed to a model turned into a dict."""


def _tree(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return {n: _tree(getattr(value, n)) for n in type(value).model_fields}
    if isinstance(value, dict):
        return _Map({k: _tree(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return [_tree(v) for v in value]
    return value


def _map_keys(tree: Any, into: dict[str, str]) -> None:
    if isinstance(tree, _Map):
        for k in tree:
            into.setdefault(k, str(len(into)))
    if isinstance(tree, dict):
        for v in tree.values():
            _map_keys(v, into)
    elif isinstance(tree, list):
        for v in tree:
            _map_keys(v, into)


def _blank(tree: Any, keep: frozenset[str], keys: dict[str, str], field: str | None = None) -> Any:
    if isinstance(tree, Enum):  # a member is a label, not data
        return tree
    if isinstance(tree, str):
        return tree if field in keep else BLANK
    if isinstance(tree, _Map):
        return {keys[k]: _blank(v, keep, keys) for k, v in tree.items()}
    if isinstance(tree, dict):
        return {k: _blank(v, keep, keys, k) for k, v in tree.items()}
    if isinstance(tree, list):
        return [_blank(v, keep, keys, field) for v in tree]
    return tree


def blank_strings[M: BaseModel](model: M, *, keep: frozenset[str] = frozenset()) -> M:
    """A copy of `model` with every string value replaced by `"0"`.

    Enum members, numbers and the strings of fields named in `keep` stay as
    they are; mapping keys become digit placeholders.
    """
    tree = _tree(model)
    keys: dict[str, str] = {}
    _map_keys(tree, keys)
    return type(model).model_validate(_blank(tree, keep, keys))


def _enum_types(value: Any) -> set[type[Enum]]:
    if isinstance(value, Enum):
        return {type(value)}
    if isinstance(value, BaseModel):
        return set().union(*(_enum_types(getattr(value, n)) for n in type(value).model_fields))
    if isinstance(value, dict):
        return set().union(*(_enum_types(v) for v in value.values()), set())
    if isinstance(value, list | tuple):
        return set().union(*(_enum_types(v) for v in value), set())
    return set()


def normalise_run(run: str) -> str:
    """The form in which a piece of template text is compared: digit runs are
    `#` (a count is not prose), whitespace is collapsed, edge punctuation goes."""
    flat = " ".join(run.split())
    return _DIGITS.sub("#", flat).strip(_EDGE)


def _is_prose(run: str) -> bool:
    """Words, or a symbol that can carry a verdict. Digits, bars and rules are not."""
    return any(ch.isalpha() or any(lo <= ord(ch) <= hi for lo, hi in _SYMBOL_BLOCKS) for ch in run)


def _runs(pieces: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for piece in pieces:
        for part in piece.split("·"):
            run = normalise_run(part)
            if _is_prose(run):
                seen.setdefault(run)
    return list(seen)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pieces: list[str] = []
        self._open: list[str] = []  # script/style elements currently open

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._open.append(tag)
        if tag != "meta":  # meta content is machine configuration, never displayed
            self.pieces += [v for k, v in attrs if k not in _NOT_TEXT and v]

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            if self._open and self._open[-1] == tag:
                self._open.pop()
            else:  # an end tag with no start must not change what is hidden
                self.pieces.append(f"stray end tag {tag}")

    def handle_data(self, data: str) -> None:
        if not self._open and data.strip():
            self.pieces.append(data)

    def close(self) -> None:
        super().close()
        self.pieces += [f"unclosed {tag} element" for tag in self._open]


def _markdown_pieces(text: str) -> list[str]:
    pieces: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(#{1,6}\s+|[-*+]\s+|>\s*)", "", line)
        for cell in _UNESCAPED_PIPE.split(line):
            cell = cell.replace("**", "").replace("`", "")
            pieces.append(re.sub(r"\\(.)", r"\1", cell))
    return pieces


def prose_runs(rendered: str, *, html: bool) -> list[str]:
    """The pieces of text in `rendered`, normalised, in order of first appearance."""
    if html:
        parser = _Text()
        parser.feed(rendered)
        parser.close()
        return _runs(parser.pieces)
    return _runs(_markdown_pieces(rendered))


def template_forms[M: BaseModel](
    render: Callable[[M], str],
    model: M,
    *,
    html: bool = False,
    keep: frozenset[str] = frozenset(),
    inline: frozenset[type[Enum]] = frozenset(),
) -> dict[str, str]:
    """`{run: form}` for the template text `render` emits over the blanked model.

    A run that is exactly a value of an enum type the model uses is data (a
    machine token such as `data-sev="note"`) and is omitted; the whole type
    counts, not just the members present, so what needs a label does not depend
    on which data a report held. For the enum types named in `inline`, whose
    values the template prints as-is inside a phrase (`markdown (detected`),
    `form` is the run with those values removed; an allowlist entry matches the
    run or its form. A template word equal to an inline value is hidden by it,
    so name only types whose values are data.
    """
    whole = {normalise_run(str(m.value)) for t in _enum_types(model) for m in t}
    words = sorted({normalise_run(str(m.value)) for t in inline for m in t}, key=len, reverse=True)

    def bare(run: str) -> str:
        for word in words:
            run = re.sub(rf"\b{re.escape(word)}\b", " ", run)
        return normalise_run(run)

    runs = prose_runs(render(blank_strings(model, keep=keep)), html=html)
    forms = {run: bare(run) for run in runs if run not in whole}
    return {run: form for run, form in forms.items() if _is_prose(form)}


def unprojected[M: BaseModel](
    render: Callable[[M], str],
    model: M,
    labels: frozenset[str],
    *,
    html: bool = False,
    keep: frozenset[str] = frozenset(),
    inline: frozenset[type[Enum]] = frozenset(),
) -> list[str]:
    """Template text `render` emits that is not a label (see `template_forms`)."""
    forms = template_forms(render, model, html=html, keep=keep, inline=inline)
    return sorted(run for run, form in forms.items() if run not in labels and form not in labels)
