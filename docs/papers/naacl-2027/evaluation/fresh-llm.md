# Live policy answers: quoting the policy instead of refusing

Llama 3.3 70B answers 30 new synthetic cases; the same first draft is judged with and without
a cited-passage fallback. Two labellers judged every distinct answer. The cases are developer
written and small, so read the caveats before quoting a number.

## Design

An earlier 30-case pilot showed one clear weakness: every
policy answer was withheld, because a paraphrase cannot pass the extractive policy check. We
added one fallback. When a policy-only answer and
its repair both fail, code quotes the best retrieved passage (and any passage scoring within
80% of it) verbatim, with its source and date. Turns that touched a record never use it.

The test was run on 30 new cases (`data/naacl2027/fresh-llm-v2/cases.json`, 10 policy, 2 with
no document) frozen before any call. Three configurations judged **the same first Llama 3.3 70B
draft** in every case (30/30), through a response cache keyed by the exact request:

| Configuration | Released, correct | Released, wrong | Withheld |
|---|---|---|---|
| before (no policy fallback) | 17 | 0 | 13 (10 policy) |
| after (policy fallback) | 26 | 0 | 4 |
| after + LLM evidence review | 25 | 0 | 5 |

Labels: two labellers judged all 43 distinct answers. The AI assistant labelled first
(`labels.json`, not blind); Apurba Bose, a co-author who wrote no cases, then labelled blind to
gate outcomes and to those labels (`labels-second.json`). They agree on 41 of 43 (95%). Each
marks one draft wrong, and both of those drafts were blocked, so the table is identical under
either set: the AI assistant flags a draft giving the expected settlement date as the actual one
(`rec-actual-missing`); Apurba flags a draft saying the *merchant* should not retry a code 05
decline, where the policy names no one (`pol-05-fix`). Kappa is not informative here because
almost every answer is correct.

Under both label sets, 29 of 30 drafts are correct and deterministic checks still block 16 of
them; the fallback now answers most of them by quotation. Of the 4 remaining refusals, 2 are
correct (questions the knowledge base does not cover), 1 is a retrieval miss and 1 is a mixed
record-and-policy question. The review again adds no benefit.

```sh
# v2 replays only on the code it was frozen with; see frozen-studies.md for the tagged v3 replay
python scripts/naacl2027/paired_gate_study.py replay   # offline, from responses.json
python scripts/naacl2027/paired_gate_study.py score
```

### Re-run on the final runtime (fresh-llm-v3)

Later commits changed the policy checks (requested-code coverage for quotes, context
budgets), so the v2 freeze no longer matches the code and `replay` stops at its hash check.
We therefore re-froze the same 30 cases as `data/naacl2027/fresh-llm-v3/` and ran the study
again, reusing v2's saved responses for byte-identical requests (`--seed`). Only 15 requests
were new (370 replayed). All 43 distinct answers are byte-identical to v2 answers, so both
label sets carry over unchanged (no relabelling). Counts are identical for `before` and
`after` (17 → 26 released, 13 → 4 withheld, none wrong under either labeller); `after_review`
now matches `after` (one comparison case is repaired instead of withheld).

```sh
python scripts/naacl2027/paired_gate_study.py score --version fresh-llm-v3   # runs on main
```

`replay` checks the runtime against the freeze, so on `main` (which has later fixes) it
refuses by design. Run it at the tag `fresh-llm-v3-freeze` (commit `75a720f`), where it
gives 90/90 identical answers. See [frozen-studies.md](frozen-studies.md).
