# Fresh LLM answers, checked three ways

This is the first evaluation in this repository of answers **newly generated** by a live
model and scored against labels. It is small (30 cases) and its labels are provisional.
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
  and completeness, with a rationale, in `results/naacl2027/fresh-llm-v1/labels.json`.
  Success means supported **and** complete. Checker verdicts are never used as labels.

## Caveats

- **The labels are provisional and not independent.** They were made by the AI assistant
  working for the authors, which also wrote the cases and the checker prompt, and which had
  seen the per-case allow/block summary before labelling. The authors should review them
  (the label file is a form: change `supported`, `complete` and `rationale`, then rerun
  `score`). The checker is a different model family from the labeller and the writer.
- **Only 2 of 30 first drafts were labelled wrong.** Detection rates on 2 items mean little.
- **The checker was rate-limited upstream.** OpenRouter returned HTTP 429 from Google AI
  Studio during the first two check attempts (20 and 19 of 30 reviews unavailable) and for
  12 of 59 reviews in the combined end-to-end run. A third, paced attempt
  (`fresh_llm_recheck.py --attempt 3 --pause 6`, same frozen checker and inputs) had 5 of 30
  unavailable. All attempts are kept. Unavailable reviews block in the application (fail
  closed) but are not counted as detections below.
- One run per case; temperature 0 does not make the provider deterministic.

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

**End to end** (all 30 cases; labels on every released answer):

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

## What this supports

- The LLM review, as configured, **adds no measured benefit**: it missed both wrong drafts,
  was often unavailable, and lowered the number of correct released answers. It stays off
  by default.
- The deterministic gate releases mostly correct answers here (23 of 24 released), at the
  cost of refusing every policy question and of many repairs and fallbacks. Its false
  rejections are the main usability problem.
- Neither result is a general accuracy estimate.

## Fixes made after the study

The requested-information triggers were too broad ("Has the refund come through?" asked for
an amount; "When did it actually settle?" also asked for the expected date; "the settlement
date" asked for both dates), and "was not refunded" did not count as stating the absence.
These were fixed **after** seeing the results, so the study data are now development data
for them; the frozen results above are unchanged and were not rerun as evidence.

## Reproduce

```sh
python scripts/naacl2027/fresh_llm_study.py score          # labels + saved verdicts, no calls
python scripts/naacl2027/fresh_llm_recheck.py score
```

Regenerating needs an OpenRouter key and a checkout of the frozen commit
(`data/naacl2027/fresh-llm-v1/protocol.json` lists the source hashes).
