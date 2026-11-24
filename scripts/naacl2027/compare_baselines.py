"""Cache-only component comparison with stronger, untuned question heuristics.

Never calls a provider or fills missing replies. Reports missing coverage explicitly;
paired comparisons use only episodes completed by both methods. Existing results are
not overwritten. These exploratory comparisons were added after the initial study.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from finbot.evalstats import cluster_bootstrap  # noqa: E402
from scripts.naacl2027 import simulate_customers as sim  # noqa: E402

SELECTORS = ("fixed", "amount_first", "most_distinct", "information_gain", "decision_value", "show_list")


class MissingCachedReply(Exception):
    pass


class ReadOnlyCache:
    def __init__(self, path: Path):
        self.data = {r["key"]: r["value"] for r in map(json.loads, path.read_text().splitlines())}

    def get_or(self, key, compute):
        if key not in self.data:
            raise MissingCachedReply(key)
        return self.data[key]


def rates(rows: list[dict]) -> dict:
    complete = [r for r in rows if r["complete"]]
    n = len(complete)
    return {"requested": len(rows), "completed": n, "missing_cache": len(rows) - n,
            "rates_denominator": "completed_episodes_only",
            **{k: sum(bool(r[k]) for r in complete) for k in ("correct", "wrong", "unresolved")},
            **{f"{k}_rate": sum(bool(r[k]) for r in complete) / n if n else None
               for k in ("correct", "wrong", "unresolved")},
            "top1_rate": sum(bool(r["map_correct"]) for r in complete) / n
                if n and complete[0]["selector"] != "show_list" else None,
            "mean_questions": sum(r["questions"] for r in complete) / n if n else None}


def paired_difference(left: list[dict], right: list[dict], episodes: dict, metric: str) -> dict:
    a = {r["episode"]: r for r in left if r["complete"]}
    b = {r["episode"]: r for r in right if r["complete"]}
    common = sorted(a.keys() & b.keys())
    groups = defaultdict(list)
    for key in common:
        groups[episodes[key]["target_id"]].append(float(a[key][metric]) - float(b[key][metric]))
    delta = sum(sum(g) for g in groups.values()) / len(common) if common else None
    interval = cluster_bootstrap(list(groups.values()), seed=2027) if common else None
    return {"metric": metric, "common_episodes": len(common), "target_record_clusters": len(groups),
            "decision_value_minus_baseline": delta, "paired_record_cluster_bootstrap_ci95": interval}


def evaluate(bench: str) -> tuple[dict, list[dict]]:
    path = ROOT / f"data/naacl2027/{bench}.jsonl"
    episodes = {r["id"]: r for r in map(json.loads, path.read_text().splitlines())}
    rows, summaries, comparisons = [], [], []
    sources = [path, ROOT / "finbot/clarification.py", Path(__file__),
               ROOT / "scripts/naacl2027/simulate_customers.py"]
    for name in ("haiku", "llama"):
        cache_path = ROOT / f"results/naacl2027/clarification-sim/cache-{name}.jsonl"
        sources.append(cache_path)
        cache = ReadOnlyCache(cache_path)
        groups = {}
        for selector in SELECTORS:
            for budget in ((0,) if selector == "show_list" else (1, 2)):
                group = []
                for episode in episodes.values():
                    base = {"simulator": name, "bench": bench, "selector": selector, "budget": budget,
                            "episode": episode["id"]}
                    try:
                        result = sim.run_episode(None, cache, episode, selector, budget, "mixed", bench=bench)
                    except MissingCachedReply as exc:
                        row = {**base, "complete": False, "missing_cache_key": str(exc)}
                    else:
                        row = {**base, "complete": True, **{k: result[k] for k in
                            ("selected", "correct", "wrong", "unresolved", "questions", "map_correct")},
                            "replies": result.get("replies", [])}
                    group.append(row)
                rows.extend(group)
                groups[selector, budget] = group
                summaries.append({"simulator": name, "selector": selector, "budget": budget, **rates(group)})
        for budget in (1, 2):
            for baseline in ("fixed", "amount_first", "most_distinct", "show_list"):
                comparisons.append({"simulator": name, "budget": budget, "baseline": baseline,
                    "differences": [paired_difference(groups["decision_value", budget],
                        groups[baseline, 0 if baseline == "show_list" else budget], episodes, metric)
                        for metric in ("correct", "wrong", "questions")]})
    return {"protocol": "finbot-strong-baselines-v1", "bench": bench, "new_model_calls": 0,
            "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            "definitions": {
                "amount_first": "Amount first, then original kind/merchant/date order; skip constant attributes.",
                "most_distinct": "Most distinct options first; ties use original kind/merchant/date/amount order.",
                "shared": "Same Bayesian updates, response settings, 0.95 threshold, budgets and two-record confirmation.",
                "stopping": "Heuristics stop at budget/threshold/exhaustion; DV may also stop on nonpositive decision value."},
            "limitations": ["Exploratory component comparison added after viewing the original results.",
                "Missing cached replies are unmeasured, not unresolved or incorrect customer outcomes.",
                "Compare methods on the reported paired intersection when coverage differs.",
                "Bootstrap resamples target records (2000 draws, seed 2027); eight synthetic customers limit generalization.",
                "No human effort, live demo accuracy, equivalence or non-inferiority claim."],
            "results": summaries, "paired_comparisons": comparisons}, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", choices=("ambiguity-8", "ambiguity-8-same-amount"), default="ambiguity-8")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "results/naacl2027/strong-baselines")
    args = parser.parse_args()
    report, rows = evaluate(args.bench)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"{args.bench}-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / f"{args.bench}-rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    for r in report["results"]:
        print(r["simulator"], r["selector"], r["budget"], f"coverage={r['completed']}/{r['requested']}",
              f"correct={r['correct']}", f"wrong={r['wrong']}", f"questions={r['mean_questions']}")


if __name__ == "__main__":
    main()
