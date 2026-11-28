# Replaying the frozen studies

Two studies were frozen against the exact code that produced them. Each study's protocol
records the SHA-256 of every runtime and evaluator file. `replay` and `run` refuse to start
when the checkout differs, so a saved result can't quietly turn into a result from different
code. The release snapshot on `main` has received later fixes, so these commands have to run
at the tagged commits below. On `main`, the refusal is expected.

| Study | Tag | Commit | What it checks |
|---|---|---|---|
| Live policy answers, re-run (`fresh-llm-v3`) | `fresh-llm-v3-freeze` | `75a720f` | Offline replay of saved Llama responses: 90/90 answers identical |
| Public questions, post-fix arm (`public-wording-v2`) | `public-wording-v2-freeze` | `d1a8afc` | 60/60 post-fix answers identical |
| Public questions, pre-fix arm | `public-wording-v2-baseline` | `59a1d2f` | Archived automatically by the study; 60/60 pre-fix answers identical |

```sh
# Tags, if present: git fetch origin --tags. The full commit IDs below also work without them.
git fetch origin 75a720f6a7ab91f3613b87f02f71fd12f28092ae d1a8afc9aff926c580a909f35e1d718a11ad16a0 \
                 59a1d2f384435a282d66dd87bc0ec936caa607d9
git worktree add ../finbot-v3 75a720f6a7ab91f3613b87f02f71fd12f28092ae
cd ../finbot-v3
mv results/naacl2027/fresh-llm-v3/replay.json /tmp/replay.saved.json   # replay never overwrites
python scripts/naacl2027/paired_gate_study.py replay --version fresh-llm-v3
python scripts/naacl2027/paired_gate_study.py score --version fresh-llm-v3
cd - && git worktree remove --force ../finbot-v3

git worktree add ../finbot-pw2 d1a8afc9aff926c580a909f35e1d718a11ad16a0
cd ../finbot-pw2
mkdir -p /tmp/pw2 && mv results/naacl2027/public-wording-v2/{baseline-runs,runs}.json /tmp/pw2/
python scripts/naacl2027/support_coverage_study.py run   # pre-fix arm comes from git archive of 59a1d2f
cd - && git worktree remove --force ../finbot-pw2
```

After `support_coverage_study.py run` writes both run files, it stops with `FileExistsError`
on `review-form.json`. That is expected: the review form is part of the frozen record, and the
script never overwrites it. Compare the regenerated `baseline-runs.json` and `runs.json` with
the saved copies. Only timing fields differ.

`score` (for both studies) and every other command in the [evaluation guide](README.md) run
on `main`. The tests (`python -m unittest discover -s tests`) check that the current runtime still
behaves as reported, so they validate the current code. The tagged replays reproduce the
historical results.
