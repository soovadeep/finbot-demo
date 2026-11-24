# Evaluation scope and reproduction

The released evaluations measure different things. Do not describe component results as measured
performance of the hosted conversation, or engineering checks as a human study.

## Submission evidence without participant recruitment

The current submission uses the following completed evaluations:

- Cached simulated-customer comparisons, including full-list, amount-first and most-distinct
  baselines. Report correct/wrong confirmations, unresolved cases and question count.
- Authored replays through the deployed conversation controller. Report regression coverage,
  including its failure boundaries, rather than a customer-accuracy estimate.
- Matched clean/corrupted drafts, reporting both pre-existing failures and mutation-triggered
  rejections, alongside the historical live-writer audit and its known semantic errors.
- Varied inspector workflow replays and policy/comparison component probes, including equal-value,
  paraphrase and omission controls. See [results and concrete examples](varied-support.md).

These results can be reproduced without recruiting participants or making new model calls.
They do not establish that clarification is faster, easier, or preferred by real users.
The full-list baseline's strong identification results are part of the finding, not a gap
that must be filled with a human study before reporting the engineering evaluation.

## Clarification component benchmark

`simulate_customers.py` evaluates `ClarificationSession`: uniform prior over two to eight records,
multiple-choice replies, probabilistic updates, and confirmation from a ranked two-record shortlist.
The 224 openings are seen by the simulator but are **not parsed by this selection controller**.
Its response reliabilities are assumptions. It does not execute the answer-writing stage.
The saved two-family results and their limitations remain in `results/naacl2027/clarification-sim/`.

`compare_baselines.py` adds amount-first and most-distinct heuristics, with cache-only coverage
reporting and paired differences. Run it with `--bench ambiguity-8` and `--bench ambiguity-8-same-amount`.
See `results/naacl2027/strong-baselines/README.md`: a stronger heuristic exceeds one-question DV,
so the old comparison against fixed order alone is insufficient to claim selector superiority.

## Deployed conversation workflow

`POST /api/conversation` calls `run_conversation`, which uses `Conversation`. It parses the opening
and subsequent messages, treats unhedged details as exact filters, retains alternatives for hedged
details, and shows matching records plus an expandable group of other records. It does not use the
benchmark's ranked two-record shortlist. The public demo has four fixed synthetic $200 records.
Both controllers share Bayesian scoring functions; this does not make their policies equivalent.
In particular, a confident mistaken detail can filter out the intended record.

Run `python scripts/naacl2027/evaluate_conversation.py` for authored event sequences through the
**same controller called by the public endpoint**, including initial details, uncertainty,
corrections before/after an answer, absence, a wrong confirmation, and failure to recall.
Each runs under four fault conditions, with the scripted writer and no network/model calls.
The report records source hashes, selection outcomes, recovery paths, and narrow expected-field
checks on final answers. Hidden target IDs enter only the scorer. A correct-looking answer about
a wrongly confirmed record is counted as a wrong selection, even if verification passes.

These are workflow regression checks, not an accuracy estimate: events are authored, fault
variants repeat the same tasks, and expected-field checks do not establish prose completeness.
The wrong-confirmation case deliberately demonstrates a remaining failure boundary. The scripted
customer asks about and confirms a transfer while the evaluator's hidden target is a card payment;
the controller does not know that hidden intent. The UI's "Other records" buttons now pause when an authorized record contradicts a confidently
supplied detail. No new record lookup or answer occurs at that step. The prompt shows each supplied
and selected value; **Use this record and correct my details** both corrects the conflicting fields
and explicitly confirms the record. **Keep my earlier details; choose again** retains the details
without confirming. Typed corrections and unresolved choices cancel the pending conflict. Resolution
is bound to the current record and conflict ID. Tentative/unknown details do not trigger this check.

The **60 runs are 15 scripts × four configured faults**. The original nine scripts remain; six additions
cover repeated conflicting selection, accepting the correction, keeping earlier details, a typed
correction, leaving unresolved, and switching to a conflicting record after an answer. Results:

- 32 correct selections with the expected scripted answer fields.
- Four deliberately wrong selections consistent with the customer's stated details.
- 16 explicit unresolved endings, eight appropriate because the target is absent.
- Eight awaiting contradiction clarification, with no current answer or confirmed record.

