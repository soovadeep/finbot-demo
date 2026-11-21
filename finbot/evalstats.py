"""Small statistics for evaluation reports: intervals for rates, so "0 of 2,400" is reported
as "0% (95% CI 0-0.15%)" rather than as a guarantee.

wilson(k, n)            Wilson score interval for a binomial proportion (good at k = 0)
bootstrap(xs, stat)     percentile bootstrap interval for any statistic of per-item values
cluster_bootstrap(...)  the same, resampling whole groups (e.g. cases, when turns within a
                        case are not independent)
percentile(xs, q)       nearest-rank percentile (latency p50/p95)
"""
from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt_rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n if n else 0:.1%} [{lo:.1%}, {hi:.1%}]"


def bootstrap(xs: Sequence[float], stat: Callable[[Sequence[float]], float] = lambda v: sum(v) / len(v),
              reps: int = 2000, seed: int = 0, alpha: float = 0.05) -> tuple[float, float]:
    if not xs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    vals = sorted(stat([xs[rng.randrange(len(xs))] for _ in xs]) for _ in range(reps))
    return (vals[int(alpha / 2 * reps)], vals[min(reps - 1, int((1 - alpha / 2) * reps))])


def cluster_bootstrap(groups: Sequence[Sequence[float]], reps: int = 2000, seed: int = 0,
                      alpha: float = 0.05) -> tuple[float, float]:
    """Interval for the pooled mean, resampling whole groups."""
    groups = [g for g in groups if g]
    if not groups:
        return (0.0, 0.0)
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        pick = [groups[rng.randrange(len(groups))] for _ in groups]
        n = sum(len(g) for g in pick)
        vals.append(sum(sum(g) for g in pick) / n)
    vals.sort()
    return (vals[int(alpha / 2 * reps)], vals[min(reps - 1, int((1 - alpha / 2) * reps))])


def percentile(xs: Sequence[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[max(0, min(len(s) - 1, math.ceil(q / 100 * len(s)) - 1))]
