# Probative critique: checkout-prd.md

test/model · 1 document · 431 characters · 0.0s · 10 successful model calls

**2 blocking · 1 warnings · 0 notes**

| Dimension | Checked | Clean | Block | Warn | Note | Floor (0 to 10) | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| Evidence | 2 | 1 of 2 (50%) | 1 | 0 | 0 | 0.0 | BLOCKED · small sample |
| Problem framing | 2 | 1 of 2 (50%) | 1 | 0 | 0 | 0.0 | BLOCKED · small sample |
| Segments | 1 | 1 of 1 (100%) | 0 | 0 | 0 | 10.0 | clean · small sample |
| Story quality | 1 | 1 of 1 (100%) | 0 | 0 | 0 | 10.0 | clean · small sample |
| Dependencies | 0 | — | 0 | 0 | 0 | — | nothing found to check |
| Constraints | 0 | — | 0 | 0 | 0 | — | nothing found to check |
| Stress test: least sure about | 3 | 2 of 3 (67%) | 0 | 1 | 0 | 8.0 | warnings · small sample |

## Findings

### Blocking

#### Evidence: The statement presents a specific figure, proportion, ranking, benchmark or study finding as fact, and gives no basis for it. (1 of 2)

> “FLAG Competitors convert far better than we do.”

checkout-prd.md, line 4\
Fix: Name where the figure comes from, or restate it as an assumption to be tested

#### Problem framing: The need names a feature, a screen or UI element, an implementation, or a named technology instead of the customer benefit. (1 of 2)

> “Users need a FLAG \<script\>alert\(1\)\</script\> \| \`tick\` \*\*bold\*\* \[x\]\(http:​//evil.test\)”

checkout-prd.md, line 5\
Fix: Restate as a customer benefit — verb first, customer voice

### Warnings

#### Stress test: least sure about: The statement reports a change, trend, pattern or correlation, links it in its own words to a cause or a conclusion \(because, so, driving, shows that, clearly, which is why, proves\), and rules out no other explanation: seasonality, a change in who or what was counted, a concurrent release or event, a selection effect. (1 of 3)

> “FLAG Competitors convert far better than we do.”

checkout-prd.md, line 4\
Would have to be true: For “FLAG Competitors convert far better than we do.” to support the conclusion drawn from it, the other plausible explanations must have been excluded.\
Fix: Name the other explanations and how each was excluded, or state the conclusion as a hypothesis

## Not assessed

- Dependencies: nothing found to check
- Constraints: nothing found to check

## Coverage

| Document | Format | claim | constraint | dependency | forecast | need | segment | story |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| checkout-prd.md | markdown (detected) | 2 | 0 | 0 | 1 | 2 | 1 | 1 |


100 input tokens · 50 output tokens · 1 concurrent calls · critics reply with flagged items only · probative 0.0.0-test
