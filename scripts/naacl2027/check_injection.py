"""Injected-error test of the answer checks on the NAACL ambiguity benchmark's records.

Run from the repository root:
  python scripts/naacl2027/check_injection.py

For each of the 224 target records in data/naacl2027/ambiguity-8.jsonl the script writes
correct drafts in several phrasings (these must pass) and drafts with one injected error of a
given claim type (these must be blocked), runs the demo's verifier chain (finbot/verification.py) on each
with the record as the only evidence, and reports the detection rate per claim type and the false
rejection rate. It also checks that the answer built from the record passes. No model is called;
the drafts are templates, so the numbers describe the checks, not any language model.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finbot.recordanswer import record_answer  # noqa: E402
from finbot.verification import (  # noqa: E402
    BindingVerifier,
    DomainVerifier,
    EvidenceVerifier,
    LanguageVerifier,
    ReasonVerifier,
    RecordIdentityVerifier,
    VerifierChain,
)

CHAIN = VerifierChain([RecordIdentityVerifier(), EvidenceVerifier(), ReasonVerifier(), DomainVerifier(),
                       BindingVerifier(), LanguageVerifier()])   # the production chain's record checks


def evidence_check(answer: str, log: list[dict], focus: str):
    return CHAIN.check(answer, log, focus)

OUT = ROOT / "results/naacl2027/check-injection.json"

SAID = {  # how a correct draft states each record status
    "approved": ["was approved", "went through"],
    "completed": ["was completed", "went through"],
    "declined": ["was declined", "did not go through"],
    "failed": ["failed", "did not go through"],
    "returned": ["was returned", "was sent back"],
    "pending": ["is still pending", "is pending; its outcome is not confirmed yet"],
    "processing": ["is still processing", "is still being processed"],
}
WRONG = {  # a definite outcome the record contradicts or does not establish
    "approved": ["was declined", "failed"],
    "completed": ["was declined", "failed"],
    "declined": ["was approved", "went through", "was successful"],
    "failed": ["was approved", "went through", "was successful"],
    "returned": ["was approved", "went through", "was completed"],
    "pending": ["was completed", "went through", "was declined"],
    "processing": ["was completed", "went through", "failed"],
}
NOT = {  # a negated status the record makes true: correct, and must not be read as a claim
    "approved": "was not declined", "completed": "was not returned", "declined": "was not approved",
    "failed": "was not completed", "returned": "was not completed", "pending": "has not been completed yet",
    "processing": "has not been completed yet",
}
# Held-out wordings, written after the checks were fixed on the set above and before running the
# checks on them; the checks were not changed after seeing these results.
HELD_SAID = {
    "approved": ["has been approved", "was successful"],
    "completed": ["has completed", "succeeded"],
    "declined": ["was not approved", "got declined"],
    "failed": ["was unsuccessful", "did not succeed"],
    "returned": ["came back to you", "has been returned"],
    "pending": ["has not settled yet", "is awaiting completion"],
    "processing": ["is in progress", "is still in progress"],
}
HELD_WRONG = {
    "approved": ["got declined", "has been rejected"],
    "completed": ["bounced", "was cancelled"],
    "declined": ["has cleared", "was paid"],
    "failed": ["succeeded", "has gone through", "was settled"],
    "returned": ["has cleared", "succeeded"],
    "pending": ["has cleared", "bounced", "has been completed"],
    "processing": ["succeeded", "has been cancelled", "was rejected"],
}
HELD_NOT = {
    "approved": "was not rejected", "completed": "did not fail", "declined": "did not succeed",
    "failed": "was not successful", "returned": "did not clear", "pending": "has not cleared yet",
    "processing": "is not finished yet",
}
MONTHS = "January February March April May June July August September October November December".split()


def word_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def raw_records() -> dict[str, dict]:
    """The stored records the benchmark's targets come from (data/test), as the tools return them."""
    out = {}
    for name, key in (("transactions", "txn_id"), ("transfers", "transfer_id")):
        for line in (ROOT / f"data/test/{name}.jsonl").read_text().splitlines():
            r = json.loads(line)
            out[r[key]] = r
    return out


