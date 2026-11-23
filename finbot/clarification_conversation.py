"""Message-driven, offline clarification demo; no participant evidence is collected.

Task reference and role-play notes belong to the scenario viewer. The conversation
engine receives only an authorized catalogue and customer events, never a target.
Extraction is deliberately small and visible; it is not an LLM language benchmark.
"""
from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date
from decimal import Decimal, InvalidOperation

from .clarification import Candidate, Question, ResponseModel, posterior, questions, score_dict, score_question
from .clarification_demo import TENANT
from .clarification_study import ASSUMED, catalogue

PROTOCOL = "finbot-conversation-demo-v2"
CANDIDATES = tuple(Candidate(c.record_id, c.tenant_id, {**c.attributes, "amount": "200.00", "currency": "USD"})
                   for c in catalogue()["evaluation"][0].candidates)
SCENARIOS: list[dict] = [
    {"id": "vague", "title": "A vague opening message", "opening": "My $200 payment hasn't arrived.",
     "memory": "You were paying a repair bill. You remember Willow Repairs, but are less sure whether you "
               "used a card or a transfer. You do not remember the date.",
     "target": "txn_EMIX0001", "expected": "Ask for missing details; confirm a record before explaining its status."},
    {"id": "complete", "title": "Details already supplied",
     "opening": "What happened to my bank transfer to Willow Repairs on November 15?",
     "memory": "You have a receipt showing a bank transfer to Willow Repairs on November 15, 2026.",
     "target": "txn_EMIX0001", "expected": "Use the supplied details and show one matching record, with no questions."},
    {"id": "uncertain", "title": "An uncertain recollection",
     "opening": "My $200 payment hasn't arrived. I think it was a bank transfer. I don't remember the date.",
     "memory": "The recipient was Willow Repairs. Your memory of the payment type is uncertain; "
               "you have no receipt or date available.",
     "target": "txn_EMIX0001", "expected": "Retain card possibilities; ask about the recipient instead of repeating "
                                           "the type or asking for a date the customer cannot recall."},
    {"id": "correction", "title": "Correct a remembered detail",
     "opening": "Can you check my bank transfer to Willow Repairs?",
     "memory": "After your first message, you find a card receipt for Willow Repairs on November 16. "
               "Correct your message: Actually, it was a card payment to Willow Repairs on November 16.",
     "target": "txn_EMIX0002", "expected": "Replace the earlier detail, invalidate any previous answer, "
                                           "and ask for confirmation of the newly matching card record."},
    {"id": "missing", "title": "The payment is not in these records",
     "opening": "Please check my bank transfer to Pine Pharmacy on November 18.",
     "memory": "Your receipt says Pine Pharmacy, November 18. Do not choose another payment just to finish.",
     "target": None, "expected": "Explain that the details do not match the catalogue and leave unresolved."},
]


def scenario_catalogue() -> dict:
    from .demo import FAULTS, writer
    return {"protocol": PROTOCOL, "scenarios": [{k: v for k, v in s.items() if k not in {"target", "expected"}}
                                               for s in SCENARIOS],
            "faults": {k: FAULTS[k] for k in RECORD_FAULTS},
            "live_writer": writer()["label"] if writer()["mode"] == "live_model" else None}


# Faults that act on a single confirmed record; policy and two-record faults stay in the inspector.
RECORD_FAULTS = ("none", "status_once", "amount_once", "amount_always")


MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
# A month name, full or abbreviated, as the start of a date ("Nov 15", "October 3rd").
MONTH = r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|" \
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b"


