"""Small live-model run of the demo's answering step on the NAACL benchmark's confirmed records.

Run from the repository root with an OpenAI-compatible endpoint, for example OpenRouter:
  FINBOT_DEMO_WRITER=live FINBOT_LLM_PROVIDER=openai FINBOT_MODEL=meta-llama/llama-3.3-70b-instruct \\
  FINBOT_OPENAI_BASE_URL=https://openrouter.ai/api/v1 FINBOT_OPENAI_API_KEY=... \\
  python scripts/naacl2027/live_writer_run.py

For every card-payment target in data/naacl2027/ambiguity-8.jsonl (the run covers this record
type only: the targets whose records are in data/test/transactions.jsonl), the stored record is the only record the answering step can read, as
after a confirmation. A live model writes the answer under three faults injected after it writes:
none, an invented fee in the first draft only (amount_once), and in the draft and the repair
(amount_always). The script records the gate's outcome: passed, repaired, answer built from the
record, or blocked. Rows are cached in results/naacl2027/live-writer/rows.jsonl, so a rerun only
calls the model for rows it lacks.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finbot.demo import _run_demo, writer  # noqa: E402

OUT = ROOT / "results/naacl2027/live-writer"
FAULTS = ["none", "amount_once", "amount_always"]


def targets() -> list[dict]:
    raw = {json.loads(x)["txn_id"]: json.loads(x)
           for x in (ROOT / "data/test/transactions.jsonl").read_text().splitlines()}
    out = []
    for line in (ROOT / "data/naacl2027/ambiguity-8.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["target_id"] in raw:
            out.append({**raw[e["target_id"]], "tenant_id": "m_100"})   # the demo's signed-in tenant
    return out


def one(row: dict, fault: str) -> dict:
    rid = row["txn_id"]
    try:
        r = _run_demo(f"What are the recorded status and details of {rid}?", fault, records=[row], live=True)
    except Exception as exc:  # noqa: BLE001 - record provider errors as rows, not crashes
        return {"record_id": rid, "fault": fault, "outcome": "error", "error": repr(exc)[:300]}
    return {"record_id": rid, "fault": fault, "status": row["status"], "outcome": r["outcome"],
            "injections": len(r["injections"]), "answer": r["final"]["answer"],
            "reasons": r["final"]["reasons"], "model_calls": r["metrics"]["model_calls"]}


def main() -> None:
    w = writer()
    if w["mode"] != "live_model":
        sys.exit("Set FINBOT_DEMO_WRITER=live and the model settings (see the docstring).")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "rows.jsonl"
    done = {}
    if path.exists():
        for line in path.read_text().splitlines():
            x = json.loads(line)
            if x["outcome"] != "error":
                done[(x["record_id"], x["fault"])] = x
    rows = targets()
    todo = [(r, f) for f in FAULTS for r in rows if (r["txn_id"], f) not in done]
    with ThreadPoolExecutor(8) as pool:
        for x in pool.map(lambda a: one(*a), todo):
            done[(x["record_id"], x["fault"])] = x
    path.write_text("".join(json.dumps(done[(r["txn_id"], f)]) + "\n" for f in FAULTS for r in rows))
    summary = {"writer": w["label"], "model": w["model"], "records": len(rows), "faults": {}}
    for f in FAULTS:
        got = [done[(r["txn_id"], f)] for r in rows]
        c = Counter(x["outcome"] for x in got)
        reasons = defaultdict(int)
        for x in got:
            for y in x.get("reasons", []):
                reasons[y.split(":")[0]] += 1
        summary["faults"][f] = {"outcomes": dict(c), "reasons": dict(reasons)}
        print(f, dict(c))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")


if __name__ == "__main__":
    main()
