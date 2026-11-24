# Finbot: next steps for the demo submission

Updated November 23, 2026. This is a prioritized backlog, not a report of completed work.
The current baseline is the merged `review/naacl-demo-evaluation` branch through `a81e68b`.
The repository targets **NAACL 2027 System Demonstrations**; confirm the venue/year against
the actual call before submission, since the initial discussion referred to 2026.

## Current baseline

- Clarification uses templates and Bayesian updates. The main conversation selects questions
  by decision value; the researcher view also supports information gain. No LLM drafts these questions.
- Customers confirm records; contradictory selections require explicit resolution.
- The default answer writer is scripted. The conversation has an optional live LLM switch;
  the inspector web endpoint currently uses the scripted writer.
- Confirmation currently asks the writer a standard status-and-details question, rather than
  passing the customer's original financial question through.
- Deterministic checks, bounded repair, checked record fallback and refusal are implemented.
- Optional Bedrock contextual grounding is implemented but disabled, with no live effectiveness
  measurements. NeMo is not integrated. An OpenRouter account is available according to the
  author, but its credentials/model have not been configured or exercised in this revision.
- The existing 32 wording pairs are development data: 12/32 corruptions are rejected, and
  32/32 correct counterparts pass. Of 16 pre-confirmation message sequences, 15 have the expected
  candidate set and all 16 withhold financial answers. Historical reports stay unchanged.
- The latest implementation passed 186 automated tests. Synthetic provider responses test the
  optional adapter's behavior; they do not establish Bedrock accuracy.
- The paper has six main pages, one reference page and two appendix pages. Hosted-demo and
  video synchronization remain separate work.

## 1. Preserve the actual support question (highest priority)

- [ ] Carry the customer's financial question through clarification and confirmation into
  answer generation and verification. Keep question intent separate from record-identifying details.
- [ ] Preserve the confirmed-record access boundary; a question must not authorize additional records.
- [ ] Define how later questions and corrections update intent, invalidate stale answers and
  require reconfirmation when the intended record changes.
- [ ] Add controller tests for refund amount, expected versus actual settlement, missing data,
  corrections, and unrelated requests. Extend synthetic fixtures where the current conversation
  records do not contain the required fields.

**Done when:** a refund question reaches the writer as a refund question about the confirmed
record, rather than becoming a generic status summary; correction and authorization tests pass.

## 2. Require the answer to cover the requested information

- [ ] Add explicit coverage checks for supported requests: payment/refund amount, settlement
  dates and multiple requested fields. Check the role and meaning, not just the presence of a number.
- [ ] Use the same requirements for the draft, repair and record-built fallback. If the relevant
  field is absent, allow a clear missing-evidence response rather than an invented answer.
- [ ] Add matched supported, unsupported and incomplete controls, including paraphrases.

**Required regression:** with payment = $200 and refund = $50, asked "How much was refunded?":

| Candidate answer | Required behavior |
|---|---|
| "Your payment was $200." | Trigger repair for missing refund information; the current verifier allows it. |
| "Your refund amount was $200." | Reject the amount-role mismatch. |
| "Your refund amount was $50." | Accept when the record supports it. |
| "The record does not show a refund amount." | Accept only when the relevant evidence is genuinely unavailable. |

**Done when:** the incomplete answer cannot be released in the tested end-to-end path, while
correct answers and justified missing-data responses pass. Document the finite wording coverage.

## 3. Fix the known uncertainty-parsing failure

- [ ] Keep tentative recipient information tentative when a later clause expresses certainty
  about payment type: "It may have gone to Harbor Books. I am certain it was a card payment."
- [ ] Retain both compatible card records in this case; add clause-order and punctuation controls.
- [ ] Preserve the original failing report. Treat post-fix reruns on these examples as development
  regressions and use different wording for subsequent evaluation.

**Done when:** uncertainty and confidence remain attached to the correct attributes, without
weakening explicit contradiction handling.

## 4. Make live answering available and clearly labelled

- [ ] Configure a specific writer model through OpenRouter using server-side credentials.
  Exclude credential files from Git; set a provider-key spending limit and application request caps.
- [ ] Connect the original-question flow from item 1 to live generation. Add an explicit live
  option to the inspector if live policy and comparison demonstrations are part of the paper.
- [ ] Clearly distinguish scripted answers, newly generated answers, cached answers and
  fallbacks caused by quota exhaustion or provider failures.
