# Public questions: before and after the coverage fix

This is the paper's "Public questions" result (Section 4.4).

## Setup

- **Questions.** 30 Banking77 train questions, picked ten each from three intents (refund not
  showing up, pending card payment, declined card payment), after code and sampling were frozen. Questions that overlapped earlier
  wording were screened out. An earlier set of 30 test questions found the omissions the fix
  addresses; that set is development data and is not scored here.
- **Records.** Each question is paired with two synthetic records: one with the requested
  details filled in, one with them missing. The question keeps its wording and gets a
  transaction ID appended, so this measures answering after the payment is identified.
- **Runs.** Each of the 60 tasks runs through the scripted inspector before and after the fix
  (120 runs). No model calls.
- **Fix.** `finbot/support_coverage.py` maps a question's topic (refund, pending payment,
  decline) and what it asks for (status, timing, cause, limits) to the record fields an answer
  must state, or must say are missing. The same plan drives the writer, the checks and the
  record-built fallback.

## Results

| Same 60 tasks | Before | After |
|---|---:|---:|
| Supported and complete, AI review (unblinded) | 23 | 50 |
| Supported and complete, blind co-author | not labelled | 56 |

- 27 tasks improved, none regressed, 33 unchanged (AI review).
- Every answer is supported under both label sets; they differ only on completeness.
  They agree on 52 of 60 post-fix answers (kappa 0.37). In 7 of the 8 differences the co-author
  accepted an answer that says the record lacks a requested field.
- Ten post-fix answers are incomplete under the AI review and still pass the gate, for example
  "when will the decline be fixed?", which gets a missing settlement date rather than a limit.
- Pre-fix answers have AI labels only, so the improvement rests on one labeller.

## Files

Under `results/naacl2027/public-wording-v2/`:

- `baseline-runs.json`, `runs.json`: before and after outputs.
- `paired-review-form.json`: the blank form both labellers used.
- `labels-ai.json`, `paired-score-ai.json`: AI labels and counts.
- `labels-second.json`, `label-agreement.json`: co-author labels and agreement.

Questions, records and the frozen protocol are in `data/naacl2027/public-wording-v2/`;
`scripts/naacl2027/support_coverage_study.py` produced the runs and the AI score.
