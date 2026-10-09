# PROBATIVE_BUILD_PLAN.md — Sequencing, Risks, and Gates

Why the phases run in this order, what can go wrong at each step, and what is still unconfirmed.

---

## Phase Sequencing

### PB0 → everything: the no-key test rule is a foundation decision, not a testing decision

The repository is public from the first commit, so CI on a pull request from a fork has no secrets. If the recorded-fixture pattern is not established at PB0, it will be established at PB14 instead — by which point a dozen agent phases have tests that only run on a machine with a key, contributors cannot verify their own PRs, and the fix means rewriting every one of them. This costs an afternoon now and a fortnight later.

### PB3 → PB4 → PB5–PB8: the framework before the critics

Writing the first critic and the critic framework together produces a framework shaped entirely by that one critic. `SpaceWarden` is a pure text-classification problem; `DependencyCritic` needs graph-ish reasoning about boundaries; `RedTeam` is generative. Building the frame first, against the requirements of all four kinds, is what lets a contributor add the fifth by writing a rubric file.

### PB9 before PB10: Slice C ships before the graph exists

This is deliberate and slightly uncomfortable. The critique layer has no cold-start problem — it works on documents people already have — so it is the distribution wedge and the thing that earns the first attention. It also forces the `Finding` model, the rubric format and the extraction machinery into existence early, where every later phase needs them.

The risk is building throwaway code. The mitigation is that PB4's extraction is the same extraction the evidence ledger uses at PB13, and PB3's findings are the same findings the runtime consumes at PB12. If either turns out to be throwaway, that is a signal the abstraction was wrong, not that the sequencing was.

### PB10 → PB36–PB41 → PB20: onboarding before the forward pipeline

`onboard` needs the graph and the ingestion layer. It does not need the runtime, the formulas or any gate. Sequencing it before the forward pipeline buys three things: a second zero-cold-start entry point beside `critique`; a working as-is model feeding the brownfield path rather than a hypothetical one; and the earliest possible test of whether the tier model survives contact with messy real evidence — because `delivery` evidence is the messiest there is.

The risk of building it early is that it is the mode most likely to produce confident nonsense, since almost everything it emits is T4 inference. That is also the argument for building it early: if the banding discipline cannot hold here, it will not hold anywhere, and better to find out in week five than week fourteen.

### PB11 → PB18: the formula registry gates all scoring

I4 says numbers are computed, never generated. The only way to make that true rather than aspirational is for the formulas to exist, be tested against Olsen's own worked examples, and be the only path to a numeric field before anything computes a score. Build opportunity scoring first and there will be a `float` somewhere that a model produced, it will be plausible, and it will never be found.

### PB10 carries `partition` and `owner` from the start

Multi-operator federation ships in v0.2, but the ownership axis ships in v0.1. Two fields on every node cost nothing now. Adding an ownership axis after PB26 means every node type, every migration, every renderer and every exporter. This is the cheapest expensive decision in the project.

### PB13 → PB20: brownfield rides the same pipeline

`ProcessMapper` and `IncumbentRater` are additional producers feeding the same evidence ledger and the same needs machinery. Brownfield is not a parallel pipeline; if it starts becoming one, something has been modelled wrongly and the right response is to fix the model, not to fork the pipeline.

### PB22 → PB25: constraints before the gate that blocks on them

G4 is supposed to block on untraced obligations (I8). A G4 built before `ConstraintTracer` exists is a gate that passes everything, and gates that have always passed do not get trusted later when they start failing.

### PB26 → PB27/PB28/PB29: the story map is the fan-out point

Baselines, exporters and the provenance map are three independent consumers of a committed story map. They can be built in any order, or in parallel by different people. PB29 is the demo, so it goes first if there is any external deadline.

---

## Risks by Phase

### PB0
- **Risk**: LiteLLM's abstraction leaks, and agent code ends up written against Anthropic's tool-use semantics anyway.
- **Mitigation**: the provider adapter exposes a narrow internal interface — structured output against a Pydantic model, plus token accounting. No agent imports LiteLLM directly. A test asserts that no module outside `probative/llm/` imports it.

