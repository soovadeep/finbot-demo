# Exploratory policy cases, version 1

`policy_cases.jsonl` contains 32 synthetic candidate-answer cases written before the first
benchmark run on November 19, 2026. Each includes its sources, candidate, KB-lookup flag,
release-support label and rationale. Labels were authored with Codex assistance, not by
independent annotators. This is a purposive diagnostic set, **not a held-out benchmark**.

The labels ask whether the answer is supported by its cited evidence, preserving policy
conditions and context. An absent or wrongly scoped citation is a release-support failure
even if the sentence occurs elsewhere in retrieved text. Valid paraphrases are labelled
supported. Source sentences used outside their stated context are labelled unsupported.

There are eight exact supported answers, eight supported paraphrases, eight contradictions,
four citation failures, two context omissions and two cases without a KB lookup. All policies
are fictional. No real financial record, customer text or Banking77 material is in this set.
The repository's MIT license applies to these newly authored fixtures.

Run `python scripts/naacl2027/evaluate.py` from the repository root. The manifest records
the corpus SHA-256 and the exact source hashes used. The experiment invokes the policy
component in `off` and `extractive` modes on identical candidates. It does not invoke the
writer, retrieval, financial gate, repair or a live model. The missing-lookup cases test a
trigger limit, not an extractive sentence-matching failure. Do not infer end-to-end financial
correctness from these component results.

Keep version 1 unchanged when improving the verifier. Any revised labels need a separate
version and a rationale. Obtain independent support/completeness labels and new cases before
making generalization claims. The current finite case counts do not justify a population
confidence interval. Model-review comparisons remain pending live-provider evaluation.

# Ambiguity benchmark

`ambiguity.jsonl` (2 to 5 candidates per episode) and `ambiguity-8.jsonl` (8 candidates) are
built by `python scripts/naacl2027/build_ambiguity_set.py` (add `--size 8`), seed 2027. Each of
the 224 episodes takes a record-backed Banking77 question from `data/test`, deletes the
transaction or transfer reference, and pairs the original record (the hidden `target_id`) with
similar records from the same customer: same kind first, then nearest dates. The wording is real
Banking77 text (CC-BY-4.0); the records are synthetic.
