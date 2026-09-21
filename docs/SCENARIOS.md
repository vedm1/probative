# Acceptance scenarios

The narrative versions of these journeys live in [GETTING-STARTED.md](GETTING-STARTED.md). This file is the test side: what each one must do to count as working.

Each becomes a fixture for PB32:

```
evals/scenarios/<id>/
├── input/           the seed corpus — synthetic or public-domain only
├── expected.yaml    structural assertions, not golden output
└── README.md        the scenario in prose
```

Assertions are **structural, never literal**. LLM output varies between runs and providers; golden-file matching would make the suite useless inside a week.

**Get S1, S2 and S5 right first.** S1 is how strangers arrive, S2 is where the product most easily becomes a fiction generator, and S5 is the only door that opens for a large part of the intended audience.

---

## S1 · Critique of an existing document — *v0.1, PB9*

A PM with no investment in the project runs one command on a PRD they already wrote.

- Under 60 seconds on a 30-page document (I6 time-to-first-artifact)
- Every finding carries a locator that resolves to the source
- Runs in CI against recorded fixtures with **no API key present** (S3 testing rule)
- **Zero blocks on the clean fixture PRD.** A critic that fires on good work is worse than no critic
- Dimension scores are deterministic: identical findings always produce identical scores

## S2 · Greenfield from an idea, no customer evidence — *v0.1, PB14–PB19*

A founder with two market PDFs and strong opinions.

- Zero T1 evidence ⇒ **zero green cells in any artifact**
- Every persona labelled proto-persona, in every artifact, without exception
- `export --jira` refuses and explains why
- Every assumption-ledger entry has a test with a cost and a kill criterion (I2)
- Elicitor stops on marginal information gain below threshold; the count is reported in the run manifest (I6)
- `unknown` is accepted as a non-failing answer and becomes a Question plus a research task

## S3 · Brownfield modernisation — *v0.1, PB20–PB22*

A BA on a policy administration replacement, with process docs, a ticket export, an API surface and regulatory circulars.

- Every satisfaction score renders **with its operational signal beside it**, never alone
- `WorkaroundHunter` detects a shadow process referenced across two source kinds
- No `Constraint` rests on T4 inference; each carries a source document and locator (I8)
- G4 blocks, naming both untraced constraints and unowned dependencies
- RTM exports and **every row resolves end to end**: evidence → constraint/need → chunk → story → AC

## S4 · Greenfield with real research — *v0.1, PB16–PB19*

A PM with eleven transcripts, a ticket export and competitor teardowns.

- Both opportunity formulas always computed and always rendered
- Disagreement in the top five raises a `Question` node — specified behaviour, not a bug
- Every plotted point carries a confidence envelope sized by n and dispersion
- Every point opens an evidence drawer with the verbatim quote and speaker
- **No numeric field anywhere was model-produced** — `FormulaValidator` recomputes every one on commit (I4)

## S5 · Plugin, no terminal — *v0.1, PB34*

A BA on a locked-down laptop, working inside Claude.

- **Skin parity: identical findings to the CLI on identical input.** If the plugin holds any logic of its own, the thin-skin claim is false
- No install, no terminal, no environment variables at any point

## S6 · Continuous critique in CI — *v0.1, PB35*

A team keeping specs in git.

- The PR comment **updates in place** on a new push rather than posting again
- `fail-on: block` fails the check; `fail-on: none` is advisory
- Runs from a repository secret; the action's own tests run without one

## S9 · Inheriting a project — *v0.1, PB36–PB41*

A PM joins a four-year-old brownfield project. The previous PM has gone. There is a Jira export, a repo, and a Confluence space of unknown currency.

- **Every reconstructed claim carries a band**, visible in every artifact it appears in
- Claims in **safe to say** trace to running code or an explicit decision record — nothing weaker
- **I9: no artifact evaluates a past decision or attributes fault to a person.** `NeutralityCritic` blocks evaluative language; `RedTeam` does not run in this mode
- Contradictions between doc, code and tickets are surfaced, not resolved
- Absences are detected — a whole category with no tickets in four years is reported
- The people map describes **where knowledge lives**, never who performed well
- `onboard brief --topic X` returns assertable / caveat / ask, plus who uniquely holds what
- Works from **exports**, not only live connectors — a week-one joiner often has no access yet
- Control: on a corpus with a known handover document, the reconstruction's safe-to-say band must not contradict it

## S7 · Two analysts collide — *v0.2, PB12 federation*

Two BAs on one programme, one owning payments and one owning servicing.

- Detects a satisfaction revision in one partition invalidating MVP membership in another
- Detects a boundary dispute where both partitions claim one need
- Routes each conflict to both owners with the evidence for each side attached
- **Detection ships before resolution.** Reporting the collision is most of the value
- Control: git merges the same change silently; Probative must not

## S8 · Drift after commit — *v0.3*

Eleven weeks into delivery, a story is moved to Won't Fix in the tracker.

- Variance fires **at commit time**, not on a schedule and not at review
- Names the affected downstream nodes, not only the changed one
- Matches the premortem prediction automatically
- **Probative writes nothing back to the tracker.** Read-only, one-directional, always

---

## Assertion format

```yaml
s3_brownfield:
  gates:
    G4: blocked
  blocking_reasons:
    - constraint_untraced: 2
    - dependency_unowned: 3
  invariants:
    I4_computed_numbers: pass      # every numeric field recomputes
    I8_constraint_provenance: pass # no constraint rests on T4
  artifacts:
    rtm: all_rows_resolve
  forbidden:
    - green_cell_without_t1_evidence
    - persona_without_t1_customer_evidence
```

`forbidden` matters as much as the positive assertions. Most of the ways this product fails are things it should never have produced, not things it failed to produce.
