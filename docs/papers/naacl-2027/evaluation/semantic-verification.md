# Optional semantic verification and a three-way study

**Status:** implemented, disabled by default, tested with synthetic API responses. No live
Bedrock evaluations or fresh writer calls have been made for this extension. No improvement
in semantic accuracy is claimed. The default demo still needs no AWS account or API key.
The hosted demo and video have not been redeployed by this branch update.

## What changes

The customer confirms the intended record. `Conversation.confirm()` checks that selection
against stated details and controls access to the confirmed record. The model drafts an
answer; `HallucinationGate` checks it. An optional `BedrockGroundingVerifier` now joins that
gate, so it checks the first draft, model repair and record-built fallback. Existing identity,
authorization, evidence, financial-role, comparison and policy checks remain in place.

The checker sends the question, draft and trusted tool results to Bedrock contextual grounding.
The evidence retains record IDs, field names and tool boundaries; third-party fields cannot
vouch for claims. For repeated identical lookups only the latest result is eligible, including
a later not-found result. The inspector displays grounding/relevance scores, thresholds,
version, latency and whether the assessment was unavailable. No evidence is silently truncated.

Both GROUNDING and RELEVANCE assessments must be present and well formed. Below-threshold
scores block even for a detect-only AWS policy. Provider failures, missing assessments,
unexpected policy mixtures and excessive input lengths withhold the answer as **unavailable**,
not as a detected factual error. This can reduce availability during an outage. Bedrock's
rewritten output is never substituted for the draft; Finbot owns recovery. A passing score
does not prove record ownership, completeness, or correctness.

## What the comparison measures

`scripts/naacl2027/semantic_study.py` runs the same supplied drafts/evidence through:

1. The current deterministic component chain, including request-specific comparison/policy checks.
2. The Bedrock contextual-grounding checker alone (evaluation only).
3. Both together, rejecting if either detects a violation.

The semantic-only arm does not disable authorization in the running app. One semantic call
is shared by arms 2 and 3 to avoid differing random assessments or duplicate charges. The
report retains every row, independent labels, reasons, scores, usage units and wall time.
It reports incorrect drafts detected, correct drafts rejected, unavailable assessments,
matched new rejections, remaining unsupported drafts and accepted incomplete answers.
Accuracy rates name their assessed denominators; unavailable cases also appear explicitly.
A new rejection in a pair still does not prove the specific injected error was identified.

