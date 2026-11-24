# Agent design and context management

Finbot separates record clarification, tool access, model drafting, verification and
recovery. The conversation controller chooses template questions using Bayesian beliefs
and expected decision value; the customer explicitly confirms the record. General policy
questions in the inspector do not need record clarification. The LLM drafts answers and
requests tools; it does not grant access or execute payments.

## What survives a long conversation

`SessionMemory` holds the focused record ID, tool-derived facts with provenance/time,
user-supplied IDs, tickets and recent user requests. Assistant prose is not promoted to
financial evidence. New record snapshots supersede missing fields as well as changed
values; reappearing fields can become active again. A not-found lookup suppresses old
facts. The next answer still needs fresh tool evidence: session memory is continuity,
not proof that an earlier payment status is still current.

The prompt renders at most 4,000 characters of the focused snapshot. A larger snapshot
is omitted in full with an instruction to refetch it, rather than cutting off amounts,
conditions or JSON. Only the last eight inactive IDs, eight recap requests (200 characters
each) and eight tickets are rendered. The full ledger is retained for audit; its storage
size is a separate concern and these prompt limits do not guarantee a database item limit.

## Context admission

Before every writer call, including tool-loop and repair calls, Finbot checks the complete
system prompt, conversation/state messages and tool schemas. The isolated policy reviewer
is checked too. Input plus reserved output and margin must fit the configured capacity.

| Setting | Default | Meaning |
|---|---:|---|
| `FINBOT_CONTEXT_WINDOW_TOKENS` | 131072 | Set to the smallest window of the configured writer/policy-review/failover models |
| `FINBOT_CONTEXT_OUTPUT_RESERVE_TOKENS` | 16000 | Reserved output capacity; raised to an explicit client's larger output cap |
| `FINBOT_CONTEXT_MARGIN_TOKENS` | 1024 | Additional headroom for provider formatting |
| `max_turns_per_thread` | 30 | Roll the old conversation history into a fresh thread |
| `max_history_chars` | 120000 | Additional history-size rollover trigger |

The local estimate counts UTF-8 bytes of the serialized request, plus message/schema
overhead. One byte per estimated token is deliberately conservative for ordinary English
BPE text. It is **not an exact provider token count or a universal tokenizer bound**.
Provider-specific framing varies; deployments must configure capacities and validate
against actual usage. A smaller model needs a smaller configured window and appropriate
output reserve. This may compact earlier than necessary, trading conversational detail
for headroom.

At the start of a turn, the size calculation includes the incoming question and fresh
state. When needed, whole earlier turns are removed and at most eight short user requests
are carried forward. The active request and tool-call/result pairs are never truncated.
If tool results or the active request still exceed the budget, no further writer call is
sent; the user is asked to narrow the question. Failed turns restore the previous history
and memory consistently, including after a rollover. Risk signals are retained.

The optional separate `LLMEvidenceVerifier`/Bedrock checker sends scoped evidence rather
than chat history and has its own payload limits. The new writer budget does not measure
those providers' tokenization. Oversized policy reviews fail closed; no API failure is
counted as successful error detection.

## Other execution limits

- Six model/tool rounds per `_loop`, one repair by default, and a 90-second turn deadline
  bound ordinary execution. Tool authorization/provenance budgets span the whole turn,
  including repair. There are no automatic financial writes.
- Transient model failures use bounded retries, circuit breakers and configured failover.
  Context admission happens before provider calls; retrying the same oversized input is
  not a recovery strategy. Deadlines prevent new calls after expiry; an already-running
  provider request also depends on the adapter's transport timeout.
- Record fallback uses retrieved fields. Policy-only fallback quotes retrieved passages
  with citations. Explicit code questions additionally require every requested numeric
  or alphanumeric code to be covered by the actual passages or their section headings.
  Fallback ranks within each requested code and refuses incomplete coverage. This check
  does not establish general semantic relevance or customer eligibility.
- Telemetry records prompt-size estimates and limits, not prompt/evidence text, for the
  new context diagnostic. The inspector's financial checks and model-provider labels
  remain distinct from context-management tests.

## Verification and scope

`python -m unittest discover -s tests -p test_context_budget.py -v` exercises nine offline
contracts: full-payload/UTF-8 accounting, configuration rejection, output reservation,
rollover with focus and refetch, oversized active requests, tool growth, rollback after an
outage, snapshot replacement, and bounded memory rendering. These are software tests,
not measured accuracy of a live LLM over long conversations. Frozen earlier studies stay
unchanged; their runtime manifests intentionally reject this revised implementation.

For example, after a long discussion about payment A, its remembered refund might be
USD 24.60. Rollover preserves which payment the customer means, but the next question
still causes a fresh lookup. If the backend now says USD 39.20, the old amount is
superseded; if the refund field is gone, it is no longer an active fact. The model's
ability to use that state correctly still needs live evaluation.

The [paired conversation protocol](papers/naacl-2027/evaluation/conversation-study.md)
now exercises actual multi-turn sessions, with matched short/long probes, backend changes,
source/runtime freezing, provider usage traces, and blind review forms. Its committed
run uses the scripted model without network calls. Independent cases and live long-chat
accuracy remain pending; neither the rehearsal nor the nine software tests supplies them.
