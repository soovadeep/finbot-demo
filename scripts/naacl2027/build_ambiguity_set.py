"""Build the ambiguity benchmark: real Banking77 wording, reference removed, similar records.

Run from the repository root:
  python scripts/naacl2027/build_ambiguity_set.py

Each episode takes one record-backed Banking77 question (both data/test sets, card payments
and transfers only), deletes the transaction or transfer reference, and pairs the original
record with 1 to 4 similar records from the same customer: same kind of payment where
possible, and the nearest dates. The original record is the hidden target. The questions are
real customer wording; the records are synthetic (see data/README.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ("data/test/banking77.jsonl", "data/test/banking77_fresh.jsonl")
REF = r"(?:txn_[A-Z0-9]{10}|xfer_[A-Z0-9]{8})"
STRIP = [  # order matters: remove whole reference phrases first, then any bare reference
    (rf"\s*(?:The reference is|It's|It is)\s+{REF}\.?", ""),
    (rf"\s*\({REF}\)", ""),
    (rf"^Re {REF}:\s*", ""),
    (rf"^{REF}\s*-\s*", ""),
    (REF, "it"),
]


def strip_reference(text: str) -> str:
    for pattern, replacement in STRIP:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if re.search(r"(txn|xfer)_", text):
        raise ValueError(f"Reference left in: {text}")
    return text


def records(data: Path) -> dict[str, dict]:
    out = {}
    for line in (data / "transactions.jsonl").read_text().splitlines():
        r = json.loads(line)
        out[r["txn_id"]] = {"record_id": r["txn_id"], "tenant_id": r["tenant_id"], "kind": "Card payment",
                            "merchant": r["merchant_name"], "date": r["created_at"][:10],
                            "amount": r["amount"], "currency": r["currency"], "status": r["status"]}
    for line in (data / "transfers.jsonl").read_text().splitlines():
        r = json.loads(line)
        party = f"account ending {r['to_account_last4']}" if r.get("to_account_last4") else "external account"
        out[r["transfer_id"]] = {"record_id": r["transfer_id"], "tenant_id": r["tenant_id"],
                                 "kind": "Bank transfer", "merchant": party, "date": r["created_at"][:10],
                                 "amount": r["amount"], "currency": r["currency"], "status": r["status"]}
    return out


def distractors(target: dict, pool: list[dict], k: int, rng: random.Random) -> list[dict]:
    """Prefer the same kind of payment, then the nearest dates; break ties at random."""
    day = date.fromisoformat(target["date"])

    def similarity(r: dict) -> tuple:
        gap = abs((date.fromisoformat(r["date"]) - day).days)
        return (r["kind"] != target["kind"], gap, rng.random())

    ranked = sorted((r for r in pool if r["record_id"] != target["record_id"]), key=similarity)
    return ranked[:k]


def build(seed: int = 2027, size: int | None = None) -> dict:
    """size=None draws 2 to 5 candidates per episode; a number fixes it (the larger-account variant)."""
    rng = random.Random(seed)
    data = records(ROOT / "data/test")
    by_tenant: dict[str, list[dict]] = {}
    for r in data.values():
        by_tenant.setdefault(r["tenant_id"], []).append(r)
    episodes = []
    for source in SOURCES:
        for line in (ROOT / source).read_text().splitlines():
            case = json.loads(line)
            if not case.get("has_record") or case["expect"].get("tools", [""])[0] not in (
                    "get_transaction", "get_transfer"):
                continue
            call = case["expect"]["tool_calls"][0]["input"]
            target = data[call.get("txn_id") or call.get("transfer_id")]
            k = rng.randint(2, 5) if size is None else size
            candidates = [target, *distractors(target, by_tenant[target["tenant_id"]], k - 1, rng)]
            rng.shuffle(candidates)
            episodes.append({"id": f"amb_{case['id']}", "source": source, "category": case["category"],
                             "opening": strip_reference(case["turns"][0]), "original": case["turns"][0],
                             "tenant_id": target["tenant_id"], "target_id": target["record_id"],
                             "candidates": candidates})
    return {"schema_version": 1, "seed": seed, "episodes": len(episodes),
            "sources": {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in SOURCES},
            "items": episodes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument("--size", type=int, help="fixed candidates per episode (default: 2 to 5)")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    args.out = args.out or ROOT / f"data/naacl2027/ambiguity{'' if args.size is None else f'-{args.size}'}.jsonl"
    report = build(args.seed, args.size)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in report["items"]))
    sizes = [len(e["candidates"]) for e in report["items"]]
    print(f"{report['episodes']} episodes, candidates per episode: "
          f"{ {n: sizes.count(n) for n in sorted(set(sizes))} } -> {args.out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
