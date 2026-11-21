# Local validation of the verification-hardening branch

Run date: 2026-11-19. Python 3.12. No live model/provider calls or paid hosted CI were used.

| Check | Result |
|---|---|
| `ruff check .` | Passed |
| `mypy finbot` | Passed, 97 source files |
| `python -m unittest discover -s tests` | 603 tests passed, including 28 new focused tests |
| `scripts/run_eval.py --data data` | 41/41 scripted cases passed |
| `scripts/run_eval.py --data data/test` | 185/185 scripted cases passed |
| `scripts/run_eval.py --data data/test --cases data/test/banking77.jsonl` | 310/310 configured expectations passed |
| `scripts/run_eval.py --data data/test --cases data/test/banking77_fresh.jsonl` | 310/310 configured expectations passed |
| `scripts/run_redteam.py` | Defended: 0/34 scripted attacks succeeded; 7/7 benign controls answered |
| `scripts/evaluate_policy_checks.py` | All 24 strict-mode decision expectations matched |

The hybrid follow-up passed the full 621-test suite, including 18 additional mocked
reviewer tests, plus lint, type checks, both scripted development/test splits and the
defended red-team replay. The policy component report was regenerated with current source
hashes and unchanged off/extractive/strict counts. No hybrid accuracy row is included:
the new tests validate protocol enforcement, isolation, evidence binding, failure handling
and bounded recovery, not the semantic accuracy of a live LLM. See
`docs/verification/hybrid.md` for the live evaluation still needed.

The infrastructure tests initially could not find Node, then could not write the jsii
cache outside the sandbox. The passing full run supplied the installed Node executable
through `JSII_NODE` and a writable `/tmp/finbot-hardening-jsii-cache` directory through
`JSII_RUNTIME_PACKAGE_CACHE_ROOT`. No infrastructure was deployed. Docker image building
and hosted CI were not run for this change.

The two Banking77 sets contain 416 record-backed cases in total, now checked against exact
arguments and returned record identity. The remaining 204 have no explicit answer-quality
expectations. These pass counts are not factuality or helpfulness estimates.

`policy-checks.json` contains all 72 component decisions (24 cases by three modes), reasons
and source/input hashes. Strict mode rejected all 17 unsupported candidates and two of seven
supported controls. The two false rejections are valid paraphrases. One allowed control is
an abstention. These authored fixtures are regression evidence, not independently labelled
held-out results or end-to-end reliability measurements. See the scope and next evaluation
steps in `docs/verification/hardening.md`.
