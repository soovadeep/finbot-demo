"""Exact finite-state clarification experiments; synthetic assumptions, not human results.

Enumerates targets and all possible reply paths (no Monte Carlo or model calls).
Measures record selection, not financial-answer correctness. All families are
development fixtures; there is no held-out or learned/calibrated response model.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from finbot.clarification import (
    STRATEGIES,
    UNKNOWN,
    Candidate,
    ClarificationSession,
    Question,
    ResponseModel,
    normalize,
    questions,
)

REGIMES = ("matched_reliable", "matched_noisy", "matched_uninformative", "misspecified", "correlated_errors")
METRICS = ("map_record_accuracy", "expected_questions", "threshold_coverage", "threshold_wrong_mass",
           "target_log_loss_nats")


def families() -> list[tuple[str, tuple[Candidate, ...], list[float]]]:
    result = []
    for i in range(24):
        n = 2 + i % 3
        candidates = tuple(Candidate(f"txn_F{i:02d}R{j:02d}", "synthetic", {
            "kind": "Card" if i % 4 == 0 else ("Card", "Transfer")[j % 2],
            "merchant": "Merchant shared" if i % 4 == 1 else f"Merchant {j}",
            "date": f"2026-11-{10 + (j // 2 if i % 4 != 2 else 0):02d}"}) for j in range(n))
        if i % 8 == 7:
            candidates = tuple(Candidate(c.record_id, c.tenant_id, dict(candidates[0].attributes))
                               for c in candidates)
        prior = normalize([3.0 if j == 0 and i % 2 == 0 else 1.0 for j in range(n)])
        result.append((f"family_{i:02d}", candidates, prior))
    return result


def channel(question: Question, regime: str, *, assumed: bool) -> ResponseModel:
    if regime == "matched_uninformative":
        return ResponseModel(1 / len(question.options), 0.1)
    if regime == "matched_noisy" or (regime == "misspecified" and not assumed):
        return ResponseModel(0.55, 0.2)
    return {"kind": ResponseModel(0.9, 0.1), "merchant": ResponseModel(0.8, 0.2),
            "date": ResponseModel(0.85, 0.15)}[question.template]


def terminal(state: ClarificationSession, target: int) -> dict[str, float]:
    guess = max(range(len(state.belief)), key=state.belief.__getitem__)
    covered = max(state.belief) >= state.threshold
    return {"map_record_accuracy": float(guess == target), "expected_questions": float(len(state.asked)),
            "threshold_coverage": float(covered), "threshold_wrong_mass": float(covered and guess != target),
            "target_log_loss_nats": -math.log(max(state.belief[target], 1e-15))}


def enumerate_replies(state: ClarificationSession, target: int, regime: str, mode: str = "ordinary") -> dict:
    question = state.next_question()
    if question is None:
        return terminal(state, target)
    total: dict[str, float] = defaultdict(float)
    mass_sum = 0.0
    for reply in (*question.options, UNKNOWN):
        if regime == "correlated_errors":
            # A persistent alternative target creates correlated mistakes across
            # questions; the selector continues to assume independent replies.
            perceived = target if mode == "honest" else (target + 1) % len(state.candidates)
            value = state.candidates[perceived].attributes[question.template]
            mass = 0.1 if reply == UNKNOWN else 0.9 if reply == value else 0.0
        else:
            mass = channel(question, regime, assumed=False).likelihood(state.candidates[target], question, reply)
        mass_sum += mass
        if not mass:
            continue
        child = copy.deepcopy(state)
        child.reply(question.template, reply)
        for key, value in enumerate_replies(child, target, regime, mode).items():
            total[key] += mass * value
    if not math.isclose(mass_sum, 1.0, abs_tol=1e-9):
        raise ValueError("Actual reply probabilities do not sum to one.")
    return dict(total)


def evaluate(question_budget: int = 2) -> dict:
    if type(question_budget) is not int or not 1 <= question_budget <= 2:
        raise ValueError("Choose a one- or two-question experiment budget.")
    rows = []
    for family, candidates, prior in families():
        for regime in REGIMES:
            for strategy in (*STRATEGIES, "provided_intent"):
                totals: dict[str, float] = defaultdict(float)
                if strategy == "provided_intent":
                    totals.update(map_record_accuracy=1.0, expected_questions=0.0, threshold_coverage=1.0,
                                  threshold_wrong_mass=0.0, target_log_loss_nats=0.0)
                else:
                    models = {q.template: channel(q, regime, assumed=True) for q in questions(candidates)}
                    modes = [("honest", 0.8), ("alternative", 0.2)] if regime == "correlated_errors" else [
                        ("ordinary", 1.0)]
                    for target, probability in enumerate(prior):
                        for mode, mode_probability in modes:
                            state = ClarificationSession(candidates, "synthetic", list(prior), strategy, models,
                                                         max_questions=question_budget)
                            for key, value in enumerate_replies(state, target, regime, mode).items():
                                totals[key] += probability * mode_probability * value
                rows.append({"family": family, "regime": regime, "strategy": strategy,
                             **{key: round(totals[key], 9) for key in METRICS}})
    summary = []
    for regime in REGIMES:
        for strategy in (*STRATEGIES, "provided_intent"):
            group = [r for r in rows if r["regime"] == regime and r["strategy"] == strategy]
            values = {key: sum(r[key] for r in group) / len(group) for key in METRICS}
            error_rate = (values["threshold_wrong_mass"] / values["threshold_coverage"]
                          if values["threshold_coverage"] else None)
            summary.append({"regime": regime, "strategy": strategy, **values,
                            "error_given_threshold": error_rate})
    sources = ("finbot/clarification.py", "scripts/evaluate_clarification.py")
    return {"schema_version": 1, "scope": "exact synthetic development simulation; no human/live-model results",
            "families": 24, "comparison_rows": len(rows), "question_budget": question_budget, "threshold": 0.95,
            "question_cost_error_units": 0.02, "seed": None,
            "method": "Exact enumeration under specified prior and reply channels; equal weight per family.",
            "limitations": ["All examples are development fixtures, not held out.",
                            "Targets are always in the candidate catalogue; missing-target errors are not measured.",
                            "MAP and confidence-threshold predictions are experimental metrics, not release rules.",
                            "Runtime financial answers require explicit confirmation and verification.",
                            "Provided-intent control assumes a correct supplied intent, not a fallible user reply.",
                            "No final-answer accuracy, human usefulness, wall-clock latency or API cost is measured.",
                            "No statistical confidence intervals: results are exact under synthetic assumptions."],
            "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
            "summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--question-budget", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    report = evaluate(args.question_budget)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"scope": report["scope"], "families": report["families"],
                      "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
