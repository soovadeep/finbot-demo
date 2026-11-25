# Shared question coverage and a prospective paired evaluation

## Implementation

`finbot/support_coverage.py` composes a payment topic (refund or pending payment)
with requested information: status, timing, cause, meaning, account-navigation
information or assistance limits. This uses finite English patterns and typed
record paths, not dataset intent labels, case IDs or a lookup table of questions.

The same requirements supply live-writer instructions, deterministic checking,
scripted answering and the checked record fallback. Repair receives both the
failed requirements and the same writer guidance. The conversation recognises
support complaints through this plan while retaining confirmation/access checks.

- Refund progress requires `refund.status` or an explicit missing-status statement.
  Giving only a payment/refund amount no longer satisfies recognised progress requests.
- Refund arrival binds to `refund.expected_date`, independently of payment settlement.
- Recognised lifecycle status assertions use the latest scoped record. A correct
  clause cannot excuse a contradictory clause; questions and negated correct states
  do not satisfy affirmative coverage. Statuses cannot be borrowed from another record.
- A recognised “why pending?” question requires a recorded reason or explicit absence.
  The pending explanation is a fixed interpretation of the schema—completion is not
  confirmed—not a claim about a bank's processing policy or the cause of a delay.
- Absent decline reasons now produce an explicit missing-field sentence rather than
  forcing a blanket refusal. Known values, including zero, still cannot be denied.
- Account-navigation and assistance requests recognised by the plan receive explicit
  record/capability limits. It does not invent account-interface instructions or move money.

The parser and explanation grammar remain finite. In particular, some explanations
require the code-owned schema sentence; equivalent LLM paraphrases may still trigger
repair/fallback. This change does not establish a general semantic verifier, add NeMo,
or change the optional Bedrock/LLM checker configuration.

Eleven new tests cover status omissions and contradictions, latest evidence, record
binding, refund-vs-settlement timing, missing causes, live hints and all recovery stages.
The complete suite passes **285 tests**. Earlier financial-role component measurements
remain identical; the workflow tests explicitly check the added refund-status sentence.

## Development and frozen evaluation are separate

The already-inspected public-v1 cases are development data. Two development reports
retain the initial and final implementation outcomes (`support-coverage-development*.json`).
The first revealed a remaining auxiliary/negation parsing gap; the shared grammar was
extended before freezing. Neither report replaces the original v1 experiment.
Replaying the earlier cached 30-case LLM study still rejects **16/29 correct initial
drafts** and its one incorrect draft; policy-paraphrase false rejections remain.

Implementation commit: `1400816`. Protocol/sampler freeze: `632bc34`. Selected questions
committed before execution: `d3fe7ca`. Exact source hashes are in the frozen protocol.

After freezing, we downloaded the pinned BANKING77 **train** split (10,003 questions),
screened 474 rows in three predeclared intents, and selected ten questions per intent
using a fixed hash order. Screening flagged 51 overlaps with prior or selected wording;
all public-v1 questions were included in the archived prior corpus. This establishes
unused wording under the stated exact/near-match procedure, not semantic independence
or lack of language-model pretraining exposure. No model was trained on these rows.

Each of 30 questions is paired with populated/missing synthetic details and executed
through **both** the pinned pre-fix (`59a1d2f`) and frozen revised inspector:
30 questions × 2 record conditions × 2 versions = **120 scripted runs**. The questions
keep their original wording and append a transaction ID, so this measures answering
after identification rather than clarification or long-conversation reasoning.
All first outcomes are retained; there was no tuning after inspecting this new set.

## Results

| Measure, on the same 60 tasks | Pre-fix | Revised |
|---|---:|---:|
| Released answers | 57 | 60 |
| Supported and complete outcomes, provisional AI review | 23 | 50 |
| Released, supported and complete answers | 20 | 50 |
| Appropriate evidence-limited refusals | 3 | 0 |
| Incomplete outcomes | 37 | 10 |

There are **27 improved, zero regressed and 33 unchanged** support-and-completeness
judgments. These are paired observations, not independent samples. The original v1
set had 24 complete releases plus three appropriate refusals; the baseline count here
is different because this is a different question set.

The implementing Codex AI assistant reviewed all 120 question/evidence/answer pairs
using the same rubric as v1, judging support and completeness separately from gate
acceptance. Review was **unblinded and provisional**, not independent human annotation.
All financial assertions were judged supported by the synthetic evidence; completeness
of indirect complaints remains subjective. Statements about current identified
payments do not establish the cause of every earlier attempt or account-wide status.
No new provider calls or inference charges occurred.

