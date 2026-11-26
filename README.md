# Finbot

An inspectable AI assistant for evidence-grounded payment support. Code, data and demo for
the NAACL 2027 System Demonstrations paper by Sandip Nandi, Apurba Bose, Aishwarya Bose and
Soovadeep Bakshi.

- **Hosted demo:** <https://finbot-demo-20852907589.us-central1.run.app/> (nothing to install)
- **Walkthrough:** [reviewer guide](docs/papers/naacl-2027/reviewer-guide.md), with every scenario and what to look for
- **Agent design:** [context windows, session memory and execution limits](docs/agent-design.md)
- **Paper:** [finbot-naacl2027.pdf](docs/papers/naacl-2027/finbot-naacl2027.pdf)
- **Video (2.5 min):** [finbot-naacl2027-demo.mp4](docs/papers/naacl-2027/video/finbot-naacl2027-demo.mp4)

## What it shows

Finbot works on synthetic account records and fictional policies, and has two views:

1. **Conversation.** It reads the customer's details, asks up to two scored clarification
   questions and asks the customer to confirm the record. Then it answers the customer's own
   question about that record. A correction pauses the turn until the customer reselects.
2. **Evidence inspector.** Decline explanations, unknown outcomes, two-record comparisons and
   cited policy answers, with the retrieved evidence, each draft and every check result.
   You can inject a wrong status, an invented fee, swapped amounts or a reversed policy rule.
   The turn then shows a repair, a checked answer built by code from the record or the quoted
   policy text, or a refusal.

Finbot is read-only. It does not start payments, refunds or disputes. The checks cover fixed
claim formats; they do not prove an answer is semantically correct or complete. A customer
can still confirm the wrong record if it matches what they said.

## Run it locally

You need Python 3.11 or later. No packages, API key or network are needed:

```sh
python -m finbot.demo
```

Then open <http://127.0.0.1:8765/> for the conversation, or <http://127.0.0.1:8765/inspector>
for the evidence inspector. The demo uses a scripted writer, and labels it as scripted.

## Reproduce the evaluation

| Result | Command | Output |
|---|---|---|
| Tests | `python -m unittest discover -s tests` | |
| Ambiguity benchmark (224 Banking77 questions, 2 to 8 candidates) | `python scripts/naacl2027/build_ambiguity_set.py` (and `--size 8`) | `data/naacl2027/` |
| Simulated customers (two model families) | `python scripts/naacl2027/simulate_customers.py --report` | `results/naacl2027/clarification-sim/` |
| Baselines, cached replies only | `python scripts/naacl2027/compare_baselines.py` | `results/naacl2027/strong-baselines/` |
| Conversation controller replays | `python scripts/naacl2027/evaluate_conversation.py` | `results/naacl2027/conversation-replay.json` |
| Financial-role ablation | `python scripts/naacl2027/evaluate_financial_roles.py` | `results/naacl2027/financial-roles.json` |
| Live policy answers, two labellers | `python scripts/naacl2027/paired_gate_study.py score --version fresh-llm-v3` | `results/naacl2027/fresh-llm-v3/` |
| Public questions, pre/post-fix | [public-questions.md](docs/papers/naacl-2027/evaluation/public-questions.md) | `results/naacl2027/public-wording-v2/` |
| Interface and accessibility checks | `node scripts/naacl2027/interface.cjs`, `node scripts/naacl2027/conversation_axe.cjs` | `results/naacl2027/` |

The [evaluation guide](docs/papers/naacl-2027/evaluation/README.md) explains what each result
measures and where it stops. None of these results comes from real customers or a user study.

## Where things are

```
finbot/clarification*.py   clarification: beliefs, question scoring, conversation
finbot/guardrails.py       answer checks (amounts, statuses, causes, citations)
finbot/policy_documents.py policy checks and the quoted-policy fallback
finbot/demo.py             demo server; pages in finbot/demo_assets/
data/naacl2027/            benchmark and frozen study cases
results/naacl2027/         saved results
docs/papers/naacl-2027/    paper sources, walkthrough, evaluation notes and video
deploy/demo/               container and Cloud Run guide for the hosted demo
```

## License and data

Code: [MIT](LICENSE). Records and policies are synthetic. Evaluation questions use Banking77
wording under CC-BY-4.0 (see [data/naacl2027/README.md](data/naacl2027/README.md)). Not
financial advice, and not connected to any company. Citation metadata is in
[CITATION.cff](CITATION.cff).
