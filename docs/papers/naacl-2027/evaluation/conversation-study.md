# Paired conversation evaluation: prepared, live results pending

No paid API calls were made. The committed run is an **offline scripted rehearsal**
through the real `Chatbot.ask` path. It tests the evaluation machinery and context
contracts, not live LLM reasoning quality or independent generalisation. The supplied
four scenarios are AI-assisted developer-authored fixtures. They must not be relabelled
as unseen customer conversations.

The subsequently authorised US$1 live follow-up has a separate frozen protocol and
[agent handoff](live-agent-handoff.md). Use its budgeted runner for that authorisation;
the generic `live` command below has only a call-count ceiling. Live results are in
[conversation-live.md](conversation-live.md).

## What is paired

Each case has a four-turn short conversation and a 36-turn long conversation, starting
with identical record introductions and an explicit correction of the focused payment.
The long arm adds 32 actual question/model/tool/answer turns. The final question and
backend snapshot are identical between arms. Each arm gets a fresh session and model
adapter; arm order alternates across cases. No history is inserted by the evaluator.
There is no model-error injection. Backend changes occur immediately before the final
question, so both arms must fetch the latest evidence.

| Probe | Earlier evidence | Evidence at the final question | Required answer |
|---|---|---|---|
| Updated refund | USD 24.60 refunded | USD 39.20 refunded | Latest refund, not the remembered amount |
| Removed refund field | USD 24.60 refunded | No refund field | Amount unavailable; absence does not mean zero |
| Actual settlement | Expected November 26 | Actual November 27 | Actual date distinguished from expectation |
| Corrected focus | Two different payments introduced | User corrected focus to the first | First payment's refund, not the second payment's |

The rehearsal totals 160 user turns and eight final probes. It exercises the default
30-turn rollover trigger with a 131,072-token configured window, a 600-token writer
output reserve, and a 1,024-token margin. The smaller output reserve is explicit study
configuration; the application's default reserve remains 16,000. Comparing short and
long runs measures a length-associated difference, not the isolated causal benefit of
rollover. A separate ablation would be needed for that claim. These are post-identification
conversations, not an evaluation of the ambiguous-record confirmation interface.

## What gets recorded and judged

The protocol freezes case contents, runtime and harness hashes, settings, model/endpoint,
and answer rubrics. It rejects changed code or inputs and refuses to overwrite results.
Each arm saves its full sequence of questions, tool calls, drafts and final answers;
model request hashes, conservative input-size estimates, returned provider usage and
errors; and focus, recap and rollover state. Full provider requests are not duplicated
in the artifacts. There are no credentials in the result files.

Mechanical diagnostics check focus, a fresh lookup of the current snapshot, and required
or forbidden strings. They do **not** establish semantic correctness. The hash-ordered
blind form covers final-probe drafts, repairs and released answers, with user turns,
evidence and a preregistered rubric, hiding arm names and gate verdicts. Reviewers label
correct record, support and completeness separately. Long/short history length is visible,
so blinding cannot hide conversation length. Blank or edited answer/evidence items cannot
be scored. Both reviewers should label independently; preserve their two forms and report
disagreements rather than silently replacing them with an adjudicated label.

Success requires a released answer and all three positive labels. Provider failures,
unfinished arms and refusals remain visible. A model-call ceiling stops new calls, but
is **not a dollar spending cap**. Price depends on the selected endpoint and actual token
usage; an operator must separately set provider spending limits before any paid run.

## Reproduce the free rehearsal

From the checkout matching the frozen protocol:

```sh
python scripts/naacl2027/conversation_study.py rehearse --output /tmp/finbot-conversation-rehearsal
python -m unittest discover -s tests -p test_conversation_study.py -v
```

The committed protocol deliberately has no writer model or endpoint, so `live` refuses to
run against it. `rehearse` uses `FakeLLM` even if API credentials are configured locally.
The report leaves semantic accuracy unset until review. Human labels on scripted output
would still not turn the rehearsal into live-model evidence.

## Establish independent generalisation in a new version

1. Freeze the intended runtime before asking someone who did not develop the checks to
   supply new conversations, or select an independently sourced corpus with documented
   licensing and provenance. Keep the evaluation author's role explicit. Co-author review
   is not automatically external evaluation; new AI-generated cases remain synthetic.
2. Use the committed `cases.json` as the schema. Supply a source reference, author role,
   records, prefix/filler turns, final question, backend replacements and an answer rubric.
   Policy cases can include KB `pages` in the existing ingestion format. With
   `provenance.independent=true`, the importer requires `author_role=external` and rejects
   normalized probe duplicates against existing repository case files. This lexical check
   cannot prove independence, rule out paraphrases or detect model-training contamination.
3. Import into a new study directory with `prepare --input PATH --study NEW_DIR`. Freeze
   before inspecting results with `freeze --study NEW_DIR --writer-model MODEL
   --writer-base-url URL`. A locally hosted tool-calling model is usable without paid APIs;
   it measures that local model, not a different deployed writer.
4. After separately authorising any paid use and configuring credentials locally, run
   `live --study NEW_DIR --output NEW_OUTPUT --max-calls N`. The harness runs real model
   and tool turns and preserves failures. Do not tune against the held-out probes. If a
   failure motivates changes, retain this version and commission another holdout.
5. Have two reviewers complete separate copies of `review-form.json`, then use
   `score --output NEW_OUTPUT --input COMPLETED_LABELS` for each. Report paired probe
   outcomes, unassessed/unfinished arms, refusals, initial versus repaired answers and
   reviewer disagreement. Do not treat turns from the same conversation as independent
   samples or infer broad reliability from four conversations.

Independent case collection and live-model runs are **pending**. Preparation addresses
the evaluation-design gap; it does not supply the missing empirical evidence.
