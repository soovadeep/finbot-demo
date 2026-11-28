"""Same-amount slice of the eight-record benchmark.

Run from the repository root (after build_ambiguity_set.py):
  python scripts/naacl2027/build_same_amount_set.py

In the main set no two records in an episode share an amount, so an exact amount always
identifies the record. Here every candidate takes the target's amount and currency, as with
recurring payments, split bills or the demo's four $200 payments, so the amount rules nothing
out and the other attributes must do the work. Everything else (questions, targets, kinds,
payees, dates, personas) is unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/naacl2027/ambiguity-8.jsonl"
OUT = ROOT / "data/naacl2027/ambiguity-8-same-amount.jsonl"


def main() -> None:
    lines = []
    for line in SRC.read_text().splitlines():
        e = json.loads(line)
        t = next(c for c in e["candidates"] if c["record_id"] == e["target_id"])
        e["slice"] = "|same_amount"   # keeps the episode ID (same persona) but separates cached chooser calls
        e["candidates"] = [{**c, "amount": t["amount"], "currency": t["currency"]} for c in e["candidates"]]
        lines.append(json.dumps(e))
    OUT.write_text("\n".join(lines) + "\n")
    print(f"{len(lines)} episodes -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
