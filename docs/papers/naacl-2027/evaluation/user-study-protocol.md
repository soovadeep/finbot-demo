# Planned usability pilot: clarification versus showing all records

**Status: protocol and collection interface prepared; no participants recruited or results collected.**
This pilot tests the current four-record demo. It cannot substantiate benefits for eight-record
accounts, voice interfaces, real customers, or production financial accuracy.

## Question and design

Does the clarification interface reduce effort or decision time while preserving identification
success relative to showing all four records immediately? A useful outcome may instead be evidence
that the simple list is preferable. Predeclare the design before inspecting participant results.

Use a between-participant design, one primary task per person, to avoid learning the fixed records.
Two arms use the same records, attribute labels, confirmation buttons and scripted answer controller:
`clarify` shows the deployed question and matching/other-record flow; `full_list` immediately shows
all records, with no clarification questions. The research interface hides the demo inspector and
scenario answer keys. Two task notes identify a transfer or a card payment using type and recipient
while leaving the date unknown. Participants may leave a task unresolved or correct a selection.
This isolates the identification interface, not a live model's generation ability.

Generate balanced, randomly ordered assignment slots:

```sh
python scripts/naacl2027/user_study.py allocate --participants 24 --out assignments.json
python -m finbot.demo
```

The 24 slots (six per arm/task cell) are an **exploratory recruitment plan**, not a power calculation
or evidence of participation. Decide a feasible sample and stopping rule in advance. Assign slots
in order after consent; do not let participants choose the arm. Keep participant exports, assignment
records and consent records outside this public repository. Use opaque P-codes, not names or emails.
Obtain the ethics review/consent appropriate to the recruiting institution before collection.

Open each assignment's `/pilot?...` path on the local server. Default mode is rehearsal; the
researcher explicitly selects participant mode only for consented participants. Use the same device
class and viewport for both arms. If studying a small screen, fix and report its dimensions for
everyone; do not pool desktop and mobile without stratification. The current pilot has no voice arm.

## Procedure and measurements

1. Explain voluntary participation and the fictional task. Avoid coaching on a specific record.
2. Start the assigned interface. Its task note appears and the timer starts together. Participants
   use only that note; unavailable details should be answered as unsure.
3. The participant identifies a record or leaves unresolved, and rates effort on a 1–7 scale.
   They can revise their selection before finishing. The final choice defines identification success.
4. Download the session and offer it to the researcher. No export is sent automatically or persisted
   on the server; closing/reloading abandons the local session. Network failure or reload interrupts
   the task: record that fact separately, rather than silently rerunning a participant.

Primary outcomes: correct, wrong and unresolved identification counts; decision time to the final
choice; self-reported effort. Also report question count and selection changes. Timing includes
reading the task note; total elapsed time also includes the effort question. Report time for all
completed tasks and separately for correct tasks, so fast failures do not look like an improvement.
Log withdrawals/technical failures and reasons in the recruitment flow; downloaded files alone
cannot reveal missing participants. Predeclare exclusions for interruptions and protocol violations.

## Analysis and reporting

```sh
python scripts/naacl2027/user_study.py analyze collected/*.json --out pilot-summary.json
```

The analyzer rejects rehearsal data by default, duplicate participants, mixed provenance, invalid
timing, missing consent and selections inconsistent with replayed events. `--allow-rehearsal` is
for testing collection infrastructure only. The mode flag is not independent proof of recruitment;
the researcher must reconcile each file against consent and randomized assignment records.

Report denominators and arm/task cells, medians for decision time, effort and error/unresolved counts.
For this small pilot use descriptive findings; do not infer equivalence or non-inferiority from
overlapping intervals or a nonsignificant test. A powered follow-up needs a prespecified meaningful
effect size and sample calculation. Do not silently drop unresolved tasks or switch metrics after
seeing which favors the system.

The exported pilot does not contain independent answer-quality judgments. A separate blinded audit
must assess support and completeness before reporting end-to-end financial-answer success. Human
observations must be added to the paper only after collection, with actual participant counts and
limitations. The existing LLM-simulator study remains a separate component evaluation.