RAW: dict[str, dict] = {}


def tool_log(r: dict) -> list[dict]:
    """The lookup the answering step makes for the confirmed record, with the stored record."""
    rid = r["record_id"]
    if rid.startswith("xfer_"):
        return [{"name": "get_transfer", "input": {"transfer_id": rid},
                 "result": {"status": "found", "source": "transfer_db", "data": RAW[rid]}}]
    return [{"name": "get_transaction", "input": {"txn_id": rid},
             "result": {"status": "found", "source": "txn_db", "data": RAW[rid]}}]


def correct_drafts(r: dict, rng: random.Random) -> list[str]:
    s1, s2 = SAID[r["status"]]
    a, c, i = r["amount"], r["currency"], r["record_id"]
    return [f"Transaction {i} for {a} {c} {s1}.",
            f"Your {r['kind'].lower()} of {a} {c} to {r['merchant']} on {r['date']} {s2}.",
            f"I checked {i}: the payment {s1}. It was for {a} {c} on {word_date(r['date'])}.",
            f"The {r['kind'].lower()} to {r['merchant']} {s1}, according to the record for {i}.",
            f"Transaction {i} for {a} {c} {NOT[r['status']]}; it {s1}."]


def held_correct(r: dict, rng: random.Random) -> list[str]:
    s1, s2 = HELD_SAID[r["status"]]
    a, c, i, k = r["amount"], r["currency"], r["record_id"], r["kind"].lower()
    return [f"According to our records, payment {i} ({a} {c}) {s1}.",
            f"{i}: {a} {c} to {r['merchant']}, which {s2}.",
            f"The {a} {c} {k} you made on {word_date(r['date'])} {s1}.",
            f"Looking at {i}, your {k} with {r['merchant']} {s2}.",
            f"Payment {i} {HELD_NOT[r['status']]}; it {s1}."]


def held_injected(r: dict, other: dict, rng: random.Random) -> dict[str, list[str]]:
    s1 = HELD_SAID[r["status"]][0]
    a, c, i = r["amount"], r["currency"], r["record_id"]
    base = f"According to our records, payment {i} ({a} {c}) {s1}."
    wrong_amt = f"{float(a) + rng.choice([2, 7, 15, 40]):.2f}"
    fee = f"{rng.randint(1, 40)}.{rng.randint(0, 99):02d}"
    wrong_cur = next(x for x in ("GBP", "CAD", "EUR", "USD") if x != c)
    d = date.fromisoformat(r["date"]) + timedelta(days=rng.choice([-4, -1, 1, 4]))
    return {
        "amount": [f"The payment of {wrong_amt} {c} for {i} {s1}.",
                   f"You paid {r['merchant']} {c} {wrong_amt}, and it {s1}."],
        "added fee": [f"{base} There was a {fee} {c} charge on top.",
                      f"{base} A service charge of {fee} {c} applied."],
        "currency": [f"{i} was a payment of {a} {wrong_cur} that {s1}."],
        "date": [f"{base} The date on it is {d.day} {MONTHS[d.month - 1]} {d.year}.",
                 f"{base} You made it on {d.strftime('%m/%d/%Y')}."],
        "status": [f"According to our records, payment {i} ({a} {c}) {w}." for w in HELD_WRONG[r["status"]]],
        "record id": [f"{base} This relates to {other['record_id']}."],
        "reason code": [f"{base} The reason code on it is R01."],
        "link": [f"{base} More at www.example.com/help."],
        "mixed": [f"Payment {i} of {wrong_amt} {c} {s1}.",
                  f"{i} ({a} {c}) {s1} on {word_date(d.isoformat())}."],
    }


