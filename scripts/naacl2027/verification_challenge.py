"""Authored matched errors, separate from naturally occurring live-writer errors.

prepare -> freeze -> run. All operations are offline; existing artifacts are never
overwritten. Expected labels are construction-based, not inferred from gate decisions.
The blind form omits sides, mutation names, expected labels and verifier outcomes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data/naacl2027/verification-challenge-v1"
OUT = ROOT / "results/naacl2027/verification-challenge-v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write("\n")


def sources():
    paths = [*sorted((ROOT / "finbot").rglob("*.py")), Path(__file__),
             ROOT / "scripts/naacl2027/evaluate_support.py"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def record_log(*records):
    return [{"name": "get_transaction", "input": {"txn_id": r["txn_id"]},
             "result": {"status": "found", "source": "txn_db", "data": r}} for r in records]


def page(text, slug, score=2.0):
    return {"text": text, "source_url": f"https://kb.example.test/{slug}",
            "chunk_id": f"{slug}:v1:0", "version": 1, "updated": "2026-11-24", "score": score}


def doc_log(*pages):
    return [{"name": "search_knowledge_base", "input": {"query": "policy"},
             "result": {"status": "found", "source": "knowledge_base", "data": list(pages)}}]


def quoted(p):
    return f"{p['text']} (source: {p['source_url']})"


def build_cases():
    rows = []

    def add(family, i, question, evidence, clean, corrupted, basis, *, supported=False, complete=True):
        rows.append({"id": f"{family}-{i}", "family": family, "question": question,
                     "evidence": copy.deepcopy(evidence), "label_basis": basis,
                     "clean": {"answer": clean, "supported": True, "complete": True},
                     "corrupted": {"answer": corrupted, "supported": supported, "complete": complete}})

    for i, (amount, refund) in enumerate(((137.25, 27.25), (246.80, 46.80), (79.45, 19.45), (180.60, 80.60))):
        rid = f"txn_CHAL{i:04d}A"
        other = f"txn_CHAL{i:04d}B"
        a, r = f"{amount:.2f}", f"{refund:.2f}"
        record = {"txn_id": rid, "tenant_id": "m_100", "status": "approved", "amount": a,
                  "currency": "USD", "refund": {"status": "succeeded", "amount": r},
                  "settlement": {"status": "settled", "expected_date": f"2026-11-{10+i:02d}",
                                 "actual_date": f"2026-11-{14+i:02d}"}}
        evidence = record_log(record)
        refund_templates = ["Your refund amount was ${v}.", "Refund amount: {v} USD.",
                            "Your refund came to {v} USD.", "You got ${v} back."]
        clean = refund_templates[i].format(v=r)
        add("refund_role", i, f"How much was refunded on {rid}?", evidence, clean,
            refund_templates[i].format(v=a), "refund.amount is the refund; the larger amount is the payment")
        add("payment_role", i, f"What was the payment amount for {rid}?", evidence,
            f"Your payment amount was ${a}.", f"Your payment amount was ${r}.", "amount is the original payment")
        actual, expected = record["settlement"]["actual_date"], record["settlement"]["expected_date"]
        good_date, bad_date = (actual, expected) if i < 2 else (f"November {14+i}, 2026", f"November {10+i}, 2026")
        add("settlement_role", i, f"When did {rid} actually settle?", evidence,
            f"Transaction {rid} settled on {good_date}.", f"Transaction {rid} settled on {bad_date}.",
            "settlement.actual_date differs from settlement.expected_date")
        add("requested_omission", i, f"How much was refunded on {rid}?", evidence,
            f"Your refund amount was ${r}.", f"Your payment amount was ${a}.",
            "The payment amount is true but does not answer the refund question", supported=True, complete=False)
        b = {**copy.deepcopy(record), "txn_id": other, "amount": f"{amount+41:.2f}", "currency": "GBP"}
        both = record_log(record, b)
        good = f"{rid}: {a} USD. {other}: {b['amount']} GBP."
        question = f"Compare {rid} and {other}: what are their amounts and currencies?"
        add("cross_record_amount", i, question, both, good,
            f"{rid}: {b['amount']} USD. {other}: {a} GBP.", "Amounts are swapped between the two records")
        add("currency_binding", i, question, both, good,
            f"{rid}: {a} GBP. {other}: {b['amount']} USD.", "Currencies are swapped between the two records")
        absent = {k: v for k, v in record.items() if k != "refund"}
        add("missing_fact", i, f"How much was refunded on {rid}?", record_log(absent),
            "The record does not show a refund amount.", f"Your refund amount was ${a}.",
            "The record contains no refund field; the payment amount cannot establish a refund")
        refreshed = {**copy.deepcopy(record), "refund": {"status": "succeeded", "amount": f"{refund+3:.2f}"}}
        add("stale_snapshot", i, f"How much was refunded on {rid}?", record_log(record, refreshed),
            f"Your refund amount was ${refund+3:.2f}.", f"Your refund amount was ${r}.",
            "The later lookup supersedes the old refund amount")
        policy = page("Surcharges apply to credit cards only. Debit and prepaid cards cannot be surcharged.", f"cards-{i}")
        add("policy_negation", i, "Can debit and prepaid cards be surcharged?", doc_log(policy), quoted(policy),
            quoted(policy).replace("cannot", "can"), "The draft reverses the prohibition")
        terms = page(f"Refunds may be requested within {20+i} days of settlement. This excludes final-sale purchases.",
                     f"refunds-{i}")
        add("policy_exception", i, "What are the refund rules, including exceptions?", doc_log(terms), quoted(terms),
            f"Refunds may be requested within {20+i} days of settlement. (source: {terms['source_url']})",
            "The final-sale exception was removed", supported=True, complete=False)
        code = page("Code 51 means the card has insufficient available balance.", f"code-51-{i}", 2.0)
        expired = page("Code 54 means the card has expired.", f"code-54-{i}", 1.0)
        add("wrong_policy_quote", i, "What does decline code 51 mean?", doc_log(code, expired), quoted(code),
            quoted(expired), "The quoted source is authentic but answers a different code question",
            supported=True, complete=False)
        add("policy_paraphrase", i, "Can a prepaid card be surcharged?", doc_log(policy),
            f"A surcharge is not permitted on a prepaid card. (source: {policy['source_url']})",
            f"A surcharge is permitted on a prepaid card. (source: {policy['source_url']})",
            "The clean paraphrase preserves the prohibition; removing 'not' reverses it")
    return {"version": "verification-challenge-v1", "kind": "authored matched stress test",
            "provenance": "Developer-authored with AI assistance, before running the checks. No customer data. "
                          "Expected labels follow explicit field values or documented mutations; no independent labels yet.",
            "scope": "Supplied drafts against the production deterministic chain, not generated error prevalence, "
                     "full conversations, or independent held-out accuracy. No LLM calls.", "pairs": rows}


def blind_form(cases):
    items = []
    for pair in cases["pairs"]:
        for side in ("clean", "corrupted"):
            item = {"question": pair["question"], "evidence": pair["evidence"], "answer": pair[side]["answer"]}
            items.append({"key": digest(item), **item, "supported": None, "complete": None, "rationale": ""})
    unique = {item["key"]: item for item in items}
    return {"reviewer": "", "instructions": "Judge support and completeness independently from the evidence. "
            "Do not consult the report or case labels before submitting this form.",
            "items": [unique[k] for k in sorted(unique)]}


def summarize(rows):
    eligible = [r for r in rows if r["clean"]["action"] == "allow"]
    return {"pairs": len(rows), "correct_rejected": sum(r["clean"]["action"] == "block" for r in rows),
            "incorrect_blocked": sum(r["corrupted"]["action"] == "block" for r in rows),
            "eligible_clean_accepted_pairs": len(eligible),
            "paired_new_rejections": sum(r["corrupted"]["action"] == "block" for r in eligible),
            "unsupported_released": [r["id"] for r in rows if not r["corrupted"]["supported"]
                                     and r["corrupted"]["action"] == "allow"],
            "incomplete_released": [r["id"] for r in rows if not r["corrupted"]["complete"]
                                    and r["corrupted"]["action"] == "allow"]}


def evaluate(cases):
    from finbot.comparison import ComparisonCoverageVerifier
    from finbot.policy_documents import PolicyDocumentVerifier
    from finbot.requested_fields import RequestedInformationVerifier
    from finbot.verification import VerifierChain
    from scripts.naacl2027.evaluate_support import component_chain
    base = component_chain().verifiers[:-1]
    rows = []
    for pair in cases["pairs"]:
        if pair["clean"]["answer"] == pair["corrupted"]["answer"]:
            raise ValueError("unchanged pairs are controls, not corruptions")
        chain = VerifierChain([*base, ComparisonCoverageVerifier(pair["question"]),
                              RequestedInformationVerifier(pair["question"]),
                              PolicyDocumentVerifier("extractive", question=pair["question"])])
        ids = {c["input"]["txn_id"] for c in pair["evidence"] if c["name"] == "get_transaction"}
        focus = next(iter(ids)) if len(ids) == 1 else None
        row = {"id": pair["id"], "family": pair["family"]}
        for side in ("clean", "corrupted"):
            item = pair[side]
            result = chain.check(item["answer"], pair["evidence"], focus)
            row[side] = {"supported": item["supported"], "complete": item["complete"],
                         "action": result.action, "reasons": result.reasons}
        rows.append(row)
    return {"scope": cases["scope"], "label_basis": cases["provenance"], "summary": summarize(rows),
            "by_family": {name: summarize([r for r in rows if r["family"] == name])
                          for name in sorted({r["family"] for r in rows})}, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "freeze", "run", "replay-development"))
    parser.add_argument("--output", type=Path, default=OUT / "report.json")
    args = parser.parse_args()
    if args.command == "prepare":
        cases = build_cases()
        write_new(DATA / "cases.json", cases)
        write_new(OUT / "review-form.json", blind_form(cases))
        print(f"Prepared {len(cases['pairs'])} pairs; no checks run.")
        return
    cases = json.loads((DATA / "cases.json").read_text())
    if args.command == "replay-development":
        if args.output == OUT / "report.json":
            raise SystemExit("Use --output with a new development report path; the frozen report stays unchanged.")
        protocol = json.loads((DATA / "protocol.json").read_text())
        if protocol["cases_sha256"] != digest(cases):
            raise SystemExit("The original challenge cases changed.")
        report = {**evaluate(cases), "kind": "post-fix development replay, not held-out evaluation",
                  "original_protocol_sha256": digest(protocol), "current_sources": sources()}
        write_new(args.output, report)
        print(json.dumps(report["summary"], indent=2))
        return
    if args.command == "freeze":
        write_new(DATA / "protocol.json", {"cases_sha256": digest(cases), "sources": sources(),
                  "base_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  "claim": "Authored stress test; label expectations specified before the first run. "
                           "No paid providers, human labels, or generalisation claim."})
        print("Frozen; no checks run.")
        return
    protocol = json.loads((DATA / "protocol.json").read_text())
    if protocol["cases_sha256"] != digest(cases) or protocol["sources"] != sources():
        raise SystemExit("Cases or runtime changed after freeze; preserve old results and use a new study version.")
    report = {"protocol_sha256": digest(protocol), **evaluate(cases)}
    write_new(args.output, report)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