Example from the new set: “Card payment is still pending, why is that the case?”
Previously, the response gave payment approval and an expected settlement date.
It now adds the pending status, its bounded schema meaning, and “The record does
not show a settlement reason.” This addresses why without inventing a cause.

Ten outcomes still pass the gate but are incomplete: both record conditions for
five questions. They ask about checking a refund in a statement, a “returned
transaction,” resolving the issue, “How come” it is pending, or when a decline
problem will be fixed. The last question still receives a missing **settlement**
date rather than an explicit limit on predicting a fix. These failures remain
unchanged in the frozen result and are not called successes.

A separate, authored component diagnostic accepts all 60 matched correct
status/absence controls and rejects all 60 unsupported-status corruptions. It
repeats a small number of status schemas across IDs and is **not** a natural LLM
error rate, an independent sample of 60 failure types, or a substitute for answer review.

## Later development fixes for the ten omissions

After inspecting and reporting the frozen results, revision `e75a046` extends the shared rules:

- Statement/app questions require an explicit access/information limit. The assistant
  cannot inspect the customer's statement; it does not invent where the bank displays refunds.
- Cause requests include "how come" and "what is going on", in either order relative
  to a decline description. They require a recorded reason or an explicit absence notice.
- Requests to fix/resolve an issue require the assistant's read-only capability limit.
- Resolution timing is separate from refund/settlement timing. A retry interval does not
  establish when a decline issue will be fixed. Compound questions retain both requirements.
- "Returned transaction/payment/transfer" without explicit refund wording prompts a
  clarification: merchant refund or payment returned to sender. It does not assume that
  a populated date field resolves the meaning. The exact code-owned clarification question
  is excluded from the broad refund-mention check; surrounding assertions remain checked.

The same rules guide the scripted/live writer, verifier, repair and record fallback.
Seven added test methods cover these paths, present/absent fields, positive and negative
controls, and an actual conversation clarification/follow-up. **All 292 tests pass.**
The finite parser and strict wording requirements remain limitations.

`support-coverage-followup.json` separately replays all 60 already-inspected tasks.
All 60 produce a response; 48 are byte-identical and 12 change. The revised coverage
check rejects all ten original incomplete answers. Provisional unblinded review of
the changed answers finds eight of those omissions answered with the required facts
or limits; the other two ask the return-type clarification and **remain unresolved**
pending the customer reply. The two additional changed answers add missing-decline-reason
notices to previously accepted evidence-limited guidance. See
`support-coverage-followup-review-ai.json` for answer-bound rationales.

This is development regression evidence, **not a new generalisation score**. The frozen
23/60 to 50/60 comparison, raw outputs and original labels are unchanged. No fresh LLM
calls were made. A separate conversation test verifies that an explicit follow-up about
the refund keeps the confirmed record and answers with refund timing or its absence;
that authored test is not a completed customer interaction in the frozen study.

Reproduce this development replay with an unused output path:

```sh
python scripts/naacl2027/replay_support_coverage.py --output /tmp/finbot-coverage-followup.json
```

## Frozen study artifacts and reproduction

- Protocol, source attribution, overlap audit and selected questions:
  `data/naacl2027/public-wording-v2/`.
- Historical/current raw outputs: `baseline-runs.json` and `runs.json` under
  `results/naacl2027/public-wording-v2/`.
- `paired-review-form.json`, `labels-ai.json` and `paired-score-ai.json` preserve
  questions, evidence, answer hashes, judgments and rationales.
- `status-pairs.json` contains the narrow status diagnostics separately.

Reproduction on the matching revision, retaining original outputs:

Use the original study checkout (`d1a8afc`) for the frozen reproduction below;
later runtime fixes intentionally fail its source-hash check.

```sh
python - <<'PY'
from pathlib import Path
from scripts.naacl2027 import support_coverage_study as study
study.OUT = Path('/tmp/finbot-coverage-replay')  # an empty/new directory
study.configure()
study.run()
PY
```

Source/case hash checks reject changed code and inputs. The baseline runs from an
isolated archive of its pinned Git revision. New live LLM evaluation remains
pending because this checkout has no model key. The new instructions are wired
into the live writer and repair path, but scripted improvements do not establish
how a live writer will follow them. Deployment/video synchronisation and broader
policy/paraphrase evaluation remain separate work.
