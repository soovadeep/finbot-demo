# NAACL 2027 paper: details beyond the two-page appendix

The demo call limits appendices to two pages, so this file holds the details the paper's appendix
points to. Everything here can be recomputed from the scripts and cached results in this repository.

## Models and settings

- Simulated customers: `claude-haiku-5-5` through the Anthropic API (default sampling, at most 200
  output tokens, no extended thinking) and `meta-llama/llama-3.3-70b-instruct` through OpenRouter
  (temperature 0, at most 80 output tokens).
- Question chooser: `claude-sonnet-5-5` (default sampling, no extended thinking).
- Live writer: `meta-llama/llama-3.3-70b-instruct` through OpenRouter (default sampling, at most 400
  output tokens).
- The clarification step and the answer checks use no model.

## Seeds, caches and scripts

- The benchmark is built with seed 2027 (`scripts/naacl2027/build_ambiguity_set.py`); the
  same-amount copy with `build_same_amount_set.py`. Each episode's persona and misremembered detail
  come from seeds derived from the episode ID, so every selector and simulator meets the same
  customer. The injected-error test (development set) and the 20 reliability draws use seed 2027,
  the held-out set seed 2028.
- Every simulator reply is cached with the prompt that produced it
  (`results/naacl2027/clarification-sim/cache-*.jsonl`, `results/naacl2027/review-studies/`).
- Scripts in `scripts/naacl2027/`: `simulate_customers.py` (main study and same-amount slice),
  `review_studies.py` (sensitivity, chooser, free text), `check_injection.py` (development and
  held-out template tests), `live_writer_run.py` (live writer).
- The live-writer audit is in `results/naacl2027/live-writer/audit.json`.
- Intervals are 95% Wilson score intervals (z = 1.96). The follow-up studies made about 3,500 model
  calls and cost under US$5.

## Simulator prompts

System prompt: *You are role-playing a bank customer in a support chat, for a software test. Stay
in character. Use only what your memory note says. If the note does not tell you the answer, say
you are not sure. Never invent certainty you do not have. Reply with JSON only, no other text.*

Memory notes. Receipt and misremembers (with one detail taken from another candidate): *You have
the details in front of you: a ⟨kind⟩ to ⟨payee⟩ on ⟨date⟩ for ⟨amount⟩.* Vague: *You remember it
was a ⟨kind⟩ to ⟨payee⟩, some time in ⟨month⟩, for roughly ⟨rounded amount⟩. You do not remember
the exact day or the exact amount.*

Turns. Each prompt repeats the opening message and the memory note, then gives the question and its
options (reply `{"choice": ...}`), the short list or full list (reply `{"number": ...}`, 0 for
none), or, in the free-text study, the question alone (*Answer in your own words, in one short
sentence, as a customer would type it in a chat*). The chooser sees the opening message, every
candidate's kind, payee, date and amount, the questions so far with their answers, and the
remaining questions with their options, and replies `{"ask": ...}` or `{"ask": "stop"}`.

## All episodes against the 192 naturally fitting ones (%)

| Strategy, measure | Haiku all 224 | Haiku fitting 192 | Llama all 224 | Llama fitting 192 |
|---|---|---|---|---|
| No questions, top-1 | 13.4 | 14.1 | 13.4 | 14.1 |
| Fixed order 1, top-1 | 18.8 | 18.2 | 19.2 | 18.8 |
| Decision value 1, top-1 | 69.2 | 68.8 | 74.1 | 74.0 |
| Decision value 2, correct | 48.7 | 51.6 | 66.1 | 67.7 |
| Show all 8, correct | 60.3 | 63.0 | 81.2 | 83.3 |

## Sensitivity, chooser and free text

- Reliabilities: within this benchmark, one common reliability for all attributes, from 0.6 to
  0.99, changes no question or outcome. With equal reliabilities the amount question, whose options
  split every candidate, scores highest whenever it is offered; once it is answered no single
  further question can change the most likely record, so the one-step decision value is zero and
  the selector stops. In 20 draws of each attribute's reliability between 0.6 and 0.99, correct
  confirmations stay within 40-50% (Haiku) and 63-67% (Llama), wrong selections within 2.2-2.7% and
  4.0-4.9%. A question cost from 0 to 0.1 cuts mean questions from about 1.5 to 1.1 and moves
  correct rates by at most one point.
- Chooser: Claude Sonnet 5.5 mostly asks for the amount, which identifies a record exactly but is
  what vague customers remember least.
- Free text: the rules read 300 of 475 replies whose option answer was definite and none wrongly,
  abstain on 175 (payees given as account digits, day-first dates, approximate amounts), and read a
  value from 1 of 195 replies whose option answer was "not sure".

## Interface checks

An automated Chromium walkthrough runs 18 acceptance checks on the inspector (every preset scenario,
trace export, keyboard navigation, stale inputs, layouts from 320 to 1440 pixels); all pass. A second
script exercises the conversation page (parsing, questions, unknown replies, corrections, an
unmatched payment, the mobile layout). axe-core 4.10.3 finds no WCAG 2.1 A or AA violations in 14
interface states. No page made an external request or raised a script error. These are feature
checks, not measures of user comprehension.

## Live-writer audit

Every passing live answer with no injected fault (125, on 108 distinct records) was compared with its
stored record: a script matched each stated field value, and the remaining sentences (statuses,
causes, guidance, settlement, refunds, disputes) were read against the record and the policy table.
No answer states a wrong amount, status, code, cause or piece of advice. Nine state the expected
settlement date as the date the payment settled, which the record does not say, and one omits a
completed refund. Per-answer verdicts: `results/naacl2027/live-writer/audit.json`.
