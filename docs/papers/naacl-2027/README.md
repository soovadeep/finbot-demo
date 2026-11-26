# NAACL 2027 System Demonstrations: paper materials

**Finbot: From Payment Ambiguity to Evidence-Grounded Answers.**
Sandip Nandi, Apurba Bose, Aishwarya Bose, Soovadeep Bakshi (independent researchers).

- [Paper (PDF)](finbot-naacl2027.pdf) and [source](paper/main.tex), in the official ACL style
  (see [TEMPLATE.md](paper/TEMPLATE.md)).
- [Reviewer guide](reviewer-guide.md): the hosted demo, the local demo and what to try.
- [Evaluation guide](evaluation/README.md): every result in the paper, with its command and output.
- [Agent design](../../agent-design.md): context budgets, memory, tool-loop limits and recovery.
- [Demo video](video/finbot-naacl2027-demo.mp4) (2:28), with its [script](video/narration.md),
  [captions](video/captions.srt) and [scope note](video/README.md).

## Build the paper

With TeX Live or MacTeX and `latexmk`:

```sh
cd docs/papers/naacl-2027/paper
latexmk -pdf main.tex
```
