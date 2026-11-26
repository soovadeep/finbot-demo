"""Post-hoc matched-control analysis of the existing held-out draft mutations.

No rules are tuned and no live models are called. Historical raw rejection totals
remain in check-injection.json; this report distinguishes pre-existing rejection
from rejection caused by a mutation and records exclusions for supported codes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.naacl2027 import check_injection as legacy  # noqa: E402


def transition(clean: str, corrupted: str) -> str:
    if clean not in ("allow", "block") or corrupted not in ("allow", "block"):
        raise ValueError("Expected allow/block verifier actions.")
    return f"{clean}_to_{corrupted}"


def summarize(rows: list[dict]) -> dict:
    valid = [r for r in rows if r["eligible"]]
    n = len(valid)
    counts = Counter(r["transition"] for r in valid)
    clean_allowed = counts["allow_to_allow"] + counts["allow_to_block"]
    clean_blocked = counts["block_to_allow"] + counts["block_to_block"]
    corrupt_blocked = counts["allow_to_block"] + counts["block_to_block"]
    return {"generated_pairs": len(rows), "eligible_pairs": n, "excluded_pairs": len(rows) - n,
            **{key: counts[key] for key in ("allow_to_allow", "allow_to_block", "block_to_allow", "block_to_block")},
            "clean_allowed": clean_allowed, "clean_blocked": clean_blocked, "corrupted_blocked": corrupt_blocked,
            "clean_rejection_rate": clean_blocked / n if n else None,
            "raw_corrupted_rejection_rate": corrupt_blocked / n if n else None,
            "mutation_rejection_given_clean_allowed": counts["allow_to_block"] / clean_allowed if clean_allowed else None,
            "paired_rejection_lift": (corrupt_blocked - clean_blocked) / n if n else None}


def evaluate() -> tuple[dict, list[dict]]:
    legacy.RAW.update(legacy.raw_records())
    path = ROOT / "data/naacl2027/ambiguity-8.jsonl"
    episodes = list(map(json.loads, path.read_text().splitlines()))
    rng = random.Random(2028)
    rows = []
    for episode in episodes:
        record = next(c for c in episode["candidates"] if c["record_id"] == episode["target_id"])
        other = next(c for c in episode["candidates"] if c["record_id"] != episode["target_id"])
        log = legacy.tool_log(record)
        raw = legacy.RAW[record["record_id"]]
        for kind, pairs in legacy.held_pairs(record, other, rng).items():
            for index, pair in enumerate(pairs):
                clean = legacy.evidence_check(pair.clean, log, record["record_id"])
                corrupted = legacy.evidence_check(pair.corrupted, log, record["record_id"])
                # R01 is actually recorded on some transfers; adding it is not an error there.
                eligible = not (kind == "reason code" and raw.get("return_code") == "R01")
                rows.append({"episode": episode["id"], "record_id": record["record_id"], "kind": kind,
                    "index": index, "clean": pair.clean, "corrupted": pair.corrupted,
                    "eligible": eligible, "exclusion": None if eligible else "R01 is the recorded return code",
                    "transition": transition(clean.action, corrupted.action),
                    "clean_reasons": clean.reasons, "corrupted_reasons": corrupted.reasons})
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["kind"]].append(row)
    # Changing matched-control construction must not silently change the legacy corrupted set.
    original = json.loads((ROOT / "results/naacl2027/check-injection.json").read_text())["held_out"]
    legacy_blocked = sum(r["transition"].endswith("_to_block") for r in rows)
    if len(rows) != original["injected_total"] or legacy_blocked != original["injected_blocked"]:
        raise ValueError("Legacy held-out totals changed; investigate before comparing reports.")
    sources = [path, Path(__file__), ROOT / "scripts/naacl2027/check_injection.py"]
    report = {"protocol": "finbot-paired-verification-v1", "analysis": "post_hoc_existing_holdout",
              "new_model_calls": 0, "historical_raw_pairs": len(rows), "historical_raw_blocked": legacy_blocked,
              "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              "overall": summarize(rows), "by_claim_type": {k: summarize(v) for k, v in grouped.items()},
              "limitations": ["Paired analysis of already inspected templates is diagnostic, not fresh held-out evidence.",
                "Conditional mutation rejection applies only to accepted clean controls; also report clean rejection and all transitions.",
                "Repeated records and templates are dependent; counts are not independent user samples.",
                "Templates prescribe intended field meanings and are not independently annotated natural-language answers.",
                "A blocked draft is not proof that its intended error was identified; passing is not semantic correctness."]}
    return report, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "results/naacl2027/paired-verification")
    args = parser.parse_args()
    report, rows = evaluate()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / "pairs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    for kind, r in report["by_claim_type"].items():
        print(kind, f"raw blocked={r['corrupted_blocked']}/{r['eligible_pairs']}",
              f"clean blocked={r['clean_blocked']}", f"new rejection={r['allow_to_block']}/{r['clean_allowed']}",
              f"excluded={r['excluded_pairs']}")


if __name__ == "__main__":
    main()
