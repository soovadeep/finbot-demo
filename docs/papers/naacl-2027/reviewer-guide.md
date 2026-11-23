# Finbot demo: reviewer guide

Finbot demonstrates read-only payment support through a conversation interface and an evidence
inspector. The conversation handles uncertain descriptions, confirmation, corrections and
confirmed-record explanations. The separate inspector adds decline and timeout explanations,
two-record comparisons, cited policy responses, controlled faults and recovery traces.

The hosted demo needs no install: the conversation is at
<https://finbot-demo-20852907589.us-central1.run.app/> and the evidence inspector this guide
walks through is at <https://finbot-demo-20852907589.us-central1.run.app/inspector>.
The rest of this guide runs the same server locally.

This guide covers the **offline scripted demo**, using synthetic payment records and policies.
It requires no API key, subscription, AWS account, database, Node.js or Docker. It makes no
model API calls. The interface demonstrates implemented verification and recovery behavior;
the examples are not evidence of natural model-error rates or general financial correctness.

## 1. Obtain and run the source

Prerequisites: Python **3.11 or later** and a modern browser. This guide was smoke-tested on
macOS with Python 3.12 in a fresh virtual environment without third-party packages. Windows
and Linux instructions have not yet been separately validated.

Clone the repository:

```sh
git clone https://github.com/soovadeep/finbot-demo.git
cd finbot-demo
git rev-parse HEAD
```

If using the eventual downloadable source archive, extract it and enter its root directory
(the one containing `finbot/`, `tests/`, `README.md` and `LICENSE`) instead. Record the
revision or archive checksum.

On macOS/Linux:

```sh
python3 --version
python3 -m venv .venv-demo
source .venv-demo/bin/activate
python -m finbot.demo
```

On Windows PowerShell:

```powershell
py -3 --version
py -3 -m venv .venv-demo
.\.venv-demo\Scripts\python.exe -m finbot.demo
```

No `pip install` is needed for this offline entry point.

Open **<http://127.0.0.1:8765/inspector>** for the evidence inspector this guide covers; the
conversation demo is at <http://127.0.0.1:8765/>. The terminal prints both addresses and
identifies the mode as offline/synthetic. Leave the terminal running. Stop the server with **Ctrl-C**.
For an occupied port, use `python -m finbot.demo --port 8766` and open the printed address.

## Try a contradictory selection in the conversation

On the evaluation branch (`git checkout review/naacl-demo-evaluation`), open the local conversation
and choose **A selection conflicts with your message**. Send the preset message about the $200
card payment to Willow Repairs. Expand **Other records** and select the Willow Repairs bank transfer.
The answer pauses and the prompt displays the conflicting type. Try:

- **Keep my earlier details; choose again**, then confirm the matching card payment.
- **Use this record and correct my details**, which explicitly changes the conflicting details
  and confirms the transfer before retrieval.
- Type a correction, or leave unresolved. A typed correction still requires a fresh confirmation.

