"""Generates the PB9 latency-and-robustness fixtures: ~30-page synthetic product
specs for an invented ferry-ticketing app ("Harbor"):

- `spec_long.pdf`: realistic density (gate G1'): about 90 claims, 27 needs, 21
  stories, 9 constraints, 9 dependencies, 6 segments and 9 forecasts in about 90k
  characters, the rest neutral prose. The density is a stated choice, NOT measured
  from real PRDs.
- `spec_long_dense.pdf`: the first, claim-dense version (265 claims). Kept as a
  stress case for the cost shape; gated by nothing.

Synthetic and deterministic: no customer material, same bytes every run. It is
built from sentence templates, a mix of defects and clean statements across every
critic's territory, so a run exercises every extraction pass and every critic at
realistic volume. It is NOT an accuracy corpus: nobody labelled it, and it says
nothing about a catch rate. Its job is wall-clock (gate G1) and "does a long
document survive the pipeline".

    uv run python tests/fixtures/critique/generate.py
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from fpdf import FPDF

HERE = Path(__file__).parent
PAGES_TARGET = 30

ROUTES = ["Pier 4 to Gull Island", "Northgate to Saltmarsh", "Old Quay to Heron Point"]
GROUPS = ["commuters", "day visitors", "island residents", "freight clerks", "school parties"]
FEATURES = ["a QR ticket wallet", "a live-map screen", "a fare calculator widget", "a seat picker"]
DEPS = ["the port authority's berth API", "the payments gateway team", "the harbour CCTV vendor"]
LAWS = [
    "the Maritime Passenger Records Act, section 12",
    "the operator's licence condition 7.3",
    "the port authority's accessibility bylaw 4",
]

CLAIMS = [
    "{n}% of {g} miss the last sailing on {r}.",
    "Queue time at the {r} kiosk rose {n}% after the timetable change.",
    "Rival operators fill {n}% more seats per sailing than we do.",
    "Refund requests are down {n}%, so the new policy is working.",
    "Ticket scans take 1.{n} seconds on the {r} gate.",
    "The {r} service carried {n}00 passengers last month.",
]
NEEDS = [
    "{G} need {f}.",
    "{G} want to know whether the {r} sailing is delayed before leaving home.",
    "{G} need to board the {r} ferry without queueing at the kiosk.",
    "{G} need to change a ticket without calling anyone.",
    "{G} want a refund within a day of cancelling.",
]
STORIES = [
    "As a {g} traveller, I want to buy a return ticket for {r} so that I can plan one trip.",
    "As a ticket inspector, I want to scan a code so that I can confirm a booking quickly.",
    "As a {g} traveller, I want to be told of a delay so that I can rebook.",
    "As an operator, I want to export sailings so that finance can reconcile them.",
]
SEGMENTS = [
    "Our target customers are adults aged {n} to {m} who travel by ferry.",
    "The segment we are building for is {g} who cross more than twice a week.",
]
FORECASTS = [
    "Launching {f} will double repeat bookings within a year.",
    "Competitors will not respond to the new {r} fares.",
    "Once live, {f} will cut support calls by {n}%.",
]
CONSTRAINTS = [
    "Passenger names must be retained for seven years under {l}.",
    "The service must meet {l}.",
    "Tickets should feel instant.",
]
DEPENDENCIES = [
    "We rely on {d} for berth availability.",
    "Delivery depends on {d}, with no named owner yet.",
    "Sam Okoro on {d} will confirm the schedule feed by June.",
]


def _line(rng: random.Random, templates: list[str]) -> str:
    g = rng.choice(GROUPS)
    return rng.choice(templates).format(
        n=rng.randint(7, 68),
        m=rng.randint(46, 70),
        g=g,
        G=g.capitalize(),
        r=rng.choice(ROUTES),
        f=rng.choice(FEATURES),
        d=rng.choice(DEPS),
        l=rng.choice(LAWS),
    )


FILLER_POOL = [
    "This section records the working assumptions of the product group and is revised "
    "before each review.",
    "The operations team meets on Thursdays and keeps notes with the release plan.",
    "Terminology follows the glossary in the appendix, and abbreviations are expanded "
    "on first use.",
    "Open questions are tracked in the shared log and are reviewed at the start of "
    "each planning cycle.",
    "Diagrams referenced in this part are kept with the design files and are not reproduced here.",
    "Reviewers are asked to read the whole part before commenting on any single item.",
    "The numbering of items follows the order in which they were agreed, not their priority.",
    "Earlier drafts of this part are archived and can be requested from the editor.",
    "Where a paragraph refers to a table, the table appears at the end of the section.",
    "The group reviews this document again after each quarterly planning meeting.",
]

# Statements per section per part, in `build_sections` order: claims, needs, segments,
# stories, constraints, dependencies, forecasts. Three parts: realistic totals are
# 90 / 27 / 6 / 21 / 9 / 9 / 9, the density the gate is stated against.
DENSE = {
    "parts": 3,
    "counts": (70, 55, 18, 60, 30, 30, 28),
    "filler_every": 3,
    "filler_sentences": 1,
    "font": 9,
    "line": 4.5,
}
REALISTIC = {
    "parts": 3,
    "counts": (30, 9, 2, 7, 3, 3, 3),
    "filler_every": 1,
    "filler_sentences": 5,
    "font": 10,
    "line": 5.2,
}


def _filler(rng: random.Random, sentences: int) -> str:
    return " ".join(rng.choice(FILLER_POOL) for _ in range(sentences))


def build_sections(
    seed: int, counts: tuple[int, ...], filler_every: int, filler_sentences: int
) -> list[tuple[str, list[str]]]:
    rng = random.Random(seed)
    plan = [
        ("Background and evidence", CLAIMS, counts[0]),
        ("Customer needs", NEEDS, counts[1]),
        ("Target customers", SEGMENTS, counts[2]),
        ("Stories", STORIES, counts[3]),
        ("Constraints and obligations", CONSTRAINTS, counts[4]),
        ("Dependencies", DEPENDENCIES, counts[5]),
        ("Outlook", FORECASTS, counts[6]),
    ]
    sections = []
    for title, templates, count in plan:
        lines = []
        for i in range(count):
            lines.append(_line(rng, templates))
            if i % filler_every == filler_every - 1:
                lines.append(_filler(rng, filler_sentences))
        sections.append((title, lines))
    return sections


def write_pdf(path: Path, config: dict[str, Any]) -> int:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=config["font"])
    for part in range(1, config["parts"] + 1):
        for title, lines in build_sections(
            part,
            config["counts"],
            config["filler_every"],
            config["filler_sentences"],
        ):
            pdf.add_page()
            pdf.set_font("Helvetica", style="B", size=14)
            pdf.multi_cell(0, 9, f"Part {part}: {title}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=config["font"])
            for line in lines:
                pdf.multi_cell(0, config["line"], line, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(0.5)
    pdf.output(str(path))
    return pdf.page_no()


def main() -> None:
    print("spec_long_dense.pdf:", write_pdf(HERE / "spec_long_dense.pdf", DENSE), "pages")
    print("spec_long.pdf:", write_pdf(HERE / "spec_long.pdf", REALISTIC), "pages")


if __name__ == "__main__":
    main()
