# Changelog

## 1.0.0 (2026-11-24), NAACL 2027 System Demonstrations submission

- The conversation carries the customer's own question through confirmation and answers it
  about the confirmed record only; action requests are declined as read-only.
- Single-record answers must state each requested field (refund amount, settlement dates,
  payment amount, decline reason) or say the record lacks it.
- Hedges stay with the clause they qualify ("It may have gone to Harbor Books. I am certain it
  was a card payment.").
- Every answer is labelled with its writer: scripted, newly generated, cached replay, or
  scripted after a cap or provider error; the inspector offers the capped live writer too.
- Optional direct LLM evidence review (`FINBOT_SEMANTIC_VERIFICATION=llm`) and a fresh
  30-answer study frozen before generation (`results/naacl2027/fresh-llm-v1/`).
- `/pilot` pages are off unless `FINBOT_DEMO_PILOT=1`.
