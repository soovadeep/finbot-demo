"""Varied authored policy/comparison checks; no model calls or customer accuracy claim.

Workflow runs call the inspector's actual run_demo function. Component pairs use the
same Chatbot verifier chain plus extractive policy verification on controlled evidence.
The policy labels are authored fixture judgments; comparison labels come from exact
record/field expectations, never from the gate verdict. No verifier rules are tuned here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finbot.config import Settings  # noqa: E402
from finbot.demo import DemoModel, run_demo  # noqa: E402
from finbot.guardrails import LocalGuardrail  # noqa: E402
from finbot.knowledge import Index  # noqa: E402
from finbot.orchestrator import Chatbot  # noqa: E402
from finbot.policy_documents import PolicyDocumentVerifier  # noqa: E402
from finbot.tools import InMemoryLogs, InMemoryTxns, ToolBox  # noqa: E402
from finbot.verification import VerifierChain  # noqa: E402

FIXTURES = ROOT / "data/naacl2027/support-policies.json"
PROTOCOL = "finbot-varied-support-v1"
ASSERTION = re.compile(r"Transaction (txn_[A-Za-z0-9]{6,}) was (\w+) for (\d+\.\d{2}) ([A-Z]{3})")


def policy_cases() -> list[dict]:
    return json.loads(FIXTURES.read_text())


def comparison_cases() -> list[dict]:
    # Shared values are deliberate controls, not failed fault injections. New IDs
    # avoid accidentally using the inspector presets' transaction-log evidence.
    specs = [
        ("different-values", "18.75", "92.40", "USD", "USD", "declined", "approved"),
        ("mixed-currency", "210.00", "47.25", "EUR", "GBP", "approved", "declined"),
        ("equal-amount", "200.00", "200.00", "USD", "EUR", "declined", "approved"),
        ("equal-status", "0.50", "1500.00", "GBP", "GBP", "approved", "approved"),
        ("unknown-outcome", "64.80", "31.60", "USD", "USD", "unknown", "approved"),
        ("pending-vs-failed", "7.35", "810.20", "EUR", "USD", "pending", "failed"),
    ]
    cases = []
    for i, (name, a, b, ca, cb, sa, sb) in enumerate(specs):
        records = [{"txn_id": f"txn_EVAL{i:03d}{j}", "tenant_id": "m_100",
                    "amount": amount, "currency": currency, "status": status}
                   for j, (amount, currency, status) in enumerate(((a, ca, sa), (b, cb, sb)))]
        cases.append({"id": name, "records": records})
    return cases


def comparison_answer(records: list[dict]) -> str:
    return " ".join(f"Transaction {r['txn_id']} was {r['status']} for {r['amount']} {r['currency']}."
                    for r in records)


def comparison_fields(answer: str, expected: list[dict]) -> dict:
    """Narrow independent scorer for this suite's scripted sentence format.

    It checks bindings, completeness, duplicates and extra matching assertions.
    It does not certify other prose/advice or evaluate arbitrary natural language.
    """
    wanted = Counter((r["txn_id"], r["status"], r["amount"], r["currency"]) for r in expected)
    observed = Counter(ASSERTION.findall(answer))
    return {"expected": [list(v) for v in wanted.elements()],
            "observed": [list(v) for v in observed.elements()],
            "all_requested_fields_correct": observed == wanted}


def component_chain() -> VerifierChain:
    # Use Chatbot's actual chain, not a separately maintained subset. Explicit
    # offline dependencies prevent environment variables from enabling providers.
    settings = Settings(llm_provider="fake", guardrail_provider="local", store_provider="sqlite",
                        auth_mode="hmac", repair_attempts=1, record_fallback=True, routing="single",
                        policy_verification="extractive", tool_policy_path="")
    toolbox = ToolBox(InMemoryTxns([]), InMemoryLogs([]), Index(), domains=["payments"])
    bot = Chatbot(DemoModel("none", False), LocalGuardrail(), toolbox, settings)
    return VerifierChain([*bot.gate.chain.verifiers, PolicyDocumentVerifier("extractive")])


def paired_result(chain, *, case_id, family, mutation, question, evidence, clean, changed,
                  target_reason, expected_complete) -> dict:
    before, after = chain.check(clean, evidence, None), chain.check(changed, evidence, None)
    noop = changed == clean
    # Known invalid/omitted fixture content remains invalid even if it passes.
    new_rejection = before.action == "allow" and after.action == "block"
    new_reasons = sorted(set(after.reasons) - set(before.reasons))
    return {"id": case_id, "family": family, "mutation": mutation, "question": question,
            "evidence": evidence, "clean": clean, "changed": changed,
            "expected_changed_supported_and_complete": expected_complete,
            "no_op_control": noop, "clean_check": asdict(before), "changed_check": asdict(after),
            "transition": f"{before.action}_to_{after.action}", "new_rejection": new_rejection,
            "new_reasons": new_reasons, "target_reason_prefix": target_reason,
            "target_reason_observed": new_rejection and bool(target_reason)
                and any(r.startswith(target_reason) for r in new_reasons),
            "missed_error": not expected_complete and after.action == "allow"}


def policy_pairs(chain) -> tuple[list[dict], list[dict]]:
    rows, paraphrases = [], []
    for case in policy_cases():
        url = f"https://policies.example.com/{case['id']}"
        unrelated_url = "https://policies.example.com/contact"
        # Both URLs occur in evidence. A wrong-source rejection must be about
        # support, not simply an unseen URL. All policies are fictional fixtures.
        docs = [{"text": case["source"], "source_url": url, "chunk_id": case["id"],
                 "version": 1, "updated": "2026-11-01"},
                {"text": "Contact support for account questions.", "source_url": unrelated_url,
                 "chunk_id": "contact", "version": 1, "updated": "2026-11-01"}]
        evidence = [{"name": "search_knowledge_base", "input": {"query": case["question"]},
                     "result": {"status": "found", "source": "knowledge_base", "data": docs}}]
        cite = lambda text, source=url: f"{text} (source: {source})"
        clean = cite(case["source"])
        variants = {key: cite(case[key]) for key in ("rule_reversal", "changed_condition", "missing_exception")}
        variants.update({"missing_citation": case["source"],
                         "wrong_citation": cite(case["source"], unrelated_url),
                         "unsupported_conclusion": cite(case["source"] + " " + case["unsupported_conclusion"])})
        for mutation, changed in variants.items():
            rows.append(paired_result(chain, case_id=f"policy/{case['id']}/{mutation}", family="policy",
                mutation=mutation, question=case["question"], evidence=evidence, clean=clean, changed=changed,
                target_reason="policy_unsupported:", expected_complete=False))
        answer = cite(case["paraphrase"])
        paraphrases.append({"id": f"policy/{case['id']}/paraphrase", "question": case["question"],
                            "evidence": evidence, "answer": answer, "expected_supported_and_complete": True,
                            "check": asdict(chain.check(answer, evidence, None))})
    return rows, paraphrases


def comparison_pairs(chain) -> list[dict]:
    rows = []
    for case in comparison_cases():
        for reverse in (False, True):
            records = copy.deepcopy(case["records"][::-1] if reverse else case["records"])
            question = "Compare " + " and ".join(r["txn_id"] for r in records) + ": amounts, currencies and statuses?"
            evidence = [{"name": "get_transaction", "input": {"txn_id": r["txn_id"]},
                         "result": {"status": "found", "source": "txn_db", "data": r}} for r in records]
            clean = comparison_answer(records)
            for mutation, field in (("swap_amount", "amount"), ("swap_status", "status"),
                                    ("swap_currency", "currency"), ("omit_record", None)):
                changed_records = copy.deepcopy(records)
                if field:
                    changed_records[0][field], changed_records[1][field] = records[1][field], records[0][field]
                else:
                    changed_records.pop()
                changed = comparison_answer(changed_records)
                valid = comparison_fields(changed, records)["all_requested_fields_correct"]
                reason = {"amount": "value_from_other_record:amount:", "status": "status_mismatch:",
                          "currency": "value_from_other_record:currency:", None: None}[field]
                rows.append(paired_result(chain, case_id=f"comparison/{case['id']}/{int(reverse)}/{mutation}",
                    family="comparison", mutation=mutation, question=question, evidence=evidence,
                    clean=clean, changed=changed, target_reason=reason, expected_complete=valid))
    return rows


def workflow_comparisons() -> list[dict]:
    rows = []
    for case in comparison_cases():
        for reverse in (False, True):
            records = case["records"][::-1] if reverse else case["records"]
            question = "Compare " + " and ".join(r["txn_id"] for r in records) + ": what are their amounts, currencies and statuses?"
            for fault in ("none", "swap_once"):
                result = run_demo(question, fault, records=case["records"], live=False)
                fields = comparison_fields(result["final"]["answer"], records)
                found = [c["result"]["data"]["txn_id"] for c in result["evidence"]
                         if c["name"] == "get_transaction" and c["result"]["status"] == "found"]
                checks = {"requested_records_retrieved": set(found) == {r["txn_id"] for r in records},
                          "all_requested_fields_correct": fields["all_requested_fields_correct"],
                          "answer_released": result["final"]["blocked_by"] is None}
                rows.append({"id": f"comparison/{case['id']}/{int(reverse)}/{fault}", "family": "comparison",
                             "expected_records": records, "field_score": fields, "checks": checks,
                             "passed": all(checks.values()), "result": stable_result(result)})
    # Negative retrieval controls: absent and another tenant's record must not leak.
    own = comparison_cases()[0]["records"][0]
    other = {"txn_id": "txn_PRIVATE01", "tenant_id": "m_200", "status": "approved",
             "amount": "9876.54", "currency": "GBP"}
    for missing_id in (other["txn_id"], "txn_ABSENT01"):
        for reverse in (False, True):
            ids = [own["txn_id"], missing_id][::(-1 if reverse else 1)]
            result = run_demo("Compare " + " and ".join(ids) + ": amounts and statuses?", records=[own, other])
            fields = comparison_fields(result["final"]["answer"], [own])
            checks = {"available_record_correct": fields["all_requested_fields_correct"],
                      "missing_record_reported": "could not find" in result["final"]["answer"].lower(),
                      "private_value_absent": "9876.54" not in json.dumps(result),
                      "missing_lookup_not_found": any(c["input"].get("txn_id") == missing_id
                          and c["result"]["status"] == "not_found" for c in result["evidence"])}
            rows.append({"id": f"comparison/unavailable/{missing_id}/{int(reverse)}", "family": "comparison",
                         "expected_records": [own], "field_score": fields, "checks": checks,
                         "passed": all(checks.values()), "result": stable_result(result)})
    return rows


def stable_result(result: dict) -> dict:
    result = copy.deepcopy(result)
    result["metrics"].pop("latency_ms", None)  # No scripted latency claim; reproducible artifact.
    return result


def policy_content_checks(result: dict, required: list[str]) -> dict:
    answer = result["final"]["answer"]
    return {"required_policy_content": all(s in answer for s in required),
            "answer_released": result["final"]["blocked_by"] is None,
            "source_or_abstention": "https://wiki.example.com/" in answer or "won't guess" in answer}


def workflow_policies() -> list[dict]:
    # Manual task expectations independent of retrieved rank and verifier decisions.
    surcharge = ["capped at 3 percent", "disclosed before payment", "Debit and prepaid cards cannot be surcharged"]
    cases = [
        ("surcharge-general", "What are the surcharge rules?", surcharge),
        ("surcharge-debit", "Can debit and prepaid cards be surcharged?", surcharge[-1:]),
        ("surcharge-cap", "What is the credit card surcharge cap and disclosure rule?", surcharge[:2]),
        ("code-05", "What does decline code 05 Do not honor mean?", ["issuing bank declined without a specific reason"]),
        ("code-51", "What does code 51 Insufficient funds mean?", ["insufficient available balance"]),
        ("missing-policy", "What are mortgage early repayment penalties?", ["don't have documentation"]),
    ]
    rows = []
    for name, question, required in cases:
        for fault in ("none", "policy_once"):
            result = run_demo(question, fault, live=False)
            checks = policy_content_checks(result, required)
            rows.append({"id": f"policy/{name}/{fault}", "family": "policy", "required_content": required,
                         "checks": checks, "passed": all(checks.values()), "result": stable_result(result)})
    return rows


def pair_summary(rows: list[dict]) -> dict:
    mutations = [r for r in rows if not r["no_op_control"]]
    eligible = [r for r in mutations if r["clean_check"]["action"] == "allow"]
    return {"attempts": len(rows), "actual_mutations": len(mutations),
            "no_op_controls": len(rows) - len(mutations),
            "no_op_controls_blocked": sum(r["changed_check"]["action"] == "block" for r in rows if r["no_op_control"]),
            "clean_controls_blocked": sum(r["clean_check"]["action"] == "block" for r in mutations),
            "corrupted_drafts_blocked": sum(r["changed_check"]["action"] == "block" for r in mutations),
            "accepted_clean_controls": len(eligible),
            "new_rejections": sum(r["new_rejection"] for r in mutations),
            "target_reason_observed": sum(r["target_reason_observed"] for r in mutations),
            "missed_errors": sum(r["missed_error"] for r in mutations)}


def evaluate() -> dict:
    chain = component_chain()
    policies, paraphrases = policy_pairs(chain)
    pairs = policies + comparison_pairs(chain)
    workflows = workflow_comparisons() + workflow_policies()
    sources = ["scripts/naacl2027/evaluate_support.py", "data/naacl2027/support-policies.json",
               "finbot/demo.py", "finbot/orchestrator.py", "finbot/verification.py", "finbot/guardrails.py",
               "finbot/policy_documents.py", "finbot/binding.py", "finbot/tools.py", "finbot/llm.py"]
    return {"protocol": PROTOCOL, "evaluation_type": "authored_synthetic_diagnostics",
            "new_model_calls": 0, "human_participants": 0, "verifier_rules_changed": False,
            "sources": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
            "workflow_summary": {family: {"runs": len(rs := [r for r in workflows if r['family'] == family]),
                "passed": sum(r["passed"] for r in rs)} for family in ("policy", "comparison")},
            "pair_summary": {family: pair_summary([r for r in pairs if r["family"] == family])
                             for family in ("policy", "comparison")},
            "by_mutation": {f"{family}/{mutation}": pair_summary([r for r in pairs
                if (r["family"], r["mutation"]) == (family, mutation)])
                for family, mutation in sorted({(r["family"], r["mutation"]) for r in pairs})},
            "paraphrase_controls": {"supported": len(paraphrases),
                                    "blocked": sum(r["check"]["action"] == "block" for r in paraphrases)},
            "limitations": [
                "Authored synthetic cases, not held-out natural requests, users or live-model accuracy.",
                "Orders and mutations share fixtures; counts are dependent, not independent trials.",
                "Workflow runs use the inspector's run_demo function and existing demo policies.",
                "Component probes use controlled tool envelopes; they do not test retrieval or generation.",
                "Policy fixture labels are author judgments, not independent human annotations.",
                "Field/content scorers are independent of gate decisions but limited to specified content and formats.",
                "A new rejection and a matching reason indicate a targeted diagnostic, not semantic proof.",
                "Supported paraphrases test the deliberate extractive-mode restriction, not a violation of that contract.",
            ], "workflow_rows": workflows, "paired_rows": pairs, "paraphrase_rows": paraphrases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/naacl2027/varied-support.json")
    args = parser.parse_args()
    report = evaluate()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("workflow_summary", "pair_summary", "paraphrase_controls")}, indent=2))
    # Missed errors are findings, not harness failures. Preserve them in the report.


if __name__ == "__main__":
    main()
