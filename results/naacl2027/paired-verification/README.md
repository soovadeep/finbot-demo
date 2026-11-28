# Matched-control verification analysis

Run `python scripts/naacl2027/paired_verification.py`. This is a **post-hoc diagnostic of the
already inspected holdout**, not a new independent held-out test. No model calls or verifier rule
changes are involved. The original `check-injection.json` remains the historical raw report.

The paired generator preserves its 3,240 corrupted texts and original RNG sequence. Each is paired
with the same frame before the field substitution or unsupported addition. Both verdicts and
their reasons are retained in `pairs.jsonl`. Any reason-code addition already supported by a
record is ineligible as an error; the current benchmark has zero such exclusions.

## What the counts mean

- Original corrupted drafts rejected: **2,668/3,240 (82.3%)**.
- Paired clean controls already rejected: **570/3,240 (17.6%)**. Their corrupted counterparts also fail.
- Clean controls accepted: **2,670**. Of these, **2,098** change from allow to block after mutation:
  **78.6% conditional mutation rejection**. This denominator excludes the rejected controls.
- Paired rejection lift: **(2,668 - 570)/3,240 = 64.8 percentage points**.
- Separate original correct-draft suite: **114/1,120 (10.2%)** rejected. Its template distribution
  differs from the repeated matched controls, so the two clean rejection rates are not interchangeable.

| Mutation | Pairs | Clean already blocked | New rejection / accepted controls |
|---|---:|---:|---:|
| Amount | 448 | 76 | 372/372 |
| Added fee | 448 | 76 | 372/372 |
| Currency | 224 | 38 | 186/186 |
| Record ID | 224 | 38 | 186/186 |
| Status | 552 | 114 | 394/438 |
| Date | 448 | 76 | 172/372 |
| Reason code | 224 | 38 | 58/186 |
| Bare link | 224 | 38 | 0/186 |
| Mixed wording | 448 | 76 | 358/372 |

For bare links, all 38 raw rejections arise from the clean base's unrelated settlement phrase.
Adding the link produces no additional rejection. Crediting these as link detection is misleading.

The report keeps all four transitions (allow→allow, allow→block, block→allow, block→block), including
zero counts. Conditional sensitivity without clean rejection would hide false positives. No rate
here establishes universal correctness, natural-model error rates or answer completeness. Repeated
record/template pairs are dependent; the generation rules prescribe the intended claim meaning.