### PB1
- **Risk**: PDF extraction produces offsets that do not survive re-extraction, silently breaking every provenance claim downstream.
- **Mitigation**: the round-trip test is the gating check, not a nice-to-have. Any extractor that cannot reproduce its own spans is rejected before it ships.
- **Risk**: scanned PDFs need OCR, and OCR output has no reliable offsets into the original.
- **Mitigation**: OCR'd sources are tagged as such and their spans carry a lower confidence ceiling. Do not pretend an OCR offset is a byte offset.

### PB2
- **Risk**: "Confluence export" is at least three different formats depending on version and whether it is Cloud or Data Center.
- **Mitigation**: OI5. Confirm which variants matter before building; support one properly rather than three badly. **Resolution (PB2 session)**: no real Confluence sample was available in PB2's build session, so Confluence was split out entirely to PB2-p2 rather than guessed at — the mitigation was applied by deferring, not by picking a variant blind. **Resolution (PB2-p2 session)**: two real Confluence Cloud per-page exports (Word and PDF) confirmed the format *and* invalidated the assumption behind the risk itself — a Confluence page carries no issue/hierarchy structure to "get wrong," so the three-formats-for-one-schema risk this stub anticipated doesn't apply to the per-page export variants. What remains genuinely unconfirmed is the space-level bulk export (see OI5's updated note).
- **Risk (materialised, not anticipated)**: real Jira/ADO exports turned out to have their own format-variance risk the original stub didn't name — two different Jira CSV column-set sizes, three different Jira export formats (CSV/HTML/XML) for the same data, and two different markup dialects (wiki markup vs. real HTML) hiding behind the same "Description" field name.
- **Mitigation (applied)**: real samples of every in-scope format were inspected before writing the spec; column/field recognition is name-driven and column-order/repeat-column independent rather than positional, so instance-to-instance variance within a format doesn't require a code change.

### PB4
- **Risk**: extraction quality silently caps the quality of every critic built on top of it, and it is hard to attribute a bad finding to bad extraction.
- **Mitigation**: precision and recall measured against a hand-labelled fixture at PB4 and recorded. Critic evals at PB32 report extraction-attributable failures separately. **Resolution (PB4 session)**: measured live on `anthropic/claude-sonnet-5` against a 3-document, 21-label synthetic corpus — recall 1.0, overall precision 0.78, all precision loss in the dependency kind (constraint sentences double-tagged). The corpus is far too small to generalise from and prompts were deliberately not tuned on it; OI17 tracks the larger corpus. PB32 should report these extraction-attributable errors separately, as planned.

### PB5–PB8
- **Risk**: critics drift toward finding fault to appear useful. A critic that blocks everything is as useless as one that blocks nothing, and it is far more annoying.
- **Mitigation**: every critic ships with a clean fixture set on which it must raise nothing. False-positive rate is a gating check, not a metric to look at later.
- **Risk**: critic behaviour varies by provider, so a rubric tuned on one model misbehaves on another.
- **Mitigation**: OI2 — pin a reference model for published numbers; report per-provider variance from PB32. **Resolution (PB5 session)**: OI2 resolved (`REFERENCE_MODEL`). PB5 measured both critics at 12/12 caught and 0/10 false positives on dev and on held-out, **with prompts untuned** — and then an independent review showed how little that proves on a synthetic single-author corpus (OI21): the false-positive discipline is in place as a *method* (clean fixtures that must raise nothing, a held-out split recorded once, critics that fail closed), but the measured rate is not yet evidence about real PRDs. Do not quote it without n and that caveat.
**Resolution (PB6 session)**: both PB6 critics were recorded the same way (dev, held-out once, stress, mixed batches) and again caught 24/24 with 0/24 (EvidenceAuditor) and 0/20 (SegmentSkeptic) false positives — the same caveat applies in full. The one genuinely new information is a *failure shape*, not a rate: the blocking `demographic_only` also fires on whole-market statements (2 of 4 held-out seeds, after a dev-written tie-break of unmeasured out-of-sample effect), and both critics fire on a basis or need that sits in a later sentence (recorded in the stress split, not fixed). See OI21, OI23.
**Resolution (PB7 session)**: both PB7 critics were recorded the same way (dev, held-out once, stress; mixed batches for `DependencyCritic`). `ConstraintCritic` caught 14/14 untraced constraints and `DependencyCritic` 12/12 on dev and on held-out, with 0 false positives (0/16 clean constraints and 0/8 traced constraints in seeded documents; 0/12 clean statements), no prompt tuned after seeing a held-out number — and the pre-recording review showed held-out was a slot-for-slot reskin of dev and that a three-clause rule ("must or required means met, a person's name means met, otherwise block") would have scored 24/24 on the held-out dependency set before it was repaired. Quote the held-out-only bounds (≈ 0.78 catch, ≈ 0.22 false-positive) with that caveat. The new information is again a failure shape: the single-statement `DependencyCritic` blocks a dependency whose owner sits in the next sentence or another table cell (stress). See OI21, OI23, OI25.

**Resolution (PB8 session)**: `RedTeam` was recorded the same way (dev, held-out once, stress, mixed batch) and caught 18/18 on dev and on held-out with 0/19 clean flagged on each, 14/16 on stress as labelled, and 36/36 with 0/38 in the mixed batch. The pre-recording review found 7 blockers, among them dev items that copied the rubric examples' templates and disputed labels; the gated clean set was then rewritten, which removed the bare-report cases that would have exposed `definition_drift` over-applying. The answer to PB8's known unknown (can a generative critic meet a false-positive standard?) is yes only because the output is a closed taxonomy where "clean" means the statement addresses the mode or the mode does not apply; the free-text counter-case is deferred. The new information is again a failure shape (OI26).

### PB11
- **Risk**: the two opportunity formulas rank differently and the implementation quietly prefers one.
- **Mitigation**: both are always computed and both are always rendered. Disagreement in the top five raises a `Question` node. This is specified behaviour, not a bug.

### PB14
- **Risk**: the Elicitor is tedious, and tedium is an I6 violation that kills the product rather than annoying the user.
- **Mitigation**: information-gain stopping is in the gating check. A question that changes no downstream computed value or confidence is measured and reported. Sessions are resumable.
- **Risk**: the Elicitor leads the witness, contaminating T3 evidence at source.
- **Mitigation**: `BiasHunter` audits the transcript in the same phase. Not a later addition.

### PB21
- **Risk**: deriving satisfaction from operational signals is an inference dressed as a measurement — cycle time is not satisfaction.
- **Mitigation**: the signal is always rendered beside the derived score with its own confidence band, and the mapping is a registered formula with a stated rationale, not a model's judgement.

### PB22
- **Risk**: wrongly asserting a regulatory obligation, or missing one. Both are liabilities in a regulated programme.
- **Mitigation**: constraints may never rest on T4 inference; each carries a source document and locator; constraint recall is a published eval metric. When uncertain, the system raises a `Question`, it does not assert.

### PB27
- **Risk**: variance computation on every commit becomes slow enough that people turn it off.
- **Mitigation**: blast radius is a transitive closure over an indexed graph; budget it and measure it in the gating check. If it cannot run synchronously, the design is wrong.

### PB36–PB41 — onboarding
- **Risk**: an 80%-correct reconstruction is worse than none. A new PM asserts it in a meeting and burns credibility they cannot afford to lose.
- **Mitigation**: banding is mandatory and visible on every claim in every artifact. The "ask, don't say" band must be generous — over-banding costs the user a question, under-banding costs them standing.
- **Risk**: the output reads as a critique of the departed PM. Career-limiting for the user, and they will never open it again.
- **Mitigation**: I9. `NeutralityCritic` blocks evaluative language and fault attribution; `RedTeam` is disabled in this mode. The people map describes where knowledge lives, never who performed well.
- **Risk**: volume. Four years of Jira is 8,000 tickets and the whole corpus will not fit in any budget.
- **Mitigation**: sampling and prioritisation strategy is part of PB38's spec, not an afterthought. Recency, reopen count, link density and Won't-Fix status are the obvious ranking signals.
- **Risk**: a week-one joiner often has no Jira, Confluence or repo access yet — the irony being that the people who most need this have it last.
- **Mitigation**: the mode must work from exports someone else pulls, not only from live connectors.

### PB33/PB34 — distribution
- **Risk**: the reachable audience is narrower than the stated audience. A PM or BA who cannot install a CLI and does not use Claude Code has no door in, and the fallback — an engineer runs it for them — inverts the operator/beneficiary model the whole design rests on.
- **Mitigation**: PB33 and PB34 ship immediately after PB9, not at the end of the roadmap. OI12 tracks the remainder. Do not let "an engineer can run it" become a design assumption.

### PB28
- **Risk**: a second export duplicates ninety issues in someone's real backlog. This is the failure that loses a user permanently.
- **Mitigation**: the diff plan is printed and approved before any write. Idempotency tested against a recorded tracker fixture. Subagent review required.

### PB32
- **Risk**: the eval harness becomes the thing that never quite gets built, because it is unglamorous and always deferrable.
- **Mitigation**: it is the last phase of v0.1 and v0.1 is not complete without it. The published numbers are the moat; a version of this product with no measured fabrication rate is indistinguishable from every other AI PM tool.

---

## Open Items

Resolve before the phase that depends on them. Never delete a row — strike through and record how it was resolved.

| Item | Blocks | Status |
|------|--------|--------|
| **OI1** Project name. **Resolved 2026-09-10: Probative.** Chosen after two earlier candidates were eliminated on collision. `assay` was rejected: `github.com/brandon-rhodes/assay` is an existing Python testing framework, and more seriously `github.com/metahub-ai/assay` is a trust layer for AI artifacts — same ecosystem, adjacent theme, also claiming the open-standard position. Also checked and taken on PyPI: `touchstone`, `cupel`, `plumbline`, `warrant`, `cairn`, `lodestone`, `attestor`, `adduce`, `sextant`, `winnow`. Final shortlist clear on search: `proofmark`, `trigpoint`, `probative`, `toulmin`. `probative` chosen — the legal standard for whether evidence actually tends to prove a fact, which is native vocabulary for the regulated-enterprise audience this is built for. **Residual check moved into PB0's gating check:** confirm on pypi.org and GitHub directly, plus domain, before the first publish. **Residual check completed 2026-09-21, PB0:** PyPI name free (simple-index 404). GitHub has two unrelated 1-day-old, 0-star `probative` repos, neither with traction — proceeded. Domain is `probative.wevit.ai` (not a bare `probative.*` — parented under the operator's existing `wevit.ai`, see `docs/DESIGN.md` R7). PyPI trusted-publisher registration and the first `v0.1.0.dev0` tag are the actual name-lock moment and happen right after this PR merges — see PB0's Implementation notes in `PROBATIVE_PHASE_SPECS.md`. | PB0 | ✅ Resolved |
| ~~**OI2** Pin a reference model for published eval numbers, so catch rate and false-positive rate are comparable across releases~~ **Resolved 2026-10-04, PB5:** `anthropic/claude-sonnet-5`, pinned as `probative.config.REFERENCE_MODEL` — a module constant, deliberately not a `Settings` field, so neither an env var nor a change to the `Settings.model` default can silently move a published number. Each recorded response carries the model the API itself reported (`claude-sonnet-5`) and a test checks it. Per-provider variance against this reference is still PB32's job | PB5, PB32 | ✅ Resolved |
| ~~**OI3** Choose the LLM response recording library for fixture-based tests (vcr-style cassettes vs. a hand-rolled JSON fixture store)~~ **Resolved 2026-10-04, PB5: hand-rolled, kept and shared** (`tests/_recording.py`, moved from `tests/extract/`; directory and re-record hint are parameters). It records at the `completion_fn` seam, so `LiteLLMProvider`'s real parse path runs on replay; keys are prompt hashes, so a prompt or rubric edit fails replay loudly (it caught a real stale-recording risk during PB5). A vcr-style cassette records HTTP: that couples to litellm internals and puts request headers on a public repo | PB5 | ✅ Resolved |
| **OI4** Dogfood corpus — the real, messy seed material the ingester and elicitation are built against. Shape and messiness matter more than volume | PB1, PB13 | 🔲 Open |
| **OI5** Which Confluence export variants matter — Cloud, Data Center, XML, HTML. **Note (PB2 build session):** PB2 itself shipped scoped to Jira CSV/HTML/XML + ADO CSV only — none of the samples available during that session were Confluence exports, so this item was not resolved and PB2 was not blocked on it; the split is recorded as phase **PB2-p2**. **Note (PB2-p2 build session):** two real Confluence Cloud per-page exports (a "Word" export — MHTML behind a `.doc` extension — and a "PDF" export) were provided and are now built (`probative/ingest/confluence_word.py`, `probative/ingest/confluence.py`; the PDF variant needed no new code, reusing PB1's `pdf.py` unchanged). **Narrowed, not closed:** Confluence's admin-level "export space" bulk XML/HTML variant (a zip of many pages, the one place real page hierarchy might actually live) remains unconfirmed — no sample exists, and none was guessed at | (resolved for per-page exports; bulk export unconfirmed) | 🔶 Partially resolved |
| **OI6** Jira and ADO CSV column variation across real instances. Needs a sample from at least two different organisations | PB28 | 🔲 Open |
| **OI7** Process model notation — is mermaid sufficient, or does a BFSI audience expect BPMN? | PB20 | 🔲 Open |
| **OI8** Story-point threshold above which a chunk must be split (Olsen p. 80 leaves this to the team). Needs a default and a config key | PB24 | 🔲 Open |
| **OI9** Interactive PDF library for form fields and internal links | PB30 | 🔲 Open |
| **OI10** Does `RedTeam` output ship inside stakeholder artifacts, or stay in-process? Default is in-artifact as a "least sure about" panel | PB29 | 🔲 Open |
| **OI13** Ticket sampling strategy for large histories. Which signals rank a ticket as worth reading — recency, reopen count, link density, Won't-Fix, comment volume — and what the budget cap should be | PB38 | 🔲 Open |
| **OI14** Does `onboard` read live connectors (Jira/Confluence/GitHub MCP) or exports only in v0.1? Exports work for a joiner without access; live is better for everyone else | PB36 | 🔲 Open |
| **OI12** How a PM/BA on a locked-down enterprise laptop installs this at all. No terminal, no admin rights, no Python. The plugin path answers it only for people already inside Claude. Signed standalone binaries are the other candidate and cost money and a certificate. Affects who the reachable audience actually is | PB34 | 🔲 Open |
| **OI11** Shared remote convention for partitions — a git repo, or a filesystem layout? Affects the v0.2 merge design but the schema must not preclude either | PB10 | 🔲 Open |
| **OI15** ADO CSV `Parent` references frequently point outside the exported set (confirmed: 0 of 17 distinct parents resolved within a real 40-row sample). PB2 records `parent_key` verbatim without resolving it. Graph-era hierarchy building (PB10) and constraint/dependency traceability (PB25) need a defined behaviour for a dangling parent — treat as an unresolved reference `Question`, or silently drop the edge? | PB10, PB25 | 🔲 Open |
| **OI16** `EvidenceSpan` (PB1) is neither frozen nor validated (`start < end`, `len(text) == end - start`), so anything holding a span can mutate it after the fact. PB4's candidates validate coherence at construction only. Decide at PB10 whether spans become frozen, since graph nodes are persistent | PB10 | 🔲 Open |
| **OI17** PB4's measured numbers rest on 3 synthetic documents / 21 labels. Dependency precision (0.33–0.5) is the known weak point. Build a larger, messier labelled corpus (real-shaped PRDs, synthetic content) before tuning any extraction prompt, so a tuned number is not measured on its own test set. **Note (PB5 session):** PB5 tuned no extraction prompt, so it was not blocked; it applied the same discipline to the critics (dev/held-out split, held-out recorded once) — but see OI21: PB5's own corpora share OI17's weakness | PB32 | 🔲 Open |
| **OI18** `score_dimension` (PB3) is not normalised by candidate count: five `warn` findings zero a dimension whether the document has 5 stories or 500, and any `block` zeroes it outright. Fine as a veto, wrong as a conformance score. PB9's report and PB32's "INVEST conformance" metric need a defined behaviour — a rate over candidates checked, reported beside the raw floor score | PB9, PB32 | 🔲 Open |
| **OI19** `LiteLLMProvider` passes no `max_tokens` and no `temperature`. PB5's critics batch up to 5 candidates (about 340 output tokens per story for INVEST) and all-or-nothing `check` raises on a truncated reply; recordings are n=1 at the provider default, so run-to-run variance is unmeasured. Decide default token limits and whether critics run at temperature 0, and measure repeat-run variance | PB32 | 🔲 Open |
| **OI20** Register `invest_score` (DESIGN §8) as a formula. PB5 emits findings and PB3's deterministic dimension score only; the "rubric over the six INVEST properties" formula, its inputs (per-property verdicts) and the book citation (p. 78) belong in the registry | PB11 | 🔲 Open |
| **OI21** PB5's critic corpora are synthetic, single-author and stylistically separable; held-out is not independent of the rubric text; the clean sets contain no boundary cases; injections are addressed to "the critic". `stress` and mixed-batch measurements exist in code but are unrecorded. Build an independently authored, messier corpus (real-shaped PRD language: PRD voice, customer-demanded standards such as SSO/PDF/SMS, internal personas, stories with embedded acceptance criteria) and record stress/mixed before publishing any critic number. Also decide a guard for an all-`cannot_tell` reply, which currently passes a blocking critic silently **Note (PB6 session):** the PB6 corpora were written against these weaknesses (boundary cases in the clean sets, injections in several forms none of which reuse the prompt's wording, dev and held-out differing in sentence shape, a four-word-run guard against the rendered prompt) and `stress` + mixed-batch measurements are now **recorded** for EvidenceAuditor and SegmentSkeptic — but they are still single-author, and PB5's `stress`/mixed recordings are still not made. OI21 stays open until an independently authored corpus exists **Note (PB7 session):** PB7's corpora repeat the weakness in a sharper form — the pre-recording review measured that held-out is a slot-for-slot reskin of dev (identical constraint/story/untraced counts and the same twelve kinds in the same order in all 24 constraint pairs) and that a three-clause rule would have scored 24/24 on the held-out dependency set until obligation-grammar seeds were added; both critics again scored perfectly. OI21 stays open | PB32 | 🔲 Open |
| **OI22** Onboarding-mode critic exclusion (I9). `SegmentSkeptic`'s output is a verdict on how someone else defined a segment, and `ConstraintCritic`'s and `DependencyCritic`'s (PB7) are verdicts on whether a past author traced an obligation or named an owner, i.e. evaluations of past decisions, so none of them may run in onboarding mode; S5 and CLAUDE.md name only `RedTeam` (built in PB8; its docstring records the exclusion and nothing enforces it). The same argument arguably covers every evaluative critic (`SpaceWarden`, `INVESTCritic`, `EvidenceAuditor`) run over reconstructed claims. There is no mode config to enforce any of it until PB12/PB39: for now it is documented in the critics' docstrings and DESIGN §13 and enforced by nothing. Decide the exclusion list and make it a config exclusion (not a prompt request), with a test that the onboarding config omits it | PB12, PB39 | 🔲 Open |
| **OI23** PB6 critic limits that block quoting a rate or tuning a prompt. (a) `SegmentSkeptic`: the blocking `demographic_only` also fires on whole-market statements (held-out 2 of 4 seeds after a dev-written tie-break in the judge preamble whose effect out of sample is unmeasured — no held-out baseline from before it exists) — a whole-market statement can be blocked as well as warned. Any further prompt or rubric edit makes the p2 held-out recording stale (OI17 discipline) and needs fresh held-out fixtures first. (b) Both critics judge one statement, so a basis or need stated in the next sentence or a later paragraph is flagged (`adjacent_source`, `need_in_next_sentence` in stress, both fire; for SegmentSkeptic that is a **block**). Decide whether the critic should be given the surrounding paragraph (a change to `LLMCritic`'s contract), and quote the stress number beside any catch rate until then. (c) Segment extraction is measured on 3 documents / 4 gold labels | PB9, PB32 | 🔲 Open |
| **OI24** DESIGN has `ConstraintCritic` block at G4 on a constraint with no `Story` (I8), but stories are produced at P6/G5 (PB26), after G4 commits (§9.5, PB25/PB26). At G4 there may be no story to trace to. Decide what an I8 trace target is at G4 (a chunk? an MVP-scope item?) or move the block to G5; PB7's standalone critic traces to `StoryCandidate`s found in the document and does not answer this | PB22, PB25 | 🔲 Open |
| **OI25** PB7 critic limits that block quoting a rate or tuning a prompt. (a) `DependencyCritic` judges one statement, so an owner named in the next sentence or another table cell is blocked (stress: `owner_in_next_sentence`, `owner_in_table_column` fire); same decision as OI23(b) (give the critic the surrounding paragraph?). (b) `ConstraintCritic`'s link check proves a quote exists in a story, not that the story traces the obligation; the false-trace rate is measured only by seeded decoys, on a corpus whose held-out is a slot-for-slot reskin of dev (OI21). (c) A mistyped story id or non-verbatim quote is a block with no re-ask (zero in every recording). (d) "Specific requirement" is a policy line: partial coverage and report-versus-delivery are labelled "defensible either way". (d2) ConstraintCritic turns a PB4 extraction false positive (a wish with a charter attached) into a block, with no carve-out; stress counts "as labelled" include known false positives and one deterministic case, so the model-judged stress result is weaker than 10/10 and 14/14 read. (d3) Constraints trace only to stories with the same `source_id`: a regulation ingested as its own document leaves its constraints blocked in standalone use (PB22). (d4) The link-quote content-word check is Latin-script only; the re-ask path was never exercised live. (e) `DependencyCritic` does not check `by_when`, covers inbound reliance only, and takes "a person on either side" as the owner rule. Any further prompt or rubric edit makes the held-out recordings stale and needs fresh held-out fixtures first | PB9, PB22, PB25, PB32 | 🔲 Open |
| **OI26** PB8 limits that block quoting a rate or tuning a prompt. (a) `RedTeam`'s `definition_drift` over-applies: it co-fired on 4 of 6 `rival_explanation` seeds and on a bare report of a change (stress), and the gated clean sets contain no bare report of a change in a measured category, so the gated numbers cannot see it; add such clean items and decide whether the check should require an explicit comparison across two named periods or groups. (b) A precondition, base or definition in the next sentence is flagged (3 of 3 stress cases). (c) Free-text counter-case, `Hypothesis`-backed "what would have to be true" and overlap with `Premortem` (PB25) are deferred: a model-authored proposition needs a `Test` (I2). (d) `RedTeam` must not run in onboarding mode (I9, see OI22). (e) The forecast extraction pass was tuned once on PB4's PRD, so that 0 false positives is not out-of-sample; no larger forecast corpus exists (OI17) | PB12, PB25, PB39 | 🔲 Open |

---

## Deferred beyond v0.1

Recorded here so they are not rediscovered as ideas.

- **Semantic merge and cross-partition variance** (v0.2). Schema support ships at PB10; mechanics wait until two real partitions exist to test against. Conflict *detection* ships before conflict *resolution* — reporting a collision is most of the value.
- **`BuildPhasePlanner`** (v0.2) — committed story map to phase plan, each item carrying its story id and provenance chain.
- **Tracker read-back and delivery signals** (v0.3). One-directional, opt-in. If it ever writes work items on a schedule, the product has failed.
- **Computed post-mortem** (v0.3) — reconciliation of baseline against delivered state, with premortem predictions scored.
- **Signed standalone binaries** (PyInstaller or Nuitka) for operators who cannot install Python. Needs a code-signing certificate; see OI12.
- **Editable process models**, BPMN export, web UI, alternative methodologies (JTBD, opportunity-solution trees) as additional scorers over the same graph.
