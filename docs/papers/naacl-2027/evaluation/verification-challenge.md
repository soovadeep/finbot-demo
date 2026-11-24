# Matched error challenge and agent context tests

The live v2 study has only one incorrect initial draft under each labeller's judgments.
It measures recovery from unnecessary rejections more convincingly than varied error
detection. This separate **authored stress test** deliberately supplies errors; its error
frequency must not be presented as a live writer's error rate.

## Protocol and scope

`data/naacl2027/verification-challenge-v1/cases.json` contains 48 matched pairs: four
instances of each of 12 error families, for 96 draft checks. Each pair uses the same
question and evidence. The correct and corrupted answers and their support/completeness
expectations were written before evaluation. Runtime and input hashes were then frozen
in `protocol.json`. The test uses the actual deterministic verifier chain plus comparison,
requested-field and extractive policy checks, with no model calls or paid services.

These are AI-assisted developer-authored examples, not independent held-out customer
questions. Some policy instances share wording with different source IDs; instances
are not independent observations. Expected labels follow explicit fields and mutations,
not gate verdicts. `results/naacl2027/verification-challenge-v1/review-form.json` provides
91 distinct question/evidence/answer items, deduplicated and ordered by content hash, with
blank judgments and no mutation names, side labels or verifier decisions. A blind co-author
(Apurba Bose) labelled all 91 on 2026-11-24 (`labels-second.json`). She agrees with the
construction labels on 79/91 (support 84/91, completeness 84/91). All 12 differences are
corrupted answers she accepted: reversed policy rules, dropped exceptions, off-code quotes,
swapped payment/refund roles and a superseded refund (`label-agreement.json`). She rejected
no clean answer. Do not substitute these expectations for the two labellers'
judgments on the separate live v2 study.

## Results on the frozen implementation

| Error family | Pairs | Correct controls blocked | Corrupted drafts blocked |
|---|---:|---:|---:|
| Refund vs payment role | 4 | 1 | 4 |
| Payment vs refund role | 4 | 0 | 4 |
| Expected vs actual settlement date | 4 | 0 | 4 |
| Requested refund information omitted | 4 | 0 | 4 |
| Amount swapped between records | 4 | 0 | 4 |
| Currency swapped between records | 4 | 0 | 4 |
| Refund invented when no refund is recorded | 4 | 0 | 4 |
| Superseded refund value from an older lookup | 4 | 0 | 4 |
| Policy prohibition reversed | 4 | 0 | 4 |
| Policy exception omitted | 4 | 0 | 4 |
| Correct policy paraphrase vs reversed paraphrase | 4 | 4 | 4 |
| Authentic quote answering a different decline code | 4 | 0 | 0 |
| **Total** | **48** | **5** | **44** |

Raw corrupted-draft rejection is 44/48 (91.7%); correct-control rejection is 5/48 (10.4%).
Only 43 pairs have accepted clean controls. Among those, the corruption causes 39/43
new rejections (90.7%). The other five blocked corruptions were already blocked in their
correct form and are **not** counted as mutation-triggered detections.

Four incomplete answers pass: asked about code 51, the draft quotes an authentic code 54
passage. Its quotation and citation are valid but it does not answer the question. This
exposes a relevance/coverage gap; source fidelity alone is insufficient. No unsupported
corruption passes this particular set, which does not establish general semantic safety.
The five false rejections are four faithful policy paraphrases and one refund paraphrase.
The test measures initial-draft decisions, not repair, fallback or complete conversations.

## Replay

Use the branch/revision containing this report. Source hashes intentionally prevent a
changed runtime from silently being called the same frozen experiment.

```sh
python scripts/naacl2027/verification_challenge.py run --output /tmp/finbot-challenge-replay.json
python -m unittest discover -s tests -p test_verification_challenge.py -v
```

The output path must not already exist. `prepare` and `freeze` were used before the first
run; they refuse to overwrite the committed cases or protocol. Changing the verifier
after inspecting these cases makes subsequent results development results, requiring a
new version and fresh cases for another prospective test.

## Post-fix development replay

The original frozen results above are retained. The revised extractive/strict verifier
requires coverage of explicit requested code identifiers by the actual quoted passages,
using their text or section headings. It supports numeric and alphanumeric identifiers
and multi-code requests; a shared citation URL alone cannot supply coverage. The
question-aware fallback ranks passages within each requested code and abstains when
one is unavailable. A later unsuccessful search supersedes earlier fallback candidates.

`results/naacl2027/policy-relevance-development/report.json` rechecks the **same, already
inspected 48 pairs**: all 48 corruptions are blocked, the same five clean controls are
blocked, and all 43 eligible pairs now produce a new rejection. The four authentic
off-topic quotations are blocked without rejecting their four correct controls.
This is a regression result after fixing a known failure, **not unseen generalisation**.
The identifier check does not establish free-text semantic applicability or customer
eligibility; faithful paraphrases remain restricted in extractive mode.

```sh
python scripts/naacl2027/verification_challenge.py replay-development --output /tmp/policy-development.json
python -m unittest discover -s tests -p test_policy_relevance.py -v
```

## Context and agent design

[Agent design](../../../agent-design.md) documents prompt admission, state rollover,
record refresh, tool loops, repair, deadlines and failover. Nine offline context/memory
contracts pass. They test the runtime's behavior, including stopping before a request that
exceeds the configured budget, not live long-conversation reasoning accuracy. The token
budget uses a conservative byte-based estimate with output headroom; it is not an exact
provider tokenizer. Older frozen LLM studies retain their original runtime and results.
