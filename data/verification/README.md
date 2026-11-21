# Policy-check regression corpus

`policy_checks.jsonl` contains 24 authored synthetic cases with seven supported controls
and 17 unsupported candidates under the stated evidence protocol. Labels consider citation,
context, and the configured metadata/recency requirements. Dates use a fixed evaluation
clock of 2026-11-19 and a 30-day age limit; they are not evaluated against the wall clock.

These are development fixtures written with Codex assistance. They are not held out or
independently adjudicated, and they do not establish real-world error rates. Some scenarios
follow the failure categories already discussed in the NAACL documentation branch. All
records, policies and example URLs are fictional. No Banking77 text is included here.

Each row contains an ID, category, question, sources, candidate, lookup-presence flag,
clock and age limit, evidence-support label, expected strict-mode decision and rationale.
`expected_strict` is a regression assertion, not a substitute for `expected_supported`:
two valid paraphrases are expected to be rejected and must count as false rejections.
An explicit abstention is a non-asserting control; allowing it does not mean task completion.

Run:

```bash
python scripts/evaluate_policy_checks.py --out results/verification/policy-checks.json
```

The runner makes no model calls. It compares `off`, `extractive` and `strict` on the same
candidate/evidence pairs, reports all four support/decision counts, and exits nonzero on a
strict-mode regression. It saves per-case decisions, reasons and input/source hashes.
It does not run retrieval, financial checks, repair or the complete conversation pipeline.

Fresh independent evaluation requires new policy/document families, separately reviewed
support and task-completion labels, and a frozen test split. Keep all variants, versions
and paraphrases of a policy family in the same split. Do not rename these fixtures as a
new test set after using them to improve the implementation.
