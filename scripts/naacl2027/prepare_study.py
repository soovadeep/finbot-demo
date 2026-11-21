"""Prepare counterbalanced assignments and matched JSON traces, without inventing participants."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finbot.demo import SCENARIOS  # noqa: E402

TASKS = [
    ("T1", "correct", "Which record supports this answer, and what can a passing check establish?"),
    ("T2", "repair", "What was wrong in the first draft, and how did the final answer change?"),
    ("T3", "fallback", "Why was fallback used, and who constructed the final answer?"),
    ("T4", "timeout", "Is this payment known to have failed, and what should happen before retry?"),
    ("T5", "pair", "Associate each amount and status with its transaction."),
    ("T6", "binding", "Why was the draft rejected when both amounts existed?"),
    ("T7", "refusal", "Why was the answer withheld, and why was no record fallback shown?"),
    ("T8", "policy", "Why did the citation fail to justify the draft? Give the supporting source sentence."),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", type=Path, default=ROOT / "results/naacl2027/scenario-traces.json")
    parser.add_argument("--out", type=Path, default=ROOT / "results/naacl2027/study-kit")
    args = parser.parse_args()
    traces = json.loads(args.traces.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    assignments = [(rotation, first) for rotation in range(8) for first in ("ui", "json")]
    random.Random(20261119).shuffle(assignments)
    with (args.out / "assignments.csv").open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["assignment", "order", "task", "preset", "mode"])
        for slot, (rotation, first) in enumerate(assignments, 1):
            for position in range(8):
                task, preset, _ = TASKS[(position + rotation) % 8]
                mode = first if position % 2 == 0 else "json" if first == "ui" else "ui"
                writer.writerow([f"A{slot:02}", position + 1, task, preset, mode])
    prompts = [{"task": task, "preset": preset, "prompt": prompt} for task, preset, prompt in TASKS]
    (args.out / "task-prompts.json").write_text(json.dumps(prompts, indent=2) + "\n")
    for case in SCENARIOS:
        # Give JSON readers the same title/description/fault hints present in the UI.
        bundle = {"scenario": case, "trace": traces[case["id"]]}
        (args.out / f"trace-{case['id']}.json").write_text(json.dumps(bundle, indent=2) + "\n")
    (args.out / "responses-template.csv").write_text(
        "participant_code,assignment,task,mode,seconds,timeout,assisted,response,"
        "rater_1,rater_2,adjudicated_score,notes\n")
    cases_path = ROOT / "data/naacl2027/policy_cases.jsonl"
    cases = [json.loads(line) for line in cases_path.read_text().splitlines()]
    random.Random(20261119).shuffle(cases)
    with (args.out / "policy-annotation.csv").open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["item", "candidate", "sources", "kb_lookup", "supported", "complete", "notes"])
        for i, case in enumerate(cases, 1):
            # Internal chunk IDs contain fixture categories; do not reveal them to annotators.
            sources = [{k: v for k, v in s.items() if k != "chunk_id"} for s in case["sources"]]
            writer.writerow([i, case["candidate"], json.dumps(sources), case["kb_lookup"], "", "", ""])
    (args.out / "facilitator-policy-key.json").write_text(json.dumps(
        [{"item": i, "case": case["id"]} for i, case in enumerate(cases, 1)], indent=2) + "\n")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.out.iterdir())
              if p.is_file() and p.name != "manifest.json"}
    (args.out / "manifest.json").write_text(json.dumps({
        "status": "materials only; no participant responses", "seed": 20261119,
        "human_participants": 0, "assignment_slots": 16, "tasks_per_slot": 8, "sha256": hashes,
        "source_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "trace_input_sha256": hashlib.sha256(args.traces.read_bytes()).hexdigest(),
        "policy_corpus_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
    }, indent=2) + "\n")
    print("Prepared 16 balanced slots, 8 matched traces, task prompts and blank interface/policy annotation sheets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
