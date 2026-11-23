# Varied policy and comparison diagnostics

Run from the repository root with Python 3.11 or later:

```sh
python scripts/naacl2027/evaluate_support.py
python -m unittest discover -s tests -p 'test_support_evaluation.py' -v
```

The complete report is `results/naacl2027/varied-support.json`. It includes source hashes,
questions, fixture evidence, clean/changed drafts, individual verdicts and reasons, workflow
traces, independent field/content checks and failures. It is reproducible without API calls,
credentials or additional dependencies. No runtime verifier, retrieval rule or public endpoint
was changed to improve these results. The evaluator completes successfully when it records
missed errors: those are findings, not evaluator crashes. Unit tests check scoring and report
reproducibility, rather than requiring the system to reject every mutation.

## Actual inspector workflow checks

These call `finbot.demo.run_demo`, the function behind `/api/run`, with its scripted writer
and extractive policy mode. The comparison fixtures use the existing internal `records=`
argument; the public endpoint does not accept arbitrary records. Policy workflows use the
demo's existing knowledge base. They are local Python workflow replays, not hosted HTTP,
live-model or conversation-clarification measurements.

| Family | Construction | Required-content checks passed |
|---|---|---:|
| Comparison | Six two-record datasets × two request orders × two fault settings, plus absent/other-tenant controls in both orders | 28/28 |
| Policy | Six differently worded questions × `none`/`policy_once` | 10/12 |

Comparisons cover USD/EUR/GBP, differing and equal amounts/statuses, small and large amounts,
unknown and pending outcomes, and missing/inaccessible records. Field checks compare every
requested record's amount, currency and status with the fixture; wrong bindings, omitted records,
duplicate assertions and extra matching assertions fail. This is a narrow scripted-format scorer,
not a semantic judge for other prose or financial advice.

Policy questions cover the general surcharge rule, debit/prepaid exclusion, cap/disclosure,
decline codes 05 and 51, and an unavailable mortgage policy. The two failed checks share the
question **“What is the credit card surcharge cap and disclosure rule?”** The scripted workflow
returns **“I don't have documentation on that, so I won't guess.”** under both fault settings.
This avoids invention but fails the task: the policy exists in the demo knowledge base.
The report preserves this retrieval miss. The injected policy fault has no effect when there
is no matching sentence to alter; fault settings are not counted as actual injections.

## Matched component probes

These use the actual `Chatbot` verifier chain plus `PolicyDocumentVerifier("extractive")`,
with controlled tool-result envelopes. They bypass retrieval, the writer, repair and the UI.
Six authored policies cover surcharges, refund timing, retry rules, cancellation, fee waivers
and dispute deadlines. They are fictional evaluation policies, not financial guidance.

| Mutation | Actual changed drafts | Newly blocked | Missed |
|---|---:|---:|---:|
| Reverse a policy rule | 6 | 6 | 0 |
| Change a policy condition/threshold | 6 | 6 | 0 |
| Omit a required policy exception | 6 | 0 | 6 |
| Remove the policy citation | 6 | 6 | 0 |
| Cite a different retrieved source | 6 | 6 | 0 |
| Add an unsupported eligibility conclusion | 6 | 6 | 0 |
| Swap record amounts | 10 | 10 | 0 |
| Swap record statuses | 10 | 10 | 0 |
| Swap record currencies | 6 | 0 | 6 |
| Omit a requested record | 12 | 0 | 12 |

All 74 paired clean controls are accepted. The 30/36 policy and 20/38 comparison rejections
are therefore new rejections, each with a new reason matching the targeted check. The report
also retains raw rejection totals and reason deltas so pre-existing failures cannot masquerade
as error detection. A matching diagnostic is still not proof of general semantic detection.

Ten additional swap attempts leave the text unchanged because the values are equal. These
are accepted controls and are excluded from the 38 actual comparison mutations. Six separately
authored, supported policy paraphrases are all rejected: the demo's extractive mode deliberately
requires source-sentence reuse. Report this restriction alongside zero rejections of exact-source
controls; do not describe the latter as zero false rejections across policy language.

Policy expectations were authored before the run; they are independent of the gate verdict but
are not independent human annotations. Comparison expectations use exact fixture fields, without
reusing the production binding parser. Repeated orders and mutations share fixtures. Do not pool
these counts into customer accuracy or treat them as independent trials with binomial intervals.
This is a diagnostic suite developed with knowledge of the implementation, not a held-out benchmark.

## Concrete observed examples

**Successful recovery, `comparison/mixed-currency/0/swap_once`:**

- Request: “Compare txn_EVAL0010 and txn_EVAL0011: what are their amounts, currencies and statuses?”
- Evidence: `txn_EVAL0010` is **210.00 EUR, approved**; `txn_EVAL0011` is **47.25 GBP, declined**.
- Injected draft: “Transaction txn_EVAL0010 was approved for 47.25 EUR. Transaction txn_EVAL0011
  was declined for 210.00 GBP.” The draft also contains the scripted retry guidance.
- Observed result: the gate blocks both wrong amount bindings with
  `value_from_other_record:amount:` reasons. The scripted repair restores **210.00 EUR** to
  the first record and **47.25 GBP** to the second. The independent field scorer passes.

**Missed error, `comparison/mixed-currency/0/swap_currency`:**

With the same evidence, the component draft says **210.00 GBP** for the first record and
**47.25 EUR** for the second. The gate allows it, while the independent field scorer marks
the bindings wrong. Currency membership in the combined evidence is insufficient to establish
which currency belongs to which record.

**Missed completeness, `policy/surcharge/missing_exception`:**

The question asks which cards qualify and the cap. The fixture source states:
“Credit cards may carry a surcharge of at most 3 percent. Debit and prepaid cards are excluded.”
Removing the second sentence leaves a cited, source-matching answer. The gate allows it, but
the authored task expectation fails because a required exception is omitted. This is why a
passing evidence check must not be counted as a complete answer.