- [ ] Rehearse visitor-written questions with fault injection off. Retain scripted fault presets
  for explaining verification and recovery.

**Done when:** a visitor can ask an in-scope question in their own words and see an accurately
labelled live answer, with authorization, confirmation, rate limits and recovery still enforced.

## 5. Add and evaluate one semantic checker using available access

- [ ] Select a checker model and provider configuration. OpenRouter can serve a model used by
  a NeMo adapter or a direct LLM verifier; the existing Bedrock adapter separately requires AWS access.
  Choose one initial route rather than making both integrations prerequisites.
- [ ] If choosing NeMo, implement and test its adapter inside `HallucinationGate`; do not label
  direct LLM prompting as a NeMo integration. Keep the existing deterministic checks enabled.
- [ ] Assess both evidence support and question coverage. NeMo's standard fact-checking rail
  alone may accept a true statement that does not answer the question.
- [ ] Extend the existing three-way harness to the chosen checker. Pin model, prompts, version,
  thresholds and provider settings; retain unavailable/malformed responses as operational failures.
- [ ] Record actual model usage and cost. Keep paid checks opt-in until the credentials and
  spending limit are configured; no paid evaluation has been authorized or run by this backlog.

**Done when:** the checker participates in draft, repair and fallback verification, produces
inspectable findings, and has real provider measurements distinct from mock-response tests.

## 6. Run fresh evaluation after freezing the implementation

- [ ] Freeze runtime, checker, prompts, thresholds and scoring before preparing the new test set.
  Keep the existing 32 pairs and observed failures for development only.
- [ ] Prepare varied synthetic questions/evidence covering refund/payment roles, expected/actual
  dates, policy exceptions, record comparisons, omissions and missing evidence.
- [ ] Generate fresh LLM answers with injected faults off; save failures and refusals as well
  as successful answers. Use a separate set for deliberately corrupted matched-pair tests.
- [ ] Review answers against source evidence, recording support and completeness separately
  with rationales. Author adjudication needs no recruited participants but is not independent review.
  The checker must not supply its own gold labels.
- [ ] Compare deterministic checks, semantic checking and their combination on identical inputs.
  Report detections, false rejections, paired new rejections, remaining errors, unavailable cases,
  latency and measured cost; retain denominators and raw results.
- [ ] Evaluate the deployed controller end to end as well as supplied-draft components. Success
  requires the intended record AND a supported, sufficiently complete final answer.

**Done when:** reproducible new results support the final claims, including unsuccessful cases.
Replaying cached answers or previously inspected wording must remain labelled as replay/development.

## 7. Synchronize the submission artifacts

- [ ] Revise the paper and capability-to-evidence table around measured behavior and results.
  Credit the underlying methods/providers and retain limitations; do not infer an accuracy gain
  from adopting a named guardrail framework.
- [ ] Confirm the actual venue, track, year, deadline and formatting requirements against its call.
- [ ] Deploy the selected release to the hosted demo and verify its revision, live-mode labels,
  mobile/keyboard behavior, request limits and failure handling.
- [ ] Re-record the video using that release and update narration/captions. Update reviewer
  instructions and make every advertised workflow reproducible.
- [ ] Rebuild and visually inspect the PDF, retaining the required page limit and readable figures.

**Done when:** the paper, video, hosted app and reviewer guide describe the same released behavior.

## 8. Make the release easy to cite

- [ ] Add `CITATION.cff` with the correct authors, title and repository URL; update it when a
  preprint or proceedings record exists. Do not invent publication status, venue acceptance or DOI.
- [ ] Tag the evaluated release and archive the software/evaluation artifacts with a persistent
  identifier, for example through Zenodo, when the authors are ready to publish that archive.
- [ ] Link the paper or public preprint, versioned code, evaluation protocol and results.

Human recruitment is optional future work, not a dependency for this backlog. Clarification can
remain template-based; adding LLM-generated clarification questions is not needed for these fixes.

## Existing starting points

- [Semantic integration, study commands and current limitations](evaluation/semantic-verification.md)
- [Fresh-wording failure cases and frozen original results](evaluation/fresh-wording.md)
- [End-to-end scoring and claim boundaries](evaluation/claim-boundaries.md)
- [Capability-to-evidence map](evaluation/README.md#capability-to-evidence-map)
- [Reviewer guide](reviewer-guide.md)
- [Deployment instructions](../../../deploy/demo/README.md)
