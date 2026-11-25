"""Development replay of the inspected public-v2 cases, never a new held-out score.

Save to a new file; original cases, answers and labels are read-only. Inspect all
60 current answers, and pair each of the ten originally incomplete outputs with
its revised answer and current gate decision. Gate acceptance is not completeness.
No model endpoint is used.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.naacl2027 import public_wording_study as common


def run(output: Path):
    from finbot.demo import run_demo
    from finbot.requested_fields import RequestedInformationVerifier
    from finbot.support_coverage import RETURN_TEXT

    data = ROOT / "data/naacl2027/public-wording-v2/cases.json"
    original = ROOT / "results/naacl2027/public-wording-v2"
    paths = [data, original / "runs.json", original / "labels-ai.json"]
    inputs = {str(p.relative_to(ROOT)): common.sha(p.read_bytes()) for p in paths}
    old = {row["key"]: row["result"] for row in common.read(paths[1])["rows"]}
    labels = {row["key"].removeprefix("current/"): row for row in common.read(paths[2])["items"]
              if row["key"].startswith("current/")}
    rows, regressions = [], []
    with patch.dict(os.environ, {"FINBOT_DEMO_WRITER": "scripted", "FINBOT_DEMO_SEMANTIC": "off"}):
        for case in common.read(data)["cases"]:
            for condition in ("populated", "missing"):
                key = case["id"] + "/" + condition
                previous = old[key]
                if labels[key]["answer_sha256"] != common.sha(previous["final"]["answer"].encode()):
                    raise ValueError("Original label/answer binding changed.")
                current = run_demo(case["question"], records=[case[condition]], live=False)
                current["metrics"].pop("latency_ms", None)
                rows.append({"key": key, "result": current,
                             "changed": current["final"]["answer"] != previous["final"]["answer"]})
                if not labels[key]["complete"]:
                    check = RequestedInformationVerifier(case["question"]).check(
                        previous["final"]["answer"], previous["evidence"], None)
                    regressions.append({"key": key, "question": case["question"],
                                        "before": previous["final"]["answer"],
                                        "after": current["final"]["answer"],
                                        "before_checked_now": {"action": check.action, "reasons": check.reasons},
                                        "clarification_requested": RETURN_TEXT in current["final"]["answer"]})
    if any(common.sha((ROOT / p).read_bytes()) != digest for p, digest in inputs.items()):
        raise ValueError("Historical inputs changed during replay.")
    summary = {"runs": len(rows), "released": sum(not r["result"]["final"]["blocked_by"] for r in rows),
               "changed_answers": sum(r["changed"] for r in rows), "known_incomplete": len(regressions),
               "old_incomplete_answers_blocked_now": sum(r["before_checked_now"]["action"] == "block" for r in regressions),
               "clarifications_among_known_incomplete": sum(r["clarification_requested"] for r in regressions),
               "external_model_calls": 0}
    sources = {str(p.relative_to(ROOT)): common.sha(p.read_bytes())
               for p in [*sorted(ROOT.glob("finbot/**/*.py")), Path(__file__)]}
    common.write_new(output, {"scope": "Development regression on already inspected questions, not generalisation evidence.",
                              "inputs": inputs, "sources": sources, "summary": summary,
                              "known_incomplete": regressions, "rows": rows,
                              "review": "No semantic labels are inferred from gate acceptance. Review separately."})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results/naacl2027/support-coverage-followup.json")
    run(parser.parse_args().output)
