# Handoff: run the authorised US$1 live conversation evaluation

The user authorises **at most US$1 total in OpenRouter inference charges for this run**.
Use the existing account/key available to you. The preparing agent made no paid model
calls. The model is Llama 3.3 70B Instruct, as in the demo; this study runs separately
from the public demo because its public endpoints start a fresh writer session each time.

## Checkout and scope

Repository: https://github.com/soovadeep/finbot-demo

Branch: `abose/evaluation-context-gaps`

Use an isolated checkout of this branch if your workspace has unrelated changes. Do not
reset, merge or deploy over the user's work. Read the repository instructions and this
document before proceeding. Run the commands below from the repository root with Python
3.12 or newer. No AWS, Bedrock, NeMo, paid judge or additional model integration is needed.

Evaluate the four existing cases in `data/naacl2027/conversation-live-v1/cases.json`:

- Refund changes from USD 24.60 to USD 39.20.
- A previously present refund field disappears.
- An expected settlement date is followed by a different actual settlement date.
- The customer explicitly corrects which payment is in focus.

Each is paired between a four-turn and a 36-turn conversation: eight runs and 160 planned
user turns. All turns go through `Chatbot.ask`, with real model/tool exchanges and the
production context-management code. Final questions and backend snapshots match across
arms. There is no injected model error. These cases were already used for development
rehearsal; **do not call them independent, unseen wording, customer data or a user study**.

## Credentials

The runner reads `FINBOT_OPENAI_API_KEY`, then `OPENROUTER_API_KEY`, or a literal key
assignment in `.env.local` at the repository root. Use your existing secret configuration;
do not print the key, send it in chat, put it in source code, commit it or write it into
result artifacts. `.env` and `.env.local` are ignored by Git. The key does not need to be
copied from the hosted application if you already have an authorised OpenRouter key.

If your key is stored in a different local file, use `--key-file PATH` with the same
literal `FINBOT_OPENAI_API_KEY=...` format. The file is parsed as data, never executed.
Do not change the hosted demo's configuration or its shared account limits for this test.

## Verify before spending

1. Inspect `data/naacl2027/conversation-live-v1/protocol.json`. It pins runtime/case hashes,
   the budget runner hash, model, DeepInfra endpoint, pricing, settings and US$1 limit.
2. Run the free budget tests:

```sh
python3 -m unittest discover -s tests -p test_study_spending.py -v
```

3. Verify the frozen runtime/cases, without any model calls:

```sh
python3 - <<'PY'
from scripts.naacl2027 import conversation_study as study
from scripts.naacl2027.budgeted_conversation_study import DEFAULT, runner_sha
protocol, cases = study.verify(DEFAULT)
assert protocol['writer']['runner_sha256'] == runner_sha()
assert protocol['writer']['budget_usd'] == '1.00'
print('Frozen protocol verified; no model calls made.')
PY
```

If verification fails, use the matching committed runtime in an isolated checkout. Do
not disable the hash checks, modify the cases or silently regenerate the protocol around
new code. If the result directory already exists, inspect its spending journal before
doing anything else: the US$1 authorisation is not renewed by starting another process.

## Run once with the spending controls

```sh
python3 scripts/naacl2027/budgeted_conversation_study.py run
```

Use **this budgeted runner**, not the unrestricted `conversation_study.py live` command.
It checks current public pricing before inference and uses only the pinned endpoint,
with provider fallbacks disabled and OpenRouter `max_price` constraints on prompt,
completion and per-request charges. Maximum output is 600 tokens per request.

Before each request it durably reserves the cost of the endpoint's **entire context
window plus maximum output**, instead of trusting an estimated prompt token count.
At the frozen rates (USD 0.10/million input and USD 0.32/million output), this reservation
is USD 0.0132992 per request. A valid provider `usage.cost` releases the unused portion.
If the remaining US$1 budget cannot cover the reservation, no new call is sent. Missing
cost information or a transport/provider error stops the run and retains the reservation.
This relies on OpenRouter honoring its documented prices and context limit; a dedicated
provider-key credit limit provides an additional account-level safeguard if already set.

There are no automatic provider retries and no extra paid judging calls. A 500-call
ceiling is an additional bound, not the spending control. The runner reports progress
after each arm. Allow several minutes, checking progress without starting a second run.

If interrupted or incomplete, preserve the partial artifacts and spending journal.
**Do not rerun into a fresh directory, top up credits, increase the budget or retry failed
calls automatically.** Report the stop reason, known charges and unresolved reservations.
The current runner deliberately has no resume operation that resets its accounting.

## Inspect and label the outputs

Results go to `results/naacl2027/conversation-live-v1/`:

- `spend.jsonl`: reservations and reconciled provider costs, written before/after calls.
- `response-*.json`: raw provider responses and usage; no credential headers.
- `run-*.json`: user turns, tool evidence, drafts, repairs, final answers, focus and rollover.
- `report.json`: completion counts, mechanical diagnostics and spending; semantic accuracy
  remains unset until answers are labelled.
- `review-form.json`: hash-ordered final-probe drafts and final answers, hiding gate verdicts
  and arm names. Conversation length remains visible, so blinding is limited.

Review each distinct answer against the question, earlier user turns, retrieved evidence
available at that draft, and the preregistered rubric. Label `correct_record`, `supported`
and `complete` separately, with a short rationale. The backend snapshot is a reference
for currentness and identity, not a substitute for evidence retrieved before the answer.
Do not infer any label from gate acceptance, a matching amount or a successful tool call.
An honest missing-field answer can be correct; an unnecessary refusal is not a complete
answer when the requested information is available.

If you, an AI agent, perform this first review, save it as `labels-ai.json` with a clear
`reviewer` identity and `reviewer_relationship` such as `AI assistant; not independent
human review`. Do not invent human/co-author labels or describe this review as independent.
Preserve the blank form for a separate reviewer. Do not modify the writer, cases or guardrails
after seeing failures and then replace the original results.

To score a completed form:

```sh
python3 scripts/naacl2027/conversation_study.py score \
  --output results/naacl2027/conversation-live-v1 \
  --input results/naacl2027/conversation-live-v1/labels-ai.json
```

The scorer rejects missing judgments or changes to the questions, answers or evidence.
Keep incomplete arms in the planned denominator of eight; do not count provider failures
as safety detections or claim all cases passed based only on diagnostics.

## Report and preserve the evidence

Report actual provider charges separately from amounts still reserved because cost is
unknown. Give completed/planned arms, rollover counts, final current-record lookups,
wrong-record or stale-fact answers, refusals, repairs/fallbacks, and the short/long paired
outcomes. Distinguish the initial draft from the released answer. Explain that the experiment
measures this writer on four authored conversations and does not establish general reliability
or isolate a causal benefit of rollover.

Document the run and label provenance in an evaluation note. If updating the paper,
describe any AI-labelled findings as provisional, retain the independent-generalisation
limitation, rebuild the PDF and check the six-page main-text limit. Commit results/docs
separately from any later fixes, scan staged files for accidental credential inclusion,
and push only to the authorised `abose/evaluation-context-gaps` branch. Do not merge or
deploy. Return a concise result with costs, limitations, artifact paths and commit IDs.

OpenRouter references: [provider routing and price limits](https://openrouter.ai/docs/guides/routing/provider-selection),
[usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting).
