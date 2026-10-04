# PROBATIVE_PHASE_SPECS.md — Detailed Phase Specifications

Specs are written just-in-time, at the start of a phase's build session. PB0 and PB1 are fully specified. Everything later carries objective, prerequisites and scope stubs — a detailed spec written months before the phase runs will be wrong by the time you reach it.

**Implementation notes** are appended *after* a build session and are the highest-value content in this file. They record what the spec got wrong and what reality turned out to be.

---

# Shared specifications

These are cross-phase and referenced rather than restated.

## S1 — The agent contract

Every agent implements:

```python
class Agent(Protocol):
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    tools: list[Tool]              # deterministic functions it may call
    tier_policy: TierPolicy        # what evidence it may rest on

    def run(self, state: GraphState, ctx: RunContext) -> AgentResult: ...


class AgentResult(BaseModel):
    proposed_nodes: list[Node]
    proposed_edges: list[Edge]
    tool_calls: list[ToolCall]     # audited; formula calls must appear here
    rationale: str
    self_assessment: SelfAssessment
    cost: CostRecord
```

**Agents never mutate the graph.** They return a patch. The `Committer` applies it only after deterministic validators and then critics pass. Rejected patches are retained under `runs/<id>/rejected/` with their findings attached.

`SelfAssessment` carries what the agent was least sure about, and is surfaced in the assumption ledger rather than discarded.

## S2 — Rubric file format

Critics are configured by data, not by prose buried in a prompt. A contributor adds a critic by writing a rubric and a class with one method — or, for an LLM-backed critic (PB5), a rubric and two class attributes (`candidate_type`, `preamble`) on `LLMCritic`.

```yaml
id: space_warden
severity: block
invariant: I3
applies_to: [NeedCandidate]          # candidate class names, matched by type(x).__name__ (PB3/PB4)
checks:
  - id: solution_grammar
    description: A Need that names a feature, a UI element, or an implementation
    examples_bad: ["users need a dashboard", "provide an API for reconciliation"]
    examples_good: ["help me see where my money went this month"]
    remedy: Restate as a customer benefit — verb first, customer voice
    # severity: block                  # optional (PB5): overrides the rubric's severity for this check
clean_fixtures: fixtures/clean/**/*.json    # must raise nothing on these
defect_fixtures: fixtures/seeded/**/*.json  # must catch every one
```

*(PB5 reconciled this sample with reality: `applies_to` names candidate classes, not graph node types, which do not exist until PB10; `RubricCheck.severity` is a new optional field; real rubrics live at `src/probative/critics/rubrics/<id>/rubric.yaml` with fixtures beside them, split `dev`/`held_out` — see PB5.)*

Every rubric names both a defect fixture set it must catch and a clean set on which it must raise nothing. **The false-positive requirement is not optional** — a critic that fires on clean input is worse than no critic.

## S3 — Testing without an API key

The repository is public; CI on a fork PR has no secrets. Consequences, binding from PB0:

- Default `pytest` run passes with **no LLM credentials in the environment**.
- Every agent test uses a recorded response fixture. Recording is a developer action, replay is the default.
- Live tests are marked `@pytest.mark.live` and excluded from default CI.
- Fixtures are committed. Any fixture derived from real customer material must be synthetic or public-domain — see `CLAUDE.md` § Secrets.
- A phase whose tests only pass with a key is not done.

## S4 — Artifact design system

Three phases render single-file HTML (PB19, PB29, PB9) and they must read as one system. No build step, no CDN, no external fonts — everything inline.

**Provenance scale.** The one visual language the whole product depends on. Chosen to survive both themes and the common forms of colour blindness; tier is *always* also carried by a text label and a pattern, never by hue alone.

| Tier | Role | Encoding |
|---|---|---|
| T1 Primary | strongest | solid fill, darkest weight |
| T2 Secondary | strong | solid fill, mid weight |
| T3 Elicited | provisional | hatched fill |
| T4 Inferred | derived | dotted outline, no fill |
| T5 Simulated | quarantined | ghost — reduced opacity, distinct channel, never the primary series |

**Rules.** Light and dark both defined as token sets on `:root`, never a colour defined only inside a media query. Every chart element reachable by keyboard. Every number rendered next to its confidence, never alone. Every clickable element opens the evidence drawer — if a thing cannot be traced, it is not clickable, and that absence is itself information.

## S5 — Reconstruction banding and posture (onboarding mode)

Cross-phase, used by PB39, PB40 and PB41. See `docs/DESIGN.md` §7.6.

**The three bands.** Every reconstructed claim carries exactly one, and it travels with the claim into every artifact:

| Band | May rest on | Rendering |
|---|---|---|
| `safe_to_say` | T1 `system` evidence — code running in production — or an explicit decision record with a locator | solid, darkest weight |
| `caveat` | T4 inference over T1 `delivery` evidence: tickets, PRs, commits, review threads | hatched |
| `ask` | T4 with thin, conflicting or single-source support | dotted outline |

Banding is computed, not authored — it derives from the claim's provenance, so it is a `formula_id` like any other numeric or categorical field (I4).

**Asymmetry rule.** When a claim is borderline between two bands, it goes to the *weaker* one. Over-banding costs the user a question; under-banding costs them their standing in a meeting. These are not equivalent errors and the implementation must not treat them as such.

**Posture — I9.** Enforced by `NeutralityCritic`:

- Claims are phrased as *what appears to have been decided, and what it rests on*. Never whether it was right.
- No claim attributes fault, competence or intent to a named person.
- `RedTeam` does not run in onboarding mode. This is a runtime exclusion in the mode config, not a prompt instruction.
- `SegmentSkeptic` (PB6-p2) must be excluded too: its verdict is an evaluation of how a past author defined a segment. The same argument arguably covers the other evaluative critics. Nothing enforces this until the mode config exists — OI22.
- The people map states where knowledge is concentrated and where contributors have become inactive. It never characterises how anyone performed.

**Test the negative.** Each of PB39–PB41 ships with a fixture corpus containing a genuinely bad past decision. The assertion is that the output describes it neutrally and does not evaluate it. An implementation that produces a fair-but-critical assessment has failed the phase.

---

# PB0 — Foundation

**Objective**: A public, installable, CI-verified Python repository that does nothing yet and does it correctly.

**Prerequisites**: OI1 ✅ — the name is Probative. The residual availability check is part of this phase's gating check below, not a blocker on starting.

**In scope**

- `pyproject.toml`, `uv` lockfile, Python 3.12+, src layout: `src/probative/` with `core/`, `agents/`, `graph_runtime/`, `render/`, `exporters/`, `interfaces/`, `llm/`, `formulas/`.
- Tooling: `ruff` (lint + format), `pytest` with coverage, `mypy` strict on `src/probative/core` and `src/probative/formulas`, permissive elsewhere initially.
- `src/probative/llm/` — the provider adapter. Narrow internal interface: structured output against a Pydantic model, plus token accounting. LiteLLM is an implementation detail behind it.
- Configuration: environment variables, `.env` for local dev (gitignored), `.env.example` committed.
- CLI entry point: `probative --version`, `probative --help`. Nothing else.
- CI: GitHub Actions running `ruff check`, `mypy src`, `pytest` on push and on pull requests **from forks**, with no secrets available.
- Repository furniture: `LICENSE` (Apache-2.0), `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.gitignore`, `docs/DESIGN.md`.
- Pre-commit: ruff, secret scanning, large-file check.

**Out of scope for PB0**: any graph type, any agent, any formula, any parsing. Phase 0 is foundation and nothing else. If it is tempting to add "just the node types while we're here", that temptation is PB10.

**Tests**

- `test_version` — `probative --version` returns the packaged version.
- `test_no_llm_import_leak` — asserts no module outside `src/probative/llm/` imports `litellm`. This test is the PB0 risk mitigation and it must exist from the first commit.
- `test_config_loads_without_env` — configuration loads with no environment variables set and reports missing credentials as a typed error, not a crash.
- Smoke test asserting the package imports cleanly.

**Gating check**

```bash
uv sync            # clean install on a fresh machine
uv run ruff check  # clean
uv run mypy src    # passes
uv run pytest      # passes with no LLM credentials in the environment
```

CI runs all four on a pull request from a fork and passes. Secret-scanning pre-commit hook rejects a test commit containing a fake key.

**Name verification — do this before the first `git push`, not after:** confirm `probative` is unclaimed on pypi.org directly (the JSON API blocks automated fetching, so check in a browser), search GitHub for an existing `probative` project in the AI-tooling space, and check the domain. If any of these is taken, stop and re-decide — this is the last cheap moment. Fallbacks already vetted and clear on search: `proofmark`, `trigpoint`, `toulmin`.

**Implementation notes (resolved during build session)**:

- **Name verification, resolved 2026-09-21.** PyPI: free (`/simple/probative/` → 404; the project page itself is behind a bot-challenge and not usable as the check). GitHub: two unrelated `probative` repos exist, both created 2026-08-28/29, both ★0, both untouched since — `Vojtaupan/probative` is a same-space AI-tooling side project ("checks whether the tool-call record backs up what your agent said") but has no traction. Domains `probative.io`/`.ai` are taken by others; **the project's own domain is `probative.wevit.ai`** (parented under wevit.ai per `docs/DESIGN.md` R7). Decision: proceed with `probative`, register a PyPI pending publisher immediately, and cut a `0.1.0.dev0` tag as soon as this PR merges — that's the moment the name is actually locked, not the decision to use it.
- **The GitHub repo `vedm1/probative` already existed** (Apache-2.0 `LICENSE`, a stub `README.md`, a `.gitignore`) with one commit before this session started. PB0 built on top of that commit (`git init` locally, added it as `origin`, checked out `main`) rather than re-initializing — the upstream `LICENSE` and `.gitignore` (the GitHub Python template) were kept and only extended, not replaced.
- **PyPI trusted publishing, not an API token.** `release.yml` publishes via OIDC (`pypa/gh-action-pypi-publish` + `id-token: write`) on a `v*` tag. Registering the pending publisher on pypi.org (owner `vedm1`, repo `probative`, workflow `release.yml`, environment `pypi`) is a manual step only the account owner can do — it's not automatable from this session and isn't done yet.
- **`no_args_is_help=True` exits 2, not 0.** The spec's test list implies a clean `--help` path; Click's actual behaviour for a bare invocation under `no_args_is_help` is a usage-error exit (2) with help text on stdout, not exit 0. `test_no_args_shows_help` asserts 2 — verified against the installed Typer/Click version rather than assumed.
- **`no-any-return` under mypy strict bit twice** in code that looked innocuous: `getattr(self, field_name)` in `Settings.credential_for` and `return litellm.completion` in `LiteLLMProvider._completion` (litellm has no type stubs, so `ignore_missing_imports = true` makes every attribute on it `Any`). Fixed by replacing the `getattr` indirection with an explicit `dict[str, SecretStr | None]` literal, and an explicit `cast(CompletionFn, litellm.completion)` at the one deliberate boundary where an untyped SDK meets typed code.
- **`ruff format` walks Markdown fenced Python blocks by default** in this ruff version, and would have reformatted the illustrative `AgentResult`/`Agent` snippets in `docs/DESIGN.md` and this very file (S1). Excluded `docs/` and `*.md` from ruff's scope (`extend-exclude` in `pyproject.toml`) — those files are prose owned by the planning process, not source PB0 should be rewriting. The same reasoning was applied to the `trailing-whitespace`/`end-of-file-fixer` pre-commit hooks, scoped away from `docs/` and the root `CLAUDE.md`/`PHASES.md`/`PROBATIVE_*.md` files so a future build session's `pre-commit run --all-files` can't silently carry a whitespace diff into a doc it wasn't asked to touch.
- **The secret-scanning gating check needed a non-placeholder fake key to prove anything.** A first attempt using AWS's own documented example key (`AKIAIOSFODNN7EXAMPLE`) passed gitleaks silently — it's a well-known placeholder gitleaks' default ruleset (implicitly, via entropy/allowlist behaviour) doesn't flag. A randomly generated key in the same `AKIA[16 chars]` shape was correctly caught (`aws-access-token` rule, hook exits 1). Recorded here because the spec's own gating check ("commit a test key, watch the hook reject it") is easy to satisfy with a false negative if the test key is a recognisable textbook example.
- **`uv sync` (no flags) already installs the `dev` dependency-group** — `uv` treats `dev` as a default group, so the gating check's literal `uv sync` command (not `uv sync --all-groups`) is sufficient to get `ruff`/`mypy`/`pytest` on PATH via `uv run`. Confirmed rather than assumed, since the spec's four-line gating block would otherwise be unrunnable as written.
- **`Settings.model` reads from the `MODEL` env var**, case-insensitively (pydantic-settings default) — documented in `.env.example` as `MODEL=`, not `PROBATIVE_MODEL=`; no `env_prefix` was set, since there's only one provider-agnostic settings object in the project so far and a prefix would just add noise. Revisit if a second `BaseSettings` subclass appears.

---

# PB1 — Ingest: unstructured documents

**Objective**: Turn a folder of ordinary documents into `Source` and `EvidenceSpan` records whose offsets survive re-extraction, so that every downstream provenance claim can be verified rather than trusted.

**Prerequisites**: PB0 ✅. OI4 (dogfood corpus) helpful but not blocking — a synthetic fixture set is sufficient to build against.

**In scope**

- Formats: PDF (text-layer), DOCX, XLSX, CSV, Markdown, plain text.
- `Source` — id, path, sha256 of the bytes, format, ingested-at, declared `tier` and `kind` (see `docs/DESIGN.md` §5.1), extractor and extractor version.
- `EvidenceSpan` — source id, character offsets into a **normalised text projection** of the source, the extracted text, and a locator meaningful to a human (page and line for PDF, sheet and cell for XLSX, heading path for Markdown).
- A stable normalisation step per format, versioned, so that the same file always produces the same projection. The extractor version is recorded on the source because a change to normalisation invalidates existing offsets and must be detectable.
- OCR is **detected and refused** at PB1 with a clear message naming the file. Scanned documents are PB1-ext, not a silent partial extraction.
- Encrypted or corrupt files fail loudly, naming the file and the reason.

