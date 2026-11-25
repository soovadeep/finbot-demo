# Public wording on a frozen scripted demo

Source: PolyAI BANKING77, Casanueva, Temcinas, Gerz, Henderson and Vulić (2020),
*Efficient Intent Detection with Dual Sentence Encoders*.
[Dataset](https://github.com/PolyAI-LDN/task-specific-datasets/tree/57ec275d8078af65b7731c2a98be812d844a6d6b/banking_data),
[paper](https://aclanthology.org/2020.nlp4convai-1.5/).
Public question excerpts and intent labels are **CC BY 4.0** (see SOURCE-LICENSE),
not the repository's MIT code licence. Finbot's synthetic records are adaptations
for this evaluation, not records supplied by BANKING77.

The runtime and selection procedure are frozen in `protocol.json` **before**
downloading/selecting the public test questions. `prior-questions.json` captures
prior repository wording for exact and approximate overlap screening, including
removal of old synthetic reference wrappers. The sampling script is also frozen.
Its source hashes, not a mutable branch name, identify the implementation.

Ten questions per intent (refund not showing up, pending card payment, declined
card payment) are selected by a fixed hash ordering, excluding prior matches.
The original wording is kept unchanged; the adapted question appends an explicit
synthetic record reference. This tests answering after record identification,
not ambiguous-record selection. Each question is paired with two fixed records:

- Refund: pending USD 23.40 refund vs no refund data.
- Pending payment: pending settlement with expected date vs no expected date.
- Decline: declined with code 51 vs declined with no reason.

The payment amount is USD 81.70 throughout. No record is tailored to the wording
of an individual question. Premises may conflict with these records; such cases
remain in the evaluation and are flagged in review. No outcome-based filtering
or replacement is permitted. Dataset intent labels are **not** correctness labels
for generated financial answers.

Commands from the repository root, Python 3.12:

```sh
# Already committed: do not overwrite the freeze.
python scripts/naacl2027/public_wording_study.py freeze
# Download the protocol's exact source_url to a local CSV, then:
python scripts/naacl2027/public_wording_study.py select --input /tmp/banking77-test.csv
# Commit cases.json and selection.json before examining outcomes.
python scripts/naacl2027/public_wording_study.py run
python scripts/naacl2027/public_wording_study.py score --input results/naacl2027/public-wording-v1/labels-ai.json
```

Output files use exclusive creation. Use the committed study revision in a fresh
checkout and a temporary output directory to reproduce existing results without
overwriting their provenance. There are no paid calls in this script. Its
automated counts measure execution contracts; support/completeness require
separate review. AI review is explicitly provisional and not independent human
annotation. The public wording is unused in the checked repository corpus, not
guaranteed unseen by an LLM during pretraining.
