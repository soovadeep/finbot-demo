# Finbot: next steps for the demo submission

Updated November 24, 2026 on `abose/evaluation-context-gaps`, based on main `1c866d9`.
Boxes distinguish implemented software and authored evaluations from outstanding live
validation or human review. Earlier frozen studies retain their original results.

## Status, November 24

- **Question carried through (1):** the conversation records the customer's question, answers
  it about the confirmed record only, declines action requests (cancel, refund) as read-only,
  and answers a follow-up question about the same record without reconfirmation.
- **Coverage (2):** `finbot/requested_fields.py` requires single-record answers to state each
  requested refund amount, settlement date, payment amount or decline reason, or say the record
  lacks it. The $200/$50 regression table below is a test (`tests/test_requested_information.py`).
- **Uncertainty parsing (3):** hedges stay with their own clause (`tests/test_uncertainty_parsing.py`).
  The original failing report is unchanged; the fixed example is now a development case.
- **Live answers (4):** both views offer the capped Llama 3.3 70B writer through OpenRouter;
  every answer is labelled scripted, newly generated, cached replay, or scripted after a cap
  or provider failure. `/pilot` is hidden unless `FINBOT_DEMO_PILOT=1`.
- **Semantic checker (5, 6):** a direct LLM evidence review (`LLMEvidenceVerifier`, Gemini 2.5
  Flash Lite via OpenRouter) and a fresh 30-answer study frozen before generation. Results and
  caveats: [evaluation/fresh-llm.md](evaluation/fresh-llm.md). Its effect depends on the
  labeller, so it stays off by default. Two label sets: the AI assistant and a co-author.
- **Second labels complete:** the live v2 study now has AI and blind co-author labels for
  43 distinct answers, agreeing on 41; both give 26 correct releases and four refusals.
- **Error diversity:** 48 matched pairs across 12 families, frozen before evaluation;
  originally 44 corruptions and five correct controls blocked, 39/43 new rejections.
  Requested-code coverage now blocks all four wrong-policy quotations in development
  replay: 48 corruptions, unchanged five false rejections, 43/43 new rejections.
  [Historical results, fix and review form](evaluation/verification-challenge.md).
- **Context and memory:** full-prompt admission, output reserve, rollover, bounded state,
  rollback and fresh-snapshot replacement; nine offline contracts pass. [Design](../../agent-design.md).
- **Conversation evaluation prepared:** four paired short/long scenarios complete 160 actual
  chatbot turns using the scripted writer. Frozen runtime, raw traces, independent-case
  import and blind review forms are available. No paid calls or live reasoning results.
  [Protocol and pending evaluation](evaluation/conversation-study.md).
- **Hosted smoke:** scripted policy quotation and missing-document refusal checked on
  November 24 (`results/naacl2027/hosted-smoke-2026-11-24.json`). This does not attest the
  deployed Git revision; the new context branch has not been deployed. Video is unchanged.
- **Still open:** independently authored wording and live long-conversation/full-controller
  assessment, human review of the new challenge, broader semantic applicability, and
  release/deployment identity. External participants remain optional.

## 1. Preserve the actual support question (highest priority)

- [x] Carry the customer's financial question through clarification and confirmation into
  answer generation and verification. Keep question intent separate from record-identifying details.
- [x] Preserve the confirmed-record access boundary; a question must not authorize additional records.
- [x] Define how later questions and corrections update intent, invalidate stale answers and
  require reconfirmation when the intended record changes.
- [x] Add controller tests for refund amount, expected versus actual settlement, missing data,
  corrections, and unrelated requests. Extend synthetic fixtures where the current conversation
  records do not contain the required fields.

**Done when:** a refund question reaches the writer as a refund question about the confirmed
record, rather than becoming a generic status summary; correction and authorization tests pass.

## 2. Require the answer to cover the requested information

- [x] Add explicit coverage checks for supported requests: payment/refund amount, settlement
  dates and multiple requested fields. Check the role and meaning, not just the presence of a number.
- [x] Use the same requirements for the draft, repair and record-built fallback. If the relevant
  field is absent, allow a clear missing-evidence response rather than an invented answer.
- [x] Add matched supported, unsupported and incomplete controls, including paraphrases.

**Required regression:** with payment = $200 and refund = $50, asked "How much was refunded?":

| Candidate answer | Required behavior |
|---|---|
| "Your payment was $200." | Trigger repair for missing refund information; covered by the current regression test. |
| "Your refund amount was $200." | Reject the amount-role mismatch. |
| "Your refund amount was $50." | Accept when the record supports it. |
| "The record does not show a refund amount." | Accept only when the relevant evidence is genuinely unavailable. |

