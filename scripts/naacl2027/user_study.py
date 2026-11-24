"""Allocate a planned pilot or analyze collected exports; never invent participants.

python scripts/naacl2027/user_study.py allocate --participants 24 --out assignments.json
python scripts/naacl2027/user_study.py analyze collected/*.json --out pilot-summary.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from finbot.usability import ARMS, PROTOCOL, TASKS, summarize  # noqa: E402


def allocate(participants: int, seed: int) -> dict:
    cells = [(arm, task) for arm in ARMS for task in TASKS]
    if participants <= 0 or participants % len(cells):
        raise ValueError("Planned slots must be a positive multiple of four for balanced arm/task cells.")
    assignments = cells * (participants // len(cells))
    random.Random(seed).shuffle(assignments)
    return {"protocol": PROTOCOL, "status": "planned_not_collected", "seed": seed,
            "slots": [{"participant_code": f"P{i:03d}", "arm": arm, "task": task,
                "path": f"/pilot?participant=P{i:03d}&arm={arm}&task={task}"}
                for i, (arm, task) in enumerate(assignments, 1)]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("allocate")
    plan.add_argument("--participants", type=int, required=True)
    plan.add_argument("--seed", type=int, default=2027)
    plan.add_argument("--out", type=Path, required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("exports", nargs="+", type=Path)
    analyze.add_argument("--allow-rehearsal", action="store_true", help="infrastructure checks only")
    analyze.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = (allocate(args.participants, args.seed) if args.command == "allocate" else
                  summarize([json.loads(p.read_text()) for p in args.exports], allow_rehearsal=args.allow_rehearsal))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report.get('status', report.get('mode'))}: {args.out}")


if __name__ == "__main__":
    main()
