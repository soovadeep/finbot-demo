# Claim boundaries and independent answer scoring

## What the present evidence supports

The contribution is inspectable payment support linking message interpretation, ambiguous-record
clarification, customer confirmation, scoped retrieval, evidence-consistency checks and recovery.
The separate inspector also demonstrates record comparisons and cited policy answers; those
scenarios are not general-purpose routing capabilities of the conversation interface.
It is not a novel Bayesian method,
an established best question selector, or a universally safe financial agent. The component's
most-distinct heuristic outperforms one-question decision value on this benchmark.

The original live-writer audit covers 125 initially passing answers from one model on card payments
(108 distinct records). It identifies **nine expected-versus-actual settlement-date errors and one
refund omission**. Treat these as semantic-role and completeness failures; the historical audit's
"minor issue" label does not establish low financial impact. Its 115 other answers were assessed
by authors with AI assistance, not an independent blinded study. Preserve that provenance.
The [financial-role checker](financial-roles.md) now blocks those nine date errors when replaying
the same saved drafts, while accepting all 115 author-labelled supported answers. The omitted
refund still passes. These inspected failures informed the implementation; this is retrospective
development replay, not fresh live-model or held-out validation. The original audit is unchanged.

Confirmation is an authorization boundary, not a correctness oracle. A selected record that conflicts
with confidently supplied type, payee, date, amount, currency or reference now pauses before retrieval.
The customer sees both values and can explicitly correct those details and confirm the record, retain
their earlier details and choose again, type a correction, or leave unresolved. The resolution event
must identify the current conflict; repeated selection or a stale acknowledgement cannot bypass it.
Tentative/unknown details do not block selection. Previous answers are superseded during a change.
A customer can still confirm a wrong record consistent with their stated details, or explicitly accept
the wrong correction; the verifier cannot independently recover hidden intent. The 60 controller
replays test these boundaries but do not measure customer error reduction. Policy answering and record
comparison now also have [40 scripted inspector runs and matched component probes](varied-support.md).
The original 74 mutations exposed missed currency bindings and required omissions; one policy
query failed retrieval under both fault settings. Fixes now reject all 74 mutations, accept all
paired clean drafts and pass all 40 workflow cases. These are the same inspected development
cases, not a new holdout. Original and post-fix reports are preserved separately. All six supported
paraphrases still fail extractive checking. Broader natural-query performance remains unmeasured.
See the capability-to-evidence table in [evaluation scope](README.md).
The observed wrong-selection rates of 2.2%/4.0% for the two-question DV component
are numerically above 1.8%/3.6% for the full list. Neither overlapping intervals nor a small observed
difference establishes equivalence, non-inferiority or a production safety bound.

Structured-value extraction is finite and format-dependent. Report successes as observations on
the tested formats. Value membership alone does not establish a financial role; the new checker
handles four explicit role formats. Other role errors, completeness (a refund omitted), temporal
validity and applicability remain outside that check.

## End-to-end success

For an actionable task, require **correct intended record AND supported final answer AND sufficient
completeness for the user's task**. Report wrong selections, unresolved tasks, missing answers and
unsupported/incomplete answers separately. Report appropriate abstention for absent/indistinguishable
targets separately from successful actionable answers.

Prepare independent audit forms for the deployed workflow replay:

```sh
python scripts/naacl2027/score_end_to_end.py prepare \
  --runs results/naacl2027/conversation-replay.json --out annotations.json
```

The forms deliberately contain null judgments. Give reviewers the original customer events/task,
final answer and source record/policies, with method/fault labels and gate decisions concealed where
feasible. Review **all released answers**, including repaired and record-built fallbacks. Judge:

- Support: every substantive claim agrees with the intended record, including field roles,
  status chronology, settlement expectations, refund state and advice applicability.
- Completeness: the answer covers the requested information and material qualifiers; unsupported
  payment execution claims fail. Identification-only fixtures do not establish cancellation ability.

Use two reviewers where feasible, record disagreements and adjudicate before final scoring. Keep
the independent reviewer process and rubric documented; a nonempty reviewer code alone cannot
prove independence. Fill explicit boolean judgments and notes, then run:

```sh
python scripts/naacl2027/score_end_to_end.py score \
  --runs results/naacl2027/conversation-replay.json --annotations annotations.json --out end-to-end.json
```

Stale hashes, duplicate runs and unfilled submitted judgments are rejected. Without completed audits,
the score remains null for potentially successful unassessed answers. Gate passes and the replay's
expected-field checks are never silently converted into independent answer-quality labels.

The [fresh LLM study](fresh-llm.md) is the only labelled set: 30 answers with provisional,
AI-assisted support and completeness labels written by the authors' assistant, not by an
independent reviewer. Its end-to-end counts are therefore provisional.

No independent end-to-end accuracy or human usability result is claimed in this revision. Auditing
authored regression cases remains a regression assessment; estimating customer performance requires
the actual deployed controller on separately collected customer/simulator interactions.