Selecting a conflicting alternative after an answer marks the old answer superseded. Tentative
recollections do not block selection. A mistaken selection consistent with supplied details remains
possible. This new behavior requires this branch's code; a branch push does not update the hosted service.
The [capability-to-evidence map](evaluation/README.md#capability-to-evidence-map) identifies which
features have component experiments, regression checks or prepared examples only.

## 2. Five-minute walkthrough

Choose a scenario and click **Run inspection**. Selecting a scenario fills its question and
fault setting; running it creates a fresh session. You can edit both before running.
The displayed run's original question remains above the panels. Editing inputs marks the
results as stale and disables trace export until a new run succeeds.

1. **A supported answer:** expand the retrieved transaction, then select the draft stage.
   Locate the status and amount supporting the final answer.
2. **Catch swapped amounts:** inspect the rejected draft. Both amounts occur in retrieved
   records, but their record associations are wrong. Compare the draft with the repair.
3. **A citation is not enough:** the draft retains a valid source URL while reversing the
   debit/prepaid surcharge rule. Inspect the unsupported statement and source, then the
   supported repair. These are synthetic policies, not real payment-network guidance.
4. **Recover after failed repair:** see rejection of both injected-fee drafts and a passing
   record-built fallback. Code constructs that summary; it is not another model repair.
5. **When recovery is unavailable:** both policy drafts fail and no transaction summary is
   available. Inspect the refusal and distinguish it from a complete useful answer.

The full preset inventory is:

| Preset | Expected trace outcome | What to inspect |
|---|---|---|
| A supported answer | `passed` | Evidence agrees with the draft |
| Catch a wrong status | `repaired` | Approval claim replaced by the recorded decline |
| Recover after failed repair | `record_fallback` | Draft and repair block; fallback allows |
| An unknown outcome | `passed` | Timeout remains unknown; check status before retrying |
| Keep two records separate | `passed` | 129.00 USD declined and 54.20 USD approved stay with their records |
| Catch swapped amounts | `repaired` | `value_from_other_record:amount:` reason in draft |
| When recovery is unavailable | `blocked` | Policy answer has no eligible transaction fallback |
| A citation is not enough | `repaired` | Reversed rule fails despite the valid citation |

The source says **“Debit and prepaid cards cannot be surcharged.”** The injected draft
changes **cannot** to **can**. Extractive checking rejects that sentence, and repair restores
the source wording. This illustrates a deterministic check, not a measured semantic reviewer.

## 3. Read and export a trace

- **Retrieved evidence:** exact tool results for the selected stage. The eligible-evidence
  view excludes designated third-party fields, including their nested numbers and objects.
  Eligibility is a configured field policy, not proof that a source is true or current.
- **Draft & verification:** select `draft`, `repair` or `fallback` when present. `action=allow`
  means the configured gate passed; `block` includes failure reasons. Policy `checks` carry
  individual statement verdicts and source excerpts where available. A citation is not
  by itself a supported verdict.
  Rejection codes also have plain-language explanations. The policy-mode note describes
  sentence reuse, paraphrase rejection, context loss and the KB-lookup trigger.
- **Customer answer:** the final response after output checks. A passing intermediate stage
  is not sufficient to identify what was finally returned.
  Record-built summaries include a reminder to check completeness across records and question parts.
- **Export trace:** downloads JSON schema version 2. `mode=offline_scripted` and
  `synthetic_data=true` identify the run; `injections` records faults actually applied.
  `steps[].evidence` is the raw stage snapshot; `steps[].trusted_evidence` is the eligible
  subset; `steps[].checks` contains policy findings. Top-level `evidence` is the tool history.
  `final`, `outcome` and `metrics` describe the returned result and local execution counts.

The exported trace contains observable drafts and decisions, not hidden model reasoning.
`model_calls` counts scripted calls; `latency_ms` is local elapsed time. Neither is a live
provider cost/latency result. Selecting an inapplicable fault can leave `injections` empty.

Every run starts a new in-memory session with synthetic account `m_100`. There is no multi-turn
chat continuity or persistent history to reset. Click **Run inspection** again for a new run;
refreshing clears the browser display. Exported files remain in your browser's download
location until you delete them. The server stores no run history.

## 4. Reproduce the acceptance checks

From the repository root with the demo virtual environment active:

```sh
python -m unittest discover -s tests -p test_demo.py -v
```

Expected: **all 23 tests pass**, including all eight presets, stage
evidence, JSON export content, input limits, tenant isolation and local HTTP boundaries.
This is engineering validation, not a user study.
The interface checks (paper Appendix F) passed 18/18 browser criteria across
the eight scenarios, exports, keyboard selection, stale/error states and responsive widths.

For a command-line trace while the server runs, use a second terminal (macOS/Linux):

```sh
curl --fail --silent --show-error http://127.0.0.1:8765/api/run \
  -H 'Content-Type: application/json' \
  --data '{"question":"What are the surcharge rules?","fault":"policy_once"}' \
  -o finbot-policy-trace.json
python -m json.tool finbot-policy-trace.json
```

Expect `outcome` to be `repaired`, two verification steps and an applied `policy_once` fault.
Delete the downloaded JSON when no longer needed.

## Reproduce varied policy and comparison checks

On `review/naacl-demo-evaluation`, run `python scripts/naacl2027/evaluate_support.py` without
starting a server. It saves `results/naacl2027/varied-support.json`, including full local
inspector traces, six additional synthetic policy fixtures, matched drafts and expected fields.
See [the results and concrete examples](evaluation/varied-support.md): 28/28 comparison workflow
checks and 10/12 policy checks pass; controlled probes expose currency-binding and omission gaps.
The records supplied by the evaluator are internal fixtures, not new hosted presets. There are
no model calls or participants, and a branch push does not redeploy the hosted service or video.

## 5. Troubleshooting and limits

| Symptom | Action / explanation |
|---|---|
| `No module named finbot` | Run from the extracted/cloned repository root |
| Syntax or import error | Confirm Python 3.11+ and that the full source tree was extracted |
| Address already in use | Choose `--port 8766` (allowed range: 1024–65535) |
| Browser cannot connect | Keep the terminal running and open the address on the same machine |
| HTTP 403 | Use the exact loopback address/port; foreign Host/Origin headers are rejected |
| No fault appears | Not every corruption applies to every question; inspect `injections` |
| Changing provider variables has no effect | The inspector explicitly selects scripted/local adapters |
| An unexpected question gets a limited answer | The scripted model handles fixtures, not arbitrary natural-language dialogue |

The launcher binds to loopback and exposes rejected drafts for inspection. Do not enter real
customer data or expose this development server as a public deployment. Synthetic exports
are masked, but a production diagnostic workflow needs explicit access and retention controls.

The inspector enables **extractive** policy verification. Normal application configuration
defaults to `off`; optional model review and Bedrock Guardrails are separate paths that may
require credentials and incur provider charges, and are not enabled by this guide. Automated Reasoning and NeMo are
not integrated. A legitimate paraphrase may fail extractive checks, while a reused sentence
can still omit important context. Multi-record fallback can be incomplete. Passing the
implemented checks is not a universal correctness or financial-safety guarantee.

## License and data

The code is [MIT licensed](../../../LICENSE), copyright 2026 Sandip Nandi. The inspector uses
synthetic fixtures from `finbot/tools.py` and `finbot/demo.py`. Separate evaluation sets use
Banking77 wording under **CC-BY-4.0**, with attribution and modifications documented in
[data/naacl2027/README.md](../../../data/naacl2027/README.md); Banking77 is not real customer transaction data.
Preserve these notices in any reviewer package. Policies and records are examples for
evaluation, not production financial advice.