Latency is uncached checking time; combined latency is the sequential sum of the checks,
not chat completion time. API retries are disabled in the study client. Cost remains unknown
unless all response usage is present and an explicit unit price and dated pricing source are
supplied; estimates exclude writer generation and hosting. See
[AWS pricing](https://aws.amazon.com/bedrock/pricing/). No price is hard-coded.

## Run without spending money

```sh
PYTHONHASHSEED=0 python scripts/naacl2027/semantic_study.py development \
  --out /tmp/finbot-semantic-development.json
python -m unittest discover -s tests -p test_semantic_verification.py -v
```

This runs **64 drafts: 32 correct/corrupted pairs**, using the already inspected
`fresh-wording-v1` fixtures as development data. The current rules reject 12/32 incorrect
drafts and accept 32/32 correct drafts. Semantic and combined results are **pending**, not
zero accuracy or mock accuracy. The committed offline report is
`results/naacl2027/semantic-development-offline.json`. Unit-test API responses validate wiring
and accounting only; they are not provider-performance evidence.

Historical reports and frozen data are unchanged. Two regression tests compare current
outcomes against historical outcomes, excluding only their original source manifests. Exact
historical reproduction uses its recorded revision; `fresh-wording-v1` still refuses a changed
runtime. The old 32 pairs must not become a new holdout after semantic tuning.

## Optional paid setup

Do this only when choosing to use an AWS account. Configure credentials through a local
AWS profile/SSO or role, never in the repository or chat. Install the optional SDK with
`python -m pip install boto3`. Create a **dedicated contextual-grounding-only** guardrail,
enable grounding and relevance, and publish a numbered version. Standard tier supports
conversational wording and requires cross-Region inference; availability is region-specific.
Classic and Standard scores are not interchangeable. See the
[AWS guide](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html).
The harness reads the published configuration before evaluation and rejects mismatched
thresholds/tier or additional policy families. It does not create or modify AWS resources.

Example study config (replace placeholders; the thresholds are a starting configuration,
not validated settings). Save outside version control:

```json
{
  "guardrail_id": "YOUR_GUARDRAIL_ID",
  "version": "1",
  "region": "us-east-1",
  "tier": "STANDARD",
  "grounding_threshold": 0.7,
  "relevance_threshold": 0.7,
  "usd_per_unit": null,
  "pricing_source": null,
  "writer": {
    "provider": "openai",
    "model": "YOUR_WRITER_MODEL",
    "base_url": "http://localhost:11434/v1"
  }
}
```

The writer can be a local OpenAI-compatible endpoint, a hosted endpoint, or `converse` for
Bedrock. `FINBOT_OPENAI_API_KEY` is read locally when a hosted writer needs a key. Writer and
checker are separate roles. The checker in this implementation uses Bedrock even if the
writer runs locally. NeMo is not integrated: its open-source fact-checking rail can instead
use a local model, but would need its own adapter and evaluation, not a renamed Bedrock result.

```sh
# Development comparison: at most 64 paid checking calls, no writer calls.
python scripts/naacl2027/semantic_study.py development --live --max-calls 64 \
  --config /tmp/semantic-config.json --out /tmp/semantic-development-live.json

# Enable inside the application only after configuring the service.
export FINBOT_SEMANTIC_GUARDRAIL_ID=YOUR_GUARDRAIL_ID
export FINBOT_SEMANTIC_GUARDRAIL_VERSION=1
export AWS_REGION=us-east-1
export FINBOT_SEMANTIC_VERIFICATION=bedrock
# Separate explicit opt-in for the synthetic demo (up to three checks per answered request).
export FINBOT_DEMO_SEMANTIC=bedrock
python -m finbot.demo
```

Leave both switches unset or `off` for the free, offline default. The semantic demo bypasses
the live-writer answer cache so an old answer cannot skip the enabled checks. Public demo
traffic can incur checking costs; the study's `--max-calls` cap does not cap server traffic.

## Fresh generated answers after freezing

1. Tune only on development data. Freeze the code, configuration and writer before preparing
   fresh questions. Keep the freeze file in version control before generating/evaluating.
2. Prepare new synthetic questions and source evidence, covering wording, financial roles,
   policy exceptions and comparison omissions. Do not reuse the old 32 pairs as test data.
3. Generate answers with no checker feedback, saving refusals and provider failures too.
4. Review each answer against its source: support **and** completeness, with a rationale.
   The checker cannot provide its own gold labels. Author review is not independent annotation.
5. Run the frozen three-way evaluation. If tuning resumes, use another new test set.

```sh
python scripts/naacl2027/semantic_study.py freeze --config /tmp/semantic-config.json \
  --out /tmp/semantic-plan.json
python scripts/naacl2027/semantic_study.py generate --live --max-calls 24 \
  --plan /tmp/semantic-plan.json --prompts /tmp/fresh-prompts.json --out /tmp/fresh-drafts.json
python scripts/naacl2027/semantic_study.py evaluate --live --max-calls 24 \
  --plan /tmp/semantic-plan.json --drafts /tmp/fresh-drafts.json \
  --labels /tmp/fresh-labels.json --out /tmp/fresh-semantic-results.json
```

The draft and label files remain separate. Prompt format is a JSON list of
`{id, family, question, focus, evidence}`; `evidence` uses the inspector's tool-log schema.
Each label row has `{id, supported, complete, rationale}`. Its envelope is
`{drafts_sha256, annotator, basis: "source_based_author_review", rows}`;
`drafts_sha256` is `semantic_study.digest()` of the parsed draft file. Every output must
receive a label, including empty or failed generations, to prevent silent exclusions.
Freeze hashes cover runtime and study code, and outputs refuse overwrites. These controls
support reproducibility; they cannot prove that an author did not inspect test wording.
This is draft-level evaluation on supplied evidence, not retrieval, customer usability, or
end-to-end conversational task accuracy. Live measurements remain outstanding.
