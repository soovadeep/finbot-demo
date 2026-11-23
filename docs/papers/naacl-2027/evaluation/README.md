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
the controller does not know that hidden intent. Separately, the UI's "Other records" buttons
permit confirming authorized records that contradict supplied details; there is no contradiction
confirmation step implemented.

The 36 runs are nine customer-event scripts under four configured faults. User messages and
confirmation actions are authored, while the real controller chooses its template-based questions.
The answer writer is scripted (`live=False`), not a live LLM. Twelve runs end unresolved and never
generate a financial draft; their fault settings have no effect. The count is regression coverage,
not 36 independent customer samples or distinct injected failures.

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
