# Financial-role verification and its evidence

The systems contribution connects customer confirmation to inspectable checks of a claim's
record, financial role and source field. An amount or date can occur on the correct record
while supporting a different claim. The new `FinancialRoleVerifier` checks four explicit roles:

| Claim role | Required transaction field |
|---|---|
| Payment amount | `amount` |
| Refund amount | `refund.amount` |
| Expected settlement date | `settlement.expected_date` |
| Actual settlement date | `settlement.actual_date`, with `settlement.status == settled` |

Only the latest lookup can support a recognized claim. A later failed lookup invalidates the
earlier evidence. Shared policy prose, other records and merchant text cannot supply these fields.
The inspector shows each recognized phrase, record ID, role, field path, stated value, recorded
value (or unavailable) and verdict. The same chain checks repair and record-built fallback.
This is a finite English parser over explicit amounts and ISO calendar dates, not a general
semantic correctness or completeness guarantee. Adapter field mappings must be correct.

## Try it

Run `python -m finbot.demo`, then open `/inspector` and choose:

- **Expected is not actual:** the synthetic record says settlement status is settled and
  expected date is 2026-11-20, but has no actual date. An injected actual-date claim is blocked.
  Repair preserves the expected date and says an actual date is not recorded. Missing a date
  does not mean settlement did not happen.
- **Payment is not refund:** a $200 payment has a $50 refund. The fault replaces the refund
  amount with $200, which exists on that same record. Repair restores $50.

These preset faults edit scripted drafts before verification. They do not measure natural LLM errors.
The hosted demo and recording require separate synchronization; pushing this branch does not deploy them.

## Reproduce the ablation

```sh
python scripts/naacl2027/evaluate_financial_roles.py
python -m unittest discover -s tests -p 'test_financial_role*.py'
```

The report is `results/naacl2027/financial-roles.json`. It contains exact inputs, labels,
individual check results and source hashes. Labels describe authored interventions and do not
come from gate decisions. The full production chain is ablated by removing verifier components.

| Configuration | Within-record role errors blocked / 48 | Cross-record errors blocked / 12 | Clean counterparts accepted / 60 | Equal-value controls accepted / 12 |
|---|---:|---:|---:|---:|
| Existing chain without record binding | 0 | 0 | 60 | 12 |
| Existing chain with record binding | 0 | 12 | 60 | 12 |
| Add financial roles | 48 | 12 | 60 | 12 |

The 48 within-record interventions comprise 12 expected-as-actual claims, 12 swaps of actual
and expected dates, 12 payment amounts used as refunds and 12 refund amounts used as payments.
Six authored records and two wordings share fixtures: these are dependent development cases,
not 60 independent customers or held-out examples. Every substituted amount/date already occurs
in the evidence. Equal-value controls verify that identical values in distinct fields remain valid.
All blocked corruptions have accepted clean counterparts. Four additional `run_demo` runs check
acceptance, both role repairs and fallback, with expected fixture details scored separately.

Two deliberately out-of-grammar erroneous probes still pass: “The transaction settled on
November 10, 2026” and “You got $200.00 back.” These expose parsing boundaries; the implementation
was not extended to make their reported scores disappear. Omissions are outside this check.

## Retrospective live-draft replay

The original `live-writer/rows.jsonl` and `audit.json` remain unchanged. Applying only the new
role checker to their 125 originally passing drafts blocks all nine previously identified
expected-as-actual date errors, blocks none of the 115 author-labelled supported answers, and
still allows the one answer omitting a refund. These errors informed development; this is
retrospective component replay, not fresh model generation, an independent audit or a new holdout.

`varied-support-roles.json` separately reruns the prior support suite under the revised runtime:
40/40 workflows and all 74 mutations pass their expectations. Earlier original and post-fix
reports remain preserved as `varied-support.json` and `varied-support-fixed.json`.

## Novelty boundary

Bayesian clarification, human confirmation, semantic alignment, guardrails and repair are
established techniques. [Ryt AI](https://aclanthology.org/2025.emnlp-industry.45/) already combines
financial guardrails with confirmation. [Epistemic Erosion](https://aclanthology.org/2026.aacl-long.223/)
studies changes in expressed certainty, including omissions. [ContractEval](https://arxiv.org/abs/2609.09458)
studies query-conditioned procedural obligations. We do not claim to introduce these concepts.

Finbot contributes a reproducible payment-support demonstration linking ambiguity resolution,
record ownership, explicit financial roles and visible recovery. Value-preserving interventions
show why field roles add information beyond record binding. This strengthens a demo's systems
contribution; it does not establish a new general reasoning algorithm or superiority over those systems.

The [subsequent fresh-wording challenge](fresh-wording.md) freezes the implementation and
precommits new labels before running it. It rejects 12/32 new corruptions while accepting 32/32
correct counterparts, exposing substantial wording sensitivity beyond the original ablation.
