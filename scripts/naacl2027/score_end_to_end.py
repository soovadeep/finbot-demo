"""Score record identification AND independently audited answer quality.

prepare creates unfilled annotation forms, never labels. score leaves the overall
rate undefined while potentially successful answers remain unassessed. Gate verdicts
and scripted expected-field checks are deliberately not used as quality labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def identity(row: dict) -> str:
    return f"{row['case']}:{row['fault']}"


def fingerprint(row: dict) -> str:
    return hashlib.sha256(json.dumps({k: row[k] for k in ("case", "fault", "target_id", "selected_id", "answer")},
                                    sort_keys=True).encode()).hexdigest()


def prepare(rows: list[dict]) -> list[dict]:
    return [{"run": identity(r), "source_sha256": fingerprint(r), "reviewer": "", "supported": None,
             "complete": None, "notes": ""} for r in rows if r["answer"] is not None]


def score(rows: list[dict], annotations: list[dict]) -> dict:
    if not rows or len({identity(r) for r in rows}) != len(rows):
        raise ValueError("Supply nonempty runs with unique case/fault identities.")
    by_id = {identity(r): r for r in rows}
    audits = {}
    for audit in annotations:
        key = audit.get("run")
        if key not in by_id or key in audits or audit.get("source_sha256") != fingerprint(by_id[key]):
            raise ValueError("Unknown, duplicate or stale audit.")
        if not isinstance(audit.get("reviewer"), str) or not audit["reviewer"].strip():
            raise ValueError("An independent reviewer must fill each submitted audit.")
        if any(type(audit.get(k)) is not bool for k in ("supported", "complete")):
            raise ValueError("Supported/complete need explicit independent boolean judgments.")
        audits[key] = audit
    outcomes = []
    for row in rows:
        audit = audits.get(identity(row))
        if row["target_id"] is None:
            result = "appropriate_abstention" if row["selected_id"] is None and row["answer"] is None else "wrong_action"
        elif row["selected_id"] != row["target_id"]:
            result = "wrong_record" if row["selected_id"] is not None else "unresolved"
        elif not row["answer"]:
            result = "missing_answer"
        elif audit is None:
            result = "unassessed_answer"
        else:
            result = "success" if audit["supported"] and audit["complete"] else "unsupported_or_incomplete"
        outcomes.append({"run": identity(row), "outcome": result})
    actionable = sum(r["target_id"] is not None for r in rows)
    successes = sum(r["outcome"] == "success" for r in outcomes)
    unassessed = sum(r["outcome"] == "unassessed_answer" for r in outcomes)
    return {"actionable_runs": actionable, "successes": successes, "unassessed_answers": unassessed,
            "end_to_end_success_rate": successes / actionable if actionable and not unassessed else None,
            "definition": "Correct target selected AND final answer independently judged supported AND complete.",
            "limitations": "Reviewer independence must be established by the study procedure. "
                "Authored workflow replays remain regression cases, not customer-accuracy samples.",
            "outcomes": outcomes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "score"))
    parser.add_argument("--runs", type=Path, required=True, help="JSON report with a rows list")
    parser.add_argument("--annotations", type=Path, help="JSON list of independently completed judgments")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        rows = json.loads(args.runs.read_text())["rows"]
        annotations = json.loads(args.annotations.read_text()) if args.annotations else []
        report = prepare(rows) if args.command == "prepare" else score(rows, annotations)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(args.out)


if __name__ == "__main__":
    main()
