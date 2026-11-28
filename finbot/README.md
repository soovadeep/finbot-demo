# The `finbot` package

The modules are kept flat so that import paths match the frozen studies (their protocols hash
files by path). This map groups them by what they do. The demo starts at `demo.py`, and a
customer's turn runs through `orchestrator.py`.

## Demo and evaluation entry points

| Module | Role |
|---|---|
| `demo.py`, `demo_assets/` | Demo server: conversation (`/`), evidence inspector (`/inspector`), writer labels and live-model caps |
| `clarification_demo.py` | Clarification wired to the real answer pipeline |
| `clarification_study.py`, `usability.py` | Local, export-only study pages (no recruitment) |
| `evalstats.py` | Confidence intervals for the scripts in `scripts/naacl2027/` |

## Clarification and conversation

| Module | Role |
|---|---|
| `clarification.py` | Belief state over authorized candidate records, question scoring (decision value, most-distinct, fixed order) |
| `clarification_conversation.py` | Deployed conversation controller: parsing, confirmation, conflicts, corrections |
| `comparison.py` | Coverage for questions that compare two payments |

## Answering a turn

| Module | Role |
|---|---|
| `orchestrator.py` | The turn pipeline: ordered stages, each of which may answer and end the turn |
| `tools.py` | Typed, read-only, tenant-scoped tools (records, logs, policy search) |
| `knowledge.py` | Policy knowledge base: chunking and hybrid retrieval |
| `llm.py`, `models.py` | Model clients behind one interface, and model routing |
| `context.py`, `memory.py` | Prompt admission and entity-scoped session memory |
| `replies.py` | Every fixed reply decided by code rather than the model |
| `policy.py` | Payment retry policy and next-step routing, decided in code |

## Verification and recovery (the paper's core)

| Module | Role |
|---|---|
| `verification.py` | The gate: verify, bounded repair, verify again |
| `guardrails.py` | Amount, status, cause and citation checks on each draft |
| `binding.py`, `provenance.py` | Record binding: each value must come from the record its sentence is about |
| `financial_roles.py` | Financial-role checks: payment vs refund, expected vs actual date, and similar |
| `requested_fields.py`, `support_coverage.py`, `missing_information.py` | What the customer asked for, and whether the answer covers it or says it is missing |
| `reasons.py` | Plain-word decline reasons, checked against the record |
| `policy_documents.py`, `policy_relevance.py` | Extractive policy checks and the quoted-policy fallback |
| `semantic_verification.py` | Optional model-based evidence review (off by default) |
| `recordanswer.py` | The record-built fallback answer |
| `faults.py` | Fault injection used by the inspector and the tests |

## Platform (identity, scoping and storage the pipeline builds on)

| Module | Role |
|---|---|
| `security.py`, `security_gateway.py`, `agent_identity.py`, `tenancy.py`, `pii.py`, `dlp.py`, `untrusted.py`, `crypto.py` | Identity, per-call authorization, tenant scoping, masking, untrusted content |
| `registry.py`, `ports.py`, `config.py` | Adapter registries, interfaces and settings |
| `store.py`, `store_dynamo.py` | Session store adapters (SQLite, DynamoDB) |
| `resilience.py`, `telemetry.py`, `auditlog.py` | Retries, traces and audit records |
| `actions.py`, `tickets.py`, `freshness.py`, `language.py` | Write-request hand-off, source freshness, language detection |
| `adaptive/`, `domains/`, `processors/` | Guard-policy tuning, domain plug-ins, processor routing |
