# Fresh wording on a frozen runtime

This is a prospective developer challenge, not independently authored customer data or a new
live-model evaluation. Codex authored the sentences and expected labels with knowledge of the
implementation and earlier failures. The runtime was frozen at `1db94bb`; all 32 draft pairs,
16 message sequences and labels were committed in `c14f1c3` **before the first evaluation**.
No production code or labels were changed after inspecting the results.

## Who supplies the answers?

The test fixture supplies the financial answers: each pair contains one supported statement
and one assigning the same record's real value to the wrong financial role. The real Finbot
verifier checks these texts. No LLM generates answers during this test, and the verifier's
decision is not used as the expected semantic label.

The conversation part sends newly authored messages to the same `run_conversation` function
called by the demo endpoint. It tests candidate filtering and preservation of uncertainty before
confirmation. There are no confirm events, so **no financial answer should be generated**. This
part does not measure final-answer correctness or completed customer tasks.

An evaluation of freshly generated Finbot answers would require a writer, such as the existing
Llama integration. An LLM can also generate diverse test messages, but neither API generation nor
an LLM judge makes labels independent or reliable automatically. Expected facts should be specified
from source records and policy passages; ambiguous labels need review. No external writer or
simulator calls were made for the present challenge.

## Results

| Role asserted by the draft | Corrupt drafts rejected | Paired correct drafts accepted |
|---|---:|---:|
| Actual settlement date | 3/8 | 8/8 |
| Expected settlement date | 4/8 | 8/8 |
| Refund amount | 3/8 | 8/8 |
| Payment amount | 2/8 | 8/8 |
| Total | **12/32** | **32/32** |

Without the financial-role verifier, the same production chain rejects 0/32 corruptions and
accepts 32/32 correct counterparts. All 12 added rejections carry the expected new role reason.
The other 20 errors pass. For example, a record has a payment of 187.60 USD and a refund of
42.15 USD. “The refund amount was 187.60 USD on this record” is blocked, but **“Your refund came
to 187.60 USD” passes incorrectly**. Both numbers occur in evidence; the latter phrasing escapes
the finite role parser. Acceptance of correct prose alone does not establish understanding.

The controller returns the exact expected candidate set in **15/16** message sequences and
retains every compatible candidate in 15/16. It generates no financial answer before confirmation
in **16/16**. The failed sequence is:

> It may have gone to Harbor Books. I am certain it was a card payment.

The controller incorrectly treats Harbor Books as definite and excludes the Willow Repairs card
record. The expectation retains both card records because the recipient is tentative. This is
an uncertainty-parsing failure, not an observed wrong confirmation or financial answer.

These cases share one financial record and the demo's four conversation records. Counts are
dependent and do not estimate natural customer accuracy. The earlier 60/60 role ablation remains
valid for its original formats; the new 12/32 result exposes the language-coverage limitation.
Neither set should be described as a general financial correctness rate.

## Reproduce

```sh
PYTHONHASHSEED=0 python scripts/naacl2027/evaluate_fresh_wording.py
python -m unittest discover -s tests -p 'test_fresh_wording_evaluation.py'
```

The script checks hashes for every production Python source and the chain-construction helper,
as well as the precommitted fixture. It refuses a changed runtime or fixture and refuses to
overwrite a different result. To reproduce after later runtime changes, use a checkout of this
evaluation's commit. `PYTHONHASHSEED=0` pins set iteration in the frozen controller. The report at
`results/naacl2027/fresh-wording-v1.json` includes texts, source-field labels, verdicts, candidate
sets and provenance. No runtime fixes were made as part of this evaluation.

## How the earlier model experiments differ

- **Haiku and Llama customer simulation:** each model role-plays a customer on 224 scenarios,
  using exact, vague or mistaken memory. It answers clarification questions and selects from
  candidate lists. The study compares selectors in `ClarificationSession`; it does not execute
  the deployed opening parser or final answer-writing stage. Model replies were generated
  originally, then cached and reused for reproducible selector comparisons.
- **Llama live writer:** a separate experiment generates support answers for 128 card-payment
  target entries (including repeated records), under no injected fault, an injected fee in the
  first draft, or a fee in both draft and repair. Of 128 unmodified drafts, 125 initially pass;
  the author audit identifies nine date-role errors and one omitted refund among those passes.
  Later checking of saved answers is retrospective replay, not fresh model generation.
- **Original held-out template wording:** the answer-check experiment also includes previously
  held-out authored phrases, generated without a model. Those results have since been inspected;
  they are not a fresh test of the latest runtime.

A fresh LLM-writer study would complement this diagnostic. It should freeze the evaluated
version, keep generation separate from judgment, preserve rejected as well as released drafts,
and measure supported/complete answers separately from guardrail acceptance.
