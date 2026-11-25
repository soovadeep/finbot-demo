"""Development replay of saved live answers; makes no model calls.

Keeps the original studies unchanged. Rechecking an old draft cannot establish
what a model would generate after a changed gate/repair trajectory.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.naacl2027.fresh_llm_study import chain_for, sha, sources, write_new


def evaluate():
    conversation = ROOT / "results/naacl2027/conversation-live-v1-run2"
    paired = ROOT / "results/naacl2027/fresh-llm-v3"
    inputs, probes, drafts = {}, [], []

    def read(path):
        inputs[str(path.relative_to(ROOT))] = sha(path.read_bytes())
        return json.loads(path.read_text())

    for path in sorted(conversation.glob("run-*.json")):
        run = read(path)
        probe = next(t for t in run["trace"] if t["probe"])
        for index, call in enumerate(probe["calls"]):
            if call["response"]["stop_reason"] == "tool_use":
                continue
            answer = "\n".join(c["text"] for c in call["response"]["content"] if c["type"] == "text")
            verdict = chain_for("deterministic", probe["question"]).check(answer, call["evidence"], probe["focus"])
            probes.append({"case": run["case"], "arm": run["arm"], "call_index": index,
                           "question": probe["question"], "answer": answer, "evidence": call["evidence"],
                           "historical_final_reasons": probe["turn"]["reasons"], "current": asdict(verdict)})
    cases = {c["id"]: c for c in read(ROOT / "data/naacl2027/fresh-llm-v3/cases.json")["cases"]}
    labels = {i["key"]: i for i in read(paired / "labels-second.json")["items"]}
    for row in read(paired / "runs.json")["rows"]:
        draft = next(s for s in row["after"]["steps"] if s["stage"] == "draft")
        key = f"{row['id']}:{sha(draft['answer'].encode())[:12]}"
        label = labels[key]
        current = chain_for("deterministic", cases[row["id"]]["question"]).check(
            draft["answer"], draft["evidence"], None)
        drafts.append({"case": row["id"], "answer": draft["answer"],
                       "supported_and_complete": label["supported"] and label["complete"],
                       "historical_action": draft["action"], "historical_reasons": draft["reasons"],
                       "current": asdict(current)})
    removed = [r for r in probes if r["case"] == "refund_removed"]
    return {"evaluation_type": "development_replay_of_saved_live_drafts", "external_model_calls": 0,
            "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "runtime_sources": sources(), "inputs": inputs,
            "limitations": ["Known answers motivated this fix; this is not a held-out result.",
                            "No regeneration or end-to-end counterfactual success claim.",
                            "Historical co-author labels are reused only for byte-identical paired-study answers.",
                            "A supported absence statement followed by an unrecognized refund mention can still fail."],
            "summary": {"removed_refund_saved_answers": len(removed),
                        "removed_refund_now_allowed": sum(r["current"]["action"] == "allow" for r in removed),
                        "paired_drafts": len(drafts),
                        "paired_correct_drafts": sum(r["supported_and_complete"] for r in drafts),
                        "paired_correct_previously_rejected": sum(r["supported_and_complete"] and r["historical_action"] == "block" for r in drafts),
                        "paired_correct_now_rejected": sum(r["supported_and_complete"] and r["current"]["action"] == "block" for r in drafts),
                        "paired_incorrect_now_rejected": sum(not r["supported_and_complete"] and r["current"]["action"] == "block" for r in drafts)},
            "probe_rows": probes, "paired_rows": drafts}


if __name__ == "__main__":
    report = evaluate()
    write_new(ROOT / "results/naacl2027/missing-information-development.json", report)
    print(json.dumps(report["summary"], indent=2))
