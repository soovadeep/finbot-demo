"""Build an evaluation set from real customer wording: Banking77 questions on Finbot records.

No public dataset pairs real support questions with real account records (that data is
private). This takes the questions from Banking77 (Casanueva et al., 2020; PolyAI, CC-BY-4.0:
13,083 customer queries in 77 banking intents) and attaches a synthetic record of the matching
kind, so the wording is a customer's and every fact can still be checked.

  * Intents about something a record can answer ("declined_card_payment", "pending_transfer",
    "unable_to_verify_identity", "pin_blocked", ...) get a record of that domain, chosen to fit
    the intent where it says the outcome (a declined payment for "declined_card_payment"), and
    the record id is added to the question in one of a few ways a customer would write it.
  * Intents with no record behind them ("exchange_rate", "age_limit", "apple_pay_or_google_pay")
    are kept as they are: the bot should answer from a help page or say it doesn't know.

Record expectations require the correct lookup arguments and a found result identifying
that same record. These are retrieval checks, not answer-correctness labels. Answers still
need independent annotation (scripts/run_live.py, scripts/score_annotations.py); the gate's
shadow verdict is diagnostic and must not become its own ground truth.

  curl -O https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/test.csv
  python3 scripts/build_banking77_set.py --banking77 test.csv --data data/test --out data/test/banking77.jsonl

A second set, built after the checks were changed in response to the first live run, uses
Banking77's training split (no question in common with the test split) and a different seed:

  curl -O https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/train.csv
  python3 scripts/build_banking77_set.py --banking77 train.csv --data data/test --seed 2027 \
      --id-prefix b77f --out data/test/banking77_fresh.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
from collections import defaultdict

# intent -> (records file, id field, lookup tool, statuses that fit the intent or None for any, write request?)
RECORD_INTENTS: dict[str, tuple[str, str, str, tuple[str, ...] | None, bool]] = {
    "declined_card_payment": ("transactions", "txn_id", "get_transaction", ("declined", "failed"), False),
    "declined_cash_withdrawal": ("transactions", "txn_id", "get_transaction", ("declined", "failed"), False),
    "pending_card_payment": ("transactions", "txn_id", "get_transaction", None, False),
    "card_payment_not_recognised": ("transactions", "txn_id", "get_transaction", ("approved",), False),
    "transaction_charged_twice": ("transactions", "txn_id", "get_transaction", ("approved",), False),
    "Refund_not_showing_up": ("transactions", "txn_id", "get_transaction", ("approved",), False),
    "reverted_card_payment?": ("transactions", "txn_id", "get_transaction", None, False),
    "card_payment_fee_charged": ("transactions", "txn_id", "get_transaction", ("approved",), False),
    "failed_transfer": ("transfers", "transfer_id", "get_transfer", ("failed", "returned"), False),
    "declined_transfer": ("transfers", "transfer_id", "get_transfer", ("failed", "returned"), False),
    "pending_transfer": ("transfers", "transfer_id", "get_transfer", ("pending", "processing"), False),
    "transfer_timing": ("transfers", "transfer_id", "get_transfer", ("pending", "processing", "completed"), False),
    "transfer_not_received_by_recipient": ("transfers", "transfer_id", "get_transfer", None, False),
    "cancel_transfer": ("transfers", "transfer_id", "get_transfer", ("pending", "processing"), True),
    "balance_not_updated_after_bank_transfer": ("accounts", "account_id", "get_account", None, False),
    "balance_not_updated_after_cheque_or_cash_deposit": ("accounts", "account_id", "get_account", None, False),
    "terminate_account": ("accounts", "account_id", "get_account", None, True),
    "unable_to_verify_identity": ("kyc", "case_id", "get_verification",
                                  ("rejected", "needs_documents", "in_review", "pending"), False),
    "verify_my_identity": ("kyc", "case_id", "get_verification", None, False),
    "card_not_working": ("issuing", "card_id", "get_card", ("blocked", "frozen", "expired"), False),
    "contactless_not_working": ("issuing", "card_id", "get_card", None, False),
    "virtual_card_not_working": ("issuing", "card_id", "get_card", None, False),
    "pin_blocked": ("issuing", "card_id", "get_card", ("blocked", "frozen"), False),
    "card_about_to_expire": ("issuing", "card_id", "get_card", None, False),
    "activate_my_card": ("issuing", "card_id", "get_card", None, False),
    "compromised_card": ("issuing", "card_id", "get_card", None, False),
}
TEMPLATES = ["{q} The reference is {id}.", "{q} ({id})", "{id} - {q}", "Re {id}: {q}", "{q} It's {id}."]


def rows(d: str, f: str) -> list[dict]:
    path = os.path.join(d, f"{f}.jsonl")
    return [json.loads(line) for line in open(path)] if os.path.exists(path) else []


def build(banking77: str, data: str, per_record_intent: int, per_other_intent: int, seed: int,
          id_prefix: str = "b77") -> list[dict]:
    from finbot.domains import DOMAINS
    rng = random.Random(seed)
    tools = {d.tool for d in DOMAINS.values()} | {"get_transaction"}
    by_intent: dict[str, list[str]] = defaultdict(list)
    with open(banking77, newline="") as f:
        for r in csv.DictReader(f):
            by_intent[r["category"]].append(r["text"].strip())
    cases = []
    for intent in sorted(by_intent):
        qs = by_intent[intent][:]
        rng.shuffle(qs)
        spec = RECORD_INTENTS.get(intent)
        if spec and spec[2] in tools:
            file, key, tool, statuses, write = spec
            pool = [r for r in rows(data, file) if statuses is None or r.get("status") in statuses]
            if not pool:
                continue
            for i, q in enumerate(qs[:per_record_intent]):
                rec = rng.choice(pool)
                text = rng.choice(TEMPLATES).format(q=q.rstrip(), id=rec[key])
                cases.append({"id": f"{id_prefix}_{intent.strip('?')}_{i}", "category": f"b77:{intent}",
                              "source": "banking77", "has_record": True, "write_request": write,
                              "tenant_id": rec["tenant_id"], "groups": ["support"], "role": "customer",
                              "turns": [text], "expect": {"tools": [tool], "tool_calls": [{
                                  "name": tool, "input": {key: rec[key]}, "turn": 0,
                                  "result": {"status": "found", "data": {key: rec[key]}}}]}})
        else:
            for i, q in enumerate(qs[:per_other_intent]):
                cases.append({"id": f"{id_prefix}_{intent.strip('?')}_{i}", "category": f"b77:{intent}",
                              "source": "banking77", "has_record": False, "write_request": False,
                              "tenant_id": "m_910", "groups": ["support"], "role": "customer",
                              "turns": [q], "expect": {}})
    return cases


def main() -> int:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    ap = argparse.ArgumentParser()
    ap.add_argument("--banking77", required=True, help="Banking77 test.csv (text,category)")
    ap.add_argument("--data", default="data/test")
    ap.add_argument("--per-record-intent", type=int, default=8)
    ap.add_argument("--per-other-intent", type=int, default=2)
    ap.add_argument("--seed", type=int, default=77)
    ap.add_argument("--out", default="data/test/banking77.jsonl")
    ap.add_argument("--id-prefix", default="b77", help="case id prefix (b77f for the fresh set)")
    a = ap.parse_args()
    cases = build(a.banking77, a.data, a.per_record_intent, a.per_other_intent, a.seed, a.id_prefix)
    with open(a.out, "w") as f:
        for c in cases:
            f.write(json.dumps(c, sort_keys=True) + "\n")
    n_rec = sum(c["has_record"] for c in cases)
    print(f"{len(cases)} cases ({n_rec} with a record, {len(cases) - n_rec} without) -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
