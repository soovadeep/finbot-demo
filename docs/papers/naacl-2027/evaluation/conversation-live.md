# Live paired conversation run (US$1 cap): results

Run on 2026-11-24 with the frozen protocol `data/naacl2027/conversation-live-v1/protocol.json`
and `scripts/naacl2027/budgeted_conversation_study.py`, following
[live-agent-handoff.md](live-agent-handoff.md). Writer: Llama 3.3 70B Instruct through
OpenRouter, pinned to the DeepInfra endpoint, temperature 0, 600 output tokens.

## Two runs, both kept

1. **`results/naacl2027/conversation-live-v1/` (stopped).** At 21:52 UTC the pinned endpoint
   went down (OpenRouter showed it at 0% uptime for the last 5 minutes). After 1 of 8 arms and
   turn 12 of the second, request 31 failed with an HTTP error, and the runner stopped as
   designed. Charged: US$0.0099. One reservation (US$0.0133) is unreconciled; the request was
   rejected in 157 ms and was most likely not billed. Kept unchanged.
2. **`results/naacl2027/conversation-live-v1-run2/` (complete).** The user authorised one fresh
   run under a new US$1 cap once the endpoint recovered. It started at 22:33 UTC after four
   consecutive 100% uptime readings, four minutes apart. 8/8 arms, 160 user turns,
   329 requests, **US$0.2039 provider-reported, no unknown costs**.

Total charged across both: about US$0.214.

## Results (run 2)

| Case | Arm | Rollovers | Final answer (released) | AI label |
|---|---|---|---|---|
| Updated refund | 4 turns | 0 | 39.20 USD | correct |
| Updated refund | 36 turns | 1 | 39.20 | correct |
| Removed refund field | 4 turns | 0 | record-built fallback: no refund amount recorded | correct |
| Removed refund field | 36 turns | 1 | record-built fallback: no refund amount recorded | correct |
| Actual settlement | 4 turns | 0 | November 27, 2026 | correct |
| Actual settlement | 36 turns | 1 | 2026-11-27 | correct |
| Corrected focus | 4 turns | 0 | 24.60 for txn_LONG0001 (after one repair) | correct |
| Corrected focus | 36 turns | 1 | 24.60 | correct |

- Every long arm rolled its history over once and still answered about the current record:
  no stale refund, no wrong record, no refusal in any of the 160 turns.
- Short and long arms reach the same final outcome in all four pairs.
- The **removed-refund** case shows unnecessary blocking: in both arms, correct model drafts
  that said the refund is not recorded were blocked, and code released the record-built
  answer instead. The final answer is correct but not the model's.
- In the short **corrected-focus** arm the first draft gave the right value without any
  evidence retrieved for that draft (labelled unsupported); the repair fetched the record.

## Labels

`labels-ai.json` (scored in `score-ai.json`) was written by Claude, the AI assistant working for
the authors. It is **not an independent human review**: the labeller saw the run's progress
lines (completion and mechanical diagnostics) before labelling. All 8 released answers are
labelled correct-record, supported and complete; one draft is labelled unsupported. The blank
`review-form.json` is preserved for a separate reviewer.

## What this does and does not show

It shows the writer and the context code handling four authored conversations, short and
long, with one rollover each, live. The cases were used in development, so this is not
independent wording, customer data or a user study, and four pairs cannot establish general
reliability or a causal benefit of rollover.
