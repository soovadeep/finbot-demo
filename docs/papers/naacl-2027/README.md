# NAACL 2027 demo submission workspace

Title: **Clarify, then Verify: A Payment-Support Assistant That Asks Which Record You Mean
Before It Answers**. Authors: Sandip Nandi, Apurba Bose, Aishwarya Bose, Soovadeep Bakshi
(independent researchers). Status: full draft with measured results; the video and a final
artifact link are still to come.

## What is here

- [ACL manuscript](paper/main.tex): six pages in the official ACL style. It describes the combined
  conversation (`/study`): Bayesian clarification of which record the customer means, explicit
  confirmation and corrections, then the record-grounded answer and the evidence inspector.
- [Reviewer guide](reviewer-guide.md): no-key installation and the inspector scenarios.
- The earlier [evaluation record](evaluation/README.md) for the
  inspector (policy component, interface before and after fixes).

## Evaluation behind the paper

| Result | Command | Output |
|---|---|---|
| Ambiguity benchmark (224 episodes; 2 to 5 and 8 candidates) | `python scripts/naacl2027/build_ambiguity_set.py` and `--size 8` | `data/naacl2027/ambiguity*.jsonl` |
| Simulated customers, two model families, safety conditions | `python scripts/naacl2027/simulate_customers.py --simulator haiku` (and `llama`, `--bench ambiguity-8`, `--conditions overconfident`), then `--report` | `results/naacl2027/clarification-sim/` |
| Inspector acceptance checks and axe scans | `node scripts/naacl2027/interface.cjs` | `results/naacl2027/interface-after.json` |
| Conversation page axe scan | `node scripts/naacl2027/conversation_axe.cjs` | `results/naacl2027/conversation-axe.json` |

See [the simulation README](../../../results/naacl2027/clarification-sim/README.md) for what each
file holds.

## Official requirements

Checked November 19, 2026 against the [System Demonstrations call](https://2027.naacl.org/calls/system_demonstration/).
Use the call as the authority if it changes.

| Item | Requirement / action |
|---|---|
| Deadline | December 4, 2026, 23:59 AoE; December 5, 03:59 US/Pacific |
| Review | Single blind: include agreed authors and affiliations |
| Paper | Up to six content pages; up to two appendix pages; references and optional ethics/broader-impact material have extra space |
| Evaluation | Required; complete measured evaluation before submission |
| Video | At most 2.5 minutes; prepare an accessible screencast |
| Reviewer access | Accessible live demo or downloadable installable package |
| AI assistance | Disclose coding, research and writing assistance in acknowledgements |
| Originality | Resolve overlap with the core manuscript and any other archival submission |

Links: [conference](https://2027.naacl.org/),
[OpenReview demo track](https://openreview.net/group?id=aclweb.org/NAACL/2027/Demo_Track),
[official ACL style](https://github.com/acl-org/acl-style-files),
[publication ethics](https://www.aclweb.org/adminwiki/index.php/ACL_Policy_on_Publication_Ethics).
Create/verify OpenReview author profiles early; personal-email activation can take two weeks.

## Build the manuscript

The `paper/` directory is a standalone LaTeX project, suitable for a local TeX installation
or upload to Overleaf. It vendors unmodified official style files; their pinned source and
checksums are recorded in [TEMPLATE.md](paper/TEMPLATE.md).

From the repository root, with TeX Live/MacTeX and `latexmk` installed:

```sh
cd docs/naacl-2027/paper
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Alternatively run `pdflatex main`, `bibtex main`, then `pdflatex main` twice. The generated
`main.pdf` and auxiliary files are ignored by Git. Codex's built-in LaTeX editor can also
open and compile this folder without a terminal TeX installation.

The draft uses the official `preprint` option to retain authors and page numbers. The
template's `review` option anonymizes authors and is unsuitable for this single-blind call.
Confirm the final required option with the current track instructions. Do not change margins,
font sizes or style files to fit the limit. Pending results are explicitly identified in the
text; no fabricated result rows or invented author details are supplied.

Documentation validation on November 19, 2026: the manuscript compiled successfully with
the desktop editor's LaTeX compiler; all 19 demo tests and an HTTP smoke check of all eight
presets passed in a fresh Python 3.12 environment without third-party packages. Local links,
bibliography keys and the unmodified upstream style copies were checked. Final PDF page-count
and visual inspection remain part of submission preparation; compilation alone does not
establish layout or page-limit compliance.
