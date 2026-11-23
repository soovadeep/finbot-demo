"""Replay authored cases through the public demo controller, without model calls.

This is a workflow regression evaluation, not a simulated-customer or human study.
Targets and expected outcomes are available only to the scorer, never the controller.
Run: python scripts/naacl2027/evaluate_conversation.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finbot.clarification_conversation import CANDIDATES, SCENARIOS, run_conversation  # noqa: E402

PROTOCOL = "finbot-deployed-workflow-replay-v1"


def message(text: str) -> dict:
    return {"type": "message", "text": text}


def confirm(record: str) -> dict:
    return {"type": "confirm", "record_id": record}


def cases() -> list[dict]:
    openings = {s["id"]: s["opening"] for s in SCENARIOS}
    transfer, card = "txn_EMIX0001", "txn_EMIX0002"
    correction = message("Actually, it was a card payment to Willow Repairs on November 16.")
    unresolved = {"type": "unresolved"}
    return [
        {"id": "vague", "target": transfer, "selected": transfer, "events": [
            message(openings["vague"]), message("Bank transfer"), message("Willow Repairs"), confirm(transfer)]},
        {"id": "complete", "target": transfer, "selected": transfer, "events": [
            message(openings["complete"]), confirm(transfer)]},
        {"id": "tentative", "target": transfer, "selected": transfer, "events": [
            message(openings["uncertain"]), message("Willow Repairs"), confirm(transfer)]},
        {"id": "correct-before-answer", "target": card, "selected": card, "events": [
            message(openings["correction"]), correction, confirm(card)]},
        {"id": "correct-after-answer", "target": card, "selected": card, "events": [
            message(openings["complete"]), confirm(transfer), correction, confirm(card)]},
        {"id": "missing", "target": None, "selected": None, "events": [
            message(openings["missing"]), unresolved]},
        {"id": "wrong-amount", "target": None, "selected": None, "events": [
            message("My $500 bank transfer to Willow Repairs on November 15."), unresolved]},
        # A customer's explicit but mistaken confirmation can authorize the wrong record.
        # A passing answer gate must not turn this into a successful identification.
        {"id": "confident-wrong-confirmation", "target": card, "selected": transfer, "events": [
            message(openings["complete"]), confirm(transfer)]},
        {"id": "cannot-recall", "target": transfer, "selected": None, "events": [
            message("My payment hasn't arrived."), message("I'm not sure"), message("I'm not sure"), unresolved]},
    ]


def score(case: dict, result: dict) -> dict:
    selected, target = result["selected_id"], case["target"]
    financial = result["financial"]
    answer = financial["final"]["answer"] if financial else None
    selection = ("correct" if selected is not None and selected == target else
                 "wrong" if selected is not None else "appropriate_unresolved" if target is None else "unresolved")
    checks = {"expected_selection": selected == case["selected"],
              "question_budget": result["questions_asked"] <= 2,
              "no_answer_without_confirmation": selected is not None or financial is None}
    field_checks = None
    if selected:
        candidate = next(c for c in CANDIDATES if c.record_id == selected)
        status = "pending" if candidate.attributes["kind"] == "Bank transfer" else "declined"
        found = [c["result"]["data"] for c in financial["evidence"] if c["result"]["status"] == "found"]
        # Independent, deliberately narrow checks of the scripted answer; the gate verdict
        # is not used as a factuality label. These do not adjudicate arbitrary prose.
        field_checks = {"record_id": selected in answer, "amount": "200.00" in answer,
                        "currency": "USD" in answer, "record_status": status in answer.lower()}
        checks.update({"selected_record_only": bool(found) and all(r.get("txn_id") == selected for r in found),
                       "expected_fields": all(field_checks.values()),
                       "earlier_answers_invalidated": all(m.get("superseded") for m in result["messages"]
                           if m.get("record_id") and m["record_id"] != selected)})
        expected = {"none": "passed", "status_once": "repaired", "amount_once": "repaired",
                    "amount_always": "record_fallback"}[result["fault"]]
        checks["expected_recovery"] = financial["outcome"] == expected
    return {"case": case["id"], "fault": result["fault"], "target_id": target, "selected_id": selected,
            "selection_outcome": selection, "questions": result["questions_asked"],
            "answer": answer, "answer_outcome": financial["outcome"] if financial else None,
            "answer_field_checks": field_checks,
            "correct_selection_and_expected_fields": selection == "correct" and bool(field_checks)
                and all(field_checks.values()),
            "checks": checks, "regression_passed": all(checks.values())}


def evaluate() -> dict:
    rows = []
    for case in cases():
        for fault in ("none", "status_once", "amount_once", "amount_always"):
            # This is the exact function called by POST /api/conversation. No mocking,
            # alternate selection engine, hidden target, or scenario answer is passed in.
            result = run_conversation({"events": case["events"], "fault": fault, "live": False})
            rows.append(score(case, result))
    sources = ["finbot/clarification_conversation.py", "finbot/demo.py", "finbot/demo_assets/conversation.js",
               "scripts/naacl2027/evaluate_conversation.py"]
    return {"protocol": PROTOCOL, "evaluation_type": "authored_workflow_regression",
            "controller": "finbot.clarification_conversation.run_conversation", "writer": "scripted",
            "human_participants": 0, "new_model_calls": 0,
            "sources": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
            "runs": len(rows), "regressions_passed": sum(r["regression_passed"] for r in rows),
            "selection_outcomes": dict(Counter(r["selection_outcome"] for r in rows)),
            "correct_selection_and_expected_fields": sum(r["correct_selection_and_expected_fields"] for r in rows),
            "limitations": ["Authored events over four synthetic records; no estimate of customer accuracy.",
                "Repeated fault variants are dependent and are not independent users.",
                "Expected-field checks do not establish semantic completeness or general factuality.",
                "The 224-episode ClarificationSession experiment is a separate component study."], "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/naacl2027/conversation-replay.json")
    args = parser.parse_args()
    report = evaluate()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['regressions_passed']}/{report['runs']} workflow regressions passed; "
          f"selection outcomes: {report['selection_outcomes']}")
    if report["regressions_passed"] != report["runs"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
