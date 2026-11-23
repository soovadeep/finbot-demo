# Evaluation scope and reproduction

The released evaluations measure different things. Do not describe component results as measured
performance of the hosted conversation, or engineering checks as a human study.

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
The wrong-confirmation case deliberately demonstrates a remaining failure boundary.

## Answer verification

`check_injection.py` measures rejection of templated drafts against stored evidence; the live-writer
audit concerns saved Llama answers about card payments. Neither measures full customer conversations.
Report false rejections alongside corrupted-draft rejections. Do not use a passing gate as its own
independent factuality label.

## Planned human pilot

`http://127.0.0.1:8765/pilot` provides an export-only comparison of the current four-record
clarification UI and a full-list baseline. See [the protocol](user-study-protocol.md) for assignment,
consent, timing and analysis. The default is rehearsal; no participant results are bundled.
Run `python scripts/naacl2027/user_study.py --help` for allocation and analysis commands.
