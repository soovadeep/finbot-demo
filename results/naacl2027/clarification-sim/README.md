# Simulated-customer study of Bayesian clarification (NAACL 2027 demo)

Language models play customers who did not quote a transaction reference; Finbot asks up to
three multiple-choice questions and the customer then confirms a record. These are simulated
customers, not people.

This is a **component evaluation of `ClarificationSession`**, not a measurement of the hosted
`Conversation` controller. The deployed controller parses openings, filters on unhedged details,
and presents matching/other records rather than a ranked two-record shortlist. See
[evaluation scope](../../../docs/papers/naacl-2027/evaluation/README.md) and the separate
`conversation-replay.json` workflow regression report.

| File | Contents |
|---|---|
| `rows-<sim>.jsonl` | One row per episode run on the 2-to-5-candidate benchmark, shortlist confirmation (the demo's design) |
| `rows-<sim>-ambiguity-8.jsonl` | The same on the 8-candidate benchmark (the paper's main table) |
| `rows-<sim>-overconfident.jsonl` | Safety test: the system assumes every reply is 99% reliable |
| `rows-<sim>-sequential.jsonl` | Earlier protocol: records proposed one at a time for a yes or no |
| `cache-<sim>.jsonl` | Every simulated reply, keyed by episode, persona, question or list. Re-running uses it and makes no new calls |
| `usage-<sim>.json` | Token counts. Calls made before usage tracking was added are not counted, so the number of cache lines (4,745 Haiku, 4,756 Llama) is the true call count |
| `summary.json` | Rates with 95% Wilson intervals per benchmark, confirmation mode, simulator, condition, budget and selector, plus source hashes |

Simulators: Claude Haiku 5.5 (Anthropic API, thinking off) and Llama 3.3 70B Instruct
(OpenRouter, temperature 0). Personas: receipt 40%, vague 35%, misremembers 25%, fixed per
episode by seed; the `all_misremember` condition gives every customer one confident wrong detail.

## Main results (8 candidates, mixed personas, shortlist of two)

| Simulator | Strategy | Questions | Top guess right | Confirmed right | Confirmed wrong |
|---|---|---|---|---|---|
| Haiku | No questions | 0 | 13% | 17% | 3.1% |
| Haiku | Fixed order, budget 1 | 1 | 19% | 24% | 2.2% |
| Haiku | Decision value, budget 1 | 1 | 69% | 47% | 2.2% |
| Haiku | Decision value, budget 2 | 1.36 | 74% | 49% | 2.2% |
| Haiku | Show all eight | 0 | n/a | 60% | 1.8% |
| Llama | No questions | 0 | 13% | 21% | 5.4% |
| Llama | Fixed order, budget 1 | 1 | 19% | 30% | 5.8% |
| Llama | Decision value, budget 1 | 1 | 74% | 63% | 4.0% |
| Llama | Decision value, budget 2 | 1.31 | 79% | 66% | 4.0% |
| Llama | Show all eight | 0 | n/a | 81% | 3.6% |

Acting on the top guess without confirmation would pick the wrong record in 26% (Haiku) and
21% (Llama) of episodes; 42% when every customer misremembers. Showing the full list resolves
more episodes than two questions and a two-record list; the paper reports this as the boundary
of where clarification helps (voice, small screens).

## Protocol change, stated plainly

The first full run proposed records one at a time and counted only an explicit "yes". Vague
customers almost never said yes to a single exact record (they answered "not sure"), so that
protocol left most episodes unresolved and favoured the list baseline for a reason unrelated to
the questions. We switched to a short list, which is what the demo shows, and kept the first
run as `rows-*-sequential.jsonl`. The 8-candidate benchmark and the overconfident condition were
added after that, to test the setting the method is for and the plan's wrong-model safety test.
