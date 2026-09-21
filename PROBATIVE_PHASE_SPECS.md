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

Critics are configured by data, not by prose buried in a prompt. A contributor adds a critic by writing a rubric and a class with one method.

```yaml
id: space_warden
severity: block
invariant: I3
applies_to: [Need, FeatureIdea]
checks:
  - id: solution_grammar
    description: A Need that names a feature, a UI element, or an implementation
    examples_bad: ["users need a dashboard", "provide an API for reconciliation"]
    examples_good: ["help me see where my money went this month"]
    remedy: Restate as a customer benefit — verb first, customer voice
clean_fixtures: fixtures/clean/needs_*.json    # must raise nothing on these
defect_fixtures: fixtures/seeded/space_*.json  # must catch every one
```

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

## PB2 — Ingest: structured exports
**Objective**: Confluence exports and Jira/ADO CSV exports become sources with recognised issue keys, hierarchy and acceptance criteria.
**Prerequisites**: PB1 ✅, OI5 resolved.
**Known unknowns**: how many Confluence export variants matter; whether ADO's HTML description field needs its own normalisation path.

## PB3 — Finding model + critic framework
**Objective**: A critic can be added by writing a rubric file (S2) and a class with one method, with no runtime change.
**Prerequisites**: PB0 ✅, OI3 resolved.
**Known unknowns**: whether dimension scores should be a weighted mean of findings or a floor-based rubric; the former is smoother, the latter harder to game.

## PB4 — Shallow extraction
**Objective**: Typed candidates — claims, needs, stories, constraints, dependencies — extracted from a single document with locators, without constructing a graph.
**Prerequisites**: PB1, PB2, PB3 ✅.
**Known unknowns**: precision/recall achievable on unstructured PRDs; whether constraint extraction needs its own pass.

## PB5 — Critics: SpaceWarden, INVESTCritic
**Prerequisites**: PB4 ✅, OI2 and OI3 resolved. Subagent review required.

## PB6 — Critics: EvidenceAuditor, SegmentSkeptic
**Prerequisites**: PB4 ✅. Subagent review required.

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
