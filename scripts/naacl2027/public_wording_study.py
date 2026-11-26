"""Previously unused BANKING77 questions on a frozen scripted demo.

freeze BEFORE downloading/selecting questions; select from a pinned public CSV;
run the real inspector with no provider; label support/completeness separately.
These are external questions adapted to synthetic records, not a customer study
or a test of fresh LLM answers. Existing frozen studies are never overwritten.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data/naacl2027/public-wording-v1"
OUT = ROOT / "results/naacl2027/public-wording-v1"
UPSTREAM = "57ec275d8078af65b7731c2a98be812d844a6d6b"
CATEGORIES = ("refund_not_showing_up", "pending_card_payment", "declined_card_payment")
SEED = "finbot-public-wording-v1-2026-11-24"
PER_CATEGORY = 10
REF = r"(?:txn|xfer)_[A-Za-z0-9]+"


def sha(content):
    return hashlib.sha256(content).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def normalized(text):
    text = unicodedata.normalize("NFKC", text).casefold().replace("’", "'")
    for pattern in (rf"\s*(?:the reference is|it's|it is)\s+{REF}\.?",
                    rf"\s*\({REF}\)", rf"^re {REF}:\s*", rf"^{REF}\s*-\s*"):
        text = re.sub(pattern, "", text)
    text = re.sub(REF, "record", text)
    text = re.sub(r"\d+(?:\.\d+)?", "number", text)
    return " ".join(re.findall(r"[a-z]+", text))


def questions(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"question", "opening", "original", "text"} and isinstance(value, str):
                yield value
            elif key in {"turns", "prefix", "filler"} and isinstance(value, list):
                yield from (v for v in value if isinstance(v, str))
            else:
                yield from questions(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from questions(value)


def sources():
    paths = sorted(ROOT.glob("finbot/**/*.py")) + [Path(__file__)]
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}


def freeze():
    previous, inputs = {}, {}
    for path in sorted((ROOT / "data").rglob("*.json*")):
        if path.is_relative_to(DATA):
            continue
        value = ([json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                 if path.suffix == ".jsonl" else read(path))
        found = list(questions(value))
        if found:
            inputs[str(path.relative_to(ROOT))] = sha(path.read_bytes())
            for q in found:
                if norm := normalized(q):
                    previous.setdefault(norm, []).append(str(path.relative_to(ROOT)))
    write_new(DATA / "prior-questions.json", {q: sorted(set(paths)) for q, paths in sorted(previous.items())})
    write_new(DATA / "protocol.json", {
        "name": "public-wording-v1", "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "sources": sources(),
        "source_url": f"https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/{UPSTREAM}/banking_data/test.csv",
        "upstream_revision": UPSTREAM, "split": "test", "licence": "CC BY 4.0",
        "categories": CATEGORIES, "per_category": PER_CATEGORY, "seed": SEED,
        "selection": "SHA256(seed + category + normalized question), ascending; no outcome filtering",
        "overlap": "Remove IDs/wrappers, case/punctuation/number normalization; reject exact matches, "
                   "character SequenceMatcher >=0.88 or token Jaccard >=0.85 with at least 5 tokens; "
                   "compare against prior repository questions and already selected questions.",
        "prior_inputs": inputs, "prior_sha256": sha((DATA / "prior-questions.json").read_bytes()),
        "adaptation": "Keep original text unchanged; append a synthetic transaction reference. Pair each "
                      "question with two fixed category-level record schemas: populated vs missing detail. "
                      "No question-specific changes or filtering of unanswerable/advice/action requests.",
        "execution": "finbot.demo.run_demo, live=False, fault=none, semantic checker off, fresh session per case",
        "automated_metrics": "released/withheld, current record lookup, draft/repair/fallback; not semantic accuracy",
        "review_rubric": "Supported: every financial assertion is entailed by the retrieved record/docs, "
                         "without equating missing evidence with zero/nonoccurrence. Complete: addresses all "
                         "parts of the original question or explicitly states what evidence cannot answer. "
                         "A generic payment summary does not answer a refund question. Correct status does "
                         "not answer why/how long/advice by itself. Never infer labels from gate decisions.",
        "limits": ["Previously unused in this repository, not necessarily unseen in model pretraining.",
                   "Synthetic records can contradict premises of the public question; retain and flag these cases.",
                   "Scripted generation; no live LLM or long-conversation generalisation claim.",
                   "Any AI review is author-assisted and not independent human annotation."]})


def verify():
    protocol = read(DATA / "protocol.json")
    if sources() != protocol["sources"]:
        raise ValueError("Frozen runtime/evaluator changed; preserve the study and use its recorded code.")
    if sha((DATA / "prior-questions.json").read_bytes()) != protocol["prior_sha256"]:
        raise ValueError("Prior-question corpus changed.")
    return protocol


def overlap(question, prior):
    if question in prior:
        return {"match": question, "method": "exact"}
    tokens = set(question.split())
    for old in sorted(prior):
        other = set(old.split())
        if min(len(tokens), len(other)) >= 5 and len(tokens & other) / len(tokens | other) >= .85:
            return {"match": old, "method": "token_jaccard"}
        if SequenceMatcher(None, question, old, autojunk=False).ratio() >= .88:
            return {"match": old, "method": "character_similarity"}
    return None


def record(category, index, populated):
    value = {"txn_id": f"txn_EXT{index:05d}", "tenant_id": "m_100", "status": "approved",
             "amount": "81.70", "currency": "USD"}
    if category == "refund_not_showing_up":
        if populated:
            value["refund"] = {"status": "pending", "amount": "23.40"}
    elif category == "pending_card_payment":
        value["settlement"] = {"status": "pending"}
        if populated:
            value["settlement"]["expected_date"] = "2026-12-01"
    else:
        value["status"] = "declined"
        if populated:
            value.update(decline_code="51", processor_response="Insufficient funds")
    return value


def select(csv_path):
    protocol = verify()
    raw = csv_path.read_bytes()
    candidates = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    previous = set(read(DATA / "prior-questions.json"))
    items, audit, chosen = [], [], set()
    for category in CATEGORIES:
        rows = [(number, row) for number, row in enumerate(candidates, 1)
                if row["category"].casefold() == category]
        rows.sort(key=lambda pair: (sha((SEED + category + normalized(pair[1]["text"])).encode()), pair[0]))
        count = 0
        for number, row in rows:
            norm = normalized(row["text"])
            match = overlap(norm, previous | chosen)
            audit.append({"row": number, "category": category, "overlap": match})
            if match or count >= PER_CATEGORY:
                continue
            count += 1
            chosen.add(norm)
            index = len(items) + 1
            items.append({"id": f"public-{index:03d}", "category": category, "source_row": number,
                          "original": row["text"], "normalized": norm,
                          "question": row["text"] + f" The reference is txn_EXT{index:05d}.",
                          "populated": record(category, index, True), "missing": record(category, index, False)})
        if count != PER_CATEGORY:
            raise ValueError(f"Only {count} unused {category} questions; do not silently change sampling.")
    write_new(DATA / "cases.json", {"source_sha256": sha(raw), "source_url": protocol["source_url"],
                                    "source_rows": len(candidates), "cases": items, "selection_audit": audit})
    write_new(DATA / "selection.json", {"cases_sha256": sha((DATA / "cases.json").read_bytes()),
                                        "protocol_sha256": sha((DATA / "protocol.json").read_bytes())})
    print(json.dumps({"selected": len(items), "screened": len(audit),
                      "overlap_exclusions": sum(bool(r["overlap"]) for r in audit)}))


def verify_cases():
    protocol = verify()
    selection = read(DATA / "selection.json")
    if selection != {"cases_sha256": sha((DATA / "cases.json").read_bytes()),
                     "protocol_sha256": sha((DATA / "protocol.json").read_bytes())}:
        raise ValueError("Selected cases or frozen protocol changed.")
    return protocol, read(DATA / "cases.json")["cases"]


def run():
    protocol, cases = verify_cases()
    from finbot.demo import run_demo
    rows, form = [], []
    with patch.dict(os.environ, {"FINBOT_DEMO_WRITER": "scripted", "FINBOT_DEMO_SEMANTIC": "off"}):
        for case in cases:
            for condition in ("populated", "missing"):
                result = run_demo(case["question"], "none", records=[case[condition]], live=False)
                result["metrics"].pop("latency_ms", None)
                key = case["id"] + "/" + condition
                rows.append({"key": key, "category": case["category"], "result": result})
                form.append({"key": key, "question": case["original"], "record": case[condition],
                             "evidence": result["evidence"], "answer": result["final"]["answer"],
                             "supported": None, "complete": None, "premise_mismatch": None, "rationale": ""})
    summary = {"questions": len(cases), "runs": len(rows), "external_model_calls": 0,
               "outcomes": dict(Counter(r["result"]["outcome"] for r in rows)),
               "released": sum(not r["result"]["final"]["blocked_by"] for r in rows),
               "with_record_lookup": sum(any(c["name"] == "get_transaction" and c["result"]["status"] == "found"
                                              for c in r["result"]["evidence"]) for r in rows),
               "semantic_accuracy": None}
    write_new(OUT / "runs.json", {"protocol_sha256": sha((DATA / "protocol.json").read_bytes()),
                                  "cases_sha256": sha((DATA / "cases.json").read_bytes()),
                                  "summary": summary, "rows": rows})
    write_new(OUT / "review-form.json", {"rubric": protocol["review_rubric"], "items": form})
    verify_cases()
    print(json.dumps(summary, indent=2))


def score(labels_path):
    verify_cases()
    form = read(OUT / "review-form.json")
    labels = read(labels_path)
    if not labels.get("provenance"):
        raise ValueError("Record reviewer provenance.")
    indexed = {item["key"]: item for item in labels["items"]}
    if len(indexed) != len(labels["items"]) or set(indexed) != {i["key"] for i in form["items"]}:
        raise ValueError("Every case must be labelled exactly once.")
    runs = {r["key"]: r for r in read(OUT / "runs.json")["rows"]}
    groups = {}
    for item in form["items"]:
        label = indexed[item["key"]]
        for field in ("supported", "complete", "premise_mismatch"):
            if type(label.get(field)) is not bool:
                raise ValueError(f"Missing {field}: {item['key']}")
        if not label.get("rationale"):
            raise ValueError("Explain each label.")
        if label.get("answer_sha256") != sha(item["answer"].encode()):
            raise ValueError("Label is not tied to this answer.")
        row = runs[item["key"]]
        for group in ("all", row["category"], item["key"].split("/")[1]):
            counts = groups.setdefault(group, Counter())
            counts["cases"] += 1
            counts["released"] += not row["result"]["final"]["blocked_by"]
            counts["supported"] += label["supported"]
            counts["complete"] += label["complete"]
            counts["supported_and_complete"] += label["supported"] and label["complete"]
            counts["premise_mismatch"] += label["premise_mismatch"]
    result = {"reviewer_provenance": labels["provenance"], "counts": groups,
              "labels_sha256": sha(labels_path.read_bytes()), "runs_sha256": sha((OUT / "runs.json").read_bytes()),
              "note": "One AI/author review is provisional; scripted outputs, paired cases are not independent."}
    write_new(OUT / "score-ai.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "select", "run", "score"))
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    if args.command in {"select", "score"} and args.input is None:
        parser.error("--input is required")
    {"freeze": freeze, "select": lambda: select(args.input), "run": run,
     "score": lambda: score(args.input)}[args.command]()