**Out of scope for PB1**: Confluence and tracker exports (PB2); images (later); tier and kind *inference* — at PB1 they are declared by the caller, not guessed; any claim extraction (PB4); DOCX table cells (paragraphs only — a documented gap, not a silent one); CSV fields containing embedded newlines (rows are assumed one physical line each).

**New package**: PB0's scaffold (`core, agents, graph_runtime, render, exporters, interfaces, llm, formulas`) has no home for format-specific parsing. This phase adds `src/probative/ingest/`. The typed shapes it produces live in `src/probative/core/evidence.py` instead, since they are the foundational graph-facing evidence types (§5.1) that PB10 will build the graph on top of — they belong under `core`'s existing strict-mypy scope, not under `ingest`.

## Types — `src/probative/core/evidence.py` (mypy strict)

```python
class Tier(str, Enum):
    T1 = "T1"   # Primary
    T2 = "T2"   # Secondary
    T3 = "T3"   # Elicited
    T4 = "T4"   # Inferred
    T5 = "T5"   # Simulated

class EvidenceKind(str, Enum):
    CUSTOMER = "customer"
    OPERATIONAL = "operational"
    DOCUMENTARY = "documentary"
    SYSTEM = "system"
    DELIVERY = "delivery"
    MARKET = "market"

class SourceFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    CSV = "csv"
    MARKDOWN = "markdown"
    TEXT = "text"

class Locator(BaseModel):
    """Human-meaningful place within a Source. Every field optional; a
    format populates only the ones that apply to it."""
    page: int | None = None          # PDF: 1-indexed
    line: int | None = None          # PDF/TXT/CSV/Markdown: 1-indexed; DOCX: paragraph index (1-indexed)
    sheet: str | None = None         # XLSX: sheet name
    cell: str | None = None          # XLSX: A1-style coordinate, e.g. "B7"
    heading_path: list[str] | None = None  # Markdown/DOCX: breadcrumb, e.g. ["Introduction", "Scope"]

class LocatorRegion(BaseModel):
    """One contiguous, non-overlapping slice of `Source.text`. Every
    Source's regions are sorted by `start` and cover `[0, len(text))`
    with no gaps — `spans()` depends on this invariant."""
    start: int   # inclusive offset into Source.text
    end: int     # exclusive offset into Source.text
    locator: Locator

class Source(BaseModel):
    id: str                      # f"src_{sha256[:16]}" — stable across re-ingests of the same bytes
    path: Path
    sha256: str                  # hex digest of the raw file bytes
    format: SourceFormat
    tier: Tier                   # declared by the caller (not inferred at PB1)
    kind: EvidenceKind           # declared by the caller (not inferred at PB1)
    ingested_at: datetime        # UTC; NOT part of idempotence — wall-clock, allowed to differ on re-ingest
    extractor: str               # e.g. "probative.ingest.pdf"
    extractor_version: str       # e.g. "pdf/1" — bumped when normalisation changes
    text: str                    # the normalised text projection, in full
    locator_regions: list[LocatorRegion]

class EvidenceSpan(BaseModel):
    source_id: str
    start: int                   # inclusive offset into the owning Source.text
    end: int                     # exclusive
    text: str                    # source.text[start:end], captured at span-creation time
    locator: Locator

# Exception hierarchy — every one names the offending file.
class IngestError(Exception):
    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")

class UnsupportedFormatError(IngestError): ...   # unrecognised extension
class EmptySourceError(IngestError): ...         # zero-byte file
class EncryptedSourceError(IngestError): ...     # password-protected PDF/DOCX/XLSX
class CorruptSourceError(IngestError): ...       # unparseable / truncated file
class NoTextLayerError(IngestError): ...         # PDF has no extractable text on ≥1 page (OCR refusal)
class MalformedCSVError(IngestError): ...        # inconsistent column count
class SpanOutOfRangeError(IngestError): ...      # spans() given an invalid range
class StaleNormalizationError(IngestError): ...  # reextract() detects a normalisation-version mismatch
```

