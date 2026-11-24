# Fresh LLM answers, checked three ways

This is the first evaluation in this repository of answers **newly generated** by a live
model and scored against labels. It is small (30 cases), and two labellers who are not external annotators produced its labels.
Read the caveats before quoting a number.

## Design

- **Frozen first.** The runtime, checker, prompt, writer settings and the 30 cases were
  committed and hashed (`data/naacl2027/fresh-llm-v1/protocol.json`) before any answer
  existed. `scripts/naacl2027/fresh_llm_study.py` refuses to run if any of them changed.
- **Cases.** 30 developer-written synthetic cases on 14 new records (`txn_FRESH*`): refund
  versus payment amounts, expected versus actual settlement, declines, an unknown outcome,
  two-record comparisons, policy questions, missing records and missing evidence.
- **Writer.** Llama 3.3 70B Instruct through OpenRouter, temperature 0, 400 output tokens,
  injected faults off, through `finbot.demo.run_demo` (the path the conversation uses after
  a record is confirmed).
- **Checker.** A direct LLM evidence review (`LLMEvidenceVerifier`, prompt
  `finbot-llm-evidence-review-v1`) with Gemini 2.5 Flash Lite through OpenRouter. It sees
  the question, the evidence and the answer, and returns support and completeness
  separately. This is a direct LLM verifier, not NeMo Guardrails or Bedrock.
- **Three configurations on identical first drafts:** deterministic checks only (the
  production chain, including the new requested-information check), the LLM review only,
  and both. Separately, two **end-to-end** runs per case through the full gate (draft,
  one repair, record-built fallback, refusal): deterministic only, and combined.
- **Labels.** Every distinct first draft and released answer (57) was judged for support
  and completeness twice: by the AI assistant (`labels.json`, with rationales) and by a
  second labeller (`labels-second.json`). Success means supported **and** complete.
  Checker verdicts are never used as labels.

## Caveats

- **Neither label set is external.** The first set was made by the AI assistant working
  for the authors, which also wrote the cases and the checker prompt, and which had seen the
  per-case allow/block summary before labelling. The second set was made by co-author Apurba
  Bose, who wrote none of the cases, prompts or first labels, and labelled through a blind web
  form that showed no checker verdicts and no first labels. The checker is a different model
  family from the first labeller and the writer.
- **Only 2 (first labeller) or 4 (second) of 30 first drafts were labelled wrong.** Detection
  rates on so few items mean little.
- **The checker was rate-limited upstream.** OpenRouter returned HTTP 429 from Google AI
  Studio during the first two check attempts (20 and 19 of 30 reviews unavailable) and for
  12 of 59 reviews in the combined end-to-end run. A third, paced attempt
  (`fresh_llm_recheck.py --attempt 3 --pause 6`, same frozen checker and inputs) had 5 of 30
  unavailable. All attempts are kept. Unavailable reviews block in the application (fail
  closed) but are not counted as detections below.
- One run per case; temperature 0 does not make the provider deterministic.
- **Scope.** Record questions name the transaction ID (5 of 30 are policy or out-of-scope
  questions with no record), so the study measures answering once the record is known. It does
  not exercise clarification or confirmation.
- **The two end-to-end runs are not paired.** Each run generated its own first draft (and
  repair); the drafts differ in 10 of 30 cases; small differences between them cannot be
  attributed to the checker alone. The component table above is the paired comparison (one
  saved draft per case, checked three ways).

## Results

**Component check on the same 30 first drafts** (attempt 3; counts exclude unavailable
reviews where noted):

| Configuration | Wrong drafts blocked | Correct drafts blocked | Unavailable |
|---|---:|---:|---:|
| Deterministic | 1 / 2 | 14 / 28 | 0 |
| LLM review | 0 / 2 (both reviewed) | 1 / 23 reviewed | 5 |
| Combined | 1 / 2 | 12 / 21 reviewed (19 / 28 with unavailable) | 7 |

