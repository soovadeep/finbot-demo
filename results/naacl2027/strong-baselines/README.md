# Stronger clarification-component baselines

Reproduce with Python 3.11+, without credentials or API calls:

```sh
python scripts/naacl2027/compare_baselines.py
python scripts/naacl2027/compare_baselines.py --bench ambiguity-8-same-amount
```

These are exploratory analyses added after the original results were examined. They run the same
`ClarificationSession` component, cached customers, Bayesian updates and shortlist confirmation.
They do not evaluate the deployed conversation policy or human usability.

`amount_first` asks amount before the original kind/merchant/date sequence, skipping constant
attributes. `most_distinct` asks the attribute with the most distinct options, breaking ties by
kind/merchant/date/amount order. Both stop at the same budget or 95% threshold as fixed order;
decision value additionally stops when its one-step benefit does not exceed its cost.

## Original eight-record set, one question

All rows have 224 completed episodes per simulator. Correct means confirmation of the hidden target,
not the top-ranked guess or verification passing.

| Selector | Haiku correct | Haiku wrong | Llama correct | Llama wrong |
|---|---:|---:|---:|---:|
| Fixed order | 54 (24.1%) | 5 (2.2%) | 68 (30.4%) | 13 (5.8%) |
| Amount first | 93 (41.5%) | 5 (2.2%) | 142 (63.4%) | 9 (4.0%) |
| Most distinct | 111 (49.6%) | 5 (2.2%) | 148 (66.1%) | 9 (4.0%) |
| Decision value | 105 (46.9%) | 5 (2.2%) | 140 (62.5%) | 9 (4.0%) |

Most-distinct exceeds one-question DV on correct identification under both simulators. One
most-distinct question also matches or exceeds DV with a budget of two (109/148 correct), which
asks 1.36/1.31 questions on average. DV uses fewer questions than heuristics **with the same
two-question budget**, but that alone is not evidence that it is the best policy.

On the same-amount set, one most-distinct question produces 73/105 correct confirmations versus
67/97 for DV. This includes indistinguishable target records and should not be read as a human
accuracy estimate; the original paper separately describes the 99 identifiable targets.

## Coverage and paired uncertainty

All requested comparisons are complete except amount-first, budget two, original set: **223/224**
episodes for each simulator. Missing cache replies are reported explicitly in the row files.
They are never filled with guessed responses, treated as abstentions, or included in denominators.
Per-method summaries state completed counts; paired differences use the common completed episodes.

The summary files include DV-minus-baseline differences for correct selection, wrong selection and
question count, with 95% percentile intervals from 2,000 paired bootstrap draws clustered by target
record (seed 2027). The full set contains 154 target records across eight synthetic customers;
record clustering does not remove all customer-level dependence. Intervals characterize this
benchmark, not real-customer performance. Identical observed wrong-selection outcomes can give a
zero-width bootstrap interval; that is not proof of population equivalence or non-inferiority.

Files ending in `-rows.jsonl` retain per-episode outcomes and missing keys; `-summary.json` files
contain definitions, coverage, comparisons and hashes of the exact source/data/cache inputs.