Twenty runs never generate a draft (16 unresolved and four awaiting an initial conflict resolution),
so their fault settings have no effect. Four more runs pause after superseding an earlier answer.
User events and the answer writer are scripted (`live=False`); question selection uses the real
controller. Fault variants are dependent test conditions, not 60 independent customers or failures.

`tests/test_clarification_conversation.py` covers all six conflict attributes, tentative details,
no answer-writer call while conflicting, current-record-only retrieval after resolution, stale and
forged resolution events, repeated confirmation, typed correction and invalidation of old answers.
`node scripts/naacl2027/contradiction_interface.cjs` tests the visible choices with keyboard input,
answer invalidation and unresolved escape at 390 and 1280 pixels. Eight new axe-core 4.10.3 states
have no detected WCAG 2.1 A/AA violations or browser errors. Run a local server first; the script
requires Playwright and axe-core, with `FINBOT_DEMO_URL` and `CHROME_PATH` overrides available.
The committed report includes source hashes. Automatic scans are not a complete accessibility audit.

## Capability-to-evidence map

| Capability | Where to demonstrate | Evaluation artifact | Evidence boundary |
|---|---|---|---|
| Attribute clarification | Conversation `/study`; strategy comparison `/clarification` | `results/naacl2027/clarification-sim/`, `strong-baselines/` | 224 scenarios per simulator; component policy differs from conversation. |
| Confirmation, correction and contradictory selections | Conversation: **A selection conflicts with your message** | `conversation-replay.json`, `contradiction-interface.json`; `tests/test_clarification_conversation.py` | 60 authored replays and regression checks; no customer-accuracy estimate. |
| Record explanations and recovery | Conversation; inspector supported answer, decline and timeout presets | `paired-verification/`, `live-writer/audit.json`; `tests/test_demo.py` | Finite mutation formats and one live writer; known semantic errors remain. |
| Two-record comparison and amount binding | Inspector **Keep two records separate**, **Catch swapped amounts** | `varied-support.json`, `varied-support-fixed.json`; unit checks | 28 workflow runs, 38 mutations; original currency/omission failures fixed on the same cases. |
| Cited policy answering and refusal | Inspector **A citation is not enough**, **When recovery is unavailable** | `varied-support.json`, `varied-support-fixed.json`; unit checks | 12 workflow runs, 36 mutations; original retrieval/context failures fixed on the same cases. Six supported paraphrases still rejected. |
| Evidence, drafts and recovery inspection | Both interfaces, trace export | `interface-after.json`, `conversation-axe.json`, `contradiction-interface.json` | Engineering/accessibility checks; no human comprehension study. |

Result paths without a prefix are under `results/naacl2027/`. The [varied support suite](varied-support.md)
extends policy/comparison evidence beyond the presets. Its authored fixtures establish tested
behavior and failure boundaries, not performance on natural customer requests. The post-fix report
is a development regression rerun, not a new holdout; the original report remains unchanged.

## Answer verification

`check_injection.py` measures rejection of templated drafts against stored evidence; the live-writer
audit concerns saved Llama answers about card payments. Neither measures full customer conversations.
Report false rejections alongside corrupted-draft rejections. Do not use a passing gate as its own
independent factuality label.

Run `python scripts/naacl2027/paired_verification.py` for the post-hoc matched-control analysis
of the existing held-out mutations. The raw 82.3% corrupted-draft rejection includes 570 pairs
whose clean controls already fail. Mutation-triggered rejection is 2,098/2,670 accepted controls
(78.6%); bare links trigger zero new rejections. Keep both denominators and the original clean-draft
false rejection rate. The verifier and historical raw result file are unchanged.

## Optional future human study

`http://127.0.0.1:8765/pilot` provides an export-only comparison of the current four-record
clarification UI and a full-list baseline. It is an optional future-work tool, not a dependency
of the current submission or its reproduction commands. No study is scheduled and no participant
results are bundled. See [the protocol](user-study-protocol.md) for assignment, consent, timing
and analysis if participants become available. The default is rehearsal.
Run `python scripts/naacl2027/user_study.py --help` for allocation and analysis commands.

## Independent end-to-end assessment

See [claim boundaries](claim-boundaries.md) for the scoring rubric and
`score_end_to_end.py` commands. Correct record selection, supported claims and sufficient
completeness must all hold. The script creates unfilled forms and leaves the success rate
undefined while relevant answers lack independent judgments. Regression field checks and
gate verdicts are not independent semantic labels. Independent judgments would be required to
claim that accuracy measure; the current submission makes no such claim.
