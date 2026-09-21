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
- **Mitigation**: OI5. Confirm which variants matter before building; support one properly rather than three badly.

### PB4
- **Risk**: extraction quality silently caps the quality of every critic built on top of it, and it is hard to attribute a bad finding to bad extraction.
- **Mitigation**: precision and recall measured against a hand-labelled fixture at PB4 and recorded. Critic evals at PB32 report extraction-attributable failures separately.

### PB5–PB8
- **Risk**: critics drift toward finding fault to appear useful. A critic that blocks everything is as useless as one that blocks nothing, and it is far more annoying.
- **Mitigation**: every critic ships with a clean fixture set on which it must raise nothing. False-positive rate is a gating check, not a metric to look at later.
- **Risk**: critic behaviour varies by provider, so a rubric tuned on one model misbehaves on another.
- **Mitigation**: OI2 — pin a reference model for published numbers; report per-provider variance from PB32.

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
| **OI2** Pin a reference model for published eval numbers, so catch rate and false-positive rate are comparable across releases | PB5, PB32 | 🔲 Open |
| **OI3** Choose the LLM response recording library for fixture-based tests (vcr-style cassettes vs. a hand-rolled JSON fixture store) | PB5 | 🔲 Open |
| **OI4** Dogfood corpus — the real, messy seed material the ingester and elicitation are built against. Shape and messiness matter more than volume | PB1, PB13 | 🔲 Open |
| **OI5** Which Confluence export variants matter — Cloud, Data Center, XML, HTML | PB2 | 🔲 Open |
| **OI6** Jira and ADO CSV column variation across real instances. Needs a sample from at least two different organisations | PB28 | 🔲 Open |
| **OI7** Process model notation — is mermaid sufficient, or does a BFSI audience expect BPMN? | PB20 | 🔲 Open |
| **OI8** Story-point threshold above which a chunk must be split (Olsen p. 80 leaves this to the team). Needs a default and a config key | PB24 | 🔲 Open |
| **OI9** Interactive PDF library for form fields and internal links | PB30 | 🔲 Open |
| **OI10** Does `RedTeam` output ship inside stakeholder artifacts, or stay in-process? Default is in-artifact as a "least sure about" panel | PB29 | 🔲 Open |
| **OI13** Ticket sampling strategy for large histories. Which signals rank a ticket as worth reading — recency, reopen count, link density, Won't-Fix, comment volume — and what the budget cap should be | PB38 | 🔲 Open |
| **OI14** Does `onboard` read live connectors (Jira/Confluence/GitHub MCP) or exports only in v0.1? Exports work for a joiner without access; live is better for everyone else | PB36 | 🔲 Open |
| **OI12** How a PM/BA on a locked-down enterprise laptop installs this at all. No terminal, no admin rights, no Python. The plugin path answers it only for people already inside Claude. Signed standalone binaries are the other candidate and cost money and a certificate. Affects who the reachable audience actually is | PB34 | 🔲 Open |
| **OI11** Shared remote convention for partitions — a git repo, or a filesystem layout? Affects the v0.2 merge design but the schema must not preclude either | PB10 | 🔲 Open |

---

## Deferred beyond v0.1

Recorded here so they are not rediscovered as ideas.

- **Semantic merge and cross-partition variance** (v0.2). Schema support ships at PB10; mechanics wait until two real partitions exist to test against. Conflict *detection* ships before conflict *resolution* — reporting a collision is most of the value.
- **`BuildPhasePlanner`** (v0.2) — committed story map to phase plan, each item carrying its story id and provenance chain.
- **Tracker read-back and delivery signals** (v0.3). One-directional, opt-in. If it ever writes work items on a schedule, the product has failed.
- **Computed post-mortem** (v0.3) — reconciliation of baseline against delivered state, with premortem predictions scored.
- **Signed standalone binaries** (PyInstaller or Nuitka) for operators who cannot install Python. Needs a code-signing certificate; see OI12.
- **Editable process models**, BPMN export, web UI, alternative methodologies (JTBD, opportunity-solution trees) as additional scorers over the same graph.
