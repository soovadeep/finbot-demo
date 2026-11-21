# Evaluation record: November 19, 2026

This completes the local evaluation work through **automated interface evaluation**. It does
not complete a human usability study or a live evaluation of the new policy reviewer. No
new model API calls, participant sessions, public deployment or paid CI were used.

## Reproduce

From the repository root with Python 3.11+:

```sh
python scripts/naacl2027/evaluate.py --out /tmp/finbot-naacl-evaluation
python -m finbot.demo --port 18765
```

For browser evaluation, install Node.js 20+ and pnpm, then use a second terminal:

```sh
cd scripts/naacl2027
pnpm install --frozen-lockfile --ignore-scripts
pnpm exec playwright install chromium
FINBOT_EVAL_OUT=/tmp/finbot-naacl-evaluation pnpm evaluate
```

Alternatively, set `CHROME_PATH` to an existing Chrome executable. The recorded run used
Chrome 157.0.8103.79 on macOS, Playwright 1.62.1 and axe-core 4.10.3. The URL defaults to
`http://127.0.0.1:18765`; `FINBOT_DEMO_URL` accepts only a loopback HTTP origin. Installation
may download browser/test packages; evaluation itself requires no model account. Output
directories above keep reruns separate from the committed measurements.

The [manifest](../../../../results/naacl2027/manifest.json) records source and dataset hashes,
Python version, revision and whether uncommitted edits were present. Browser reports carry
their own source hashes and tool versions. The baseline was `afef182`; subsequent interface
edits are identified by file hashes because measurements were captured before committing.

## Policy component results

Source: [32 fixed cases](../../../../data/naacl2027/policy_cases.jsonl), with
[construction and label rules](../../../../data/naacl2027/README.md). All labels were authored
with Codex assistance before execution. Independent human adjudication remains pending.
Both modes receive identical candidates and evidence. The experiment isolates the policy
component; it does not evaluate the financial gate, retrieval, generation or recovery.

| Mode | Supported candidates allowed | Supported candidates rejected | Unsupported candidates allowed |
|---|---:|---:|---:|
| `off` | 16/16 | 0/16 | 16/16 |
| `extractive` | 8/16 | 8/16 | 4/16 |

Extractive checking accepted all eight complete source sentences, rejected all eight valid
paraphrases, and rejected all eight contradictions and four citation failures. The four
unsupported releases consist of **two context omissions** and **two absent KB-lookup triggers**.
The latter are coverage gaps: the component never activates on those turns. The context
examples reuse a genuine sentence while dropping a merchant-eligibility restriction or
presenting an obsolete rule as current. These failures are retained in the results.

This is an exploratory, purposively constructed diagnostic set, not a random or held-out
sample. No population confidence intervals, model-accuracy claims or end-to-end improvement
claims are warranted. The `off` mode's unconditional allowance is the component baseline,
not proof that the complete application would release every candidate. `model` mode remains
unmeasured; mocked verdicts would not establish its accuracy.

Full per-case decisions and reasons: [policy-component.json](../../../../results/naacl2027/policy-component.json).

## Interface evaluation and fixes

The same 18 engineering criteria were applied before and after interface changes. Four
criteria specify the inspection features the new interface should provide; they are feature
acceptance checks, not measurements of participant comprehension.

| Measurement | Before | After |
|---|---:|---:|
| Engineering criteria passing | 13/18 | 18/18 |
| Preset outcome/export checks | 8/8 | 8/8 |
| axe states scanned | 10 | 10 |
| Reported axe violation instances | 10 | 0 |
| Human participants | 0 | 0 |

The ten baseline axe instances are **one repeated best-practice issue**: a complementary
landmark nested inside `main`. They are not ten different accessibility defects. A labelled
note now replaces that landmark. Automated accessibility success is not WCAG certification.
The scan flags one color-contrast check per state as incomplete; that and real screen-reader
use need manual review. Keyboard stage selection was exercised, but only Chromium was tested.
The incomplete check concerns the question textarea: axe could not determine its background
because it considered the control partially obscured. This is retained as a manual-check
item, not counted as either a confirmed violation or an accessibility pass.

Other changes make the decision easier to inspect:

1. Raw rejection codes now have plain-language explanations while retaining the exact code.
2. The completed run's question remains visible after input edits. A stale-state notice
   distinguishes previous results, and export stays disabled until a successful new run.
3. The inspector explains extractive sentence reuse, paraphrase rejection, context loss and
   the KB-lookup trigger alongside verification stages.
4. Record-built answers warn that a summary may not cover every record or question part.
   Stage buttons also expose explicit passed/rejected accessible names.

The browser walkthrough covers all presets and JSON exports, source passages, keyboard
stage selection, stale inputs, multi-record fallback, a simulated server failure and recovery,
blank-input validation, and overflow at 320, 390, 768 and 1440 CSS pixels. No page JavaScript
errors or external page requests were observed. Simulated outage handling is a browser test,
not a deployed-service reliability result. The policy and fallback screenshots were visually
inspected for readable text, wrapping and panel layout.

Evidence: [before report](../../../../results/naacl2027/interface-before.json),
[after report](../../../../results/naacl2027/interface-after.json),
[desktop policy screenshot](../../../../results/naacl2027/interface-policy-desktop.png),
[mobile fallback screenshot](../../../../results/naacl2027/interface-fallback-mobile.png),
[eight synthetic traces](../../../../results/naacl2027/scenario-traces.json).

## Next empirical steps

The [participant-study protocol](participant-study.md) defines recruitment, consent,
counterbalancing, eight tasks, a two-point rubric and analysis. Before collecting responses,
freeze participant materials and assignments and obtain any required ethics review. Only
real, consented responses can support the paper's interface-usefulness claim.
The [prepared kit](../../../../results/naacl2027/study-kit/) includes 16 balanced assignment slots,
prompts, matched JSON bundles and an empty response CSV. Run
`python scripts/naacl2027/prepare_study.py` after regenerating the scenario traces.

For live policy comparisons, freeze model/provider versions, prompts, eligible source
snapshots and the corpus; independently annotate new cases; then compare `off`, `extractive`
and `model` with full writer/reviewer call, token, latency and cost accounting. Include a
genuinely code-only renderer in the recovery study. The existing live harness does not yet
meet all those recording requirements, so its outputs cannot silently stand in for that study.
Authors must agree provider access and a run budget before new billed evaluations.
