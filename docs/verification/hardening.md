# Verification hardening: initial scope

Branch: `abose/finbot-verification-hardening`, based on main at `26d6cb6`.
This change starts the verification expansion independently of the NAACL manuscript branch.
It adds engineering controls and reproducible regression evidence, not a completed human
study or a claim of semantic verification for arbitrary financial answers.

## Implemented

1. **Record identity at runtime.** Every successful record-tool result must contain the
   same record ID as the request. This check runs alongside the financial verifiers in all
   policy modes, including on repair and fallback. It catches adapter/result mix-ups; it
   does not authenticate records or authorize their retrieval.
2. **Strict policy coverage.** `FINBOT_POLICY_VERIFICATION=strict` checks drafts even when
   there was no KB call. Non-abstention document text must reproduce a whole retrieved
   chunk in a cited paragraph. This prevents the tested adjacent-exception and historical
   context omissions. Arbitrary added conclusions and paraphrases are rejected.
3. **Source metadata checks.** Strict mode requires a chunk ID, positive integer version
   and valid update date. It rejects future/over-age sources, lower retrieved versions of
   the same URL and conflicting chunk identities. The age limit is `FINBOT_KB_MAX_AGE_DAYS`
   (positive, default 540); it is a recency policy, not proof of policy validity.
4. **Bounded recovery.** Missing evidence and failed checks enter the existing single
   repair attempt through the same authorized tools and budgets. Exact abstentions and
   canonical record summaries can pass strict review; summaries still pass the financial
   chain and the identity check. No new provider, subscription or paid judge is required.
5. **Stronger retrieval scoring.** `expect.tool_calls` requires an exact tool name and
   input, optional result-field expectations and an optional zero-based turn index. Both
   Banking77-derived sets now require correct arguments and a matching `found` record for
   their 208 record-backed cases each. This is separate from factuality/task success.
6. **Opt-in LLM semantic review.** The subsequent `hybrid` mode retains source/record
   requirements and asks the configured model for separate support and applicability
   verdicts, backed by exact quotes. It can accept faithful paraphrases. Its protocol and
   bounded repair have mocked integration tests; its semantic accuracy is unmeasured.
   See [hybrid verification](hybrid.md).

The existing `off`, `extractive` and `model` policy modes remain available for comparison.
The offline inspector retains its extractive baseline. Enable strict mode on the normal
application, for example for an offline session:

```bash
FINBOT_LLM_PROVIDER=fake FINBOT_GUARDRAIL=local FINBOT_POLICY_VERIFICATION=strict \
  FINBOT_KB_MAX_AGE_DAYS=540 python -m finbot.app
```

## Local validation

The focused tests cover incorrect returned IDs, fallback rejection, missing retrieval,
recovery through the authorized gateway, full-passage controls, omitted context, negation,
source metadata, budgets and exact argument/result scoring. The component runner is:

```bash
python scripts/evaluate_policy_checks.py --out results/verification/policy-checks.json
python scripts/run_eval.py --data data/test --cases data/test/banking77.jsonl
python scripts/run_eval.py --data data/test --cases data/test/banking77_fresh.jsonl
```

Use `FINBOT_LLM_PROVIDER=fake FINBOT_GUARDRAIL=local` for offline evaluation. Real model
configuration changes these runs into paid/live evaluations; none are required here.

On the 24 authored component cases, the recorded decisions are:

| Mode | Supported allowed | Supported rejected | Unsupported allowed | Unsupported rejected |
|---|---:|---:|---:|---:|
| Off | 7 | 0 | 17 | 0 |
| Extractive | 6 | 1 | 10 | 7 |
| Strict | 5 | 2 | 0 | 17 |

Both strict false rejections are valid paraphrases. No `hybrid` accuracy row is reported:
mocked reviewer approvals cannot establish accuracy. These selected cases measure the
implemented contract, not population accuracy; no confidence interval or superiority
claim is warranted. One allowed supported control is an abstention, not a completed task.
The report includes source hashes and every per-case decision. Historical paper tables
and live-model results have not been rescored or rewritten.

## Next scope and independent validation

- Create an independent evaluation set before tuning additional language coverage. Hold
  out whole policy/scenario families, including versions and paraphrases. Preserve source
  snapshots, record IDs, task intent and a code/prompt/configuration manifest.
- Have two reviewers label evidence support and task completeness without seeing the
  verifier verdict or system condition. Record disagreement and adjudication. The verifier
  and any LLM judge are measurements to evaluate, not the annotation ground truth.
- Compare current and strengthened checks on identical candidate/evidence pairs, followed
  by end-to-end runs with the same writer, tools, authorization and budgets. Separate clean
  model outputs from injected faults. Count reviewer and repair calls in cost/latency.
- Report unsafe releases, false rejections, complete supported answers, incomplete
  fallbacks and abstentions with explicit denominators. Use scenario/conversation-level
  uncertainty for sampled data; do not count paraphrases as independent people or tasks.
- Add validated policy applicability/effective-date schemas and complete-document context
  before claiming case-specific eligibility checking. An exact passage can still be
  irrelevant to the user, or omit context located in a different chunk. Recent metadata
  does not prove a policy is authoritative or currently effective.
- Consider typed financial claims and validated calculations, with a check that the
  displayed prose preserves them. Preference learning and clarification studies should
  be evaluated separately once this factual-validation foundation is measured.

Strict mode is conservative by construction: it cannot currently accept free paraphrases,
arbitrary personalized conclusions or most mixed record/document explanations. The
independent evaluation must measure this utility cost as well as missed errors.