The deterministic checks caught the draft that stated an expected date as the settlement
date (financial-role check). Neither configuration caught the other wrong draft, which
repeated record guidance about "the cause of the failure" for a payment that had been
refunded, not failed. That guidance comes from the policy table's fallback for statuses it
does not map, which is itself a bug to fix. The LLM review approved both wrong drafts.

The deterministic checks blocked half of the correct drafts. By check: extractive policy
matching 5 (paraphrased policy answers), requested-information coverage 4 (over-broad
triggers, see below), comparison field coverage 2, the older refund-mention check 2, retry
advice 1, missing documentation 1. Most are recovered by the repair or the record-built
answer, which is why end-to-end results are better than these component numbers.

**End to end** (all 30 cases; first labeller's labels on every released answer):

| Gate | Released, supported and complete | Released, wrong | Withheld |
|---|---:|---:|---:|
| Deterministic | 23 | 1 | 6 |
| Deterministic + LLM review | 21 | 2 | 7 |

Outcomes, deterministic: 15 passed, 6 repaired, 3 record-built, 6 refused. Combined: 10
passed, 6 repaired, 7 record-built, 7 refused (several because the review was unavailable).
All 4 policy questions and the cross-decline comparison were refused under both gates even
though their drafts were correct. Median wall time per case: 2.1 s deterministic, 2.9 s
combined. The checker used about 15,000 input and 450 output tokens over 30 reviews in the
paced attempt; total OpenRouter spend for the whole study, including generation, was about
US$0.30.


## Second labeller

`python scripts/naacl2027/fresh_llm_agreement.py` writes `label-agreement.json`.

The first round of the form left out the payment policy table that the runtime attaches to
declined, timed-out and unmapped records (record field `guidance`, from `finbot/policy.py`),
so retry rules such as "retry at most once after 1 hour" had no visible source, and the second
labeller rightly marked five such answers unsupported. A second round re-showed the 11
answers from the five cases with that table; their round-2 labels replace round 1 (round-1
labels are kept in the file). `label-form.json` has the same omission.

| | Supported | Complete | Both |
|---|---:|---:|---:|
| Agreement (57 answers) | 53 (93%) | 53 (93%) | 51 (89%) |
| Cohen's kappa | 0.30 | -0.03 | 0.20 |

Kappa is low because almost every answer is correct, so chance agreement is high. The six
disagreements on the combined label:

- Second labeller stricter: a "which has settled?" answer naming only the settled payment
  (incomplete); two decline-51 answers that give a single retry but not the "4 times in 16
  days" limit; a pending-refund answer that also says no log events were available.
- First labeller stricter: a record-built summary that never says who approved the payment
  (the question); and the refunded payment's answer that repeats the policy table's
  "investigate the cause of the failure" guidance. The text is on the record, but this
  payment did not fail.

Under the second labeller's labels:

| Configuration (component, attempt 3) | Wrong drafts blocked | Correct drafts blocked |
|---|---:|---:|
| Deterministic | 2 / 4 | 13 / 26 |
| LLM review | 0 / 3 reviewed | 1 / 22 reviewed |
| Combined | 2 / 4 | 18 / 26 (with unavailable) |

| Gate (end to end) | First labeller: good / wrong | Second labeller: good / wrong | Withheld |
|---|---:|---:|---:|
| Deterministic | 23 / 1 | 22 / 2 | 6 |
| Deterministic + LLM review | 21 / 2 | 23 / 0 | 7 |

Whether the review helps end to end depends on who labels, and differs by two or three
answers either way. It stays off by default; a larger study with an external labeller
would be needed to decide.

## What this supports

- The LLM review, as configured, shows **no consistent benefit**: under the first labels it
  missed both wrong drafts and lowered the number of correct released answers; under the
  second labels the combined gate released 23 correct and no wrong answers. It was also often
  unavailable. It stays off by default.
- The deterministic gate releases mostly correct answers here (23 of 24, or 22 of 24, released), at the
  cost of refusing every policy question and of many repairs and fallbacks. Its false
  rejections are the main usability problem.
- Neither result is a general accuracy estimate.

## Fixes made after the study

The requested-information triggers were too broad ("Has the refund come through?" asked for
an amount; "When did it actually settle?" also asked for the expected date; "the settlement
date" asked for both dates), and "was not refunded" did not count as stating the absence.
Also, the policy table gave a refunded payment the "unmapped failure; investigate the logs"
guidance. These were fixed **after** seeing the results, so the study data are now
development data for them; the frozen results above are unchanged. A development rerun of
the deterministic checks on the same saved drafts (`development-rerun-after-fixes.json`)
blocks 11 of 28 correct drafts instead of 14 and still 1 of 2 wrong drafts; because the
fixes were made on these drafts, that is not evidence of improvement. A new frozen case set
would be needed for that.

## Reproduce

```sh
python scripts/naacl2027/fresh_llm_study.py score          # labels + saved verdicts, no calls
python scripts/naacl2027/fresh_llm_recheck.py score
python scripts/naacl2027/fresh_llm_agreement.py      # both label sets, agreement
```

Regenerating needs an OpenRouter key and a checkout of the frozen commit
(`data/naacl2027/fresh-llm-v1/protocol.json` lists the source hashes).

## Why correct drafts were blocked (attempt 3, deterministic checks)

Of the 28 drafts labelled correct, 14 were blocked on first check:

| Cause | Drafts | Cases |
|---|---|---|
| Policy answer paraphrased instead of quoted (`policy_unsupported`) | 5 | decline-05, policy-debit, policy-cap, policy-51, policy-05-retry |
| Requested-field trigger too broad, narrowed afterwards (`requested_information_missing`) | 3 | refund-pending, actual-vs-expected, multi-field |
| Refund absence worded in an unrecognized way (`ungrounded_refund_claim`) | 2 | refund-none-1, refund-none-2 |
| Comparison missing a required field (`comparison_missing_field`) | 2 | compare-refunds, compare-missing |
| Retry advice flagged against the 05 policy | 1 | compare-decline |
| Answer without documentation | 1 | no-evidence-1 |

Repair or the record-built fallback recovered 9 of these, so 23 correct answers were released;
all four policy questions were withheld.

## Paired follow-up (fresh-llm-v2): quoting the policy instead of refusing

The v1 study left one clear weakness: every policy answer was withheld, because a paraphrase
cannot pass the extractive policy check. We added one fallback. When a policy-only answer and
its repair both fail, code quotes the best retrieved passage (and any passage scoring within
80% of it) verbatim, with its source and date. Turns that touched a record never use it.

The test was run on 30 new cases (`data/naacl2027/fresh-llm-v2/cases.json`, 10 policy, 2 with
no document) frozen before any call. Three configurations judged **the same first Llama 3.3 70B
draft** in every case (30/30), through a response cache keyed by the exact request:

| Configuration | Released, correct | Released, wrong | Withheld |
|---|---|---|---|
| before (no policy fallback) | 17 | 0 | 13 (10 policy) |
| after (policy fallback) | 26 | 0 | 4 |
| after + LLM evidence review | 25 | 0 | 5 |

Labels: two labellers judged all 43 distinct answers. The AI assistant labelled first
(`labels.json`, not blind); Apurba Bose, a co-author who wrote no cases, then labelled blind to
gate outcomes and to those labels (`labels-second.json`). They agree on 41 of 43 (95%). Each
marks one draft wrong, and both of those drafts were blocked, so the table is identical under
either set: the AI assistant flags a draft giving the expected settlement date as the actual one
(`rec-actual-missing`); Apurba flags a draft saying the *merchant* should not retry a code 05
decline, where the policy names no one (`pol-05-fix`). Kappa is not informative here because
almost every answer is correct.

Under both label sets, 29 of 30 drafts are correct and deterministic checks still block 16 of
them; the fallback now answers most of them by quotation. Of the 4 remaining refusals, 2 are
correct (questions the knowledge base does not cover), 1 is a retrieval miss and 1 is a mixed
record-and-policy question. The review again adds no benefit.

```sh
rm results/naacl2027/fresh-llm-v2/replay.json          # replay refuses to overwrite it
python scripts/naacl2027/paired_gate_study.py replay   # offline, from responses.json
python scripts/naacl2027/paired_gate_study.py score
```
