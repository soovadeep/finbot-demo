# NAACL 2027 System Demonstrations: paper materials

**Clarify, then Verify: A Payment-Support Assistant That Asks Which Record You Mean Before It
Answers.** Sandip Nandi, Apurba Bose, Aishwarya Bose, Soovadeep Bakshi (independent researchers).

- [Reviewer guide](reviewer-guide.md): the hosted demo, the local demo and what to try.
- [Paper (PDF)](finbot-naacl2027.pdf)
- [Paper source](paper/main.tex): LaTeX in the official ACL style (see [TEMPLATE.md](paper/TEMPLATE.md)).
- [Paper details](evaluation/paper-details.md): prompts, settings and extra results the
  appendix refers to.
- [Demo video](video/finbot-naacl2027-demo.mp4) (2:26), with its [script](video/narration.md)
  and [captions](video/captions.srt).

## Reproduce the evaluation

All model replies are cached, so every table recomputes without API calls.

| Result | Command | Output |
|---|---|---|
| Ambiguity benchmark (224 episodes; 2 to 5 and 8 candidates) | `python scripts/naacl2027/build_ambiguity_set.py` and `--size 8` | `data/naacl2027/ambiguity*.jsonl` |
| Simulated customers, two model families, safety conditions | `python scripts/naacl2027/simulate_customers.py --simulator haiku` (and `llama`, `--bench ambiguity-8`, `--conditions overconfident`), then `--report` | `results/naacl2027/clarification-sim/` |
| Answer checks on injected errors | `python scripts/naacl2027/check_injection.py` | `results/naacl2027/check-injection.json` |
| Inspector acceptance checks and axe scans | `node scripts/naacl2027/interface.cjs` | `results/naacl2027/interface-after.json` |
| Conversation page axe scan | `node scripts/naacl2027/conversation_axe.cjs` | `results/naacl2027/conversation-axe.json` |

See [the simulation README](../../../results/naacl2027/clarification-sim/README.md) for what each
file holds.

## Build the paper

With TeX Live or MacTeX and `latexmk`:

```sh
cd docs/papers/naacl-2027/paper
latexmk -pdf main.tex
```