`EvidenceSpan` deliberately does **not** carry `source_path`/`format`/`extractor_version` — see the revised `reextract` contract below. Duplicating those onto every span would create a second source of record for fields `Source` already owns (CLAUDE.md's "single source of record per field").

## Contracts — `src/probative/ingest/__init__.py`

```python
def ingest(path: Path, *, tier: Tier, kind: EvidenceKind) -> Source: ...

def spans(source: Source, ranges: list[tuple[int, int]]) -> list[EvidenceSpan]: ...

def reextract(source: Source, span: EvidenceSpan) -> str:
    """Re-run extraction on source.path and slice at [span.start:span.end].

    Deviation from the original single-arg sketch: taking `source` avoids
    denormalising path/format/version onto EvidenceSpan (see above). Raises
    StaleNormalizationError if re-ingesting now would produce a different
    extractor_version (the normalisation algorithm changed since this
    source was ingested — existing offsets are not guaranteed valid), and
    CorruptSourceError if the file's sha256 no longer matches (the file on
    disk changed since ingestion). Otherwise returns the freshly-extracted
    text at the span's original offsets, which must equal span.text.
    """
```

`ingest()` algorithm: read the raw bytes; `EmptySourceError` on zero length; compute `sha256`; detect `SourceFormat` from the file extension (`UnsupportedFormatError` if unrecognised — content-sniffing is out of scope); dispatch to the matching per-format extractor (below), which returns `(text, locator_regions, normalization_version)` or raises a typed `IngestError`; assemble and return `Source`. `id` and `sha256` are pure functions of the file's bytes, so re-ingesting the same file is idempotent by construction; `ingested_at` is the one field allowed to differ between calls.

`spans()` algorithm: for each `(start, end)`, validate `0 <= start < end <= len(source.text)` (else `SpanOutOfRangeError`); binary-search `source.locator_regions` (sorted by `start`) for the region containing offset `start`; build the `EvidenceSpan` with `text = source.text[start:end]`. If a range straddles two locator regions, the *first* character's locator wins — offsets are the source of truth for provenance; the locator is a best-effort human aid.

## Per-format extraction algorithms

Each lives in its own module under `src/probative/ingest/`, exposing `NORMALIZATION_VERSION: str` and `extract(path: Path) -> ExtractedDocument` (an internal, unexported `text` + `locator_regions` pair — not a public type, lives in `src/probative/ingest/_extracted.py`).

**`text.py` (`.txt`) — version `"text/1"`.** Decode UTF-8 (strip a leading BOM if present); normalise line endings (`\r\n`, `\r` → `\n`). One `LocatorRegion` per line (`Locator(line=i)`, 1-indexed), spanning that line's text plus its trailing `\n` (the last line may lack one).

**`markdown.py` (`.md`, `.markdown`) — version `"markdown/1"`.** Same decode/line-ending normalisation as `text.py`. `text` is the verbatim normalised source (no HTML rendering — offsets must point at raw Markdown a human would read). Heading tracking is a hand-rolled line scanner (no new dependency, since only heading detection is needed): track `in_fence: bool` and `fence_marker: str | None`; a line whose stripped form starts with three-or-more `` ` `` or `~` toggles fence state (recording the marker on entry, matching it on exit) — headings inside a fence are not headings. Outside a fence, a line matching `^(#{1,6})\s+(.*)$` sets heading level `len(group 1)`; a stack of `(level, text)` is popped down to `level - 1` and the new heading pushed; `heading_path` for every subsequent line (until the next heading changes the stack) is `[text for _, text in stack]`. One `LocatorRegion` per line: `Locator(line=i, heading_path=current_path or None)`.

**`csv_.py` (`.csv`) — version `"csv/1"`.** Same decode/line-ending normalisation; `UnicodeDecodeError` → `CorruptSourceError`. `text` is the verbatim normalised source. First non-empty line is the header; its column count (via `csv.reader` on that one line) is the expected count. Every subsequent non-empty line is parsed the same way (one line = one record — embedded newlines in quoted fields are explicitly unsupported, see out-of-scope); a mismatched column count raises `MalformedCSVError` naming the file and the 1-indexed line number. One `LocatorRegion` per physical line: `Locator(line=i)`.

**`xlsx.py` (`.xlsx`) — version `"xlsx/1"`.** `openpyxl.load_workbook(path, data_only=True)` in **normal (non-read-only) mode** — deliberately, since read-only mode can silently truncate iteration when a sheet's `<dimension>` metadata undercounts its actual populated cells; loading fully in memory sidesteps that class of silent-partial-extraction bug entirely. `EncryptedSourceError` on `zipfile.BadZipFile` / `openpyxl.utils.exceptions.InvalidFileException` (password-protected XLSX is not a valid OOXML zip). No header/schema assumption — this is cell-level, unstructured extraction; table semantics are PB2's job. Walk every sheet in workbook order, every non-empty cell in row-major order; for each, append `str(cell.value) + "\n"` to `text` and record a `LocatorRegion` of `Locator(sheet=sheet.title, cell=cell.coordinate)`. A sheet with zero non-empty cells contributes nothing (not an error by itself; a workbook where *every* sheet is empty raises `EmptySourceError`).

**`pdf.py` (`.pdf`) — version `"pdf/1"`.** `pdfplumber.open(path)` (MIT, wraps pdfminer.six — chosen over PyMuPDF specifically to avoid pulling an AGPL dependency into an Apache-2.0-distributed package). A `pdfminer` password/decryption exception → `EncryptedSourceError`; any other parse failure → `CorruptSourceError`. For each page (1-indexed): if `page.chars` is empty (no extractable text objects — an image-only/scanned page), record it; **if any page in the document has no text layer, raise `NoTextLayerError` naming the file and the affected page number(s) — for the whole document, not just that page.** This is the same "no silent partial extraction" reasoning as OCR refusal generally: a document that is 90% real text and 10% a scanned exhibit should not quietly lose the exhibit. Otherwise, `page.extract_text()` split into lines; each line appended to `text` with a trailing `\n`; one `LocatorRegion` per line: `Locator(page=page_num, line=line_num_within_page)`.

**`docx_.py` (`.docx`) — version `"docx/1"`.** `docx.Document(path)`; a `docx.opc.exceptions.PackageNotFoundError` (encrypted DOCX is not a valid OOXML zip) → `EncryptedSourceError`. Walk `document.paragraphs` in order (**tables are out of scope for PB1** — a documented gap; no fixture contains one, to avoid a false impression of coverage). Heading tracking mirrors `markdown.py`'s stack algorithm, keyed off `paragraph.style.name` matching `Heading \d`. One `LocatorRegion` per paragraph: `Locator(line=paragraph_index, heading_path=current_path or None)` — `line` here means "paragraph index" (DOCX has no native line-number concept; this is the closest stable, human-checkable analogue, and is documented as such).

## Fixture corpus — `tests/fixtures/ingest/`

All synthetic, generated by a committed script (`tests/fixtures/ingest/generate.py`) so they're reproducible; the generated binaries are committed alongside it (S3 — fixtures must be usable without regenerating).

| Fixture | Format | Purpose |
|---|---|---|
| `plain.txt` | TXT | happy path, multi-line |
| `crlf.txt` | TXT | CRLF line endings → normalisation test |
| `empty.txt` | TXT | zero-byte → `EmptySourceError` |
| `notes.md` | Markdown | nested headings (H1→H2→H3) + a fenced code block containing a literal `#` (must not be read as a heading) |
| `data.csv` | CSV | happy path, header + 5 consistent rows |
| `bad_columns.csv` | CSV | one data row with a different column count → `MalformedCSVError` |
| `sheet.xlsx` | XLSX | two sheets, non-contiguous populated cells, one fully empty sheet |
| `report.docx` | DOCX | headings + paragraphs |
| `memo.pdf` | PDF | multi-page, real text layer |
| `scanned.pdf` | PDF | one page with an embedded image and no text objects → `NoTextLayerError` |
| `encrypted.pdf` | PDF | password-protected, no password supplied → `EncryptedSourceError` |
| `corrupt.pdf` | PDF | a valid PDF truncated mid-file → `CorruptSourceError` |

Generation notes: `report.docx`/`sheet.xlsx` are built directly with `python-docx`/`openpyxl` (the same libraries used to read them). `memo.pdf`/`scanned.pdf` are built with `fpdf2` (dev-only dependency, MIT). `encrypted.pdf` is `memo.pdf` re-saved with `pypdf`'s `PdfWriter.encrypt()` (dev-only dependency, MIT). `corrupt.pdf` is the first 200 bytes of `memo.pdf`.

**New dependencies**

```toml
# [project] dependencies
"pdfplumber>=0.11",
"python-docx>=1.1",
"openpyxl>=3.1",

# [dependency-groups] dev
"fpdf2>=2.8",
"pypdf>=5.1",
```

## Tests — `tests/ingest/`

- `test_roundtrip.py` — parametrised over all 6 happy-path fixtures: `ingest()`, take `spans()` at 2–3 known ranges each, `reextract(source, span) == span.text` for every span. **This is the phase's reason to exist.**
- `test_idempotence.py` — ingest each happy-path fixture twice; assert equal `id`, `sha256`, `text`, `locator_regions`; assert `ingested_at` is allowed to differ.
- `test_normalization_golden.py` — for each happy-path fixture, `source.text` equals a committed golden file under `tests/fixtures/ingest/golden/<name>.txt`.
- `test_locators.py` — `memo.pdf`: a known span reports the correct `page`; `sheet.xlsx`: a known span reports the correct `sheet` and `cell`; `notes.md`: a span under the nested heading reports `heading_path == ["Introduction", "Scope"]` (or the fixture's actual structure); a span inside the fenced code block reports the *enclosing* heading, not a heading derived from the `#` inside the fence.
- `test_failures.py` — one case per typed error: `empty.txt` → `EmptySourceError`; `encrypted.pdf` → `EncryptedSourceError`; `corrupt.pdf` → `CorruptSourceError`; `scanned.pdf` → `NoTextLayerError` naming the file; `bad_columns.csv` → `MalformedCSVError` naming the file and line number; a `.xyz` file → `UnsupportedFormatError`. Every assertion checks the file path appears in the error message, not just the exception type.
- `test_stale_normalization.py` — ingest `plain.txt`, hand-construct a `Source` copy with `extractor_version` set to a version string that isn't `text.NORMALIZATION_VERSION`, call `reextract` → `StaleNormalizationError`.
- `test_span_bounds.py` — `spans()` with `start >= end`, and with `end > len(source.text)` → `SpanOutOfRangeError` in both cases.

**Gating check**: `uv run pytest tests/ingest -q` green — round-trip across all six formats, idempotence, normalisation golden, locator correctness, and every listed failure mode — on the committed synthetic fixture corpus. `uv run mypy src` stays clean with `probative.core.evidence` under strict mode.

**Implementation notes (resolved during build session)**:

- **`git add` was silently corrupting the CRLF fixture.** This repo's local `core.autocrlf=input` rewrites CRLF→LF on every commit, which would have quietly turned `crlf.txt` into an LF file the moment it was committed — defeating the one fixture that exists to test CRLF normalisation, on every future clone or CI checkout, with no visible symptom (the working-tree copy stays untouched, so `pytest` run locally never sees the problem). Caught by literally diffing the staged blob (`git show :path | xxd`) against the working-tree bytes before assuming the commit was safe — exactly the "verify, don't assume" instinct CLAUDE.md asks for. Fixed with a new root `.gitattributes` (`tests/fixtures/ingest/** -text`), which also protects the binary PDF/DOCX/XLSX fixtures from any line-ending mangling on a contributor's machine with a different autocrlf setting.
- **pdfplumber discards the original pdfminer exception type.** Every parse failure — wrong password or genuinely corrupt file — surfaces as `pdfplumber.utils.exceptions.PdfminerException`, with the real cause (`PDFPasswordIncorrect`, etc.) preserved only as `exc.__context__`, not as the exception's type or a catchable subclass. `pdf.py` inspects `__context__` to tell "encrypted" apart from "corrupt" — confirmed empirically against both fixtures (`uv run python -c "..."` on `encrypted.pdf`/`corrupt.pdf`) rather than assumed from pdfplumber's docs, which don't document this wrapping behaviour.
- **`reextract`'s signature changed from the spec's sketch**, from `reextract(span) -> str` to `reextract(source, span) -> str`. A single-arg version would force `EvidenceSpan` to carry a duplicate `source_path`/`format`/`extractor_version` — a second source of record for fields `Source` already owns. Flagged during spec review, not discovered mid-implementation.
- **The XLSX "header row not first" failure mode from the original phase-spec stub didn't survive contact with the actual design.** Cell-level, schema-free extraction (the correct approach for *unstructured* ingestion — header/row semantics are PB2's job) has no header assumption to violate. Reinterpreted as the real XLSX risk it was probably gesturing at: `openpyxl`'s read-only mode can silently truncate iteration when a sheet's `<dimension>` metadata undercounts its actual populated cells. Mitigated by loading in normal (non-read-only) mode; the `sheet.xlsx` fixture's "Notes" sheet (data starting at `A3`, nothing above it) exercises the no-header-assumption path directly.
- **Extraction quality bar for DOCX/Markdown heading tracking**: the same (level, text) stack algorithm is used in both `markdown.py` and `docx_.py`; the `report.docx` fixture deliberately includes an H1 that pops a prior H2 off the stack (`Overview > Timeline`, then a sibling `Risks` H1), which was needed to get real test coverage of the pop branch — a fixture with only monotonically-deepening headings would never exercise it.
- **CSV embedded-newline handling was scoped out**, not silently unhandled: `csv_.py` assumes one physical line per record. A quoted field containing a literal newline will be misread as multiple records without raising an error. No fixture exercises this; a future phase (PB2, or a PB1 extension) that needs it should add explicit multi-line-record support rather than assume today's implementation already has it.
- **Coverage**: 98–100% line coverage per new module (`uv run pytest --cov=probative.ingest --cov=probative.core.evidence --cov-report=term-missing tests/ingest`). The two remaining gaps are a defensive `AssertionError` in `spans()`'s internal locator lookup (unreachable unless an extractor violates the "regions fully cover the text" invariant) and one partial branch in the Markdown fence-toggle logic.

---

# Later phases — stubs

Specs are written at the start of each build session. These record objective, prerequisites and known unknowns only.

## PB2 — Ingest: structured exports (Jira + ADO)
**Objective**: Jira CSV/HTML/XML exports and ADO CSV exports become sources with recognised issue keys, hierarchy and acceptance criteria where present.
**Prerequisites**: PB1 ✅.
**Scope note**: Confluence was originally in this phase's objective but is split into **PB2-p2** — no real Confluence export sample was available during the build session, and CLAUDE.md's "reality wins over the spec" / "don't build on an unconfirmed assumption" rules out guessing at a format never seen. OI5 (which Confluence variants matter) was not resolved by this session and now blocks PB2-p2 instead of PB2. (PB2-p2 has since shipped, on different terms than assumed here — see its own section: a Confluence page turned out to carry no issue/hierarchy structure at all.)

**Types** (`probative/core/evidence.py`): `SourceFormat` gains `JIRA_CSV`/`JIRA_HTML`/`JIRA_XML`/`ADO_CSV`. `Locator` gains `issue_key: str | None` and `field: str | None`. New `UnrecognisedTrackerFormatError(IngestError)` for a declared format whose required column/field is missing.

**Public API** (`probative/ingest/tracker.py`, deliberately separate from PB1's `ingest`/`spans`/`reextract`):
```python
class Issue(BaseModel):
    key: str
    type: str
    status: str
    parent_key: str | None
    summary: EvidenceSpan
    description: EvidenceSpan | None
    acceptance_criteria: EvidenceSpan | None

def ingest_tracker(path: Path, *, format: SourceFormat, tier: Tier, kind: EvidenceKind) -> Source
def issues(source: Source) -> list[Issue]
def reextract_tracker(source: Source, span: EvidenceSpan) -> str
```
`format` is explicit rather than extension-sniffed: a tracker export's system (Jira vs ADO) is a run-start choice (docs/DESIGN.md line 736), not something a `.csv` extension can disambiguate. `issues()` is a derived view over `Source.locator_regions` — it calls PB1's own `spans()` to build each field's `EvidenceSpan`, so provenance and re-extraction guarantees are identical to PB1's, not a second implementation of them.

**Normalised-text layout** (`probative/ingest/_tracker_text.py`): one block per issue — a `field="header"` line (`key\ttype\tstatus\tparent_key`) then exactly-bounded regions for `summary` (always) and, only when present, `description` and `acceptance_criteria`. Blank-line padding between fields gets its own untagged region so every character of `Source.text` is covered (the `LocatorRegion` "no gaps" invariant PB1 established).

**Per-format extractors** — algorithms confirmed against real Jira/ADO exports provided during the session (never committed; see Implementation notes):
- `jira_csv.py` / `ado_csv.py`: stdlib `csv.reader` + `header.index(...)` column lookup — not `DictReader`, which silently keeps only the *last* occurrence of a repeated header name. `Description`/Acceptance-Criteria pass through `_wiki.to_text()` (Jira) or `_html.to_text()` (ADO).
- `jira_html.py`: new dependency **beautifulsoup4** (stdlib `html.parser` backend). Matches built-in fields by the shared `data-id`/`class` vocabulary (`issuekey`, `issuetype`, `status`, `summary`, `description`, `parent`); matches Acceptance Criteria (a custom field with an instance-specific `customfield_NNNNN` id) by its `<th>` label text instead. Description cells carry wiki markup with `<br/>` for newlines — converted to `\n` before running the same `_wiki.to_text()` as `jira_csv.py`.
- `jira_xml.py`: stdlib `ElementTree` over `channel/item`; `<parent id="...">KEY</parent>` for hierarchy; Acceptance Criteria matched by `<customfieldname>` text under `<customfields>`. `<description>` is genuine escaped HTML here (unlike CSV/HTML-export's wiki markup) — normalised via `_html.to_text()`.

**Normalisation helpers**: `_wiki.py` (Jira wiki markup → text: list leaders, `*bold*`/`_italic_`/etc. emphasis, `!image!` macros, `[text|url]` links, `[~accountid:...]` mentions — documented v1 scope, anything else passes through verbatim) and `_html.py` (HTML → text: block tags → line breaks, tags stripped, entities unescaped).

**Test plan** (`tests/ingest/tracker/`, fixtures under `tests/fixtures/tracker/`, all synthetic): `test_jira_csv.py` (visible vs all-fields column-set independence, wiki-markup normalisation, acceptance-criteria present/absent), `test_jira_html.py` (nested lozenge/anchor markup, hierarchy, description parity with the CSV equivalent), `test_jira_xml.py` (HTML description normalisation, `<parent>` hierarchy, customfields acceptance criteria), `test_ado_csv.py` (HTML description, the dangling-parent case, acceptance-criteria present/absent), `test_roundtrip.py` (every field span reextracts exactly; idempotent re-ingestion), `test_failures.py` (one case per required-column/field omission, not-well-formed XML, empty file), `test_reextract_edge_cases.py` (wrong source, stale normalisation, file changed on disk), `test_wiki_normalize.py`/`test_html_normalize.py` (unit tests on the normalisers).

**Gating check**: `uv run pytest tests/ingest/tracker -q` green across all four formats — round-trip, hierarchy (including the dangling-reference case), and acceptance-criteria recognition (present *and* absent, never invented) all covered. `uv run mypy src` clean.

**Implementation notes (resolved during build session)**:

- **The real samples reshaped the scope before any code was written.** Six real export files (two Jira CSV column-sets, two Jira HTML column-sets, one Jira XML, one ADO CSV) were provided for structural inspection — never committed (CLAUDE.md § Secrets: sample corpora must be synthetic or public-domain). None of them was a Confluence export, which is why Confluence moved to PB2-p2 rather than being guessed at.
- **A real Jira CSV export has no dedicated Acceptance Criteria column.** DESIGN.md's exporter-schema table (§7.7, for PB28) assumes one; the real inbound export doesn't have it — the phrase only ever appears as free text inside `Description`. PB2 recognises the column only when present (`Custom field (Acceptance Criteria)` for Jira, `Acceptance Criteria` for ADO) and never fabricates it — exercised by a synthetic fixture rather than the real sample, since the real sample never had one.
- **Jira hierarchy is `Parent key` / `<parent id="...">`, not `Epic Link`.** The real export is a modern, team-managed Jira project where even Epics are linked via `Parent`, confirming the post-Epic-Link-deprecation shape rather than the older `Epic Link` custom field DESIGN.md's ADO row implies.
- **Two different markup dialects hide behind the same logical field.** Jira CSV and Jira HTML's `Description` is Jira wiki markup (`# ` list items, `*bold*`); Jira XML's `<description>` and ADO's `Description` are genuine escaped/rich-text HTML. Confirmed empirically (not assumed) by inspecting the same underlying issue across all three Jira export formats — this is why there are two separate normalisers (`_wiki.py`, `_html.py`) rather than one.
- **`csv.DictReader` was rejected, not just avoided by convention.** A real "all fields" Jira export repeats `Labels`, `Watchers`, `Attachment`, `Comment` and `Sprint` as duplicate column headers (up to 30 `Comment` columns in the real sample); `DictReader` silently collapses duplicates to the last occurrence, which would have been a silent-data-loss bug for any canonical column that ever became a repeated one. `header.index(...)` makes "first occurrence, duplicates ignored" explicit.
- **ADO's `Parent` frequently references a work item outside the exported set.** Confirmed against the real 40-row sample: 0 of 17 distinct parent IDs resolved within the file. PB2 records `parent_key` verbatim and does not attempt resolution — that's a graph-era concern (see the new open item below), not this phase's, and inventing a resolution here would risk fabricating a hierarchy edge I8/I1 don't license.
- **jira_html.py needed BeautifulSoup, not regex.** A real status cell is a lozenge `<span data-tooltip="...">`; a real key cell is `<a data-issue-key="...">`. Confirmed by direct inspection that regex extraction breaks on the real markup; `bs4`'s `get_text(strip=True)` on the matched `<td>` (found by the `class`/`data-id` field-id shared with `<th>`) is robust to arbitrary nesting.
- **Coverage**: 97% across the new/changed modules; `tracker.py` (the phase's own novel logic) at 100%. Two classes of gap remain, both documented and both mirroring PB1's own precedent of accepted gaps: (1) each CSV extractor's "no header row" branch is unreachable through the public `ingest_tracker()` entrypoint, because a zero-byte file is already rejected by `EmptySourceError` before extraction runs; (2) a handful of `jira_html.py`/`jira_xml.py` defensive branches (a `<td>` with no `class`, a `<customfield>` with an empty value) that no real export has been seen to produce.

## PB2-p2 — Ingest: structured exports (Confluence)
**Objective (reshaped from the original)**: originally "Confluence export → sources plus recognised issues, acceptance criteria and hierarchy" — mirroring PB2's Jira/ADO model. Two real Confluence Cloud per-page exports (a "Word" export and a "PDF" export) obtained this session showed that objective doesn't match reality: a Confluence page carries no issue key, status or hierarchy — it's a title plus prose paragraphs and HTML tables. Per CLAUDE.md ("reality wins over the spec"), the objective is corrected to: **a Confluence per-page export becomes a plain `Source` with provenance-bearing text**, no derived record type, no invented hierarchy.
**Prerequisites**: PB1 ✅. Blocked on OI5 (Confluence export variants) until this session's two real samples arrived.

**Types** (`probative/core/evidence.py`): `SourceFormat` gains `CONFLUENCE_WORD`. No other schema changes — `Locator`'s existing `heading_path`/`line` fields (from PB1) cover this format fully; no new `Locator` fields, no new `IngestError` subtype (`CorruptSourceError`/`EmptySourceError` cover every failure mode).

**Public API** (`probative/ingest/confluence.py`, new, deliberately separate from PB1's `ingest`/`spans`/`reextract` — same rationale as PB2's `tracker.py`):
```python
def ingest_confluence(path: Path, *, format: SourceFormat, tier: Tier, kind: EvidenceKind) -> Source
def reextract_confluence(source: Source, span: EvidenceSpan) -> str
```
`format` is explicit, not extension-sniffed: Confluence's "Word" export always uses a `.doc` extension regardless of its real content, and that extension is ambiguous with genuine legacy binary Word (a format this codebase does not support at all). No `issues()`-style derived view exists — callers use PB1's existing `probative.ingest.spans()` directly against the resulting `Source`, since there is no structured record type to rebuild.

**The other real variant — "Export to PDF" — gets no module here.** It is a well-formed PDF; `pdfplumber` (PB1's `pdf.py`, unmodified) already handles it via `SourceFormat.PDF`/`probative.ingest.ingest()`. The one real, confirmed characteristic: the export is a print of the whole browser page, so extracted text carries the top navigation chrome verbatim, ahead of the actual page content, on page 1. This is not a parsing bug — it is genuinely on the page — so it is not stripped; it is locked in with a characterisation test that calls PB1's `ingest()` unchanged.

**Extractor** (`probative/ingest/confluence_word.py`, new): the real "Word" export is MHTML — a `multipart/related` MIME message, quoted-printable, wrapping one `text/html` part — not OOXML (`python-docx` would reject it). Decoded via the stdlib `email` module (`email.message_from_bytes(..., policy=email.policy.default)`, no new dependency) to find and decode the `text/html` part, then BeautifulSoup (reused from PB2's `jira_html.py`) walks the body's `h1`–`h6`/`p`/`table` elements in document order:
- `h1`–`h6`: build a `heading_path` stack, identical algorithm to `docx_.py`'s "Heading N" style tracking.
- bare `p`: one line of `get_text(strip=True)`.
- `table`: one line per `<tr>`, cells joined `" | "`; a cell containing multiple `<p>`s joins them with `" / "` (a normalisation this codebase hasn't needed before — `docx_.py` explicitly punts on tables, and PB2's generic `_html.py` doesn't separate `<td>`/`<th>` cells at all, having been built for Jira/ADO description fields, not full pages dominated by tables).
- `<p>` elements nested inside a `<td>`/`<th>` are skipped in the top-level walk (`element.find_parent("table") is not None`) — they're already folded into their row.

One `LocatorRegion` per emitted line (`Locator(line=<sequential>, heading_path=<stack or None>)`), covering `Source.text` with no gaps, same invariant as every PB1/PB2 extractor.

**Test plan** (`tests/ingest/confluence/`, fixtures under `tests/fixtures/confluence/`, all synthetic): `test_confluence_word.py` (heading nesting including a same-level pop, table row flattening, multi-paragraph cell join, bare paragraph capture, no-gaps invariant), `test_roundtrip.py` (every region's span reextracts exactly; idempotent re-ingestion), `test_reextract_edge_cases.py` (wrong source, stale normalisation, file changed on disk), `test_failures.py` (zero-byte file, not a MIME message, a well-formed MIME message with no `text/html` part, no `<body>` tag, an empty body, a declared-UTF-8 payload that isn't valid UTF-8, an unrecognised `format`), `test_pdf_export.py` (the PDF characterisation test against PB1's unmodified `ingest()`).

**Gating check**: `uv run pytest tests/ingest/confluence -q` green — round-trip, heading nesting, table flattening, every failure mode, and the PDF characterisation all covered. `uv run mypy src` clean.

**Implementation notes (resolved during build session)**:
- **The real samples reshaped the objective, not just the scope, before any code was written.** Both were per-page exports (Confluence Cloud), never a tracker/issue-shaped export — the phase's original "issues, acceptance criteria and hierarchy" framing (copied from PB2's Jira/ADO model) didn't fit anything real and was dropped rather than forced.
- **The `.doc` "Word" export is MHTML, not OOXML.** Confirmed via `file`("news or mail text, ASCII text, with CRLF line terminators") and by inspecting the header block directly (`Content-Type: multipart/related`). `python-docx` was never attempted against it — this was caught before writing any extraction code.
- **No hierarchy exists in either sample, and none is invented.** The PDF export's visible "nav bar" text (`Home / All Thoughtworks Spaces / Internal Functions / ...`) is the account's list of *available spaces*, not this page's parent chain — confirmed by reading it in context, not assumed. Treating it as page hierarchy would have fabricated a structure I1 doesn't license. Confluence's genuine hierarchy feature (space export's page tree) is a different export variant this session has no sample of.
- **The Confluence PDF export needed no new extractor.** `pdfplumber` (already PB1's dependency) opens it and finds a real text layer; the only new information is that `page.extract_text()` includes the browser's top navigation chrome as literal text on page 1, because the export prints the whole page, not just the article. This is documented as an accepted characteristic (mirroring PB1's own "no silent partial extraction" posture) rather than something PB2-p2 tries to clean up.
- **PB2's generic `_html.py` was deliberately not reused.** Reading it during spec confirmed its block-break regex list (`br|p|div|li|ol|ul|h[1-6]|tr|table`) omits `<td>`/`<th>` — adjacent table cells would concatenate with no separator. It was built for Jira/ADO description fields (rarely tabular), not full Confluence pages, so a purpose-built walker was written instead of stretching that normaliser beyond its documented scope.
- **Coverage**: 100% line and branch on both new modules (`confluence.py`, `confluence_word.py`) — including the "no `<body>` tag" branch, confirmed reachable (unlike PB1/PB2's `pragma: no cover` precedents) because `html.parser` (unlike `lxml`/`html5lib`) does not synthesise a `<body>` when the source HTML omits one.
- **OI5 narrows, doesn't close.** The per-page Word/PDF variants are now confirmed and built; Confluence's admin-level "export space" bulk XML/HTML variant (a zip of many pages, plausibly carrying real page hierarchy) remains unconfirmed — no sample exists, and CLAUDE.md rules out guessing at it. Left open rather than built speculatively.

## PB3 — Finding model + critic framework

**Objective**: A critic can be added to Probative by writing a rubric file (S2) and subclassing a base class with one method, with no runtime change. This phase builds the `Finding`/`Rubric`/`Severity` shapes, the rubric loader, the `Critic` base, a fan-out runner and deterministic dimension scoring that every critic phase (PB5–PB9) builds directly on.

**Prerequisites**: PB0 ✅. The stub's "OI3 resolved" prerequisite is stale — `PROBATIVE_BUILD_PLAN.md`'s open-items table has OI3 (the LLM response-recording library) blocking **PB5**, not PB3, and reality confirms this: PB3 introduces no LLM/agent code at all, so there is nothing for OI3 to gate here. Corrected in this session (CLAUDE.md "reality wins").

**In scope**

- `Severity` (`block`/`warn`/`note`), `RubricCheck`, `Rubric` (the S2 shape, verbatim — no new fields invented), `Finding`, `DimensionScore`.
- A YAML rubric loader with a typed error hierarchy (missing file, invalid YAML, schema violation).
- `Critic` — an ABC with one abstract method (`check`) and a `_finding()` helper that fills `critic_id`/`invariant`/`remedy` from the rubric so a critic author never hand-populates them.
- `run_critics()` — sequential fan-out over a list of critics and candidates, filtered by each rubric's `applies_to`.
- `score_dimension()`/`aggregate()` — the floor-based dimension scoring that resolves this phase's "known unknown" (below).
- `assert_rubric_fixtures()` — S2's fixture contract ("must raise nothing on clean, must catch every seeded defect") made runnable, for every future critic phase's own tests to call.
- One throwaway demo critic + rubric + fixture pair, used only to prove the framework end-to-end. Not a real critic.

**Out of scope**: any real critic (`SpaceWarden`, `EvidenceAuditor`, etc. — PB5–PB8); candidate node types (`Claim`, `Need`, `Story`, `Constraint` — PB4); parallel/async fan-out (`run_critics` is deliberately sequential — true parallel fan-out is PB12's LangGraph runtime concern); Markdown/HTML report rendering and the `probative critique` CLI command (PB9/PB33/PB34); LLM-backed critics (the `Critic.check()` interface does not preclude one — an implementation could call a `Provider` inside `check()` — but none is built this phase).

**Known unknown, resolved**: dimension scores are **floor-based**, not a weighted mean. A `block`-severity finding collapses that dimension's score to `0.0` outright — a critic's veto (DESIGN.md §9.1: "a critic returning `severity: block` stops the pipeline. Real control flow, not a suggestion in a prompt") must not be averaged away by unrelated clean checks in the same rubric. Absent a block, the score starts at a ceiling of `10.0` and is discounted per finding — harder to game than a mean, which a critic author could keep smooth by burying one real defect among many trivial passing checks. A separate `blocked: bool` field stays distinct from the numeric floor, since a `warn`-heavy dimension can also reach `0.0` by accumulation without ever being a genuine veto — these are different facts and PB9's report must not conflate them.

### Types — `src/probative/core/critic.py` (mypy strict)

```python
class Severity(StrEnum):
    BLOCK = "block"
    WARN = "warn"
    NOTE = "note"

class RubricCheck(BaseModel):
    """One named check within a rubric (S2)."""
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    examples_bad: list[str] = Field(default_factory=list)
    examples_good: list[str] = Field(default_factory=list)
    remedy: str = Field(min_length=1)

class Rubric(BaseModel):
    """A critic's configuration, loaded from YAML (S2). Exactly the S2
    shape — no field here that isn't in the documented format."""
    id: str = Field(min_length=1)                  # e.g. "space_warden"
    severity: Severity                              # this rubric's default finding severity
    invariant: str | None = None                    # e.g. "I3"; None for a critic with no single guardrail
    applies_to: list[str] = Field(default_factory=list)  # candidate class names; [] means "all"
    checks: list[RubricCheck] = Field(min_length=1)
    clean_fixtures: str = Field(min_length=1)        # glob, relative to the rubric file's directory
    defect_fixtures: str = Field(min_length=1)       # glob, relative to the rubric file's directory

class Finding(BaseModel):
    """What a critic emits — S1's `AgentResult` never carries these directly;
    they attach to a patch via the Committer's critic fan-out (PB12)."""
    critic_id: str                     # == the rubric's id
    check_id: str                      # == one of rubric.checks[].id
    severity: Severity
    invariant: str | None
    message: str                       # critic-authored prose describing the specific violation
    remedy: str                        # copied from the matching RubricCheck.remedy
    target_id: str | None = None       # id of the candidate/node this finding is about, if any
    evidence: EvidenceSpan | None = None  # the quoted text this finding rests on, if any (I1)

class DimensionScore(BaseModel):
    """One rubric's aggregate result over a batch of findings."""
    critic_id: str
    invariant: str | None
    blocked: bool                      # True iff >=1 finding of this rubric has severity BLOCK
    score: float                       # 0.0-10.0, floor-based (see algorithm below)
    findings: list[Finding]            # this rubric's own findings, in the order they were produced

# Exception hierarchy — rubric *loading* failures, always naming the offending file.
class RubricError(Exception):
    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")

class RubricNotFoundError(RubricError): ...   # path does not exist
class MalformedRubricError(RubricError): ...  # invalid YAML syntax, not a mapping, or schema violation

# A critic-authoring bug, not a rubric-loading failure — raised at `check()` time,
# not `load_rubric()` time, so it does not need a file path.
class UnknownCheckError(ValueError):
    def __init__(self, critic_id: str, check_id: str) -> None:
        self.critic_id = critic_id
        self.check_id = check_id
        super().__init__(f"{critic_id}: no check {check_id!r} declared in its rubric")
```

`Finding.evidence` reuses `core.evidence.EvidenceSpan` rather than duplicating a text+locator shape — a finding that quotes evidence quotes the same span type everything else in the codebase does (CLAUDE.md "single source of record per field").

### Contracts — `src/probative/critics/`

```python
# rubric.py
def load_rubric(path: Path) -> Rubric:
    """Parse and validate one rubric YAML file. Raises RubricNotFoundError
    if `path` does not exist, MalformedRubricError if the file is not valid
    YAML, is not a mapping at the top level, or fails Rubric's schema."""

def resolve_fixture_paths(rubric: Rubric, rubric_path: Path) -> tuple[list[Path], list[Path]]:
    """Resolve `rubric.clean_fixtures`/`defect_fixtures` (globs relative to
    `rubric_path.parent`) to sorted lists of actual paths. An empty match is
    not an error here — fixtures are a test-time concern; a rubric can be
    loaded in a production install with no fixtures on disk at all. Only
    `assert_rubric_fixtures` (below) treats an empty match as a failure."""

# base.py
class Critic(ABC):
    """Adding a critic means writing a rubric (S2) and subclassing this
    with one method — `check`. Nothing else in the runtime changes. A
    Critic is not an Agent (S1): it never proposes a patch and never
    touches the graph: it only returns Findings."""

    def __init__(self, rubric: Rubric) -> None: ...

    @abstractmethod
    def check(self, candidates: Sequence[BaseModel]) -> list[Finding]:
        """Evaluate candidates against this critic's rubric. Return zero or
        more Findings. Never raises on a violation found in a candidate;
        never mutates a candidate."""

    def _finding(
        self, *, check_id: str, message: str, severity: Severity | None = None,
        target_id: str | None = None, evidence: EvidenceSpan | None = None,
    ) -> Finding:
        """Construct a Finding against one of this critic's own declared
        checks, filling critic_id/invariant/remedy from the rubric and
        defaulting severity to the rubric's. Raises UnknownCheckError if
        `check_id` is not declared in this critic's rubric — a typo here
        must fail loudly, not silently produce an undocumented finding."""

# runner.py
def run_critics(critics: Sequence[Critic], candidates: Sequence[BaseModel]) -> list[Finding]:
    """Run every critic against the candidates whose type name appears in
    its rubric's `applies_to` (empty `applies_to` means every candidate).
    Concatenates all Findings, critic by critic, in the order `critics` was
    given. Sequential by design — see 'Out of scope'."""

# scoring.py
def score_dimension(rubric: Rubric, findings: Sequence[Finding]) -> DimensionScore:
    """Filter `findings` to this rubric's own (`critic_id == rubric.id`).
    If any has severity BLOCK: score = 0.0, blocked = True. Otherwise:
    score = max(0.0, 10.0 - 2.0 * count(WARN) - 0.5 * count(NOTE)),
    blocked = False."""

def aggregate(rubrics: Sequence[Rubric], findings: Sequence[Finding]) -> list[DimensionScore]:
    """One DimensionScore per rubric, via score_dimension, in rubric order."""

# testing.py
def assert_rubric_fixtures(
    critic: Critic, rubric_path: Path,
    parse_fixture: Callable[[Path], Sequence[BaseModel]],
) -> None:
    """The S2 contract, made runnable. Resolves clean/defect fixture paths
    via resolve_fixture_paths; raises AssertionError immediately if either
    glob matched zero files (a fixture-authoring bug, not a critic bug).
    For each clean fixture: parse_fixture(path) then critic.check(...) must
    return []. For each defect fixture: critic.check(...) must return a
    non-empty list. `parse_fixture` is supplied by the caller because
    turning a fixture file into typed candidates needs the candidate type
    this framework doesn't know about — that knowledge lives with each
    critic phase's own tests, not here."""
```

### New dependency

```toml
# [project] dependencies
"pyyaml>=6.0",
```

Already present transitively (via `pre-commit`); this makes it a direct dependency since `critics/rubric.py` imports it.

### Fixture corpus — `tests/fixtures/critics/`

All hand-written JSON/YAML, no generator script needed (unlike PB1/PB2's binary formats).

| Path | Purpose |
|---|---|
| `example/rubric.yaml` | A minimal, real rubric (`id: non_empty_text`, `severity: warn`, `applies_to: [Note]`) — the one non-real critic this phase ships, proving the S2 loop end-to-end |
| `example/fixtures/clean/*.json` | `Note` candidates with non-empty text — `NonEmptyTextCritic` must raise nothing |
| `example/fixtures/seeded/*.json` | `Note` candidates with empty/whitespace-only text — `NonEmptyTextCritic` must catch every one |
| `malformed/missing_field.yaml` | Valid YAML, missing `checks` → `MalformedRubricError` |
| `malformed/bad_severity.yaml` | `severity: critical` (not in the enum) → `MalformedRubricError` |
| `malformed/not_a_mapping.yaml` | A YAML list at the top level → `MalformedRubricError` |
| `malformed/invalid_syntax.yaml` | Broken YAML syntax → `MalformedRubricError` wrapping the `YAMLError` |

`Note` (`id: str`, `text: str`) and `NonEmptyTextCritic` live in `tests/critics/_example.py` — test-only, not shipped in `src/`, since they exist purely to demonstrate the framework rather than to be a real critic.

### Tests — `tests/critics/`

- `test_rubric.py` — happy-path load against `example/rubric.yaml` (asserts every field); `RubricNotFoundError` on a missing path; `MalformedRubricError` for each of the four `malformed/*.yaml` fixtures; `resolve_fixture_paths` returns the expected sorted, non-empty lists for `example/rubric.yaml` and an empty list (not an error) for a glob that matches nothing.
- `test_base.py` — `Critic(rubric)` cannot be instantiated directly (`TypeError`, ABC); a concrete subclass's `_finding()` fills `critic_id`/`invariant`/`remedy` from the rubric and defaults `severity` to `rubric.severity`; an explicit `severity=` overrides it; `_finding(check_id="nonexistent", ...)` raises `UnknownCheckError`.
- `test_runner.py` — two critics with disjoint `applies_to` each see only their matching candidates; a rubric with `applies_to: []` sees every candidate; a critic with no relevant candidates in the batch is never called (spied); results from multiple critics concatenate in critic order.
- `test_scoring.py` — no findings → `score == 10.0`, `blocked is False`; one `BLOCK` finding among others → `score == 0.0`, `blocked is True` regardless of accompanying warn/note findings; 2 `WARN` findings → `6.0`; 3 `NOTE` findings → `8.5`; 10 `WARN` findings → floors at `0.0` (not negative); a finding belonging to a different `critic_id` is excluded from this rubric's score; `aggregate()` over 2 rubrics returns 2 `DimensionScore`s in the given order.
- `test_example_framework_contract.py` — `assert_rubric_fixtures(NonEmptyTextCritic(load_rubric(...)), rubric_path, parse_fixture=...)` passes against the real `example/` fixtures (the S2 contract, actually exercised); a deliberately regressed critic (`check()` always returns `[]`) run through the same call raises `AssertionError` (proving the harness would actually catch a regression); a rubric copy whose `clean_fixtures` glob matches nothing raises `AssertionError` from `assert_rubric_fixtures` itself, not a downstream error.

**Gating check** (PHASES.md): `uv run pytest tests/critics -q` green. A critic can be added by writing a rubric file and a class with one method, with no runtime change — demonstrated by `NonEmptyTextCritic` needing zero changes to `runner.py`/`scoring.py`/`base.py`. Findings aggregate into dimension scores deterministically: `test_scoring.py` calls `score_dimension` twice on the same inputs and asserts equal output. Severity ordering is enforced by type: `Rubric.model_validate({"severity": "critical", ...})` raises before any critic runs. `uv run mypy src` clean with `probative.core.critic` under strict mode; `uv run ruff check`/`ruff format --check` clean.

**Implementation notes (resolved during build session)**:

- **The spec held exactly as written** — every type, contract and algorithm above was implemented verbatim, including the floor-based scoring formula and its constants (`10.0` ceiling, `2.0`/`0.5` penalties). No deviation to record here, unlike PB1/PB2-p2 where real samples reshaped the design; PB3 had no external material to react to, only an internal design choice, which the spec itself already resolved.
- **The `applies_to` matching mechanism (`type(candidate).__name__` against a plain string list) was the one design point requiring care**: it's what lets `run_critics`/`Critic` stay fully decoupled from PB4's not-yet-existing node types (`Need`, `FeatureIdea`, etc.) while still implementing S2's documented rubric shape exactly. Confirmed by `test_runner.py` using two throwaway Pydantic models (`Alpha`, `Beta`) that share no relationship with any real or planned node type — proof the framework doesn't secretly depend on one.
- **`Critic.check()`'s LLM-backed path is unexercised.** The interface (`Sequence[BaseModel] -> list[Finding]`) doesn't preclude a critic that calls a `Provider` internally (needed later for `RedTeam`, PB8), but nothing in this phase proves that works end-to-end — it remains a documented assumption until PB8 actually builds one.
- **Coverage**: 100% line+branch on every new module except one line in `Critic`'s abstract `check` method (`raise NotImplementedError` in its body) — unreachable because Python's `ABC` machinery already prevents instantiating a `Critic` subclass that doesn't override it; `test_base.py::test_critic_is_abstract` proves that enforcement directly instead. Same class of documented, intentional gap as PB1's own unreachable defensive branches.
- **Cross-reference fix, not a scope change**: the PB3 stub previously listed "OI3 resolved" as a prerequisite. `PROBATIVE_BUILD_PLAN.md`'s open-items table was already correct (OI3 blocks PB5); the stub was stale. Corrected in the Prerequisites line above rather than left to accumulate confusion at PB5.

- **PB5 addendum**: `RubricCheck` gained an optional `severity` (unset → inherits the rubric's); `Critic._finding` resolves explicit argument > check > rubric. This is the one change PB5 made to PB3's types, additive and backward compatible. The "LLM-backed `check()` is unexercised" assumption above is now exercised end-to-end by PB5 (`LLMCritic`).

## PB4 — Shallow extraction

**Objective**: Typed candidates — claims, needs, stories, constraints, dependencies — extracted from a single `Source` with resolvable locators, without constructing a graph.

**Prerequisites**: PB1, PB2, PB3 ✅. No open item blocks it. OI2 (reference model) and OI3 (recording library) block PB5; PB4 is the first phase to need an LLM test pattern, so it ships the smallest hand-rolled recorder (under `tests/`, not `src/`) as *input* to OI3 without closing it.

**Known unknowns**: precision/recall achievable on unstructured PRDs (answered by the live recording, see Gating check); whether constraint extraction needs its own pass (built as a separate pass, per-kind live numbers decide if it earns its cost).

**Design decisions (approved)**

1. **The model proposes verbatim quotes, never offsets.** Deterministic code finds each quote in `source.text` and builds the span via `ingest.spans()`. An unlocatable quote is rejected and counted. Document text is untrusted. Quote verification means a model cannot introduce text that is not in the document, but it does **not** stop an injected sentence that *is* in the document from being quoted: gate 4 therefore depends on measured model behaviour, not on the resolver.
2. **Candidate text is the document's own wording, never a rewrite** — otherwise solution grammar would be laundered past `SpaceWarden` (I3, PB5).
3. **Tier and kind are not on candidates.** `EvidenceSpan` carries neither (single source of record); they are reached through `evidence.source_id` → `Source`.
4. **Plain function, not an S1 `Agent`.** `GraphState`/`RunContext` do not exist until PB12; PB13/PB14 wrap this later.

### Types — `src/probative/core/candidates.py` (mypy strict)

- `CandidateKind` (StrEnum): `CLAIM`, `NEED`, `STORY`, `CONSTRAINT`, `DEPENDENCY`.
- `_CandidateBase` (frozen): `id: str` (`cand_<kind>_<sha256(source_id:start:end)[:12]>`; a validator rejects any id that is not the recomputed one), `evidence: EvidenceSpan` (required, non-nullable — no locator means unconstructible, I1), property `text`.
- `ClaimCandidate`, `NeedCandidate`, `StoryCandidate`, `ConstraintCandidate`, `DependencyCandidate`, each with `kind: Literal[...]`; `Candidate` is the discriminated union. **PB5–PB7 rubrics must write `applies_to: [NeedCandidate]`** — PB3 matches `type(x).__name__`.
- `RejectReason` (`NOT_FOUND`, `EMPTY`, `TOO_LONG`, `DUPLICATE`), `RejectedQuote(kind, quote, reason)`.
- `ExtractionResult(source_id, claims, needs, stories, constraints, dependencies, rejected, usage: TokenUsage)` with `candidates()` (flat, document order).
- No numeric field on any candidate other than structural positions in the source (span offsets, locator page/line): no confidence, no score (I4). A structural test enforces exactly that set. `_CandidateBase` also validates span coherence (`0 <= start < end`, `len(text) == end - start`).

### Contract — `src/probative/extract/`

```python
def extract_candidates(source: Source, provider: Provider, *, model: str,
                       max_chars_per_call: int = 60_000,
                       max_quote_chars: int = 500) -> ExtractionResult
```

- **Passes** (`PASSES` data table): `general` (claim, need, story, dependency) and `constraint` (stricter prompt: only obligations the document itself states; never from model knowledge).
- **LLM output models**: lists of `RawQuote(quote: str)` and nothing else — no offsets, confidence, rationale or tier.
- **Prompts** (`prompts.py`): document inside `<document>…</document>` declared as data; need prompt says include feature-framed statements and do not rewrite. Prompt text is hashed into the recording key.
- **Chunking**: if `len(text) > max_chars_per_call`, split greedily at `LocatorRegion` boundaries, then `\n\n`, then line break; no overlap; one call per pass per chunk.
- **Quote resolution** (`resolve.py`), within the chunk window: reject `EMPTY` (no alphanumeric character at all, so punctuation-only quotes too); exact `find`; fallback whitespace-tolerant match in which a quote's tokens may be separated by spaces or **one** line break (a PDF wrap) but never a blank line, so a quote cannot stitch two statements or a heading into one span (span text always from `source.text`, never the model's); a match must start and end on word boundaries (no mid-word substrings); `max_quote_chars` bounds the *matched* span (`TOO_LONG`), not just the model's string; nothing fuzzier (paraphrase or curly-quote change → `NOT_FOUND`); a repeated quote takes the first occurrence not yet claimed in its kind, else `DUPLICATE`; overlap across kinds allowed.
- **Repair**: `ValidationError` from the provider → one retry with a repair message; second failure raises `ExtractionFailedError(source_id, pass_name)` chained to the validation error. Provider/network errors propagate. A malformed reply carries no usage, so `ExtractionResult.usage` is a lower bound on the repair path.
- **Guards**: `max_chars_per_call < 1` raises `ValueError` (it would otherwise loop forever); a literal `</document>` inside the document is neutralised in the prompt so the document cannot close its own data region.

### Scoring — `extract/scoring.py` (pure)

`score_extraction(predicted, gold) -> ExtractionScore`, per kind and overall. Match: same kind, character IoU ≥ 0.5, one-to-one greedy by highest IoU. Outputs TP/FP/FN, precision, recall; precision is `None` when `tp+fp == 0`, recall `None` when `tp+fn == 0` (no fake 1.0). These are eval metrics, not node fields, so outside the I4 formula registry; PB32 may absorb them. Gold labels are `{kind, quote}` JSON resolved through the same resolver; every gold quote must be unique in its document judged *loosely* (a whitespace variant elsewhere counts) and no two labels of a kind may resolve to the same span. Spans from different sources never match.

### Fixtures and recording

`tests/fixtures/extract/` (synthetic, `generate.py`): `prd_payments.md` (all five kinds plus seeded traps: feature-framed need, repeated sentence, requirement-not-claim, "must be fast" with no authority, dependency buried in prose, an injection sentence), `prd_payments.pdf` (shorter variant; locators carry `page`), `memo_logistics.txt` (nothing extractable), `gold/*.json`.

Recording lives under `tests/extract/`: a recorder wraps the real `completion_fn`, writes the existing `recorded_structured_response.json` shape keyed by `sha256(messages)[:16]`; replay is a `completion_fn` reading that store, so `LiteLLMProvider`'s real parse path runs. A changed prompt misses the key and fails loudly with the hash.

### Tests — `tests/extract/`

`test_candidates`, `test_resolve` (including a model-imagined "GDPR Art. 17 applies" quote → `NOT_FOUND`, the I8 unit guard), `test_chunking`, `test_pipeline` (FakeProvider), `test_scoring` (hand-computed cases, IoU exactly 0.5), `test_roundtrip` (`reextract == span.text` for md and pdf), `test_recorder`, `test_replay_golden`, and `test_live_record` (`-m live`).

### Gating check

1. 100% of emitted candidates resolve and round-trip.
2. Recorded live precision/recall per kind, with model name and token usage, written into the Implementation notes.
3. Zero candidates on the candidate-free memo.
4. The injection sentence yields no constraint.
5. `ruff`, `mypy src`, `pytest` green with no credentials.

No minimum precision/recall threshold is invented before a number exists; the replay golden test pins the recorded values so regressions are visible.

**Out of scope**: tracker-structured shortcuts (Jira Story → `StoryCandidate`), acceptance-criteria capture (PB5 may extend `StoryCandidate`), the document's own cited support for a claim (PB6), tier/kind inference, any graph node, any renderer, any critic.

**Implementation notes (resolved during build session)**

- **Measured result** (live recording, `anthropic/claude-sonnet-5`, 2026-10-04; 3 synthetic documents, 21 hand labels; 6 calls, 7,706 input / 2,665 output tokens in total). Recall was 1.0 on every kind in both PRDs and nothing was rejected, i.e. the model never produced a quote that is not in the document.

  | Kind | `prd_payments.md` P / R (tp·fp·fn) | `prd_payments.pdf` P / R (tp·fp·fn) |
  |---|---|---|
  | claim | 0.75 / 1.0 (3·1·0) | 1.0 / 1.0 (2·0·0) |
  | need | 1.0 / 1.0 (3·0·0) | 1.0 / 1.0 (1·0·0) |
  | story | 1.0 / 1.0 (2·0·0) | 1.0 / 1.0 (1·0·0) |
  | constraint | 1.0 / 1.0 (3·0·0) | 1.0 / 1.0 (2·0·0) |
  | dependency | **0.5** / 1.0 (3·3·0) | **0.33** / 1.0 (1·2·0) |
  | overall | 0.78 / 1.0 (14·4·0) | 0.78 / 1.0 (7·2·0) |

  `memo_logistics.txt` (nothing extractable): zero candidates, zero rejections. Usage per document (in/out): md 3,082/1,884; pdf 2,466/584; memo 2,158/197.
- **Where precision is lost, and why it is not tuned away here.** Every dependency false positive is a constraint sentence (PCI DSS, GDPR, the MSA) *also* tagged as a dependency — the cross-kind overlap the spec allows and the independent reviewer predicted from the "legal or compliance sign-off" wording in the dependency definition. The one claim false positive is the unlabelled priority statement "Checkout speed is our top priority." The prompts were deliberately **not** tuned against this three-document corpus: a number improved on its own test set stops being a measurement. OI17 tracks a larger corpus before any prompt tuning; the replay golden test pins these numbers so any change is a visible, deliberate diff.
- **Constraint pass**: on this corpus the separate pass produced all six expected constraints with zero false positives, and did not extract the injected CCPA sentence. That is evidence the stricter pass is not wasted, not proof it is necessary — a combined pass was not measured.
- **Gating check, as met**: (1) every recorded candidate re-extracts to its recorded text (`reextract`); (2) numbers above; (3) zero candidates on the memo; (4) no constraint (or any candidate) from the injection sentence — **for this model at this prompt**. The resolver does not stop an injected sentence that is in the document from being quoted, so this is measured behaviour, not a structural guarantee; (5) `ruff`, `mypy src`, `pytest` green with no credentials (258 passed; 100% line coverage on `core/candidates.py` and `extract/` except one unreachable `match` fall-through in `scoring.py`).
- **Independent review found real defects, all fixed before the recording** (a fresh subagent that had not seen the implementation reasoning): `chunk_windows(max_chars<=0)` looped forever; the whitespace fallback could bridge blank lines/headings into one multi-statement span and bypass `max_quote_chars`; quotes could match mid-word or be punctuation-only; the constraint prompt's "or states as non-negotiable" clause admitted any "must" requirement, contradicting I8; the `</document>` delimiter was escapable; gold labels could be duplicated or have a near-duplicate elsewhere; scoring ignored `source_id`; the repair message referred to a reply the model never saw. Each has a test that failed first.
- **Spec was wrong on three counts**: (1) "no numeric field except span offsets" — `Locator.page`/`line` are position integers too; the guard now names exactly {offsets, page, line}. (2) Quote verification does not blunt prompt injection as strongly as first stated (above). (3) The whitespace fallback as first specced ("whitespace-insensitive") was too permissive; it is now bounded to at most one line break between tokens.
- **Markdown bullets are part of the quote**: the model copied the leading `- ` of list items (as the prompt told it to), so story candidates in the md include it. They still match gold at IoU ≥ 0.5; PB5 should not assume story text begins with "As a".
- **The recorder is hand-rolled and lives in `tests/extract/_recording.py`** *(PB5 later moved it to `tests/_recording.py` and decided OI3 in its favour)*, keyed by `sha256(messages)[:16]`, one JSON per request in the existing fixture shape. The hash makes prompt edits fail loudly on replay (`MissingRecordingError`). It is evidence for OI3, which stays open until PB5.
- **Accepted, not fixed here**: `EvidenceSpan` (PB1) is not frozen and has no coherence validator, so a candidate's span can be mutated after construction; candidates validate coherence at construction only (OI16, for PB10). `ExtractionResult.usage` is a lower bound when a repair retry occurred (a failed reply carries no usage). Quotes straddling a chunk boundary are unresolvable (documented in `chunking.py`); this phase's corpus is single-chunk, so live chunked behaviour is exercised only with a scripted provider.
- **Re-recording**: `ANTHROPIC_API_KEY=... uv run pytest -m live tests/extract/test_live_record.py -s` deletes and rewrites `tests/fixtures/extract/recordings/`; then update the pinned counts in `test_replay_golden.py::test_recorded_recall_is_complete_and_precision_gaps_are_the_known_ones` and this table.
- **For PB5–PB7**: rubrics must write `applies_to: [NeedCandidate]` (PB3 matches `type(x).__name__`). Not built, by design: acceptance-criteria capture and the document's own cited support for a claim.

## PB5 — Critics: SpaceWarden, INVESTCritic

**Objective**: Two LLM-backed critics built on PB3's framework — `SpaceWarden` (I3: a `NeedCandidate` that names a feature, UI element, implementation or technology instead of a customer benefit, Olsen p. 39) and `INVESTCritic` (a `StoryCandidate` against the six INVEST properties, p. 78; blocks only on `testable`) — each a rubric file plus a class with two attributes, each with a measured catch rate on seeded defects and a measured false-positive rate on clean input.

**Prerequisites**: PB4 ✅. OI2 (reference model) and OI3 (recording library) resolved in this phase (see Implementation notes). Subagent review required — done twice.

**Design decisions (approved)**

1. **The model returns only `(candidate_id, check_id, verdict, quote)`** — verdict is `met | not_met | cannot_tell`. No score (I4), no prose (I5). A finding's message, remedy, severity and invariant are built from the rubric; its evidence span is built by deterministic code from the candidate's own span.
2. **Fail closed.** A blocking critic must never return "no findings" for candidates it did not manage to judge.
3. **No INVEST number is produced.** `invest_score` (DESIGN §8) is a formula and waits for PB11; the dimension score is PB3's `score_dimension` over the findings.
4. **Dev / held-out split (OI17 discipline).** Prompts are tuned only against `dev`; `held_out` is recorded once, after the prompts are frozen; any prompt or rubric edit afterwards demotes held-out to dev.
5. **One PR for both critics** (user's call), with the shared scaffolding reviewed separately from the two calibrations.

### Types and contract

- `core/critic.py`: `RubricCheck.severity: Severity | None = None` (optional; unset → the rubric's). `Critic._finding` severity precedence: explicit argument > check > rubric.
- `config.REFERENCE_MODEL: Final = "anthropic/claude-sonnet-5"` — a module constant, deliberately **not** a `Settings` field, so an env var or a `Settings.model` default change cannot silently move a published number.
- `llm/structured.py: complete_with_repair(provider, messages, *, output_model, model)` — one call, one repair retry on `ValidationError`, extracted from PB4's pipeline (which now uses it; behaviour identical).
- `critics/llm_judge.py`: `Verdict`, `CheckJudgement`, `JudgementBatch`, `JudgeStats`, `CriticJudgementError(critic_id, missing)` (with `.partial_findings`), `build_system_prompt(rubric, preamble)`, `build_user_message`, `locate_phrase`, `first_sentence`, `DEFAULT_BATCH_SIZE = 5`, and the abstract `LLMCritic(rubric, provider, *, model, batch_size=5)` with class attributes `candidate_type` and `preamble`, and `stats`.
- `critics/space_warden.py`, `critics/invest.py`: `SpaceWarden`, `INVESTCritic` (each with `from_builtin_rubric(provider, *, model, batch_size)`), rubrics at `src/probative/critics/rubrics/{space_warden,invest}/rubric.yaml`.

### Algorithm (`LLMCritic.check`)

Type-check candidates (wrong type → `TypeError`; the same candidate id twice is judged once), batch `batch_size` at a time, preserving order. Per batch: a system prompt rendered from the rubric's own `description`/`examples_bad`/`examples_good` plus the critic's `preamble`; candidates in a `<candidates>` data region (any `<candidate`/`</candidate` — case-insensitive, with spacing, zero-width or fullwidth variants — is neutralised). Verdict mapping:

- Unknown candidate/check ids: ignored and counted (a model typo is data, not an authoring bug).
- Repeats within one reply: counted; `not_met` beats anything else, and among two `not_met`s one whose quote resolves wins.
- **Omitted (candidate, check) pairs are re-asked once**, naming the pairs; still missing → `CriticJudgementError` (never a silent pass). Malformed output → one repair retry, then `CriticJudgementError`.
- `met`/`cannot_tell` → no finding. `not_met` → a `Finding` whose evidence is the first verbatim match of the quote inside the candidate (PB4's `occurrences`, word-boundary, whitespace-tolerant; at least 2 alphanumeric characters), offsets = candidate offset + position; a quote that does not resolve falls back to the whole candidate span (`unresolved_quotes` counted) — a block is never dropped for lack of a locatable phrase. Message: `check_id: “phrase” — <first sentence of the check description>`.

### Rubrics

- **SpaceWarden** (`NeedCandidate`, I3, `block`): one check, `solution_grammar`. Checks only solution grammar — not vagueness, not verb-first-ness. Domain words the customer uses for their own world are not violations.
- **INVEST** (`StoryCandidate`, rubric `warn`): `testable` (check severity **block**), `independent`, `negotiable`, `valuable`, `estimable`, `small` (warn). Judged from the story's own words only; a story with no acceptance criteria is `cannot_tell`, never `untestable`.

### Fixtures and calibration

`src/probative/critics/rubrics/<id>/fixtures/{clean,seeded}/{dev,held_out}/*.json` (synthetic, regenerated by `tests/fixtures/critics/generate_pb5.py`; excluded from the wheel, the rubrics ship). Defect files hold exactly one candidate (so each is individually caught); clean files hold five. Per critic: 12 + 12 defects, 10 + 10 clean candidates. SpaceWarden defect kinds: feature name, UI element, implementation, technology, solution smuggled into a benefit, injection. INVEST: two defects per property per split. Outside the S2 globs, `stress/*.json` holds hard cases (10 SpaceWarden, 9 INVEST), each with `expect_fired`, optional `allow_also` and a `why` — reported, never gating, never tuned on. `measure_mixed` judges every split's candidates interleaved at the production batch size.

### Gating check

1. `assert_rubric_fixtures` passes on replay for both critics over the whole corpus. ✅
2. Held-out catch and false-positive counts recorded with model and usage. ✅ (below)
3. Every finding's evidence re-extracts to its recorded text and lies inside its candidate. ✅
4. The injection fixtures behave correctly — measured for this model at this prompt, not structural. ✅ on the gated splits.
5. `ruff`, `mypy src`, `pytest` green with no credentials. ✅
6. Independent subagent review, twice. ✅

**Out of scope**: graph-level I3 (a Need may never reference a FeatureIdea — PB10), acceptance-criteria capture (PB26), the critique report and dimension normalisation (PB9), `invest_score` (PB11), the other critics (PB6–PB8).

**Implementation notes (resolved during build session)**

- **Measured (reference model `anthropic/claude-sonnet-5`; every recorded API response reports `claude-sonnet-5`)**:

  | Critic | Split | Caught | Intended check | False positives | Calls | Tokens in/out | `cannot_tell` |
  |---|---|---|---|---|---|---|---|
  | SpaceWarden | dev | 12/12 | 12/12 | 0/10 | 14 | 19,569 / 1,719 | 0 |
  | SpaceWarden | held-out | 12/12 | 12/12 | 0/10 | 14 | 19,590 / 1,472 | 0 |
  | INVEST | dev | 12/12 | 12/12 (2/2 per property) | 0/10 | 14 | 26,353 / 10,710 | 5 |
  | INVEST | held-out | 12/12 | 12/12 (2/2 per property) | 0/10 | 14 | 26,414 / 10,258 | 9 |

  No unresolved quotes, unknown ids or omitted judgements in any run. Prompts were **not tuned** — dev was perfect on its first run, so held-out was recorded against the prompts exactly as first written.
- **How much that number means — less than it looks.** Pooled over both splits, 24/24 caught (one-sided 95% lower bound ≈ 0.88) and 0/20 false positives (95% upper bound ≈ 0.14); per-check INVEST n=2 is not a catch rate. The corpus is synthetic and written by one author in one sitting: defects read "need a NOUN", clean needs read "need to VERB" (stylistically separable); every INVEST defect has exactly one flaw signposted by words from the rubric; **no clean item ever drew `cannot_tell`** (all 14 `cannot_tell` verdicts are on defect files), so nothing sat near a boundary. **Held-out is not independent of the rubric text**: "as many as possible" and "seamless" appear in a rubric description and in a held-out story; several dev defects are near-copies of rubric examples (a mobile app so I can see my balance, machine learning to recommend products); the dev clean set uses the very domain nouns the SpaceWarden preamble protects, so dev's 0/10 is partly by construction. Injection fixtures are parentheticals addressed to "the critic" — the exact attack the preamble lists; INVEST has no pass-injection in the gated splits. Conditions differ from production: n=1 per fixture at the provider's default temperature (no repeat runs), defects judged one per call whereas production batches up to 5. The `stress` split and `measure_mixed` were built to test these; **at the time of writing they are implemented and unit-tested but NOT recorded** (needs a developer run: `PB5_SPLIT=stress`), so hard-case and batched behaviour are unmeasured.
- **Spec was wrong or silent on**: (1) S2's sample `applies_to: [Need, FeatureIdea]` — rubrics name candidate classes (corrected above); (2) S2 had one severity per rubric, but DESIGN says INVEST blocks only on untestable → optional `RubricCheck.severity`; (3) `Critic.check` returning only findings leaves nowhere to put incompleteness — resolved by raising, not by widening PB3's contract; (4) the PB4 spec's INVEST expectation that `independent`/`estimable`/`small` would often be `cannot_tell` was not observed on this corpus (kept as a documented, unconfirmed expectation).
- **Independent review #1 found, all fixed with a test that failed first**: **fail-open** — a reply of `{"judgements": []}` returned `[]` from a *blocking* critic with only a counter to show for it (now re-ask once, then raise); conflicting duplicates resolved by first-wins (now `not_met` wins); the default `batch_size=20` was unmeasured and the built-in critics' own entry points still carried it after the base default changed (now 5, the largest size actually recorded, tested on the real entry points); finding messages embedded the rubric's "Not a violation: …" carve-out and read self-contradictory (first sentence only); one-character quotes accepted as evidence; the delimiter neutraliser was exact-prefix and case-sensitive; a model-pin test that was tautological (it compared a constant to a file written from that constant — now checks each recorded response's own `model` field); `invest.py` docstring predicted `cannot_tell` behaviour the recordings do not show; the live-record test deleted recordings before the API call succeeded. **Review #2 (of the fixes)** found no blocker; fixed: evidence quality among duplicate `not_met`s, a `duplicates` counter polluted by the re-ask, partial findings lost when a later batch raises (now `CriticJudgementError.partial_findings`), more invisible-character delimiter variants, an ambiguous stress label (OAuth under `negotiable`, now `allow_also`), and the live-record swap (both corpora staged, swapped together, old kept aside — `_swap.py`, unit-tested).
- **Accepted, not fixed**: an all-`cannot_tell` reply returns no findings silently (fail-open for the blocking checks; a ratio guard would be an invented threshold — PB32); remaining delimiter lookalikes (`‹`, `〈`, `&lt;`, homoglyphs) are untested against a model; a quote copied from neutralised text falls back to the whole candidate span (coarser evidence, never wrong); a sub-span's locator inherits the candidate's (a quote on page 2 of a page-spanning candidate reports page 1); `stats.calls`/`usage` are not updated on failure paths; `LiteLLMProvider` passes no `max_tokens` or `temperature` (truncation and run-to-run variance unmeasured); `check` is all-or-nothing per call; the `"- "` list-marker clause in INVEST's preamble reflects PB4's measured bullet behaviour, not this corpus.
- **OI3 decided**: the hand-rolled recorder is kept and shared (`tests/_recording.py`, moved from `tests/extract/`; the directory and re-record hint are now parameters, and PB4's tests were updated for the move). It records at the `completion_fn` seam so `LiteLLMProvider`'s real parse path runs, and a prompt/rubric edit fails replay loudly by key. A vcr-style cassette records HTTP, which couples to litellm internals and puts request headers on a public repo.
- **Coverage**: 100% line+branch on `llm_judge`, `space_warden`, `invest`, `llm/structured`, `core/critic`; `base.py` 95% (the one uncovered line is PB3's unreachable abstract body). 379 tests in the default suite (258 before), all key-free.
- **Re-recording**: `ANTHROPIC_API_KEY=… PB5_SPLIT=<dev|held_out|stress> uv run pytest -m live tests/critics/test_pb5_live_record.py -s`. Held-out refuses to overwrite without `PB5_RERECORD_HELD_OUT=1`, which demotes it to dev. The replay test pins recorded measurements; when the stress recording exists, add a `stress` replay test.

## PB6 — Critics: EvidenceAuditor, SegmentSkeptic

**Objective**: Two more LLM-backed critics on PB5's `LLMCritic`, each with a measured catch rate and false-positive rate. **PB6-p1 `EvidenceAuditor`** (I1): does a factual statement's own words state a basis, and can a stated basis carry its scope. **PB6-p2 `SegmentSkeptic`**: is a stated "segment" a group with differing needs and behaviour, or a demographic bucket (DESIGN §13). p2 also adds the `SegmentCandidate` kind and an opt-in segment extraction pass.

**Prerequisites**: PB4 ✅, PB5 ✅. Subagent review required — done (see notes).

**Design decisions (approved)**

1. **Judge only what the statement's own words say.** Neither critic judges truth, existence of a source, or whether a segment is real. A fabricated statistic with a plausible citation passes `EvidenceAuditor`; a demographic group that does differ in need elsewhere is still flagged by `SegmentSkeptic`. Both need a resolvable `Source` / graph (PB13+) to do more.
2. **Absence is the violation.** PB5's judge preamble says missing information is `cannot_tell`; that would have a blocking provenance critic pass the very claims it exists to flag. `LLMCritic.judge_preamble` (a ClassVar defaulting byte-for-byte to PB5's text, pinned by SHA-256 in a test) lets a critic supply its own verdict semantics. A critic is now "a rubric plus two class attributes, plus a third when absence is the finding".
3. **p2 segment extraction is opt-in.** `extract_candidates(..., passes=None)` runs PB4's two passes unchanged (prompt hashes pinned, so PB4's recordings keep replaying); `passes=[*PASSES, SEGMENT_PASS]` adds segments. Adding a pass to `PASSES` would have broken PB4's pass-count test and every recorded key.
4. **`demographic_only` blocks** (DESIGN §13); `whole_market` warns; per-check severity via PB5's `RubricCheck.severity`. p2 rubric `invariant` is `null` (DESIGN assigns SegmentSkeptic none; INVEST precedent). **Two caveats travel with that block** (see the notes): it also fires on whole-market statements, with a finding message that is then wrong for them, and the one genuinely harmful false block is a good segment whose need sits in the next sentence (`need_in_next_sentence`, which fires in stress). `EvidenceAuditor` claims I1 only — **not I4**: it emits no number, and I4's mechanism is `FormulaValidator` (PB11); DESIGN's "I1, I4" wording was looser than a text critic can enforce.
5. **Dev / held-out split (OI17), stress outside the S2 globs**, as PB5. Pre-recording independent reviews ran for both phases (below).

### Types and contract

- p1: `critics/evidence_auditor.py` (`EvidenceAuditor`, checks `unsourced_statistic` block, `basis_overreach` block, `unsourced_assertion` warn; applies to `ClaimCandidate`); rubric `rubrics/evidence_auditor/rubric.yaml`; `LLMCritic.judge_preamble` + `build_system_prompt(..., judge_preamble)`.
- p2: `CandidateKind.SEGMENT`, `SegmentCandidate` (no new field; id `cand_segment_<12 hex>`), `ExtractionResult.segments`, `Candidate` union; `extract/prompts.py`: `SegmentOutput`, `SEGMENT_PROMPT`, `SEGMENT_PASS`; `extract_candidates(..., passes=)` (an empty list raises `ValueError`); `critics/segment_skeptic.py` (`SegmentSkeptic`, checks `demographic_only` block / `whole_market` warn, own `judge_preamble`); rubric `rubrics/segment_skeptic/rubric.yaml`.
- Ripple into PB4 code/tests (mechanical): `scoring._make` gained a `match` case; `test_scoring`/`test_replay_golden` iterate every `CandidateKind`, so the recorded-five-kinds assertions were narrowed and the new kind is asserted all-zero on PB4's corpus.

### Rubric policy that the p2 pre-recording review forced (all in `rubric.yaml`, tested)

*Who they are* = age, gender, income, location, job title or occupation, company size, industry, a **status** (married, employed, a homeowner, living alone, a student, a subscriber), a device owned, or having bought or used something **however it is phrased**. A **situation** is a circumstance that creates a need or a task (about to renew a licence), not a status. `whole_market` = everyone, or a condition nearly everyone meets (has worn clothes, has used a phone); common knowledge may be used for that check only. `cannot_tell` only when the text names no group of people at all.

### Fixtures

Synthetic, single-author, generators `tests/fixtures/critics/generate_pb6.py` (p1) and `generate_pb6_p2.py` (p2); shipped under each rubric's `fixtures/` and `stress/` (excluded from the wheel). p1: 12+12 defects (4 per check), 12+12 clean candidates, 14 stress. p2: 12+12 defects (8 `demographic_only`, 4 `whole_market` per split), 10+10 clean candidates, 15 stress. Extraction: `tests/fixtures/extract/prd_segments.md` (4 gold segments plus traps: a story naming a role, a need naming a role, a group size, one person, an injected instruction), PB4's `prd_payments.md` as a zero-gold false-positive probe, and PB4's candidate-free memo. Guards beyond PB5's: token-overlap (Jaccard) against rubric examples and between splits; **p2 adds a four-word-run guard against the whole rendered prompt**, which caught a held-out injection copied from the preamble.

### Gating check

1. `assert_rubric_fixtures` passes **on recorded responses** for both critics over dev + held-out. ✅
2. Held-out catch/false-positive recorded with model, n and usage. ✅ (below)
3. Every finding's evidence re-extracts to its recorded text and lies inside its candidate. ✅
4. Injection fixtures behave correctly — measured for this model at these prompts, not structural. ✅ on the gated splits.
5. p2 segment extraction recorded and pinned: 4/4 gold found, none of the traps, nothing on the memo or the false-positive probe. ✅ (A pin on a document the pass's two-sentence carve-out was written against, 3 documents and 4 gold labels: not an estimate.)
6. `ruff`, `mypy src`, `pytest` green with no credentials. ✅
7. Independent subagent review. ✅ (below)

**Out of scope**: truth or existence of a cited source (PB13), graph-level I1/I2 (PB10), onboarding-mode exclusion mechanism (PB12/PB39, OI22), users-vs-buyers/adoption/personas (PB16), the critique report (PB9), `invest_score` (PB11).

**Implementation notes (resolved during build session)**

- **Measured (reference model `anthropic/claude-sonnet-5`; every recorded response reports `claude-sonnet-5`)**:

  | Critic | Split | Caught | Intended check | False positives | Calls | Tokens in/out | `cannot_tell` |
  |---|---|---|---|---|---|---|---|
  | EvidenceAuditor | dev | 12/12 | 12/12 (4/4 per check) | 0/12 | 16 | 46,203 / 8,124 | 0 |
  | EvidenceAuditor | held-out | 12/12 | 12/12 (4/4 per check) | 0/12 | 16 | 46,187 / 7,952 | 0 |
  | SegmentSkeptic | dev | 12/12 | 12/12 (8/8, 4/4) | 0/10 | 14 | 32,651 / 4,022 | 0 |
  | SegmentSkeptic | held-out | 12/12 | 12/12 (8/8, 4/4) | 0/10 | 14 | 32,563 / 3,959 | 0 |

  Stress (never gating, never tuned on; "as labelled" means every `expect_fired` check fired and nothing outside `expect_fired ∪ allow_also` did, so a known false positive labelled as expected counts as expected — **strict** `fired == expect_fired` is 11/14 for EvidenceAuditor and 13/15 for SegmentSkeptic, the differences being the cases labelled lenient): EvidenceAuditor 14/14 as labelled (39,983 / 5,587 tokens); SegmentSkeptic 15/15 as labelled (34,469 / 3,219; 2 `cannot_tell` verdicts, the stress rows do not record which cases). **Mixed batches** (every split's candidates interleaved at the production batch size 5): EvidenceAuditor 24/24 caught, 0/24 false positives over 48 candidates in 10 calls; SegmentSkeptic 24/24 caught, 0/20 over 44 candidates in 9 calls. No unresolved quote, unknown id or omitted judgement in any run.
- **What those numbers mean — less than they read.** Pooled over both splits each critic caught 24/24 (one-sided 95% lower bound ≈ 0.88) with 0/24 (p1) and 0/20 (p2) false positives (95% upper bounds ≈ 0.12 and ≈ 0.14); per-check n is 8 (p1, each check), 16 and 8 (p2), i.e. lower bounds ≈ 0.69, 0.83, 0.69. **Held-out only** (the only split no prompt was tuned against; p2 dev was tuned and both were reshaped by a pre-recording review): 12/12 caught gives a lower bound ≈ 0.78, and 0/12 (p1) and 0/10 (p2) false positives give upper bounds ≈ 0.22 and ≈ 0.26 — quote these, not the pooled ones. The corpora are synthetic and written by one author; the p2 independent review measured that a three-line regex separated clean from seeded at about 91% on the gated items before it was reshaped, and the reshaped sets are still single-author (OI21 stays open). Perfect scores on the first run left nothing to tune for p1 or p2-dev-before-review, which is itself weak evidence.
- **Co-firing in p2 (the one real finding in the recordings).** The first p2 dev recording had `demographic_only` — the *blocking* check — also fire on two `whole_market` seeds, although the rubric excludes everyone-ish groups from it. One tuning step followed, on dev only: a sentence in the judge preamble (*"a group that is everyone, … is met on demographic_only: only whole_market applies to it"*). Held-out was then recorded once on that frozen prompt. Result: dev co-firing 2 → 0 (dev is the tuned split, so that shows nothing out of sample) and **held-out co-firing on 2 of 4 `whole_market` seeds** (`consumers_at_large`, the format-instruction injection). **No held-out baseline from before the edit exists, so the tie-break has no demonstrated effect out of sample**: before the edit dev co-fired on 2 of 4, after it held-out co-fires on 2 of 4. A whole-market statement can therefore be blocked as well as warned, and the finding text then reads "defines the group only by who its members are", which is wrong for "everyone who …". Recorded and pinned in `test_pb6_replay.py::PINNED_EXTRAS`, not tuned further — any further prompt edit makes held-out stale and needs fresh held-out fixtures (OI23). p1 had one analogous extra (`unsourced_assertion` also firing on a figure whose sentence also asserts a fact; defensible).
- **Recording order, disclosed.** p2 held-out was first mistyped (env var name) and ran as dev; p2 stress and mixed were recorded before held-out, so held-out candidates were judged inside the mixed run before the held-out run. No prompt edit followed that, but held-out is therefore not "never seen by the model in any batch". After the tie-break edit, p2 dev and stress were re-recorded; held-out was not re-run.
- **Known false-positive class, measured not hidden.** One-statement judgement cannot see a basis or a need that sits in a later sentence: EvidenceAuditor `adjacent_source` fires; SegmentSkeptic `need_in_next_sentence` fires (`demographic_only`, a **block**). The p2 extraction pass quotes a two-sentence definition as one candidate and the critic then passes it (`two_sentence_definition`), but a definition in a later paragraph is invisible. A blocking check with this class means the stress number must be quoted beside the catch rate.
- **Segment extraction (recorded; 3 documents, 4 gold labels, a pin not an estimate).** `prd_segments.md`: 4/4 found including the two-sentence definition, 0 false positives, nothing rejected, none of the traps and not the injected "all humans" line; `prd_payments.md` (PB4's PRD, no target group defined) and the candidate-free memo: 0 segments. Tokens in/out 1,178/471, 1,382/1,013, 920/9.
- **Independent reviews.** *p1, before recording* (earlier session): three blockers (undefined/approximating words disputing a third of the labels; held-out was dev with the domain swapped and both near-copies of rubric examples; two causation seeds collided with the rubric's own carve-out) — fixed, plus a token-overlap guard. *p2, before recording*: **not safe to record** as built; four blockers — `whole_market` contradicted its own carve-out and "close to everyone" was undefined; `cannot_tell` was an escape hatch for the bare noun-phrase seeds; the held-out injections copied the prompt's wording; "situation" and purchase-versus-behaviour were undefined, leaving labels in dispute — all fixed, each with a test that failed first, and the held-out set was reshaped while still unrecorded. *Post-recording review of the final state* (fresh reader, whole PB6 incl. docs): verified every per-split number, the stress/mixed totals and the segment-extraction results against the committed `results.json` files, the PB4/PB5 prompt SHA pins, the PB4 test edits (mechanical, not weakened), I1/I4/I5, idempotence of both fixture generators, and by mutation that every committed recording matches the current prompt (removing the tie-break sentence fails 14 replay tests incl. both held-out). It found **two blockers** — the docs claimed this review before it existed, and the tie-break was described as having "reduced but not removed" the co-firing when only the tuned split supports that — and fixed in the same session: the claims above are rewritten to say the effect is unmeasured out of sample; plus held-out-only bounds (S1), a definition and strict counts for "as labelled" (S4), the caveats beside the block in DESIGN §13 and decision 4 (S3), SegmentSkeptic named in S5 and pointers added to PB12/PB39 (S2), stale references corrected (S6), and the live recorders now require the split variable explicitly because a mistyped default caused the disclosed incident (S7; PB5's recorder has the same default and is left alone). Not changed: the EvidenceAuditor stress case `form_minutes` ("takes about six minutes") is the judge preamble's own worked example — it is non-gating, rewording it would stale the p1 stress recording, and the four-word-run guard now covers p1's gated splits (it found them clean) with this case documented as the exception. Not verifiable from the repo: the pre-edit p2 dev recording (replaced by the re-record), the exact order of stress vs. held-out, and the "~91%" regex figure (no artifact).
- **Spec was wrong or silent on**: (1) DESIGN gives `EvidenceAuditor` "I1, I4"; a text critic enforces I1 only. (2) DESIGN §13 says `SegmentSkeptic` blocks while `docs/GETTING-STARTED.md` showed it as WARN — the sample was corrected to BLOCK. (3) PB5's "a critic is a rubric plus two class attributes" held only for open-world critics. (4) `Rubric.invariant` is nullable, which p2 uses.
- **Accepted, not fixed**: the p2 recordings are n=1 at the provider default (OI19); all-`cannot_tell` reply passes silently (OI21/PB32); onboarding-mode exclusion of `SegmentSkeptic` is documentation only until a mode config exists (**OI22**); the co-firing and single-statement visibility limits (**OI23**).
- **Re-recording**: `ANTHROPIC_API_KEY=… PB6_SPLIT=<dev|held_out|stress> uv run pytest -m live tests/critics/test_pb6_live_record.py -s` (EvidenceAuditor), `PB6P2_SPLIT=…` with `test_pb6p2_live_record.py` (SegmentSkeptic), `uv run pytest -m live tests/extract/test_live_record_segments.py -s` (segment pass; writes only `recordings_segments/`). Held-out refuses to overwrite without `PB6[P2]_RERECORD_HELD_OUT=1`, which demotes it to dev.

## PB7 — Critics: ConstraintCritic, DependencyCritic
**Prerequisites**: PB4 ✅. Subagent review required.
**Note**: in standalone critique mode these report untraced obligations and unowned dependencies found *within the document*. Graph-wide enforcement is PB22 and PB25.

## PB8 — Critic: RedTeam
**Prerequisites**: PB4 ✅. Subagent review required.
**Known unknowns**: whether a generative critic can be held to a false-positive standard the same way a rule-checkable one can.

## PB9 — Critique report
**Objective**: `probative critique <file>` → scored dimensions plus qualitative findings with quoted evidence, as Markdown and single-file HTML. **Slice C ships.**
**Prerequisites**: PB5–PB8 ✅, S4.

## PB33 — MCP server
**Objective**: Expose `critique` as an MCP tool; extend to run operations as later phases land.
**Prerequisites**: PB9 ✅.

## PB34 — Plugin skin
**Objective**: Slash commands and a skill over the MCP server. Thin by construction — no logic that is not in the core.
**Prerequisites**: PB33 ✅.

## PB36 — Ingest: delivery artifacts
**Objective**: Git history, PR review threads, Confluence page history and view counts, and feature-flag configuration become `Source` and `EvidenceSpan` records under a new `delivery` evidence kind.
**Prerequisites**: PB1, PB2, PB10 ✅. OI14 resolved (live connectors vs exports).
**Known unknowns**: whether v0.1 reads live connectors or exports only — a week-one joiner usually has neither access nor patience; how to represent a PR review thread as spans without losing who said what to whom.

## PB37 — Code archaeology
**Objective**: Extract business rules from test names, feature-flag state, DB migration timeline, dead code and API surface. This is the entire `safe_to_say` band — nothing else earns it.
**Prerequisites**: PB36 ✅, S5.
**Known unknowns**: test-name parsing is language- and framework-specific; pick one stack for v0.1 and say which. A rule extracted from a skipped or quarantined test is not a rule — detect that.

## PB38 — Ticket forensics
**Objective**: Lifecycle statistics, reopen counts, time-in-status, and Won't-Fix and stale tickets as the recovered refusal list.
**Prerequisites**: PB36 ✅. OI13 resolved (sampling strategy).
**Known unknowns**: four years of Jira exceeds any sensible budget. Ranking signals — recency, reopen count, link density, comment volume, Won't-Fix — need weights and a cap. Status names vary per project; the workflow itself has to be inferred before time-in-status means anything.

## PB39 — Reconstruction and banding
**Objective**: Product map, glossary with first appearance and who introduced each term, decision log, contradiction list, absence list. Every claim banded per S5. `NeutralityCritic` implements I9.
**Prerequisites**: PB37, PB38 ✅, S5. **Subagent review required.**
**Open item**: OI22 — the mode config must exclude `SegmentSkeptic` (and decide on the other evaluative critics) in onboarding mode; today that is documentation only.
**Known unknowns**: absence detection needs a notion of what *should* be present — probably a small taxonomy of categories (accessibility, security, performance, a user type with no tickets) rather than open-ended inference.

## PB40 — People and knowledge map
**Objective**: Contributor graph per area from commits, reviews, comments and doc edits; inactive contributors marked; concentration of knowledge surfaced.
**Prerequisites**: PB36 ✅, S5. **Subagent review required.**
**Known unknowns**: identity resolution across git, Jira and Confluence is genuinely hard — one person is three accounts and two spellings. Where identities cannot be resolved confidently, aggregate rather than guess.
**Non-negotiable**: this phase describes where knowledge lives. It never characterises performance. See S5.

## PB41 — Onboarding pack and conversation prep
**Objective**: The ranked question list with who-to-ask, the HTML pack, and `probative onboard brief --topic X`. **`onboard` ships.**
**Prerequisites**: PB39, PB40 ✅, S4, S5.
**Known unknowns**: how to rank questions by how much each unblocks — probably blast radius over the reconstruction graph, the same computation as `blast_radius`. Cap the list; a new PM arriving with forty generated questions will annoy everyone and use the tool once.

## PB35 — GitHub Action
**Objective**: Critique runs on any PR touching a spec and posts findings as review comments.
**Prerequisites**: PB9 ✅.

## PB10 — Graph core
**Objective**: Node and edge types, `graph.json` schema, SQLite mirror, `partition`/`owner` on every node, `SUPERSEDES`, I1 and I5 validators.
**Prerequisites**: PB0 ✅, OI11 considered. Subagent review required.
**Known unknowns**: whether the SQLite mirror should be generated from the schema or hand-written.

## PB11 — Formula registry
**Objective**: Every Olsen formula as a registered pure function, unit-tested against the book's worked examples. `FormulaValidator` (I4) recomputes and diffs on commit.
**Prerequisites**: PB10 ✅. Subagent review required.
**Note**: worked examples to test against — Ulwick opportunity 10/5→15 and 6/1→11 (p. 57); customer value 0.7×0.7=0.49 (p. 60); opportunity 0.7×0.3=0.21 and 0.9×0.7=0.63 (p. 61); Feature X 0.82×0.45=0.37 (p. 62); value created 0.7×0.2=0.14 (p. 63); ROI 6÷2=3 vs 6÷4=1.5 (p. 82).

## PB12 — Runtime
**Objective**: LangGraph phase machine, propose/dispose patches, `Committer`, critic fan-out and join, repair loop capped at 3 cycles, gates with `interrupt_before`, SQLite checkpointing, per-phase token and wall-clock budgets, `TediumAuditor` interaction counters.
**Prerequisites**: PB10, PB11 ✅.
**Open item**: OI22 — the mode config must exclude `SegmentSkeptic` (and decide on the other evaluative critics) in onboarding mode; today that is documentation only.

## PB13 — Evidence ledger
**Objective**: Tier and kind classification, dedupe, entity resolution, contradiction detection producing `CONTRADICTS` edges and `Question` nodes, corroboration by independent source, confidence propagation.
**Prerequisites**: PB12 ✅, OI4 resolved.

## PB14 — Elicitor + BiasHunter
**Objective**: Adaptive interrogation with basis capture, information-gain stopping, `unknown` as a valid outcome, in-the-moment challenge against ingested evidence. `BiasHunter` audits the transcript in the same phase.
**Prerequisites**: PB13 ✅.
**Known unknowns**: how to measure marginal information gain cheaply enough to run between questions.

## PB15 — DeskResearcher
**Prerequisites**: PB13 ✅.

## PB16 — Segments + proto-personas → G1
**Prerequisites**: PB14 ✅.

## PB17 — Needs, ladders, hierarchy
**Prerequisites**: PB16 ✅.

## PB18 — Ratings, opportunity, Kano → G2
**Prerequisites**: PB17, PB11 ✅.

## PB19 — Opportunity landscape
**Objective**: Interactive scatter, confidence envelopes sized by n and tier, rectangle-area value rendering, quadrant labels, T5 ghosts. **Slice A ships.**
**Prerequisites**: PB18 ✅, S4.

## PB20 — Brownfield: as-is model
**Prerequisites**: PB13 ✅, OI7 resolved.

## PB21 — Brownfield: incumbent satisfaction
**Prerequisites**: PB20 ✅.
**Known unknowns**: the mapping from operational signal to satisfaction is a registered formula with a stated rationale — which signals, and with what defensible transform, is the open question.

## PB22 — Brownfield: constraints
**Prerequisites**: PB20 ✅. Subagent review required.

## PB23 — Value proposition → G3
**Prerequisites**: PB18, PB22 ✅.

## PB24 — Features → MVP
**Prerequisites**: PB23 ✅, OI8 resolved.

## PB25 — Dependencies + premortem → G4
**Prerequisites**: PB24, PB22 ✅.

## PB26 — Story map + stories → G5
**Prerequisites**: PB25 ✅.

## PB27 — Baselines + variance
**Prerequisites**: PB26 ✅. Subagent review required.

## PB28 — Exporters
**Prerequisites**: PB26 ✅, OI6 resolved. Subagent review required.

## PB29 — Provenance story map
**Prerequisites**: PB26 ✅, S4, OI10 resolved.

## PB30 — RTM + RAID + assumption ledger
**Prerequisites**: PB27, PB29 ✅, OI9 resolved.

## PB31 — Journey + empathy projections
**Prerequisites**: PB17 ✅. *First cut candidate under schedule pressure.*

## PB32 — Eval harness
**Objective**: Metrics runner, seeded-defect corpus, per-provider variance against a pinned reference model. **v0.1 complete.**
**Prerequisites**: PB3, PB19 ✅, OI2 resolved.
