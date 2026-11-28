"""Authored role-substitution diagnostics and retrospective cached-draft replay.

No model calls, participants, new held-out claims or independent semantic labels.
Paired corruptions reuse existing values: the variable is the claimed role/owner.
The production guardrail is ablated by removing checks, not reimplementing them.
Historical drafts and their author audit are immutable inputs, not new generation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finbot.demo import run_demo  # noqa: E402
from finbot.financial_roles import FinancialRoleVerifier  # noqa: E402
from finbot.verification import VerifierChain  # noqa: E402
from scripts.naacl2027.evaluate_support import component_chain  # noqa: E402


def envelope(data):
    return {"name": "get_transaction", "input": {"txn_id": data["txn_id"]},
            "result": {"status": "found", "source": "txn_db", "data": data}}


def cases():
    rows = []
    for i in range(6):
        payment, refund = f"{200 + i * 17}.00", f"{50 + i * 3}.00"
        expected, actual = f"2026-11-{10 + i:02}", f"2026-11-{20 + i:02}"
        record = {"txn_id": f"txn_ROLETEST{i}", "amount": payment, "currency": "USD", "status": "approved",
                  "refund": {"status": "succeeded", "amount": refund},
                  "settlement": {"status": "settled", "expected_date": expected, "actual_date": actual}}
        other = copy.deepcopy(record)
        other["txn_id"] = f"txn_ROLEOTHER{i}"
        other["refund"]["amount"] = f"{90 + i}.00"
        for style in ("label", "prose"):
            prefix = record["txn_id"] + ": "
            ed = lambda value: f"Expected settlement date: {value}." if style == "label" else f"Settlement was expected on {value}."
            ad = lambda value: f"Actual settlement date: {value}." if style == "label" else f"The transaction was settled on {value}."
            ra = lambda value: f"Refund amount: {value}." if style == "label" else f"A refund of ${value} was processed."
            pa = lambda value: f"Payment amount: {value}." if style == "label" else f"The original payment amount was ${value}."

            def add(family, clean, changed, records, *, supported=False):
                rows.append({"id": f"{family}/{i}/{style}", "family": family, "style": style,
                             "evidence": [envelope(copy.deepcopy(r)) for r in records],
                             "clean": prefix + clean, "changed": prefix + changed,
                             "expected_changed_supported": supported,
                             "label_source": "authored field-role substitution; not a gate verdict"})

            missing = copy.deepcopy(record)
            del missing["settlement"]["actual_date"]
            add("expected_as_actual", ed(expected), ad(expected), [missing])
            add("swap_date_roles", ed(expected) + " " + ad(actual), ed(actual) + " " + ad(expected), [record])
            add("refund_uses_payment", ra(refund), ra(payment), [record])
            add("payment_uses_refund", pa(payment), pa(refund), [record])
            add("wrong_record_refund", ra(refund), ra(other["refund"]["amount"]), [record, other])
            equal = copy.deepcopy(record)
            equal["refund"]["amount"] = payment
            equal["settlement"]["actual_date"] = expected
            equal_text = ed(expected) + " " + ad(expected) + " " + ra(payment) + " " + pa(payment)
            add("equal_value_control", equal_text, equal_text, [equal], supported=True)
    return rows


def historical_replay():
    base = ROOT / "results/naacl2027/live-writer"
    drafts = [json.loads(line) for line in (base / "rows.jsonl").read_text().splitlines()]
    audit = json.loads((base / "audit.json").read_text())
    records = {r["txn_id"]: r for r in map(json.loads, (ROOT / "data/test/transactions.jsonl").read_text().splitlines())}
    verifier = FinancialRoleVerifier()
    rows = []
    for label in audit["rows"]:
        draft = drafts[label["row"]]
        assert draft["record_id"] == label["record_id"] and draft["fault"] == "none" and draft["outcome"] == "passed"
        result = verifier.check(draft["answer"], [envelope(records[draft["record_id"]])])
        rows.append({"row": label["row"], "record_id": draft["record_id"],
                     "historical_issues": label["issues"], "role_check": asdict(result)})
    date_errors = [r for r in rows if any("expected settlement" in issue for issue in r["historical_issues"])]
    supported = [r for r in rows if not r["historical_issues"]]
    omissions = [r for r in rows if any("omits" in issue for issue in r["historical_issues"])]
    return {"type": "retrospective_component_replay_on_previously_inspected_drafts",
            "drafts": len(rows), "known_date_errors": len(date_errors),
            "known_date_errors_blocked": sum(r["role_check"]["action"] == "block" for r in date_errors),
            "author_labelled_supported": len(supported),
            "supported_blocked": sum(r["role_check"]["action"] == "block" for r in supported),
            "known_omissions_still_allowed": sum(r["role_check"]["action"] == "allow" for r in omissions),
            "rows": rows}


def evaluate():
    full = component_chain()
    chains = {
        "existing_without_record_binding": VerifierChain([v for v in full.verifiers if v.name not in {"binding", "financial_roles"}]),
        "existing_guardrail": VerifierChain([v for v in full.verifiers if v.name != "financial_roles"]),
        "with_financial_roles": full,
    }
    rows = cases()
    for row in rows:
        row["checks"] = {name: {side: asdict(chain.check(row[side], row["evidence"], None))
                                 for side in ("clean", "changed")} for name, chain in chains.items()}

    def counts(selected, name):
        return {"pairs": len(selected),
                "clean_accepted": sum(r["checks"][name]["clean"]["action"] == "allow" for r in selected),
                "changed_blocked": sum(r["checks"][name]["changed"]["action"] == "block" for r in selected),
                "new_rejections": sum(r["checks"][name]["clean"]["action"] == "allow" and
                                      r["checks"][name]["changed"]["action"] == "block" for r in selected)}

    summary = {name: {family: counts([r for r in rows if r["family"] == family], name)
                     for family in sorted({r["family"] for r in rows})} for name in chains}
    # Deliberately outside the finite grammar: report misses, do not quietly
    # expand the parser and call the same probes independent validation.
    boundary = []
    evidence = cases()[0]["evidence"]
    for text in ("The transaction settled on November 10, 2026.", "You got $200.00 back."):
        boundary.append({"answer": text, "expected_supported": False,
                         "role_check": asdict(FinancialRoleVerifier().check(text, evidence)),
                         "full_check": asdict(full.check(text, evidence, None))})
    workflows = []
    for fault in ("none", "settlement_once", "refund_once", "amount_always"):
        result = run_demo("What are the settlement and refund details for txn_ROLE0001?", fault)
        result.get("metrics", {}).pop("latency_ms", None)
        answer = result["final"]["answer"]
        workflows.append({"fault": fault, "result": result,
                          "required_fixture_details_present": all(s in answer for s in
                           ("txn_ROLE0001", "Expected settlement date: 2026-11-20", "Refund amount: 50.00",
                            "An actual settlement date is not recorded"))})
    sources = ["finbot/financial_roles.py", "finbot/orchestrator.py", "finbot/verification.py", "finbot/demo.py",
               "finbot/llm.py", "finbot/binding.py", "finbot/guardrails.py", "finbot/recordanswer.py",
               "scripts/naacl2027/evaluate_financial_roles.py", "scripts/naacl2027/evaluate_support.py",
               "results/naacl2027/live-writer/rows.jsonl", "results/naacl2027/live-writer/audit.json",
               "data/test/transactions.jsonl"]
    return {"protocol": "finbot-financial-roles-v1", "evaluation_type": "authored_development_diagnostics",
            "new_model_calls": 0, "participants": 0,
            "corrupt_pairs": sum(not r["expected_changed_supported"] for r in rows),
            "equal_value_controls": sum(r["expected_changed_supported"] for r in rows),
            "summary": summary, "historical_replay": historical_replay(), "boundary_probes": boundary,
            "workflows": workflows, "paired_rows": rows,
            "sources": {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in sources},
            "limitations": ["Six authored records, two wordings per mutation; dependent cases, not customer accuracy.",
                            "Known audit errors informed the implementation; retrospective replay is not held-out validation.",
                            "Finite English grammar and explicit ISO dates; implicit roles and omissions remain unchecked.",
                            "Field matches assume correct adapter semantics and do not authenticate source records.",
                            "No new live answers, human study, or independent semantic annotation."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/naacl2027/financial-roles.json")
    args = parser.parse_args()
    result = evaluate()
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"summary": result["summary"],
                      "historical_replay": {k: v for k, v in result["historical_replay"].items() if k != "rows"},
                      "boundary_misses": sum(r["full_check"]["action"] == "allow" for r in result["boundary_probes"])}, indent=2))


if __name__ == "__main__":
    main()
