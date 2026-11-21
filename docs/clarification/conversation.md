# Message-driven clarification demo (v2)

Notation, worked probabilities, question-selection equations and the research plan:
[clarification design](design.md).

Open <http://127.0.0.1:8766/study> after starting `python -m finbot.demo --port 8766`.
This replaces the old quiz-like landing page with a conversation. Send the sample
message, edit it first, or choose another starting situation. No study code or consent
form is required for this local demonstration. No participant data are collected.

## What changed

The previous screen supplied the complete task and asked the participant to repeat
its details. That exercised collection and calibration plumbing, but did not establish
whether clarification helps with realistic incomplete or unreliable customer messages.
The original version remains at `/study/probes` for its versioned export/calibration
workflow, with a warning identifying that limitation. It is not the default demo.

The new conversation keeps three sources distinct:

1. **Optional private role-play notes:** a person's imperfect recollection or receipt.
   They are collapsed by default and are not sent to the conversation engine.
2. **Customer messages and authorized records:** the only inputs to interpretation,
   belief updates, question selection and record confirmation.
3. **Preset evaluator reference:** revealed only on request after confirmation or
   leaving unresolved. It never affects question choice, beliefs or the selected record.

Changing the private notes or intended reference without changing the customer
messages leaves the assistant's output unchanged; a regression test checks this.
The engine has no scenario/target argument. The outer demo controller chooses which
private notes and preset reference the UI can display.

## Try the five paths

- **Vague opening:** send “My $200 payment hasn't arrived.” Finbot asks the payment
  type. “Bank transfer” narrows the working matches to two; it then asks the date.
  “November 15” produces a single suggestion. Confirmation retrieves its pending status.
- **Details already supplied:** send the full transfer/recipient/date message.
  Finbot extracts all three and asks **zero** clarification questions. Confirmation
  still precedes retrieval and financial claims.
- **Uncertain recollection:** “I think it was a bank transfer. I don't remember the
  date.” keeps card possibilities. Finbot asks about the recipient instead of repeating
  payment type or requesting the unavailable date. Reply “Willow Repairs”: two records
  still fit the explicit details. The system may remain unresolved, which is appropriate
  when the customer cannot distinguish those records.
- **Correction:** initially send “bank transfer to Willow Repairs”; optionally confirm
  that record. Then send “Actually, it was a card payment to Willow Repairs on November
  16.” The new detail replaces the old one. Any previous answer is marked superseded,
  current evidence is cleared, and the newly matching record needs confirmation.
- **Missing payment:** the Pine Pharmacy message matches none of the records. The
  assistant says so. Choose “I cannot identify it / none of these” to end unresolved.

The customer can leave unresolved before answering a question, add multiple details
in one message, correct an earlier detail, or explicitly choose another authorized
record. Corrections do not grant access outside the fixed fictional account.

## Interpretation and mathematical limits

This is an **offline rule-based parser**, not live LLM interpretation. It recognizes
card/transfer, known recipient names or a simple “to/at NAME” phrase, absolute ISO
dates or November dates, `$`/USD/EUR/GBP amounts, and transaction references. November
dates without a year use the fictional account year 2026. Relative dates, broad
paraphrases, and arbitrary banking questions are not generally understood. Unmapped
replies prompt for supported details instead of being scored as “I'm not sure”.

The working view exposes each interpreted detail. A hedge such as “I think” labels
details in its simple sentence or “but” clause tentative. A trailing “but I'm not
sure” qualifies the preceding statement. This supports simple mixed-certainty inputs;
complex grammar and hedge scope are not modeled generally. Explicit negation or
multiple alternatives are marked unresolved instead of guessed as positive claims.
Unfamiliar recipients, amounts and currencies are retained so they cause a mismatch
instead of silently being dropped. These rules still require broader adversarial
validation before use with real customer language.

Two mechanisms are distinct:

- **Working matches** are records matching the latest explicitly supplied details.
  They represent the customer's current reference, not verified intent or facts.
  One match is shown for confirmation immediately, avoiding redundant questions.
- **Beliefs** apply Bayes updates over the authorized records using the latest
  observation for each supported attribute. Repeated statements are counted once.
  Supplied kind/merchant/date use the existing assumed response models; tentative
  recollections use an assumed accuracy of 0.65 conditional on a definite reply.
  This 65% is a demonstration setting, not a measured reliability estimate.

Information gain ranks missing, available, unasked attributes among working matches,
using their renormalized beliefs. Already supplied or unavailable attributes are
excluded. The whole conversation has a two-question budget and at most twelve events;
corrections can still replace details after that budget. An unrecognized reply does
not spend another question. A pending useful question remains pending if the user
merely repeats an unrelated detail. Confidence never releases a financial answer.

On confirmation, the existing scripted writer and actual Finbot verification pipeline
run in a fresh financial session. Previous evidence is not reused after a correction.
Passing the financial checks can still mean a factual answer about the wrong record.

## Evidence and next study

Trace exports identify `finbot-conversation-demo-v2`, `human_study_data: false`, assumed
response parameters, actual customer messages/events and interpreted details. The
v1 participant-fitting script rejects these exports. The preset reference applies
only to its authored role-play; editing a message can legitimately change the task,
so a match with that reference is **not** a participant accuracy metric.

This version fixes the interaction, not the empirical evidence gap. Before collecting
new study data, define a v2 participant protocol with separately assigned target
records, realistic partial/mistaken cues, participant-written messages, independently
annotated interpretation errors, and new disjoint development/evaluation materials.
Freeze the parser/LLM adapter, response model, selector and study endpoints together.
The exposed belief inspector belongs to the demonstration; a blinded participant
condition should not show probabilities or reference outcomes during the task.

Tests:

```sh
python -m unittest discover -s tests -p 'test_clarification_conversation.py'
node scripts/check_conversation_ui.cjs
```

The browser script uses only fictional messages. `FINBOT_UI_OUTPUT` can capture the
conversation and supplied-details screenshots. The LaTeX paper is unchanged.
