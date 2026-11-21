# Ambiguity benchmark

`ambiguity.jsonl` (2 to 5 candidates per episode) and `ambiguity-8.jsonl` (8 candidates) are
built by `python scripts/naacl2027/build_ambiguity_set.py` (add `--size 8`), seed 2027. Each of
the 224 episodes takes a record-backed Banking77 question from `data/test`, deletes the
transaction or transfer reference, and pairs the original record (the hidden `target_id`) with
similar records from the same customer: same kind first, then nearest dates. The wording is real
Banking77 text (CC-BY-4.0); the records are synthetic.

`ambiguity-8-same-amount.jsonl` is the same-amount slice (paper Appendix D), built by
`python scripts/naacl2027/build_same_amount_set.py`.

`data/test/` holds the synthetic records and Banking77-derived questions the benchmark draws on.
Banking77 (Casanueva et al., 2020) is used under CC-BY-4.0; question wording is unchanged except
that transaction references are removed.