def injected(r: dict, other: dict, rng: random.Random) -> dict[str, list[str]]:
    s1 = SAID[r["status"]][0]
    a, c, i = r["amount"], r["currency"], r["record_id"]
    base = f"Transaction {i} for {a} {c} {s1}."
    wrong_amt = f"{float(a) + rng.choice([1, 5, 10, 25]):.2f}"
    fee = f"{rng.randint(1, 40)}.{rng.randint(0, 99):02d}"
    wrong_cur = next(x for x in ("EUR", "GBP", "USD", "CAD") if x != c)
    d = date.fromisoformat(r["date"]) + timedelta(days=rng.choice([-3, -2, 2, 3]))
    return {
        "amount": [f"Transaction {i} for {wrong_amt} {c} {s1}.",
                   f"Your payment of ${wrong_amt} to {r['merchant']} {s1}."],
        "added fee": [f"{base} A processing fee of {fee} was also charged.",
                      f"{base} You were also charged a {fee} {c} fee."],
        "currency": [f"Transaction {i} for {a} {wrong_cur} {s1}."],
        "date": [f"{base} It was made on {d.isoformat()}.", f"{base} It was made on {word_date(d.isoformat())}."],
        "status": [f"Transaction {i} for {a} {c} {w}." for w in WRONG[r["status"]]],
        "record id": [f"{base} It is linked to {other['record_id']}."],
        "reason code": [f"{base} The decline code was 51."],
        "link": [f"{base} See https://help.example.com/payments for details."],
        "mixed": [f"Transaction {i} {s1}. It was for {wrong_amt} {c}.",
                  f"Your payment of {a} {c} {s1}, on {d.isoformat()}."],
    }


def run(episodes: list[dict], make_correct, make_injected, rng: random.Random) -> dict:
    caught, total, reasons = defaultdict(int), defaultdict(int), defaultdict(lambda: defaultdict(int))
    passed = clean = fallback_ok = 0
    misses: list[dict] = []
    false_blocks: list[dict] = []
    for e in episodes:
        r = next(x for x in e["candidates"] if x["record_id"] == e["target_id"])
        other = next(x for x in e["candidates"] if x["record_id"] != e["target_id"])
        log = tool_log(r)
        for draft in make_correct(r, rng):
            clean += 1
            g = evidence_check(draft, log, r["record_id"])
            if g.action == "allow":
                passed += 1
            else:
                false_blocks.append({"draft": draft, "status": r["status"], "reasons": g.reasons})
        for kind, drafts in make_injected(r, other, rng).items():
            for draft in drafts:
                total[kind] += 1
                g = evidence_check(draft, log, r["record_id"])
                if g.action == "block":
                    caught[kind] += 1
                    for x in g.reasons:
                        reasons[kind][x.split(":")[0]] += 1
                else:
                    misses.append({"type": kind, "status": r["status"], "draft": draft})
        built = record_answer(log, r["record_id"])
        if built and evidence_check(built, log, r["record_id"]).action == "allow":
            fallback_ok += 1
    return {
        "records": len(episodes),
        "correct_drafts": clean, "correct_passed": passed, "false_rejections": clean - passed,
        "injected": {k: {"drafts": total[k], "blocked": caught[k], "rate": round(caught[k] / total[k], 4),
                         "reasons": dict(reasons[k])} for k in total},
        "injected_total": sum(total.values()), "injected_blocked": sum(caught.values()),
        "record_built_answer_passes": fallback_ok,
        "misses": misses, "false_blocks": false_blocks[:50],
    }


def main() -> None:
    RAW.update(raw_records())
    episodes = [json.loads(line) for line in (ROOT / "data/naacl2027/ambiguity-8.jsonl").read_text().splitlines()]
    result = run(episodes, correct_drafts, injected, random.Random(2027))
    result["held_out"] = run(episodes, held_correct, held_injected, random.Random(2028))
    OUT.write_text(json.dumps(result, indent=1) + "\n")
    for name, res in (("development wordings", result), ("held-out wordings", result["held_out"])):
        print(f"== {name}")
        print(f"correct drafts: {res['correct_passed']}/{res['correct_drafts']} pass "
              f"({res['false_rejections']} false rejections)")
        for k, v in res["injected"].items():
            print(f"{k:12s} {v['blocked']:4d}/{v['drafts']:4d} blocked")
        print(f"all injected: {res['injected_blocked']}/{res['injected_total']}; record-built answer passes "
              f"{res['record_built_answer_passes']}/{res['records']}")


if __name__ == "__main__":
    main()
