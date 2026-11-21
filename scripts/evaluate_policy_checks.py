"""Compare offline policy components on authored regression candidates, without model calls.

This does not run retrieval, the financial chain, repair or human annotation. It is
not a held-out study. Supported paraphrases deliberately expose strict-mode false blocks.

  python scripts/evaluate_policy_checks.py --out results/verification/policy-checks.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from finbot.policy_documents import PolicyDocumentVerifier


def evaluate(cases: list[dict]) -> tuple[dict, list[dict]]:
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("cases must have unique IDs and must not be empty")
    rows, summary = [], {}
    for mode in ("off", "extractive", "strict"):
        counts: Counter = Counter()
        for case in cases:
            if type(case["expected_supported"]) is not bool or case["expected_strict"] not in ("allow", "block"):
                raise ValueError("invalid regression label")
            log = [{"name": "search_knowledge_base", "input": {"query": case["question"]},
                    "result": {"status": "found", "data": case["sources"]}}] if case["kb_lookup"] else []
            verifier = PolicyDocumentVerifier(mode, as_of=date.fromisoformat(case["as_of"]),
                                              max_age_days=case["max_age_days"])
            result = verifier.check(case["candidate"], log, None)
            support = "supported" if case["expected_supported"] else "unsupported"
            counts[f"{support}_{'allowed' if result.action == 'allow' else 'rejected'}"] += 1
            regression_pass = result.action == case["expected_strict"] if mode == "strict" else None
            rows.append({"case": case["id"], "category": case["category"], "mode": mode,
                         "expected_supported": case["expected_supported"], "action": result.action,
                         "reasons": result.reasons,
                         "strict_regression_pass": regression_pass})
        summary[mode] = {k: counts[k] for k in ("supported_allowed", "supported_rejected",
                                               "unsupported_allowed", "unsupported_rejected")}
    return summary, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "data/verification/policy_checks.jsonl")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    summary, rows = evaluate(cases)
    report = {
        "scope": "authored component regression; no live model or independent annotation; not held out",
        "cases": len(cases),
        "sha256": {"cases": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                   **{name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                      ("finbot/policy_documents.py", "finbot/provenance.py", "finbot/recordanswer.py",
                       "scripts/evaluate_policy_checks.py")}},
        "summary": summary, "rows": rows,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"scope": report["scope"], "cases": len(cases), "summary": summary}, indent=2))
    return int(any(r["strict_regression_pass"] is False for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
