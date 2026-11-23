# Clarify, then Verify

A payment-support assistant that asks which record you mean before it answers.
Code, data and demo for the NAACL 2027 System Demonstrations paper by Sandip Nandi,
Apurba Bose, Aishwarya Bose and Soovadeep Bakshi.

**Try it:** open the hosted demo at <https://finbot-demo-20852907589.us-central1.run.app/>.
Nothing to install. The [walkthrough](docs/papers/naacl-2027/reviewer-guide.md) lists
every scenario and what to look for. The [paper](docs/papers/naacl-2027/finbot-naacl2027.pdf) is in the repository. The 2.5-minute demo video is
[docs/papers/naacl-2027/video/finbot-naacl2027-demo.mp4](docs/papers/naacl-2027/video/finbot-naacl2027-demo.mp4).

Customers rarely quote a transaction ID, and "my $200 payment hasn't arrived" can match several
payments. Finbot does two things in one conversation:

1. **Clarify.** It keeps a probability for each record the customer is allowed to see, asks the
   one or two questions with the highest expected value, then shows a short list. A probability
   never selects a record; the customer confirms it.
2. **Verify.** It fetches the confirmed record again, and code checks every amount, status and
   cause in the model's draft against it. A failing draft gets one repair, then an answer built
   from the record, then a refusal.

An inspector shows the beliefs, question scores, retrieved evidence and every rejected draft.

## Run it locally

Python 3.11 or later, no packages to install, no API key, no network calls:

```sh
python -m finbot.demo
```

Then open <http://127.0.0.1:8765/> for the conversation, or <http://127.0.0.1:8765/inspector> for
the evidence inspector. The demo uses synthetic records and a clearly labelled scripted model.

## Reproduce the evaluation

The 224-question simulation evaluates the clarification **component**, not the deployed
conversation's complete interaction policy. See the [evaluation scope](docs/papers/naacl-2027/evaluation/README.md).
Run `python scripts/naacl2027/evaluate_conversation.py` for 36 authored regression replays through
the actual conversation endpoint's controller, including corrections, abstention and wrong confirmation.
These scripted checks are not customer-accuracy measurements.

| Result | Command | Output |
|---|---|---|
| Ambiguity benchmark (224 Banking77 questions, 2 to 8 candidate records) | `python scripts/naacl2027/build_ambiguity_set.py` (and `--size 8`) | `data/naacl2027/` |
| Simulated customers, two model families, safety conditions | `python scripts/naacl2027/simulate_customers.py --simulator haiku` (and `llama`), then `--report` | `results/naacl2027/clarification-sim/` |
| Interface checks and accessibility scans | `node scripts/naacl2027/interface.cjs`, `node scripts/naacl2027/conversation_axe.cjs` | `results/naacl2027/` |
| Answer checks on injected errors | `python scripts/naacl2027/check_injection.py` | `results/naacl2027/check-injection.json` |
| Tests (no installs) | `python -m unittest discover -s tests` | |

The simulations call model APIs; their saved outputs are in `results/` so nothing needs to be rerun.

## Where things are

```
finbot/clarification*.py   Bayesian clarification: beliefs, question scoring, conversation
finbot/guardrails.py       the answer checks (amounts, statuses, causes, citations)
finbot/demo.py             the demo server; pages in finbot/demo_assets/
data/naacl2027/            ambiguity benchmark
data/test/                 synthetic records the benchmark draws on
results/naacl2027/         simulation, interface and accessibility results
docs/papers/naacl-2027/    paper sources (ACL style), walkthrough and video
deploy/demo/               container and Cloud Run guide for the hosted demo
```

## License and data

Code: [MIT](LICENSE). The records and policies are synthetic. Evaluation questions use Banking77
wording under CC-BY-4.0 (see [data/naacl2027/README.md](data/naacl2027/README.md)). Not financial advice, and not
connected to any company.
