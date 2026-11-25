# Shared absence checks and an external-wording evaluation

This document preserves the first public-wording study. A subsequent shared coverage
fix and prospective paired evaluation on different questions are documented in
[support-coverage.md](support-coverage.md); the original results below remain unchanged.

## What changed

`finbot/missing_information.py` gives evidence checking and requested-field coverage
one interpretation of missing-information statements. The latest successful, scoped
record must support the stated absence. Known values, including zero, cannot be
denied; a later failed lookup cannot establish absence. Missing refund data does not
establish that no refund occurred. Mixed sentences do not inherit an exemption from
an opening absence phrase. The grammar remains finite English, not an LLM verifier.

Eight focused tests exercise missing fields, contradictory known values, failed and
superseded lookups, multiple record IDs, mixed assertions and questions. The full
suite passes 274 tests after adding the external-study integrity tests.

`results/naacl2027/missing-information-development.json` rechecks cached live text:
three of four correct missing-refund drafts now pass. One still fails because
“Let me check again for the refund details” triggers the broad refund-mention rule.
The original 30-case paired study still has 16/29 correct drafts rejected and its
one incorrect draft rejected. Strict policy paraphrase checks are unchanged.
This is **development replay**, not fresh generation or a rerun of model trajectories.
All earlier frozen studies remain byte-for-byte unchanged.

## Public questions, frozen before selection

The protocol and sampler were committed at `86187c1`, after the runtime fix
`3133085`, before downloading/selecting BANKING77 test questions. The 30 selected
questions and their paired records were committed at `4030337`, before running
the demo on them. Exact runtime/evaluator hashes, upstream commit, CSV digest,
source row numbers, original text, adaptations and selection audit are committed
under `data/naacl2027/public-wording-v1/`.

The source is PolyAI BANKING77, CC BY 4.0, attributed to Casanueva et al. (2020).
The original test split has 3,080 questions. The sampler examines 120 questions
in three intents and flags 29 exact/near overlaps against prior repository or
selected wording. It selects ten remaining questions per intent using a fixed
hash ordering. Normalization removes old added reference wrappers, case,
punctuation and numeric variation; approximate matching uses character similarity
and token overlap. This does not guarantee semantic non-overlap or lack of
pretraining exposure. It establishes unused wording relative to the archived
repository corpus and screening procedure.

Every question retains its source wording and adds a synthetic transaction ID.
Each runs once with populated details and once with the relevant detail missing.
Records follow fixed category-level schemas, not per-question tailoring. There is
no outcome-based selection. This is the inspector's **post-identification** path;
it does not evaluate clarification or long-conversation reasoning.

## Results and review provenance

All 60 runs perform the current-record lookup. The scripted writer releases 57
answers; three missing-decline-reason cases end in refusal. No provider calls or
inference charges occur. The implementing Codex AI assistant reviews every final
answer separately for support and completeness, using the frozen rubric. It had
seen aggregate execution counts, so the review is **unblinded, provisional AI
review**, not independent human annotation. No extra participant is required.

| Question family | Runs | Released | Complete under AI review |
|---|---:|---:|---:|
| Refund not showing up | 20 | 20 | 0 |
| Pending card payment | 20 | 20 | 7 |
| Declined card payment | 20 | 17 | 20 |
| Total | 60 | 57 | 27 |

The 27 complete outcomes comprise **24 released answers and three appropriate
refusals** where the requested decline cause is absent. The refusal's request for
an already supplied reference is still a usability flaw. All assertions were
judged supported by the synthetic evidence, including recorded retry guidance;
that is distinct from answering the question. The pairing and repeated schemas
mean these are not 60 independent observations. Labels, rationales and hashes
are in `labels-ai.json`, with computed counts in `score-ai.json`.

Example: the original question “Where is my refund? I have been checking my
account all day.” is paired with a pending USD 23.40 refund on a USD 81.70 payment.
The released answer gives the payment and refund amounts but omits **pending**.
With no refund data, it gives only the payment amount and never says refund
information is missing. Both are supported but incomplete. An authentic, passing
summary is therefore not counted as success.

One question says the customer has sufficient funds, whereas the populated
synthetic record reports decline code 51. That premise mismatch remains flagged
in the results; it was not replaced. Status statements and indirect complaints
require judgment, so completeness counts should not be treated as a validated
customer accuracy estimate.

## Reproduction and next work

The sampler/evaluator refuses changed runtime or case hashes and refuses to
overwrite results. Use the committed study code for reproduction. For an offline
replay without changing saved outputs:

```sh
python - <<'PY'
from pathlib import Path
from scripts.naacl2027 import public_wording_study as study
study.OUT = Path('/tmp/finbot-public-wording-replay')  # must not already contain outputs
study.run()
PY
```

The subsequent shared coverage improvement addresses **refund status, missing refund
information, pending-status explanations and explicit limits on missing causes**
across draft, repair and fallback. These inspected cases are development
cases. Keep this first report, and reserve different external wording for a future
prospective test. More regex synonyms alone will not establish semantic adequacy.

Fresh live answers on these selected questions remain **not run**: this checkout
has no model key. A credential-equipped agent can use the same questions/records,
freeze a separate writer configuration and spending-controlled protocol, and
record raw responses before labelling. It must not overwrite this scripted study,
reuse a completed study's spending journal or claim these outputs were generated
by an LLM. No new paid run is necessary to reproduce the results above.
