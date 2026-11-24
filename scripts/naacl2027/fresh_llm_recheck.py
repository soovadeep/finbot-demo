"""Second attempt of the component check, after the first was rate-limited upstream.

The first `fresh_llm_study.py check` run hit OpenRouter 429s for the frozen checker
(google/gemini-2.5-flash-lite via Google AI Studio): 20 of 30 reviews were unavailable. That
file stays as recorded. This driver repeats only the check step, with the same frozen runtime,
checker, prompt and saved drafts (verify_freeze must pass), writes component-checks-2.json,
and scores both attempts, keeping unavailable reviews apart from detections.

    python scripts/naacl2027/fresh_llm_recheck.py check                         # attempt 2
    python scripts/naacl2027/fresh_llm_recheck.py check --attempt 3 --pause 6   # paced
    python scripts/naacl2027/fresh_llm_recheck.py score
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.naacl2027.fresh_llm_study import (CONFIGS, OUT, cases, chain_for, read, sha,  # noqa: E402
                                               verify_freeze, write_new)


def check(attempt: int, pause: float) -> None:
    verify_freeze()
    generations = read(OUT / "generations.json")
    by_id = {c["id"]: c for c in cases()}
    rows = []
    for row in generations["rows"]:
        steps = row["deterministic"]["steps"]
        draft = next(s for s in steps if s["stage"] == "draft") if steps else None
        entry = {"id": row["id"], "draft": draft["answer"] if draft else None}
        if draft:
            for config in CONFIGS:
                started = time.perf_counter()
                verdict = chain_for(config, by_id[row["id"]]["question"]).check(draft["answer"], draft["evidence"], None)
                semantic = [c for c in verdict.checks if c.get("kind") == "semantic_review"]
                entry[config] = {"action": verdict.action, "reasons": verdict.reasons,
                                 "semantic": semantic[0] if semantic else None,
                                 "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
        rows.append(entry)
        print(row["id"], *(entry.get(c, {}).get("action") for c in CONFIGS), flush=True)
        time.sleep(pause)   # pacing only; the checker, prompt and inputs are unchanged
    write_new(OUT / f"component-checks-{attempt}.json", {"attempt": attempt, "pause_s": pause,
                                                "reason": "earlier attempts were rate-limited upstream",
                                                "generations_sha256": sha((OUT / "generations.json").read_bytes()),
                                                "rows": rows})


def tally(path: Path, labels: dict) -> dict:
    out = {}
    rows = [r for r in read(path)["rows"] if r["draft"] is not None]
    for config in CONFIGS:
        t = {"drafts": len(rows), "bad": 0, "bad_blocked": 0, "good": 0, "good_blocked": 0,
             "unavailable": 0, "bad_blocked_available": 0, "good_blocked_available": 0,
             "available_bad": 0, "available_good": 0}
        for r in rows:
            good = labels[f"{r['id']}:{sha(r['draft'].encode())[:12]}"]
            blocked = r[config]["action"] == "block"
            unavailable = any(x.startswith("semantic_unavailable") for x in r[config]["reasons"])
            t["unavailable"] += unavailable
            t["good" if good else "bad"] += 1
            t["good_blocked" if good else "bad_blocked"] += blocked
            if not unavailable:
                t["available_good" if good else "available_bad"] += 1
                t["good_blocked_available" if good else "bad_blocked_available"] += blocked
        out[config] = t
    return out


def score() -> None:
    labels = {i["key"]: bool(i["supported"]) and bool(i["complete"])
              for i in read(OUT / "labels.json")["items"] if i["supported"] is not None}
    attempts = sorted(OUT.glob("component-checks-*.json"))
    summary = {"attempt_1": tally(OUT / "component-checks.json", labels),
               **{f"attempt_{p.stem.rsplit('-', 1)[1]}": tally(p, labels) for p in attempts}}
    last = attempts[-1]
    rows = read(last)["rows"]
    reviews = [r["semantic"]["semantic"] for r in rows if r["draft"] and r["semantic"]["semantic"]]
    used = [x["usage"] for x in reviews if x.get("usage")]
    lat = sorted(x["latency_ms"] for x in reviews if x["verdict"] != "unavailable")
    summary["last_attempt_checker"] = {"file": last.name, "calls": len(reviews), "with_usage": len(used),
                                    "input_tokens": sum(u["input_tokens"] or 0 for u in used),
                                    "output_tokens": sum(u["output_tokens"] or 0 for u in used),
                                    "median_latency_ms": lat[len(lat) // 2] if lat else None}
    agree = [(a["semantic"]["action"], b["semantic"]["action"]) for a, b in
             zip(read(OUT / "component-checks.json")["rows"], rows, strict=True)
             if a["draft"] and not any(x.startswith("semantic_unavailable") for x in a["semantic"]["reasons"] +
                                       b["semantic"]["reasons"])]
    summary["semantic_repeat_agreement_first_vs_last"] = {"both_available": len(agree), "same_verdict": sum(x == y for x, y in agree)}
    (OUT / "component-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("check", "score"))
    parser.add_argument("--attempt", type=int, default=2)
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between cases (pacing only)")
    args = parser.parse_args()
    check(args.attempt, args.pause) if args.command == "check" else score()
