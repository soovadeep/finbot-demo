"""Evaluate precommitted fresh wording against the frozen runtime; never tune it here.

PYTHONHASHSEED=0 python scripts/naacl2027/evaluate_fresh_wording.py

Answers are pre-authored fixture text, not newly generated LLM outputs. Customer
messages reach the actual Conversation endpoint function without confirmation.
The two parts measure different components and are never pooled as task accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data/naacl2027/fresh-wording-v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze():
    protocol = json.loads((DATA / "protocol.json").read_text())
    changed = [name for name, digest in protocol["runtime_files"].items()
               if not (ROOT / name).is_file() or sha(ROOT / name) != digest]
    current = {str(p.relative_to(ROOT)) for p in ROOT.glob("finbot/**/*.py")}
    current.add("scripts/naacl2027/evaluate_support.py")
    changed += sorted(current - set(protocol["runtime_files"]))
    if changed:
        raise ValueError("Frozen runtime differs; use the recorded revision, not a tuned rerun: " + ", ".join(changed))
    if sha(DATA / "cases.json") != protocol["cases_sha256"]:
        raise ValueError("Precommitted case texts or labels changed.")
    return protocol


def pair_counts(rows, name):
    clean_ok = [r for r in rows if r["checks"][name]["clean"]["action"] == "allow"]
    return {"pairs": len(rows), "clean_accepted": len(clean_ok), "clean_rejected": len(rows) - len(clean_ok),
            "corrupted_rejected": sum(r["checks"][name]["corrupted"]["action"] == "block" for r in rows),
            "corrupted_allowed": sum(r["checks"][name]["corrupted"]["action"] == "allow" for r in rows),
            "new_rejections": sum(r["checks"][name]["corrupted"]["action"] == "block" for r in clean_ok),
            "targeted_role_rejections": sum(r["targeted_role_rejection"][name] for r in rows)}


def conversation_score(case, result):
    expected = set(case["expected_matching_ids"])
    actual = {c["record_id"] for c in result["candidates"] if c["matches_supplied"]}
    return {"expected_matching_ids": sorted(expected), "actual_matching_ids": sorted(actual),
            "exact_candidate_set": actual == expected,
            "all_compatible_candidates_retained": expected <= actual,
            "excluded_compatible_ids": sorted(expected - actual),
            "extra_candidate_ids": sorted(actual - expected),
            "no_answer_before_confirmation": result["selected_id"] is None and result["financial"] is None}


def evaluate():
    protocol = verify_freeze()
    # Import only after the snapshot has been verified. This uses the same chain
    # as the inspector, with explicit offline dependencies, not a new verifier.
    from finbot.clarification_conversation import run_conversation
    from finbot.verification import VerifierChain
    from scripts.naacl2027.evaluate_support import component_chain
    fixtures = json.loads((DATA / "cases.json").read_text())
    full = component_chain()
    chains = {"without_financial_roles": VerifierChain([v for v in full.verifiers if v.name != "financial_roles"]),
              "with_financial_roles": full}
    pairs = []
    for case in fixtures["draft_pairs"]:
        record = case["record"]
        evidence = [{"name": "get_transaction", "input": {"txn_id": record["txn_id"]},
                     "result": {"status": "found", "source": "txn_db", "data": record}}]
        checks = {name: {side: asdict(chain.check(case[side], evidence, record["txn_id"]))
                         for side in ("clean", "corrupted")} for name, chain in chains.items()}
        targeted = {}
        for name, outcome in checks.items():
            new_reasons = set(outcome["corrupted"]["reasons"]) - set(outcome["clean"]["reasons"])
            targeted[name] = outcome["clean"]["action"] == "allow" and outcome["corrupted"]["action"] == "block" and any(
                reason == f"financial_role_mismatch:{record['txn_id']}:{case['role']}" for reason in new_reasons)
        pairs.append({**case, "checks": checks, "targeted_role_rejection": targeted})
    conversations = []
    for case in fixtures["conversation_cases"]:
        result = run_conversation({"events": case["events"], "fault": "none", "live": False})
        conversations.append({**case, "score": conversation_score(case, result), "result": result})
    verify_freeze()  # Evaluation must not mutate production code or the fixture.
    committed_cases = subprocess.check_output(["git", "log", "-1", "--format=%H", "--",
                                               str(DATA.relative_to(ROOT))], cwd=ROOT, text=True).strip()
    return {"protocol": protocol["protocol"], "evaluation_type": "fresh_developer_authored_wording_on_frozen_runtime",
            "runtime_revision": protocol["runtime_revision"], "fixture_commit": committed_cases,
            "protocol_sha256": sha(DATA / "protocol.json"), "cases_sha256": sha(DATA / "cases.json"),
            "evaluator_sha256": sha(Path(__file__)), "python_hash_seed": os.environ.get("PYTHONHASHSEED", "random"),
            "authorship": protocol["authorship"], "external_model_calls": 0, "human_participants": 0,
            "runtime_changed": False,
            "draft_summary": {name: pair_counts(pairs, name) for name in chains},
            "draft_by_role": {role: {name: pair_counts([r for r in pairs if r["role"] == role], name)
                                     for name in chains} for role in sorted({r["role"] for r in pairs})},
            "conversation_summary": {"sequences": len(conversations), **{
                metric: sum(row["score"][metric] for row in conversations) for metric in
                ("exact_candidate_set", "all_compatible_candidates_retained", "no_answer_before_confirmation")}},
            "limitations": protocol["limits"] + ["Conversation tests stop before confirmation; they do not measure final answer quality or task success."],
            "draft_rows": pairs, "conversation_rows": conversations}


def same_measurement(saved, current):
    # JSON persists tuples as lists. The evaluator's source hash can change for
    # harness-only fixes; all runtime/fixture provenance and outcomes must match.
    def measurement(report):
        return json.loads(json.dumps({k: v for k, v in report.items() if k != "evaluator_sha256"}))
    return measurement(saved) == measurement(current)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/naacl2027/fresh-wording-v1.json")
    args = parser.parse_args()
    if os.environ.get("PYTHONHASHSEED") != "0":
        parser.error("Run with PYTHONHASHSEED=0 for reproducible set iteration in the frozen controller.")
    result = evaluate()
    if args.out.exists():
        if not same_measurement(json.loads(args.out.read_text()), result):
            raise ValueError("Refusing to replace a different report; preserve the first result.")
        print("Reproduced the original measurements; retained the first report and its evaluator hash.")
    else:
        args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("draft_summary", "draft_by_role", "conversation_summary")}, indent=2))


if __name__ == "__main__":
    main()
