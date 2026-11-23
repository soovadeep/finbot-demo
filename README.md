# Finbot

An inspectable AI assistant for evidence-grounded payment support.
Code, data and demo for the NAACL 2027 System Demonstrations paper by Sandip Nandi,
Apurba Bose, Aishwarya Bose and Soovadeep Bakshi.

**Try it:** open the hosted demo at <https://finbot-demo-20852907589.us-central1.run.app/>.
Nothing to install. The [walkthrough](docs/papers/naacl-2027/reviewer-guide.md) lists
every scenario and what to look for. The [paper](docs/papers/naacl-2027/finbot-naacl2027.pdf) is in the repository. The 2.5-minute demo video is
[docs/papers/naacl-2027/video/finbot-naacl2027-demo.mp4](docs/papers/naacl-2027/video/finbot-naacl2027-demo.mp4).

Payment support involves identifying the relevant payment, explaining declines or uncertain
outcomes, comparing records and answering policy questions. Finbot demonstrates these tasks
through two interfaces, using synthetic account records and fictional policies:

1. **Conversation.** Interpret supplied details, ask up to two scored clarification questions,
   request explicit record confirmation, and explain that record's status and details.
   Customer corrections invalidate the selection and mark previous answers as superseded.
2. **Evidence inspector.** Explore decline explanations, unknown outcomes, two-record comparisons
   and cited policy answers. These direct scenarios are separate from the conversation interface.
3. **Verification and recovery.** Inspect retrieved evidence, drafts and check results. Inject
   wrong statuses, invented fees, swapped amounts or policy contradictions to observe repair,
   a checked record-built fallback, or refusal. The fault options depend on the interface.

The assistant is read-only: it does not initiate payments, refunds or disputes. Checks cover
finite claim formats and do not establish semantic correctness or completeness. A customer can
still confirm a wrong record consistent with their stated details. A conflicting selection now pauses
for explicit correction or reselection before retrieval; it never silently overrides supplied details.

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
Run `python scripts/naacl2027/evaluate_conversation.py` for 60 authored regression replays through
the actual conversation endpoint's controller, including corrections, abstention and wrong confirmation.
Customer events and the answer writer are scripted; question selection and verification use the
actual demo code. Fifteen scripts run under four fault settings, including six new conflict-resolution
scripts. Twenty runs never generate a draft; four further runs pause on a conflict after superseding
an earlier answer. These are repeated test conditions, not independent customer samples. These checks are not customer-accuracy or natural LLM error measurements.

| Result | Command | Output |
|---|---|---|
| Ambiguity benchmark (224 Banking77 questions, 2 to 8 candidate records) | `python scripts/naacl2027/build_ambiguity_set.py` (and `--size 8`) | `data/naacl2027/` |
| Simulated customers, two model families, safety conditions | `python scripts/naacl2027/simulate_customers.py --simulator haiku` (and `llama`), then `--report` | `results/naacl2027/clarification-sim/` |
| Contradiction controls, keyboard/mobile behavior and accessibility | `node scripts/naacl2027/contradiction_interface.cjs` | `results/naacl2027/contradiction-interface.json` |
| Interface checks and accessibility scans | `node scripts/naacl2027/interface.cjs`, `node scripts/naacl2027/conversation_axe.cjs` | `results/naacl2027/` |
| Answer checks on injected errors | `python scripts/naacl2027/check_injection.py` | `results/naacl2027/check-injection.json` |
| Tests (no installs) | `python -m unittest discover -s tests` | |

The original simulations can call model APIs on cache misses. The added
`python scripts/naacl2027/compare_baselines.py` replays cached replies only, reports coverage,
and compares amount-first and most-distinct heuristics. A most-distinct question matches or
exceeds the correct-confirmation rate of two decision-value questions on the main component set;
showing all records remains a strong baseline. No human usability benefit has been demonstrated.

Run `python scripts/naacl2027/paired_verification.py` for matched clean/corrupted checks.
The raw 82.3% rejection rate includes pre-existing failures; mutations trigger 2,098/2,670
rejections among accepted controls (78.6%), including zero for added bare links.

The submission's evaluation uses cached simulations, controller replays and verification diagnostics;
reproducing those results requires no participant recruitment. The local `/pilot` page and
[study protocol](docs/papers/naacl-2027/evaluation/user-study-protocol.md) are optional future-work
tools, not a planned or completed study supporting this submission. No participant results are included.
See [claim boundaries and independent scoring](docs/papers/naacl-2027/evaluation/claim-boundaries.md)
for remaining semantic failures and how to assess correct selection **and** answer quality.

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
