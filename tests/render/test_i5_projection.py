"""I5 on the PB9 critique renderers: none of them has a free-text slot.

Each renderer is run over several reports with every model string blanked; what
is left is the template. Every piece of it must be in the reviewed allowlist
`probative.render.labels.FIXED_LABELS`, so adding a sentence to a renderer fails
here until someone adds it to that list, in a change a reviewer will see.

Coverage is the branches the reports below reach. A branch no report exercises
is not checked; `test_the_variants_reach_every_dimension_status` guards the
ones that matter most.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from probative.core.evidence import SourceFormat
from probative.core.projection import normalise_run, template_forms, unprojected
from probative.critique.report import CritiqueReport, DimensionStatus, SkippedFile
from probative.render import html as html_mod
from probative.render import markdown as md_mod
from probative.render.labels import FIXED_LABELS
from tests.critique._sample import sample_report

Render = Callable[[CritiqueReport], str]
RENDERERS: dict[str, tuple[Render, bool]] = {
    "summary": (md_mod.render_summary, False),
    "markdown": (md_mod.render_markdown, False),
    "html": (html_mod.render_html, True),
}


def _variants() -> dict[str, CritiqueReport]:
    base = sample_report()
    dims = list(base.dimensions)
    findingless = [d.model_copy(update={"findings": []}) for d in dims]
    incomplete = dims[0].model_copy(
        update={
            "status": DimensionStatus.INCOMPLETE,
            "unjudged": 2,
            "unextracted": 1,
            "clean_rate": None,
            "floor_score": None,
        }
    )
    not_applicable = dims[1].model_copy(
        update={
            "status": DimensionStatus.NOT_APPLICABLE,
            "checked": 0,
            "flagged": 0,
            "clean_rate": None,
            "floor_score": None,
            "findings": [],
        }
    )
    doc = base.documents[0].model_copy(
        update={"format_choice": "forced", "pages": 3, "rejected": {"not_found": 2}}
    )
    clipped = [
        f.model_copy(update={"context_clipped_before": True, "context_clipped_after": True})
        for f in dims[0].findings
    ]
    everything = base.model_copy(
        update={
            "dimensions": [
                incomplete,
                not_applicable,
                dims[2].model_copy(update={"cannot_tell": 2, "findings": clipped}),
                *dims[3:],
            ],
            "documents": [doc],
            "skipped": [SkippedFile(path="x.pdf", reason="duplicate")],
            "is_reference_model": not base.is_reference_model,
            "run": base.run.model_copy(update={"reply": "flagged"}),
        }
    )
    return {
        "sample": base,
        "no findings": base.model_copy(update={"dimensions": findingless}),
        "incomplete": base.model_copy(update={"dimensions": [incomplete, *dims[1:]]}),
        "not applicable": base.model_copy(update={"dimensions": [not_applicable, *dims[1:]]}),
        "skipped": base.model_copy(update={"skipped": [SkippedFile(path="x.pdf", reason="dup")]}),
        "reference model flipped": base.model_copy(
            update={"is_reference_model": not base.is_reference_model}
        ),
        "flagged replies": base.model_copy(
            update={"run": base.run.model_copy(update={"reply": "flagged"})}
        ),
        "forced format, pages, rejected": base.model_copy(update={"documents": [doc]}),
        "everything": everything,
    }


VARIANTS = _variants()
# string fields the renderers branch on by equality: left unblanked so each branch is reached
KEEP = frozenset({"reply", "format_choice"})
# the document format is printed as-is inside a phrase ("markdown (detected)"): it is data
INLINE = frozenset({SourceFormat})


def test_the_variants_reach_every_dimension_status() -> None:
    seen = {d.status for r in VARIANTS.values() for d in r.dimensions}
    assert seen == set(DimensionStatus)
    assert any(r.skipped for r in VARIANTS.values())
    assert any(r.run.reply == "flagged" for r in VARIANTS.values())


@pytest.mark.parametrize("variant", list(VARIANTS))
@pytest.mark.parametrize("name", list(RENDERERS))
def test_no_renderer_has_a_free_text_slot(name: str, variant: str) -> None:
    render, html = RENDERERS[name]
    assert (
        unprojected(render, VARIANTS[variant], FIXED_LABELS, html=html, keep=KEEP, inline=INLINE)
        == []
    )


def test_the_allowlist_is_in_its_own_normal_form() -> None:
    # an entry that normalise_run would rewrite can never match anything
    assert [x for x in FIXED_LABELS if normalise_run(x) != x] == []


def test_the_allowlist_has_no_dead_entries() -> None:
    used: set[str] = set()
    for report in VARIANTS.values():
        for render, html in RENDERERS.values():
            for run, form in template_forms(
                render, report, html=html, keep=KEEP, inline=INLINE
            ).items():
                used |= {run, form}
    assert sorted(FIXED_LABELS - used) == []


def test_prose_in_the_flagged_reply_branch_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    # review B1: this branch was unreachable when every string was blanked
    from probative.render import _view

    monkeypatch.setattr(
        md_mod,
        "reply_label",
        lambda r: (
            "Everything here is verified and safe to ship"
            if r.run.reply == "flagged"
            else _view.reply_label(r)
        ),
        raising=False,
    )
    flagged = VARIANTS["flagged replies"]
    bad = unprojected(md_mod.render_markdown, flagged, FIXED_LABELS, keep=KEEP, inline=INLINE)
    assert any("safe to ship" in b for b in bad)


# -- seeded defects: prose added to a renderer's own template is caught -----------


@pytest.mark.parametrize(
    ("module", "attr", "name"),
    [
        (md_mod, "totals_line", "summary"),
        (md_mod, "totals_line", "markdown"),
        (html_mod, "totals_line", "html"),
    ],
)
def test_prose_added_to_a_renderer_is_caught(
    monkeypatch: pytest.MonkeyPatch, module: object, attr: str, name: str
) -> None:
    real = getattr(module, attr)
    monkeypatch.setattr(module, attr, lambda r: real(r) + " (a great result, well done)")
    render, html = RENDERERS[name]
    bad = unprojected(render, VARIANTS["sample"], FIXED_LABELS, html=html, keep=KEEP, inline=INLINE)
    assert any("a great result" in b for b in bad)


def test_prose_in_an_html_attribute_of_the_template_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = html_mod.render_html
    monkeypatch.setattr(
        html_mod, "render_html", lambda r: real(r).replace("<body>", '<body title="Looks great">')
    )
    bad = unprojected(
        html_mod.render_html, VARIANTS["sample"], FIXED_LABELS, html=True, keep=KEEP, inline=INLINE
    )
    assert bad == ["Looks great"]
