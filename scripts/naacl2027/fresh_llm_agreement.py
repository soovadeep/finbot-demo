"""Compare the two label sets for the fresh LLM study and re-score the gate under each.

    python scripts/naacl2027/fresh_llm_agreement.py

Reads results/naacl2027/fresh-llm-v1/labels.json (provisional) and labels-second.json (second
labeller), and writes label-agreement.json: per-field agreement and Cohen's kappa, the answers
whose combined label differs, and the component (last checker attempt) and end-to-end tallies
under each label set. Checker verdicts never supply a label.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fresh_llm_recheck import tally  # noqa: E402

OUT = ROOT / "results" / "naacl2027" / "fresh-llm-v1"


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def kappa(a: list[bool], b: list[bool]) -> dict:
    n = len(a)
    agree = sum(x == y for x, y in zip(a, b, strict=True))
    po, pa, pb = agree / n, sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return {"n": n, "agree": agree, "agreement": round(po, 3),
            "kappa": round((po - pe) / (1 - pe), 3) if pe < 1 else None,
            "yes_first": sum(a), "yes_second": sum(b)}


def end_to_end(labels: dict) -> dict:
    out = {}
    for run in ("deterministic", "combined"):
        t = {"released_good": 0, "released_bad": 0, "withheld": 0, "bad_keys": []}
        for row in read(OUT / "generations.json")["rows"]:
            final = row[run]["final"]
            if final["blocked_by"]:
                t["withheld"] += 1
                continue
            key = f"{row['id']}:{hashlib.sha256(final['answer'].encode()).hexdigest()[:12]}"
            good = labels[key]
            t["released_good" if good else "released_bad"] += 1
            if not good:
                t["bad_keys"].append(key)
        out[run] = t
    return out


def main() -> None:
    first = {i["key"]: i for i in read(OUT / "labels.json")["items"]}
    second = {i["key"]: i for i in read(OUT / "labels-second.json")["items"]}
    keys = sorted(first)
    assert keys == sorted(second), "label sets cover different answers"
    both = {name: {k: bool(s[k]["supported"]) and bool(s[k]["complete"]) for k in keys}
            for name, s in (("provisional", first), ("second", second))}
    last = sorted(OUT.glob("component-checks-*.json"))[-1]
    result = {
        "agreement": {f: kappa([bool(first[k][f]) for k in keys], [bool(second[k][f]) for k in keys])
                      for f in ("supported", "complete")}
        | {"combined": kappa([both["provisional"][k] for k in keys], [both["second"][k] for k in keys])},
        "disagreements": [{"key": k, "provisional": both["provisional"][k], "second": both["second"][k],
                           "second_rationale": second[k]["rationale"]}
                          for k in keys if both["provisional"][k] != both["second"][k]],
        "component_file": last.name,
        "component": {name: tally(last, labels) for name, labels in both.items()},
        "end_to_end": {name: end_to_end(labels) for name, labels in both.items()},
    }
    (OUT / "label-agreement.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("agreement", "end_to_end")}, indent=2))


if __name__ == "__main__":
    main()
