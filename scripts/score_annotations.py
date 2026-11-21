"""Score the blinded annotation pack from scripts/run_live.py.

Each annotator fills a copy of annotation.csv (unsupported_claims: a count, helpful: 1-5) without
seeing annotation_key.csv. This joins the copies to the key and reports, per model x condition:
the share of shown answers with at least one unsupported claim (Wilson 95% CI), unsupported
claims per answer, mean helpfulness, and, with two or more annotators, Cohen's kappa on the
binary "has an unsupported claim" label (first two annotators) plus the share of items where
they disagree, which should be adjudicated before reporting.

  python3 scripts/score_annotations.py results/live/annotation_key.csv ann_a.csv ann_b.csv
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from finbot.evalstats import wilson  # noqa: E402


def read(path: str) -> dict[str, dict]:
    with open(path, newline="") as f:
        return {r["item"]: r for r in csv.DictReader(f)}


def kappa(a: list[int], b: list[int]) -> float:
    n = len(a)
    if not n:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    key = read(argv[0])
    anns = [read(p) for p in argv[1:]]
    groups: dict[tuple, list[tuple[list[int], list[float]]]] = defaultdict(list)
    pairs_a, pairs_b = [], []
    for item, k in key.items():
        counts, helpful = [], []
        for ann in anns:
            r = ann.get(item)
            if not r or r.get("unsupported_claims", "").strip() == "":
                continue
            counts.append(int(r["unsupported_claims"]))
            if r.get("helpful", "").strip():
                helpful.append(float(r["helpful"]))
        if not counts:
            continue
        groups[(k["model"], k["condition"])].append((counts, helpful))
        if len(counts) >= 2:
            pairs_a.append(int(counts[0] > 0))
            pairs_b.append(int(counts[1] > 0))
    print(f"{'model':<34} {'condition':<16} {'items':>5} {'with unsupported claim':>30} {'claims/ans':>10} "
          f"{'helpful':>8}")
    for (model, cond), items in sorted(groups.items()):
        # An item counts as unsupported if the annotators' mean count is above zero (adjudicate ties).
        flags = [sum(c) / len(c) > 0 for c, _ in items]
        k, n = sum(flags), len(flags)
        lo, hi = wilson(k, n)
        claims = sum(sum(c) / len(c) for c, _ in items) / n
        hs = [h for _, hh in items for h in hh]
        help_s = f"{sum(hs) / len(hs):.2f}" if hs else "-"
        print(f"{model:<34} {cond:<16} {n:>5} {f'{k}/{n} = {k / n:.1%} [{lo:.1%}, {hi:.1%}]':>30} "
              f"{claims:>10.2f} {help_s:>8}")
    if pairs_a:
        dis = sum(x != y for x, y in zip(pairs_a, pairs_b, strict=True)) / len(pairs_a)
        print(f"\nCohen's kappa (first two annotators, has-unsupported-claim): {kappa(pairs_a, pairs_b):.2f} "
              f"on {len(pairs_a)} items; disagreement {dis:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