def extract_details(text: str, pending: Question | None,
                    candidates: tuple[Candidate, ...] = CANDIDATES) -> tuple[dict, set[str], list[str]]:
    """Conservative matching of supported fields with simple clause-scoped hedges.

    Negation and alternatives are not silently converted into positive assertions.
    A new statement about a field replaces its previous observation (no double counting).
    """
    lowered = text.casefold().replace("’", "'")
    hedge = r"\b(think|maybe|perhaps|probably|might|not sure|unsure|not certain|guess|" \
            r"(?:don't|do not) (?:know|remember) (?:if|whether))\b"
    clauses = re.split(r"(?<=[.!?;])\s+|\bbut\b", lowered)

    def certainty_for(key: str, value: str) -> str:
        patterns = {"kind": r"\b(?:transfer|card)\b", "merchant": re.escape(value.casefold()),
                    "date": rf"\b(?:\d{{4}}-\d{{2}}-\d{{2}}|{MONTH})",
                    "reference": re.escape(value.casefold()),
                    "amount": r"\$|\b\d[\d,.]*\s*(?:usd|eur|gbp|cad)\b", "currency": r"\$|\b(?:usd|eur|gbp|cad)\b"}
        relevant = [clause for clause in clauses if re.search(patterns[key], clause)]
        blanket_caveat = bool(re.fullmatch(r"\s*(?:i'm |i am )?(?:not sure|unsure|not certain)[.!? ]*", clauses[-1]))
        return "tentative" if blanket_caveat or any(re.search(hedge, c) for c in relevant) else "supplied"
    unknown: set[str] = set()
    issues = []
    fields: dict = {}
    for key, labels in {"date": "date|day|when", "kind": "payment type|payment kind|type|kind|method",
                        "merchant": "recipient|merchant|who"}.items():
        if re.search(rf"(?:don't|do not|can't|cannot) (?:remember|recall|know) (?:the )?(?:{labels})\b", lowered):
            unknown.add(key)
    if lowered.strip(" .!?") in {"i'm not sure", "i am not sure", "not sure", "i don't know", "no idea"}:
        if pending:
            unknown.add(pending.template)
        else:
            issues.append("No detail was supplied. You can leave the payment unresolved.")
    values: dict[str, list[str]] = {"kind": [], "merchant": [], "date": [], "reference": [],
                                  "amount": [], "currency": []}
    amounts = re.findall(r"\$([\d,]+(?:\.\d+)?)", text)
    amounts += re.findall(r"\b([\d,]+(?:\.\d+)?)\s*(?:USD|EUR|GBP|CAD)\b", text, re.IGNORECASE)
    for amount in amounts:
        try:
            values["amount"].append(str(Decimal(amount.replace(",", "")).quantize(Decimal(".01"))))
        except InvalidOperation:
            issues.append("I couldn't interpret the amount.")
    values["currency"] = re.findall(r"\b(?:USD|EUR|GBP|CAD)\b", text.upper())
    if "$" in text:
        values["currency"].append("USD")
    for pattern, value in [(r"\b(?:bank )?transfer\b", "Bank transfer"),
                           (r"\bcard(?: payment)?\b", "Card payment")]:
        if re.search(pattern, lowered):
            values["kind"].append(value)
    # Known names are also recognized when supplied alone as a reply.
    for merchant in {c.attributes["merchant"] for c in candidates}:
        if re.search(rf"\b{re.escape(merchant.casefold())}\b", lowered):
            values["merchant"].append(merchant)
    # An unfamiliar recipient must remain a mismatch, not be discarded in favour of a known one.
    for match in re.finditer(r"\b(?:to|at)\s+([a-z][a-z '&-]{1,60}?)(?=\s+(?:on|for|using|with)\b|[.!?,;]|$)", lowered):
        merchant = match.group(1).strip().rsplit(" to ", 1)[-1].rsplit(" at ", 1)[-1]
        if merchant not in {v.casefold() for v in values["merchant"]}:
            values["merchant"].append(merchant.title())
    iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", lowered)
    for match in re.finditer(MONTH + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", lowered):
        month = MONTHS.index(match.group(1)[:3]) + 1
        iso_dates.append(f"{match.group(3) or '2026'}-{month:02d}-{int(match.group(2)):02d}")
    for value in dict.fromkeys(iso_dates):
        try:
            date.fromisoformat(value)
            values["date"].append(value)
        except ValueError:
            issues.append("That date is not valid. Use a date such as 2026-11-15.")
    values["reference"] = re.findall(r"\btxn_[A-Za-z0-9]+\b", text)
    # Deliberately do not guess what was affirmed inside a negated/alternative clause.
    negation = bool(re.search(r"\b(?:not a|not the|wasn't|was not|didn't|did not|isn't|is not)\b", lowered))
    for key, options in values.items():
        options = list(dict.fromkeys(options))
        if options and (len(options) > 1 or negation):
            unknown.add(key)
            issues.append(f"I could not resolve the {key} from that wording. Use one detail or say you are unsure.")
        elif options and key not in unknown:
            fields[key] = {"value": options[0], "certainty": certainty_for(key, options[0])}
    return fields, unknown, issues


class Conversation:
    """No scenario ID, task brief or evaluator target enters this engine."""

    def __init__(self, candidates: tuple[Candidate, ...] = CANDIDATES, fault: str = "none",
                 live: bool = False, client: str = ""):
        from .demo import FAULTS
        if fault not in FAULTS:
            raise ValueError("Choose a listed fault mode.")
        self.fault = fault
        self.live, self.client = live, client
        if not candidates or any(c.tenant_id != TENANT for c in candidates):
            raise ValueError("Use the authorized synthetic catalogue.")
        self.candidates = candidates
        self.details: dict = {}
        self.unknown: set[str] = set()
        self.messages: list[dict] = []
        self.trace: list[dict] = []
        self.belief = [1 / len(candidates)] * len(candidates)
        self.asked: list[str] = []
        self.pending: Question | None = None
        self.selected_id: str | None = None
        self.financial: dict | None = None
        self.unresolved = False
        self.matches = list(candidates)
        self.ranking: list[dict] = []

    def indistinguishable(self) -> bool:
        """Two or more remaining records that agree on every attribute a question could ask about."""
        return len(self.matches) > 1 and len({tuple(sorted(c.attributes.items())) for c in self.matches}) == 1

    def say(self, text: str) -> None:
        self.messages.append({"role": "assistant", "text": text})

    def update_belief(self) -> None:
        self.belief = [1 / len(self.candidates)] * len(self.candidates)
        for q in questions(self.candidates):
            detail = self.details.get(q.template)
            if detail and detail["value"] in q.options:
                base = ASSUMED[q.template]
                model = ResponseModel(.65, base.unknown) if detail["certainty"] == "tentative" else base
                _, self.belief = posterior(self.candidates, self.belief, q, detail["value"], model)
        supplied = {k: v["value"] for k, v in self.details.items() if v["certainty"] == "supplied"}
        self.matches = [c for c in self.candidates if all(
            (c.record_id if k == "reference" else c.attributes.get(k)) == v for k, v in supplied.items())]
        self.trace.append({"event": "interpretation", "details": dict(self.details),
                           "unknown": sorted(self.unknown), "belief": list(self.belief),
                           "matching_ids": [c.record_id for c in self.matches]})

    def ask_next(self) -> None:
        previous = self.pending
        self.pending = None
        self.ranking = []
        if not self.matches:
            self.say("Those details do not match any of the payments I can access. Check a detail or leave this "
                     "unresolved; I won't substitute a different payment.")
            return
        if len(self.matches) == 1:
            self.say("One record matches the details you supplied. Please confirm it below before I check its status.")
            return
        if self.indistinguishable():
            # No question can separate these records, so none is asked and none is ranked above
            # another; only a reference number the customer knows, or leaving it unresolved, can end it.
            self.trace.append({"event": "indistinguishable", "pool": [c.record_id for c in self.matches]})
            self.say(f"{len(self.matches)} payments match every detail I can ask about (type, recipient, date and "
                     "amount), so no question can tell them apart and I won't pick one. If you have the reference "
                     "number, send it; otherwise leave this unresolved.")
            return
        available = {q.template: q for q in questions(tuple(self.matches))}
        if previous and previous.template in available and previous.template not in self.details \
                and previous.template not in self.unknown:
            self.pending = available[previous.template]
            self.say(self.pending.text)
            return
        if len(self.asked) >= 2:
            self.say("There is still ambiguity after two questions. Confirm a record only if you recognize it, "
                     "add a detail, or leave this unresolved.")
            return
        pool = tuple(self.matches)
        weights = [self.belief[self.candidates.index(c)] for c in pool]
        ranked = [score_question(pool, weights, q, ASSUMED[q.template]) for q in questions(pool)
                  if q.template not in self.details and q.template not in self.unknown
                  and q.template not in self.asked]
        ranked.sort(key=lambda s: s.decision_value, reverse=True)  # demo policy; heuristics are compared separately
        self.ranking = [score_dict(s) for s in ranked]
        if ranked and ranked[0].decision_value > 1e-12:
            self.pending = ranked[0].question
            self.asked.append(self.pending.template)
            self.trace.append({"event": "question", "selected": self.pending.template,
                               "scores": self.ranking, "pool": [c.record_id for c in pool]})
            self.say(self.pending.text)
        else:
            self.say("I don't have another useful question using the available details. "
                     "Confirm a record if you recognize it, or leave this unresolved.")

    def message(self, text: str) -> None:
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
            raise ValueError("Messages must have 1–500 characters.")
        fields, unknown, issues = extract_details(text, self.pending)
        self.messages.append({"role": "user", "text": text.strip()})
        previous = self.selected_id
        if previous:
            for message in self.messages:
                if message.get("record_id"):
                    message["superseded"] = True
            self.trace.append({"event": "invalidate", "record_id": previous})
        self.selected_id, self.financial, self.unresolved = None, None, False
        for key in unknown:
            self.details.pop(key, None)
        self.unknown.update(unknown)
        self.details.update(fields)
        self.unknown.difference_update(fields)
        self.trace.append({"event": "message", "recognized": fields, "issues": issues})
        if issues:
            self.say(" ".join(issues))
        if not fields and not unknown and self.pending:
            self.say("I couldn't extract a supported detail from that message. "
                     "Please use a choice below or a payment type, recipient name, or explicit date.")
            return
        self.update_belief()
        if any(v["certainty"] == "tentative" for v in fields.values()):
            self.say("I'll treat that as a tentative recollection and keep other possibilities open.")
        self.ask_next()

    def confirm(self, record_id: str) -> None:
        from .demo import run_demo
        if record_id not in {c.record_id for c in self.candidates} or not self.messages:
            raise ValueError("Choose an authorized record after sending a message.")
        if self.selected_id:
            for message in self.messages:
                if message.get("record_id"):
                    message["superseded"] = True
            self.trace.append({"event": "invalidate", "record_id": self.selected_id})
        self.pending, self.selected_id, self.unresolved = None, record_id, False
        rows = [{"txn_id": c.record_id, "tenant_id": TENANT, "amount": "200.00", "currency": "USD",
                 "status": "pending" if c.attributes["kind"] == "Bank transfer" else "declined",
                 "created_at": c.attributes["date"] + "T12:00:00Z", "merchant": c.attributes["merchant"],
                 "payment_type": c.attributes["kind"],
                 **({"decline_code": "05", "processor_response": "Do not honor"}
                    if c.attributes["kind"] == "Card payment" else {})} for c in self.candidates]
        # Only the confirmed record reaches the answering step: the model can ask for another ID,
        # but the gateway answers "not found", so no other record can become evidence.
        self.financial = run_demo(f"What are the recorded status and details of {record_id}?", self.fault,
                                  records=[r for r in rows if r["txn_id"] == record_id],
                                  live=self.live, client=self.client)
        self.messages.append({"role": "user", "text": f"Yes, use {record_id}."})
        self.messages.append({"role": "assistant", "text": self.financial["final"]["answer"], "record_id": record_id})
        self.trace.append({"event": "confirm", "record_id": record_id})

    def leave_unresolved(self) -> None:
        if not self.messages:
            raise ValueError("Start with a message.")
        if self.selected_id:
            for message in self.messages:
                if message.get("record_id"):
                    message["superseded"] = True
            self.trace.append({"event": "invalidate", "record_id": self.selected_id})
        self.selected_id, self.financial, self.pending = None, None, None
        self.unresolved = True
        self.messages.append({"role": "user", "text": "I can't identify the payment from these records."})
        self.say("I'll leave the payment unresolved. I can't give a financial answer about an unidentified record.")

    def view(self) -> dict:
        return {"messages": self.messages, "details": self.details, "unknown": sorted(self.unknown),
                "candidates": [{"record_id": c.record_id, **c.attributes, "probability": p,
                                "matches_supplied": c in self.matches}
                               for c, p in zip(self.candidates, self.belief, strict=True)],
                "pending": asdict(self.pending) if self.pending else None, "ranking": self.ranking,
                "questions_asked": len(self.asked), "selected_id": self.selected_id,
                "indistinguishable": self.indistinguishable() and not self.selected_id,
                "unresolved": self.unresolved, "financial": self.financial, "trace": self.trace}


def run_conversation(request: dict, client: str = "") -> dict:
    if not isinstance(request, dict) or set(request) - {"scenario", "events", "inspect", "fault", "live"}:
        raise ValueError("Invalid conversation fields.")
    scenario = next((s for s in SCENARIOS if s["id"] == request.get("scenario", "vague")), None)
    events, inspect = request.get("events", []), request.get("inspect", False)
    fault = request.get("fault", "none")
    if not isinstance(fault, str):
        raise ValueError("Choose a listed fault mode.")
    if scenario is None or not isinstance(events, list) or len(events) > 12 or type(inspect) is not bool:
        raise ValueError("Choose a scenario and at most twelve events.")
    live = request.get("live", False)
    if type(live) is not bool:
        raise ValueError("live must be true or false.")
    engine = Conversation(fault=fault, live=live, client=client)
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Invalid event.")
        if event.get("type") == "message" and set(event) == {"type", "text"}:
            engine.message(event["text"])
        elif event.get("type") == "confirm" and set(event) == {"type", "record_id"}:
            engine.confirm(event["record_id"])
        elif event == {"type": "unresolved"}:
            engine.leave_unresolved()
        else:
            raise ValueError("Invalid conversation event.")
    result = {"protocol": PROTOCOL, "mode": "offline_conversation_demo", "human_study_data": False,
              "scenario": scenario["id"], "fault": fault, "response_model_source": "assumed_not_measured",
              "response_models": {k: asdict(v) for k, v in ASSUMED.items()},
              "tentative_accuracy": .65, **engine.view()}
    if inspect:
        if not engine.selected_id and not engine.unresolved:
            raise ValueError("Scenario reference is available only after confirmation or leaving unresolved.")
        result["reference"] = {"target_id": scenario["target"], "expected": scenario["expected"],
                               "matches_preset_reference": engine.selected_id == scenario["target"],
                               "note": "This reference applies to the preset role-play. Edited messages may change "
                               "the intended task. This is not a participant accuracy measurement."}
    return result
