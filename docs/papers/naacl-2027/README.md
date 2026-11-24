# NAACL 2027 System Demonstrations: paper materials

**Finbot: From Payment Ambiguity to Evidence Grounded Answers.**
Sandip Nandi, Apurba Bose, Aishwarya Bose, Soovadeep Bakshi (independent researchers).

The paper presents the conversation and evidence-inspector interfaces as a read-only support
system: clarification and corrections, payment explanations, comparisons across records,
cited policy answers, and inspectable verification and recovery. The inspector's direct policy
and comparison scenarios are distinguished from the conversation's confirmed-record summaries.

- [Reviewer guide](reviewer-guide.md): the hosted demo, the local demo and what to try.
- [Prioritized next steps](next-steps.md): remaining implementation, evaluation and submission work.
- [Paper (PDF)](finbot-naacl2027.pdf)
- [Paper source](paper/main.tex): LaTeX in the official ACL style (see [TEMPLATE.md](paper/TEMPLATE.md)).
- [Paper details](evaluation/paper-details.md): prompts, settings and extra results the
  appendix refers to.
- [Demo video](video/finbot-naacl2027-demo.mp4) (2:26), with its [script](video/narration.md)
  and [captions](video/captions.srt). The recording predates these evaluation revisions;
  see [the scope note](video/README.md) before submission.

## Reproduce the evaluation

Saved model replies support replay. The original simulator may call an API on cache misses;
the added baseline comparison is cache-only and reports missing coverage explicitly.

| Result | Command | Output |
|---|---|---|
| Actual conversation controller: 60 authored regressions | `python scripts/naacl2027/evaluate_conversation.py` | `results/naacl2027/conversation-replay.json` |
| Varied support: post-fix rerun of 40 inspector runs and 74 matched mutations | `python scripts/naacl2027/evaluate_support.py` | `results/naacl2027/varied-support-roles.json` (earlier reports preserved) |
| Financial-role ablation: 60 corruptions, 12 equal-value controls, 125 cached drafts | `python scripts/naacl2027/evaluate_financial_roles.py` | `results/naacl2027/financial-roles.json` |
| Amount-first and most-distinct baselines, cached replies only | `python scripts/naacl2027/compare_baselines.py` (also `--bench ambiguity-8-same-amount`) | `results/naacl2027/strong-baselines/` |
| Matched clean/corrupted verification | `python scripts/naacl2027/paired_verification.py` | `results/naacl2027/paired-verification/` |
| Ambiguity benchmark (224 episodes; 2 to 5 and 8 candidates) | `python scripts/naacl2027/build_ambiguity_set.py` and `--size 8` | `data/naacl2027/ambiguity*.jsonl` |
| Simulated customers, two model families, safety conditions | `python scripts/naacl2027/simulate_customers.py --simulator haiku` (and `llama`, `--bench ambiguity-8`, `--conditions overconfident`), then `--report` | `results/naacl2027/clarification-sim/` |
| Answer checks on injected errors | `python scripts/naacl2027/check_injection.py` | `results/naacl2027/check-injection.json` |
| Inspector acceptance checks and axe scans | `node scripts/naacl2027/interface.cjs` | `results/naacl2027/interface-after.json` |
| New contradiction flow: browser and axe checks | `node scripts/naacl2027/contradiction_interface.cjs` | `results/naacl2027/contradiction-interface.json` |
| Conversation page axe scan | `node scripts/naacl2027/conversation_axe.cjs` | `results/naacl2027/conversation-axe.json` |

See [varied support results and failure examples](evaluation/varied-support.md),
[financial roles, ablation and novelty boundaries](evaluation/financial-roles.md),
[evaluation scope](evaluation/README.md) and
[the simulation README](../../../results/naacl2027/clarification-sim/README.md) for what each file holds.
The submission relies on the existing simulations, automated controller checks and verification
diagnostics; participant recruitment is not part of this revision. The
[pilot protocol](evaluation/user-study-protocol.md) and local `/pilot` interface are optional
future-work tools. [Claim boundaries](evaluation/claim-boundaries.md) documents independent
end-to-end scoring. No human pilot or independent semantic audit has been completed or used
as evidence for this submission.

## Build the paper

With TeX Live or MacTeX and `latexmk`:

```sh
cd docs/papers/naacl-2027/paper
latexmk -pdf main.tex
```
