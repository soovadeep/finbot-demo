# Structured clarification pilot

The original `/study/probes` page collects coded, structured replies and exports a completed
session. It is infrastructure for a pilot, **not a completed human study**. The
default rehearsal uses assumed reply probabilities and fictional tasks. The new
[`/study` conversation demo](conversation.md) uses customer messages
and separates private role-play notes from assistant inputs. These v1 probes remain
engineering checks; they do not establish realistic clarification performance. The collector makes
no paid model calls. The existing `/clarification` inspector remains available.

## Try the UI

From a Python environment with the repository requirements installed:

```sh
python -m finbot.demo --port 8766
```

Open <http://127.0.0.1:8766/study/probes>. Keep **Rehearsal**, **Evaluation tasks**, and
code **P001**. Start, answer the questions, select a record (or leave unresolved),
and save each of the four tasks. A record selection can be corrected before saving.
The researcher view appears only after all tasks; download its JSON to retain it.
There is no server database, browser storage, or background upload. A refresh loses
progress. Exports contain the participant code, choices, task order, question wording,
option order, assumptions/model ID, corrections, belief traces and task outcomes.
Do not enter personal or real financial data.

Expected rehearsal walkthrough with the default assumed model:

1. **Four crossed records.** The task refers to the bank transfer to Willow Repairs
   on November 15. Answer **Bank transfer**, then **2026-11-15**. With a uniform
   prior, the first reply changes beliefs from 25% each to 5%, 45%, 5%, 45%.
   The date question then gives 8.5%, **76.5%**, 1.5%, 13.5%. Confirm
   `txn_EMIX0001`. A fresh retrieval produces its recorded **pending** status.
   The posterior did not authorize or select the record; the participant did.
2. **Repeated merchant.** Select November 17 and confirm `txn_EREP0001`.
3. **Missing target.** The Pine Pharmacy payment is absent. Use **I'm not sure**
   when the offered details do not fit, then **No matching record / I cannot
   distinguish them**. Expect no financial answer.
4. **Identical visible entries.** There is no discriminating question. Leave
   unresolved because the supplied details do not identify one exact reference.

The review shows expected versus observed selections and each reply's posterior.
The last two outcomes count as appropriate unresolved cases, not successful record
selections. Deliberately confirming a wrong record demonstrates why a passing
financial verifier is a separate metric from identifying the intended record.

## Collect development responses

The researcher first explains the task, voluntary participation, export handling,
retention period and withdrawal procedure. The on-screen checkbox records agreement
to save coded choices; it is not a complete institution-approved consent process.
No participants have been recruited by this implementation.

Assign a unique code such as P101; do not use names/emails. Choose **Participant**
and **Development probes**, record agreement, and run the six tasks. Each question
type (payment kind, merchant, date) has two tasks, covering both target options.
Only that attribute differs within each pair, so all templates are sampled instead
of fitting solely from the questions an adaptive selector happened to prefer.
The assigned order is reproducible and varies by participant code. Responses are
buttons, including an explicit unknown choice; no free-text interpretation is claimed.

The task card stays visible. This measures task comprehension and structured-choice
behavior under the pilot protocol, **not real-world memory reliability**. Estimates
must not be described as customer response accuracy. To study unreliable memory or
language, add independently reviewed ambiguous descriptions, partial/incorrect cues,
delays, free-text interpretation labels, and broader naturalistic tasks in a new
protocol version. Freeze those materials before collecting final evaluation data.

Save downloaded exports in a private directory. `.study/` is Git-ignored; do not
commit exports or fitted artifacts elsewhere. Keep the participant-code register
separate and private. The app cannot detect the same person returning with a new code.

## Fit and freeze

```sh
python scripts/analyze_clarification_study.py fit .study/development/*.json --output .study/frozen-v1.json
```

For each question type, counts classify observed replies as correct, incorrect, or
unknown relative to the assigned task target. Let C, W and U be those counts:

- Raw definite-reply accuracy: C/(C+W), undefined if no definite replies.
- Raw unknown rate: U/(C+W+U).
- Frozen accuracy: (C+1)/(C+W+2), a Beta(1,1) posterior mean.
- Frozen unknown rate: (U+1)/(C+W+U+2), also a Beta(1,1) posterior mean.

Counts and raw estimates accompany the smoothed parameters. Small samples do not
establish reliability. No precision/power claim is made. Repeated observations from
the same person are dependent; these counts are not independent participant counts.
The model still assumes symmetric incorrect options, unknown replies independent of
target, and independent successive replies. Binary development estimates are
extrapolated to multiclass questions; this requires validation and may be wrong.

The analysis replays the exported events against server-owned tasks. It ignores
client outcome labels, rejects incomplete or duplicate participant sessions, phase
mixing, and rehearsal data. The artifact records development participants, families,
protocol, probabilities, selector settings, source digest and a content hash. Output paths must be new:
the command refuses to overwrite an earlier freeze. A hash detects accidental changes;
it is not a signed audit record. Human provenance and consent remain attestations.

`--allow-rehearsal` exists for infrastructure tests only. Outputs retain rehearsal
provenance and cannot enable participant evaluation. Never relabel simulated replies
as participant data. Rehearsal uses assumed parameters when a participant model is
loaded, keeping that model out of the public rehearsal.

## Evaluate with new participants

Restart the local server with the frozen development artifact:

```sh
python -m finbot.demo --port 8766 --study-model .study/frozen-v1.json
```

Use **Participant → Evaluation tasks** with new participant codes. The server
refuses evaluation without a participant-derived model and refuses any code used
for development. Four evaluation structures differ from the single-feature binary
development tasks: crossed attributes, three repeated dates, absent target, and
indistinguishable metadata. These are authored pilot structures, **not a representative
held-out benchmark**, and have now been inspected during development of the software.
For publishable held-out evidence, prepare additional unseen families before freezing
a final study protocol; do not tune on evaluation outcomes.

Participants are reproducibly allocated by code hash to no questions, fixed order,
information gain, or decision value. Researchers must assign codes before observing
behavior and not choose codes to change arms. This is not guaranteed balanced
allocation; inspect arm sizes and plan participant counts in advance. The question
budget is two (zero in the no-question baseline), with the same explicit confirmation
rule and unchanged record display order. The next question is recomputed after each
reply. Study participants answer the pending question before selecting a record;
this constraint differs from the more permissive inspector and limits generalization.

```sh
python scripts/analyze_clarification_study.py evaluate .study/evaluation/*.json \
  --model .study/frozen-v1.json --output .study/evaluation-v1.json
```

The report groups descriptive counts by arm: participants, tasks, questions,
corrections, correct/wrong selections, unresolved identifiable targets, and
appropriate unresolved cases. Correct-selection accuracy should use only
`identified_target_tasks` as its denominator; report missing/indistinguishable cases
separately. Evaluation refuses model mismatches and development participant overlap.
It does not test significance, measure duration or API cost, or perform independent
answer-factuality annotation. A publishable comparison needs sufficient participants,
participant-level or cluster-aware uncertainty estimates, prespecified endpoints,
and blinded assessment of answers. A benefit from information gain is a hypothesis,
not the expected result of this pilot.

## Verification

```sh
python -m unittest discover -s tests -p 'test_clarification*.py'
node scripts/check_study_ui.cjs
```

The browser check needs Playwright and the local server. Optional `FINBOT_CHROME`
selects installed Chrome; `FINBOT_UI_OUTPUT` selects a screenshot/export directory.
All automated sessions are marked **rehearsal**. They exercise the workflow, not
human behavior. The paper source is unchanged.
