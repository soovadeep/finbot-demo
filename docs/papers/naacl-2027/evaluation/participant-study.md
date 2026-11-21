# Interface study protocol, version 1

**Status: prepared; zero participants recruited or evaluated.** The browser walkthrough is
an engineering check. It cannot establish user understanding, task time, preference or impact.

## Question and design

Does the evidence inspector help payment-support engineers identify a rejected claim, its
evidence and the final recovery outcome compared with reading the same exported JSON?

Plan a formative study with 16 consenting participants with payment support, support tooling
or relevant software evaluation experience. This is a feasibility target, not a power-based
sample-size claim. Record relevant experience in broad categories without employer/customer
identifiers. Obtain any required institutional review before recruitment. Participation must
be voluntary; explain that the interface is being evaluated, not the person's job performance.

Prepared materials are in [study-kit](../../../../results/naacl2027/study-kit/): 16 assignment
slots, eight task prompts, eight baseline JSON bundles, checksums and an empty response CSV.
Regenerate them with `python scripts/naacl2027/prepare_study.py`. Assignment slots are not
participant records and do not imply that anyone has participated.
The kit also contains a separate 32-item policy annotation sheet with blank labels. Give
annotators only that CSV and the corpus label rules, keeping the facilitator key and original
expected labels separate. This is an annotation preparation step, not a completed independent
assessment; record disagreements and revise labels transparently after adjudication.

Use eight tasks, one per existing preset. Every participant sees each task once: four in the
interface and four as the corresponding schema-v2 JSON trace. Do not compare a rich interface
with an artificially deprived baseline: JSON participants receive the same question, drafts,
evidence, final answer and mode labels, in their normal searchable text viewer. Both groups
receive the same explanation of field meanings from the reviewer guide.
JSON bundles include scenario titles and descriptions, so the UI's preset hints are also
available in the baseline. The common briefing includes the rejection-code explanations.
The comparison evaluates the complete inspection workflow, not layout alone.

Prepare 16 assignments: the eight cyclic rotations of task order, each with either UI or JSON
first and alternating modes thereafter. Assign participants sequentially to a randomized,
pre-generated list of those assignments (seed 20261119). This balances each task across modes
and order positions. Do not change an assignment based on observed participant skill.

## Procedure

1. Explain synthetic data, intentional faults, sentence-reuse limits and lack of live payments.
2. Obtain consent. Record only participant code and task responses; screen recording is optional
   and requires separate consent. No real support/customer records may be entered.
3. Give the same brief practice exercise in each mode, using a practice trace outside scored tasks.
4. For each assigned task, start timing when its trace/interface is ready. Stop when the participant
   submits their answer or after three minutes. Log timeouts rather than dropping them. Record
   unassisted answers before giving hints; any assistance is marked and reported separately.
5. After all tasks, ask which labels were confusing, whether a passed check guarantees truth,
   and whether record fallback necessarily answers every part of a multi-record question.
6. Allow withdrawal and agree retention/deletion arrangements. Store consent separately from
   task data and keep identifying information outside the repository.

## Tasks and scoring key (facilitator only)

Use the following task prompts without supplying the expected answer in the participant sheet.
Award one point for each of the two specified elements; score 0, 1 or 2. Two independent
raters score the responses, then adjudicate disagreements. Do not use Finbot's verdict as the
sole judge of the participant's explanation.

| Task/preset | Participant prompt | Two required elements |
|---|---|---|
| T1 / correct | Which record supports this answer, and what can a passing check establish? | Correct transaction and its recorded decline; passing configured checks is not proof of general correctness |
| T2 / repair | What was wrong in the first draft, and how did the final answer change? | Approval contradicts recorded decline; repair states decline |
| T3 / fallback | Why was fallback used, and who constructed the final answer? | Invented fee remained after repair; code built and verified a record summary |
| T4 / timeout | Is this payment known to have failed, and what should happen before retry? | Status unknown after processor timeout; check original payment status first |
| T5 / pair | Associate each amount and status with its transaction. | A1B2C3D4: 129.00 USD declined; E5F6G7H8: 54.20 USD approved |
| T6 / binding | Why was the draft rejected when both amounts existed? | Amounts attached to wrong transactions; corrected associations match the retrieved records |
| T7 / refusal | Why was the answer withheld, and why was no record fallback shown? | Unsupported fee survives repair; no eligible transaction summary for the policy question |
| T8 / policy | Why did the citation fail to justify the draft? Give the supporting source sentence. | Draft reverses cannot to can; exact source forbids surcharging debit and prepaid cards |

## Measures and analysis

Primary: per-task explanation score (0–2), plus the count of fully correct tasks (2/2).
Secondary: completion time including timeouts, assistance rate, and qualitative confusion.
Report results by task and mode, with each denominator and missing/withdrawn task counts.
Do not classify a timeout or unanswered question as success. Publish the scoring rubric,
assignment method and adjudication counts. For uncertainty, resample participants as clusters;
do not treat all eight tasks from one person as eight independent participants. Report
paired participant-level mode differences and task-stratified descriptive results; small
formative samples do not establish deployment impact or broad population effects.

Before recruitment, freeze the interface revision, trace hashes, practice material, assignment
list, task wording and analysis. Any pilot-led changes require a new protocol version and
separate pilot/main reporting. Do not include pilot responses in final results silently.

## Recording template

Create a private CSV with these columns (no placeholder participant records are supplied):

```text
participant_code,assignment,task,mode,seconds,timeout,assisted,response,rater_1,rater_2,adjudicated_score,notes
```

Validate that modes are `ui`/`json`, times are 0–180 seconds, scores are integers 0–2, and
each participant/task pair occurs once. Keep missing scores explicit until adjudication.
No study result should be added to the manuscript before real consented responses exist.
