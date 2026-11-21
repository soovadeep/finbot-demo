# Initial clarification simulation

These reports contain **exact synthetic expectations**, not observations from
people or live LLMs. They enumerate 24 development scenario families, five reply
regimes, and five strategy/control conditions: 600 comparison rows per budget.
The two files contain the same families at budgets of one and two questions.
They are not 1,200 independent test cases and are unrelated to Banking77.

Reproduction and limitations: [experiment documentation](../../docs/clarification/experiments.md).

## Findings

Matched reliable response model, expected MAP record-selection accuracy:

| Selector | Budget 1 | Budget 2 | Mean questions, budget 2 |
|---|---:|---:|---:|
| No questions | 48.89% | 48.89% | 0.00 |
| Fixed template order | 65.08% | 73.87% | 1.53 |
| Information gain | 68.40% | 73.86% | 1.53 |
| Decision value | 68.40% | 73.83% | 1.21 |

Selection matters more when only one question is allowed in this fixture set.
With two questions, information gain does **not** improve accuracy over fixed
ordering. The cost-sensitive selector achieves similar accuracy with fewer
questions under the specified error cost (0.02), which is not human-calibrated.

When replies are correctly modeled as uninformative, both adaptive selectors ask
zero questions. Fixed ordering asks 1.58 questions on average at budget two,
without improving selection accuracy.

When the assumed response model is overconfident, information-gain selection at
budget two achieves 48.75% accuracy, slightly below the 48.89% no-question baseline.
Among predictions above its 0.95 confidence threshold, 24.77% are wrong (coverage
10.16%). Correlated reply errors also cause overconfidence. Neither score nor
posterior threshold is a factuality guarantee or a runtime authorization rule.

The supplied-correct-intent control achieves 100% by construction. It is an
information control, not a measured clarification strategy.

## What has not been measured

Final-answer factuality, real-world record discovery, missing true candidates,
natural-language ambiguity detection, human completion/effort, learned response
model calibration, live-model errors, API cost, and latency. The runtime demo
separately tests explicit confirmation and the actual Finbot verification path.
Its customer answer is not released from a MAP guess or confidence threshold.

Each JSON report records model scope, settings, metrics, per-family expectations,
and SHA-256 hashes of its mathematical implementation and runner. No statistical
confidence intervals are attached to exact expectations under stipulated models.