**Done when:** the incomplete answer cannot be released in the tested end-to-end path, while
correct answers and justified missing-data responses pass. Document the finite wording coverage.

## 3. Fix the known uncertainty-parsing failure

- [x] Keep tentative recipient information tentative when a later clause expresses certainty
  about payment type: "It may have gone to Harbor Books. I am certain it was a card payment."
- [x] Retain both compatible card records in this case; add clause-order and punctuation controls.
- [x] Preserve the original failing report. Treat post-fix reruns on these examples as development
  regressions and use different wording for subsequent evaluation.

**Done when:** uncertainty and confidence remain attached to the correct attributes, without
weakening explicit contradiction handling.

## 4. Make live answering available and clearly labelled

- [x] Configure a specific writer model through OpenRouter using server-side credentials.
  Exclude credential files from Git; set a provider-key spending limit and application request caps.
- [x] Connect the original-question flow from item 1 to live generation. Add an explicit live
  option to the inspector if live policy and comparison demonstrations are part of the paper.
- [x] Clearly distinguish scripted answers, newly generated answers, cached answers and
  fallbacks caused by quota exhaustion or provider failures.
- [x] Rehearse visitor-written questions with fault injection off. Retain scripted fault presets
  for explaining verification and recovery.

**Done when:** a visitor can ask an in-scope question in their own words and see an accurately
labelled live answer, with authorization, confirmation, rate limits and recovery still enforced.

## 5. Add and evaluate one semantic checker using available access

- [x] Select a checker model and provider configuration. OpenRouter can serve a model used by
  a NeMo adapter or a direct LLM verifier; the existing Bedrock adapter separately requires AWS access.
  Choose one initial route rather than making both integrations prerequisites.
- [x] Record the chosen implementation accurately: direct LLM evidence review inside
  `HallucinationGate`, with deterministic checks retained. No NeMo adapter is integrated.
- [x] Assess both evidence support and question coverage. NeMo's standard fact-checking rail
  alone may accept a true statement that does not answer the question.
- [x] Extend the existing three-way harness to the chosen checker. Pin model, prompts, version,
  thresholds and provider settings; retain unavailable/malformed responses as operational failures.
- [x] Record actual model usage and cost. Keep paid checks opt-in until the credentials and
  spending limit are configured; no paid evaluation has been authorized or run by this backlog.

**Done when:** the checker participates in draft, repair and fallback verification, produces
inspectable findings, and has real provider measurements distinct from mock-response tests.

## 6. Run fresh evaluation after freezing the implementation

- [x] Freeze runtime, checker, prompts, thresholds and scoring before preparing the new test set.
  Keep the existing 32 pairs and observed failures for development only.
- [x] Prepare varied synthetic questions/evidence covering refund/payment roles, expected/actual
  dates, policy exceptions, record comparisons, omissions and missing evidence.
- [x] Generate fresh LLM answers with injected faults off; save failures and refusals as well
  as successful answers. Use a separate set for deliberately corrupted matched-pair tests.
- [x] Review live v1 and v2 answers with AI-assistant and blind co-author labels, recording
  support and completeness separately (89% and 95% agreement). This is author assessment,
  not external annotation. The separate new challenge still has construction-based expectations.
  The checker must not supply its own gold labels.
- [x] Compare deterministic checks, semantic checking and their combination on identical inputs.
  Report detections, false rejections, paired new rejections, remaining errors, unavailable cases,
  latency and measured cost; retain denominators and raw results.
- [x] Retain the 60 authored controller replays and separately score record selection and answer fields.
- [ ] Add fresh live evaluation of the complete clarification-to-answer journey. The live
  writer studies name the record and bypass clarification/confirmation. Full success requires
  the intended record AND a supported, sufficiently complete final answer.

**Done when:** reproducible new results support the final claims, including unsuccessful cases.
Replaying cached answers or previously inspected wording must remain labelled as replay/development.

## 7. Synchronize the submission artifacts

- [x] Revise the paper and capability-to-evidence table around measured behavior and results.
  Credit the underlying methods/providers and retain limitations; do not infer an accuracy gain
  from adopting a named guardrail framework.
- [ ] Confirm the actual venue, track, year, deadline and formatting requirements against its call.
- [ ] Deploy the selected release to the hosted demo and verify its revision, live-mode labels,
  mobile/keyboard behavior, request limits and failure handling.
- [ ] Re-record the video using that release and update narration/captions. Update reviewer
  instructions and make every advertised workflow reproducible.
- [x] Rebuild and visually inspect the PDF, retaining the required page limit and readable figures.

**Done when:** the paper, video, hosted app and reviewer guide describe the same released behavior.

## 8. Make the release easy to cite

- [x] Add `CITATION.cff` with the correct authors, title and repository URL; update it when a
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
