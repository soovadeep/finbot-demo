# Prospective support-coverage comparison

This is a new question set after the public-v1 failures became development cases.
Runtime, sampler, rubric and baseline revision are frozen before selection. The
sampler uses the official BANKING77 **train** split at the pinned upstream commit,
with a new seed, ten questions each for refunds, pending payments and declines,
and the same exact/near overlap screening against prior repository questions.
This includes all public-v1 questions. Selection does not depend on outputs.

Source/attribution: PolyAI BANKING77, Casanueva et al. (2020),
[Efficient Intent Detection with Dual Sentence Encoders](https://aclanthology.org/2020.nlp4convai-1.5/).
Question excerpts are CC BY 4.0; see [source licence](../public-wording-v1/SOURCE-LICENSE).
The code licence does not replace the dataset licence. Original question text,
CSV row numbers and hash are retained. Appended IDs and paired populated/missing
financial records are synthetic Finbot adaptations. Unanswerable requests and
premise mismatches remain in the sample. No model is trained on these rows.

Each of 30 questions runs against two record conditions, through both the pinned
pre-fix inspector (`59a1d2f`) and frozen current inspector: **120 scripted runs**.
The baseline is executed in an isolated temporary archive with provider settings
disabled. Current runs use the actual demo path with `live=False`. No credentials,
model calls or paid judge are required. Separate matched status controls test
schema consistency; they do not provide correctness labels for final answers.

The review rubric is unchanged from public-v1. Support and completeness are
judged separately from gate acceptance. Implementing-agent AI review is provisional
and unblinded; an additional human reviewer is not required and is not invented.
Question pairs and repeated schemas are dependent observations. These results do
not establish customer performance, live-writer generalisation, or general policy
understanding. The wording is unused in the archived repository corpus, not
guaranteed unseen in language-model pretraining.

```sh
python scripts/naacl2027/support_coverage_study.py freeze
# Download the protocol's source_url without changing it, then:
python scripts/naacl2027/support_coverage_study.py select --input /tmp/banking77-train.csv
# Commit the selected cases before running:
python scripts/naacl2027/support_coverage_study.py run
python scripts/naacl2027/support_coverage_study.py score --input results/naacl2027/public-wording-v2/labels-ai.json
```

Files are created exclusively; never overwrite the first outputs or silently
change a protocol. Reproduce using the matching study revision and override
`study.OUT` to an empty temporary directory before `configure()` and `run()`.
The baseline requires local Git history for its pinned revision.
