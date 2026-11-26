# Evaluation guide

This guide maps each result in the paper to the files and commands behind it. None of
these results comes from real customers or a user study. Records and policies are synthetic.

| Paper result | What it measures | Command | Saved output |
|---|---|---|---|
| Clarification component study (Sec. 4.1–4.3, Tables 1, 3–5) | Simulated customers confirming one of eight records; selectors compared | `python scripts/naacl2027/simulate_customers.py --report`; `python scripts/naacl2027/compare_baselines.py` (also `--bench ambiguity-8-same-amount`); `python scripts/naacl2027/review_studies.py` | `results/naacl2027/clarification-sim/`, `strong-baselines/`, `review-studies/` |
| Controller replays (Appendix F) | 15 authored event sequences × 4 fault settings through the deployed conversation controller | `python scripts/naacl2027/evaluate_conversation.py` | `results/naacl2027/conversation-replay.json` |
| Financial-role ablation (Sec. 4.4) | 60 value-preserving corruptions and 72 controls, with and without role checks | `python scripts/naacl2027/evaluate_financial_roles.py` | `results/naacl2027/financial-roles.json` |
| Live policy answers (Sec. 4.4) | 30 new frozen cases, the same Llama draft judged with and without the cited-passage fallback; two labellers | `python scripts/naacl2027/paired_gate_study.py score --version fresh-llm-v3` | `results/naacl2027/fresh-llm-v2/`, `fresh-llm-v3/` |
| Public questions (Sec. 4.4) | 30 unused Banking77 questions × 2 record conditions, pre-fix vs post-fix; AI review plus a blind co-author on post-fix answers | see [support-coverage.md](support-coverage.md) | `results/naacl2027/public-wording-v2/` |
| Interface checks (Appendix F) | Browser layouts and axe-core scans | `node scripts/naacl2027/interface.cjs`, `node scripts/naacl2027/conversation_axe.cjs` | `results/naacl2027/interface-after.json`, `conversation-axe.json` |
| Context contracts (Appendix E) | Prompt admission, rollover and snapshot replacement | `python -m unittest tests.test_context_budget` | test output |

Benchmark files are built by `build_ambiguity_set.py` (`--size 8`) and `build_same_amount_set.py`
under `data/naacl2027/`. Simulator replies are cached, so replays make no model calls.

## Details

- [Financial roles](financial-roles.md): the role checker, the ablation and its limits.
- [Live policy answers](fresh-llm.md): the paired fallback study, both label sets and the re-run.
- [Public questions](support-coverage.md): the frozen protocol, both label sets and remaining
  omissions. [public-wording.md](public-wording.md) describes the earlier development set.
- [Paper details](paper-details.md): prompts, settings and extra tables the appendix cites.

## What these results do not show

- The component study uses `ClarificationSession`; the deployed `Conversation` controller
  shares its scoring but parses free text and filters on confident details. Rates describe the
  component, not the hosted demo.
- Controller replays are regression checks on authored events, not customer accuracy.
- A passing gate does not establish a correct or complete answer. The checks recognise finite
  English claim formats; checks still reject about half of correct live drafts, which repair or
  fallback must recover.
- Live answers come from one model (Llama 3.3 70B).
