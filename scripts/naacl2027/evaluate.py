"""Offline policy component benchmark and audit of existing live artifacts; no API calls.

Run from the repository root: python scripts/naacl2027/evaluate.py
This is an exploratory authored fixture set, not independent human evaluation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finbot.demo import SCENARIOS, run_demo  # noqa: E402
from finbot.evalstats import percentile  # noqa: E402
from finbot.policy_documents import PolicyDocumentVerifier  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance() -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()  # noqa: S603,S607
    tracked = [*ROOT.glob("finbot/**/*.py"), *ROOT.glob("finbot/demo_assets/*"),
               Path(__file__), ROOT / "data/naacl2027/policy_cases.jsonl"]
    return {"created_utc": datetime.now(UTC).isoformat(), "source_revision": git("rev-parse", "HEAD"),
            "working_tree_dirty": bool(git("status", "--porcelain")), "python": platform.python_version(),
            "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sorted(tracked)},
            "model_api_calls": 0, "human_participants": 0}


def policy_benchmark(cases: list[dict]) -> dict:
    rows = []
    for mode in ("off", "extractive"):
        verifier = PolicyDocumentVerifier(mode)
        for case in cases:
            log = [{"name": "search_knowledge_base", "input": {"query": case["question"]},
                    "result": {"status": "found", "source": "knowledge_base", "data": case["sources"]}}]
            if not case["kb_lookup"]:
                log = [] if case["id"] == "trigger-missing" else [{
                    "name": "get_transaction", "input": {"txn_id": "txn_TIMEOUT01"},
                    "result": {"source": "txn_db", "status": "found", "data": {
                        "txn_id": "txn_TIMEOUT01", "status": "unknown", "error": "PROCESSOR_TIMEOUT"}}}]
            result = verifier.check(case["candidate"], log, None)
            rows.append({"case": case["id"], "category": case["category"], "mode": mode,
                         "expected_supported": case["expected_supported"], "action": result.action,
                         "correct": (result.action == "allow") == case["expected_supported"],
                         "reasons": result.reasons, "checks": result.checks})
    summary = []
    for mode in ("off", "extractive"):
        group = [r for r in rows if r["mode"] == mode]
        supported = [r for r in group if r["expected_supported"]]
        unsupported = [r for r in group if not r["expected_supported"]]
        summary.append({"mode": mode, "cases": len(group),
                        "supported_allowed": sum(r["action"] == "allow" for r in supported),
                        "supported_total": len(supported),
                        "supported_rejected": sum(r["action"] == "block" for r in supported),
                        "unsupported_allowed": sum(r["action"] == "allow" for r in unsupported),
                        "unsupported_total": len(unsupported),
                        "by_category": {cat: {"correct": sum(r["correct"] for r in group if r["category"] == cat),
                                              "n": sum(r["category"] == cat for r in group)}
                                        for cat in sorted({r["category"] for r in group})}})
    return {"scope": "PolicyDocumentVerifier component only; no financial gate, retrieval, repair or generation.",
            "labels": "Assistant-authored before running; independent human adjudication pending.",
            "sampling": "32 purposive synthetic fixtures; no population confidence interval is justified.",
            "model_mode": "not measured: no live reviewer configured; mocks are not accuracy evidence",
            "summary": summary, "rows": rows}


def audit_live() -> dict:
    groups = []
    files = []
    for path in sorted((ROOT / "results").glob("live_*/**/turns.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        source = str(path.relative_to(ROOT))
        files.append({"path": source, "sha256": digest(path), "rows": len(rows)})
        by_group: dict[tuple, list[dict]] = defaultdict(list)
        for row in rows:
            by_group[(row["model"], row["condition"])].append(row)
        saved = json.loads(path.with_name("summary.json").read_text())
        for (model, condition), rs in sorted(by_group.items()):
            outcomes = Counter(r["outcome"] for r in rs)
            counts = Counter(r["case"] for r in rs)
            last_turn = {(r["case"], r["trial"]): r for r in rs}
            injected = [r for r in rs if r.get("injected")]
            original = next(s for s in saved if s["model"] == model and s["condition"] == condition)
            metrics = {"turns": len(rs), "answered": outcomes["answered"] + outcomes["repaired"],
                       "records_only": outcomes["records_only"], "refused": outcomes["refused"],
                       "shadow_flagged_drafts": sum(bool(r["shadow_flagged"]) for r in rs),
                       "leaked_under_injection": sum(bool(r["leaked"]) for r in injected)}
            mismatches = []
            passed_cases = sum(bool(r.get("case_passed")) for r in last_turn.values())
            if original["eval_pass"]["k"] != passed_cases or original["eval_pass"]["n"] != len(last_turn):
                mismatches.append("eval_pass")
            if original["turns"] != len(rs):
                mismatches.append("turns")
            for name in ("answered", "records_only", "refused", "shadow_flagged_drafts"):
                if original[name]["k"] != metrics[name] or original[name]["n"] != len(rs):
                    mismatches.append(name)
            if injected and (original["leaked_under_injection"]["k"] != metrics["leaked_under_injection"]
                             or original["leaked_under_injection"]["n"] != len(injected)):
                mismatches.append("leaked_under_injection")
            latencies = [r["latency_ms"] for r in rs]
            groups.append({"file": source, "model_label_as_recorded": model, "condition": condition,
                           **metrics, "unique_cases": len(counts), "trials": sorted({r["trial"] for r in rs}),
                           "template_eval_passed": passed_cases, "case_trial_total": len(last_turn),
                           "injected_turns": len(injected), "uninjected_turns": len(rs) - len(injected),
                           "tool_snapshot_rows": sum(isinstance(r.get("tool_log"), list) for r in rs),
                           "source_revision_rows": sum(bool(r.get("source_revision")) for r in rs),
                           "recorded_latency_ms_p50": percentile(latencies, 50),
                           "recorded_latency_ms_p95": percentile(latencies, 95),
                           "summary_count_mismatches": mismatches})
    annotations = []
    for path in sorted((ROOT / "results").glob("live_*/**/annotation.csv")):
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        annotations.append({"file": str(path.relative_to(ROOT)), "items": len(rows),
                            "filled_support_labels": sum(bool(r["unsupported_claims"].strip()) for r in rows),
                            "filled_helpfulness_labels": sum(bool(r["helpful"].strip()) for r in rows)})
    return {"scope": "Read-only audit of committed artifacts; provider/model authenticity not independently verified.",
            "limits": ["No new provider calls or rescoring with reconstructed evidence.",
                       "Template success and shadow flags are not independent factuality or usefulness labels.",
                       "Missing per-run revisions/configuration prevent exact historical reconstruction.",
                       "Injected and uninjected subsets are separated; match cases before comparing conditions.",
                       "Recorded writer call/token counters omit the separate judge; they are not total usage.",
                       "The template_only harness still calls the writer before replacing its draft.",
                       "Zero observed events do not justify a population confidence interval [0, 0]."],
            "files": files, "groups": groups, "annotations": annotations}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/naacl2027")
    args = parser.parse_args()
    cases = [json.loads(s) for s in (ROOT / "data/naacl2027/policy_cases.jsonl").read_text().splitlines()]
    assert len(cases) == len({c["id"] for c in cases})
    assert all(type(c["expected_supported"]) is bool for c in cases)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = provenance()
    policy = policy_benchmark(cases)
    audit = audit_live()
    traces = {c["id"]: run_demo(c["question"], c["fault"]) for c in SCENARIOS}
    for name, value in (("manifest", manifest), ("policy-component", policy), ("live-artifact-audit", audit),
                        ("scenario-traces", traces)):
        (args.out / f"{name}.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(policy["summary"], indent=2))
    print(f"Audited {len(audit['files'])} live artifact files; saved {len(traces)} offline scenario traces.")
    if any(g["summary_count_mismatches"] for g in audit["groups"]):
        print("WARNING: committed summaries differ from row-level counts; inspect the audit JSON.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
