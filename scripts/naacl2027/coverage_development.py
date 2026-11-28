"""Development replay on inspected public-v1 questions; never overwrite that study.

The paired corruption appends a lifecycle status contradicted by the fixed record,
including cases where the record lacks that field. It does not simulate error rates.
No output is semantically labelled from the gate's own verdict.
"""
import json
import argparse
import os
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.naacl2027 import public_wording_study as common


def probes(record):
    evidence = [{"name": "get_transaction", "input": {"txn_id": record["txn_id"]},
                 "result": {"status": "found", "source": "txn_db", "data": record}}]
    field = "payment" if record["status"] == "declined" else "settlement" if "settlement" in record else "refund"
    corrupt = f"{field.capitalize()} status: " + ("approved." if field == "payment" else "settled." if field == "settlement" else "succeeded.")
    # Use the real tool evidence when scoring policy guidance elsewhere; these
    # narrow probes contain only the explicit correct or incorrect status claim.
    own_status = (record.get(field) or {}).get("status") if field != "payment" else record["status"]
    clean = f"{field.capitalize()} status: {own_status}." if own_status else f"The record does not show a {field} status."
    from finbot.support_coverage import check
    return {"field": field, "clean": clean, "corrupted": corrupt,
            "clean_check": asdict(check(clean, evidence, "")),
            "corrupted_check": asdict(check(corrupt, evidence, ""))}


def evaluate_cases(cases):
    from finbot.demo import run_demo
    rows = []
    with patch.dict(os.environ, {"FINBOT_DEMO_WRITER": "scripted", "FINBOT_DEMO_SEMANTIC": "off"}):
        for case in cases:
            for condition in ("populated", "missing"):
                result = run_demo(case["question"], records=[case[condition]], live=False)
                result["metrics"].pop("latency_ms", None)
                rows.append({"key": case["id"] + "/" + condition, "question": case["original"],
                             "record": case[condition], "result": result,
                             "status_pair": probes(case[condition])})
    return rows


def summary(rows):
    return {"runs": len(rows), "external_model_calls": 0,
            "released": sum(not r["result"]["final"]["blocked_by"] for r in rows),
            "status_controls_accepted": sum(r["status_pair"]["clean_check"]["action"] == "allow" for r in rows),
            "status_corruptions_rejected": sum(r["status_pair"]["corrupted_check"]["action"] == "block" for r in rows),
            "semantic_accuracy": None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/naacl2027/support-coverage-development.json")
    args = parser.parse_args()
    cases_path = ROOT / "data/naacl2027/public-wording-v1/cases.json"
    rows = evaluate_cases(common.read(cases_path)["cases"])
    report = {"type": "development_replay_of_inspected_public_v1_questions", "sources": common.sources(),
              "evaluator_sha256": common.sha(Path(__file__).read_bytes()),
              "cases_sha256": common.sha(cases_path.read_bytes()), "summary": summary(rows), "rows": rows}
    common.write_new(args.out, report)
    print(json.dumps(report["summary"], indent=2))
