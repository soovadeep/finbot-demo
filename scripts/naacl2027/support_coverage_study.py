"""Prospective paired evaluation after coverage fixes; no provider calls.

Freeze before fetching BANKING77 train.csv. Reuse the public-v1 overlap/sampling
and review rubric, with a new seed and unused split rows. Run the same questions
through the pinned pre-fix and frozen current scripted inspector. Both sets of
raw answers are preserved before separate AI review. Historical studies stay intact.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.naacl2027 import public_wording_study as common
from scripts.naacl2027.coverage_development import probes

DATA = ROOT / "data/naacl2027/public-wording-v2"
OUT = ROOT / "results/naacl2027/public-wording-v2"
BASELINE = "59a1d2f"
original_sources = common.sources


def sources():
    paths = [Path(__file__), ROOT / "scripts/naacl2027/coverage_development.py"]
    return {**original_sources(), **{str(p.relative_to(ROOT)): common.sha(p.read_bytes()) for p in paths}}


def configure():
    common.DATA, common.OUT = DATA, OUT
    common.SEED = "finbot-public-wording-v2-2026-11-24"
    common.sources = sources


def freeze():
    # Reuse the exact v1 sampling and annotation definitions; transform metadata
    # BEFORE the exclusive first write, never patch an existing frozen protocol.
    original_write = common.write_new

    def write(path, value):
        if path.name == "protocol.json":
            value = {**value, "name": "public-wording-v2", "split": "train",
                     "source_url": value["source_url"].replace("test.csv", "train.csv"),
                     "baseline_revision": subprocess.check_output(["git", "rev-parse", BASELINE], cwd=ROOT, text=True).strip(),
                     "execution": "Paired pre-fix/frozen-current finbot.demo.run_demo; scripted, faults off, semantic checker off.",
                     "review": "Same rubric as v1. Review support and completeness independently of gate decisions. "
                               "Unblinded AI review is provisional; no additional human reviewer required.",
                     "status_pairs": "Separate authored component controls: correct status/absence vs unsupported status. "
                                     "These are not a natural error rate or semantic gold labels for final answers."}
        original_write(path, value)
    common.write_new = write
    try:
        common.freeze()
    finally:
        common.write_new = original_write


def baseline(protocol, cases):
    """Execute a pinned historical checkout, isolated from current imports/env."""
    with tempfile.TemporaryDirectory(prefix="finbot-baseline-") as tmp:
        path = Path(tmp)
        archive = path / "baseline.tar"
        subprocess.run(["git", "archive", "--format=tar", "-o", str(archive), protocol["baseline_revision"]],
                       cwd=ROOT, check=True)
        subprocess.run(["tar", "-xf", str(archive), "-C", str(path)], check=True)
        source_hashes = {str(p.relative_to(path)): common.sha(p.read_bytes()) for p in sorted(path.glob("finbot/**/*.py"))}
        (path / "study-input.json").write_text(json.dumps(cases))
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FINBOT_", "OPENROUTER_")) and k != "PYTHONPATH"}
        env.update(FINBOT_DEMO_WRITER="scripted", FINBOT_DEMO_SEMANTIC="off", PYTHONHASHSEED="0")
        code = '''import json
from pathlib import Path
from finbot.demo import run_demo
rows=[]
for case in json.loads(Path("study-input.json").read_text()):
    for condition in ("populated", "missing"):
        result=run_demo(case["question"],records=[case[condition]],live=False)
        result["metrics"].pop("latency_ms",None)
        rows.append({"key":case["id"]+"/"+condition,"category":case["category"],"result":result})
Path("study-output.json").write_text(json.dumps(rows))
'''
        subprocess.run([sys.executable, "-c", code], cwd=path, env=env, check=True, timeout=120)
        return json.loads((path / "study-output.json").read_text()), source_hashes


def run():
    protocol, cases = common.verify_cases()
    old, hashes = baseline(protocol, cases)
    common.write_new(OUT / "baseline-runs.json", {"revision": protocol["baseline_revision"],
                                                  "sources": hashes, "rows": old})
    common.run()  # uses actual frozen current code and saves review-form before any labelling
    current = common.read(OUT / "runs.json")
    old_by_key = {r["key"]: r for r in old}
    review = common.read(OUT / "review-form.json")
    combined = []
    for item in review["items"]:
        for arm in ("baseline", "current"):
            row = {**item, "key": arm + "/" + item["key"]}
            if arm == "baseline":
                result = old_by_key[item["key"]]["result"]
                row.update(answer=result["final"]["answer"], evidence=result["evidence"])
            combined.append(row)
    common.write_new(OUT / "paired-review-form.json", {"rubric": review["rubric"], "items": combined})
    pairs = [{"case": case["id"], "condition": condition, **probes(case[condition])}
             for case in cases for condition in ("populated", "missing")]
    common.write_new(OUT / "status-pairs.json", {"scope": "Authored status checks, not final-answer accuracy",
                     "controls_allowed": sum(p["clean_check"]["action"] == "allow" for p in pairs),
                     "corruptions_blocked": sum(p["corrupted_check"]["action"] == "block" for p in pairs), "rows": pairs})
    common.verify_cases()
    print(json.dumps({"baseline_released": sum(not r["result"]["final"]["blocked_by"] for r in old),
                      "current_released": current["summary"]["released"], "paired_runs": len(old)*2,
                      "external_model_calls": 0}, indent=2))


def score(labels_path):
    common.verify_cases()
    labels = common.read(labels_path)
    form = common.read(OUT / "paired-review-form.json")
    if not labels.get("provenance"):
        raise ValueError("Reviewer provenance required.")
    indexed = {i["key"]: i for i in labels["items"]}
    if len(indexed) != len(labels["items"]) or set(indexed) != {i["key"] for i in form["items"]}:
        raise ValueError("Label every paired outcome exactly once.")
    counts = {arm: {"cases": 0, "supported": 0, "complete": 0, "supported_and_complete": 0} for arm in ("baseline", "current")}
    transitions = {"improved": 0, "regressed": 0, "unchanged": 0}
    for item in form["items"]:
        label = indexed[item["key"]]
        if label.get("answer_sha256") != common.sha(item["answer"].encode()):
            raise ValueError("Answer-label binding changed.")
        if any(type(label.get(k)) is not bool for k in ("supported", "complete", "premise_mismatch")) or not label.get("rationale"):
            raise ValueError("Complete all judgments and rationale.")
        c = counts[item["key"].split("/")[0]]
        c["cases"] += 1
        c["supported"] += label["supported"]
        c["complete"] += label["complete"]
        c["supported_and_complete"] += label["supported"] and label["complete"]
    for key, old in indexed.items():
        if key.startswith("baseline/"):
            now = indexed[key.replace("baseline/", "current/", 1)]
            before, after = old["supported"] and old["complete"], now["supported"] and now["complete"]
            transitions["improved" if after and not before else "regressed" if before and not after else "unchanged"] += 1
    report = {"provenance": labels["provenance"], "counts": counts, "paired_transitions": transitions,
              "labels_sha256": common.sha(labels_path.read_bytes()),
              "note": "Paired scripted outputs on synthetic records; AI review is provisional, not independent human evidence."}
    common.write_new(OUT / "paired-score-ai.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "select", "run", "score"))
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    if args.command in {"select", "score"} and args.input is None:
        parser.error("--input required")
    configure()
    {"freeze": freeze, "select": lambda: common.select(args.input), "run": run,
     "score": lambda: score(args.input)}[args.command]()
