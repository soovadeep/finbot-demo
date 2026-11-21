"""Offline clarification integrated with the real Finbot financial answer pipeline.

The server owns all synthetic candidate metadata. The client supplies only a case,
strategy, fault and bounded user events. Deterministic replay avoids mutable global
sessions; no client-supplied posterior, tenant, evidence or generated answer is trusted.
"""
from __future__ import annotations

import copy
from dataclasses import asdict

from .clarification import STRATEGIES, Candidate, ClarificationSession, ResponseModel
from .pii import mask_value

TENANT = "m_100"
CARD = "txn_CARD0001"
BANK = "txn_BANK0002"
SECOND_CARD = "txn_CARD0002"
ROWS = [
    {"txn_id": CARD, "tenant_id": TENANT, "status": "declined", "amount": "200.00", "currency": "USD",
     "decline_code": "05", "processor_response": "Do not honor", "created_at": "2026-11-12T10:00:00Z",
     "payment_type": "Card payment", "merchant": "Atlas Market"},
    {"txn_id": BANK, "tenant_id": TENANT, "status": "pending", "amount": "200.00", "currency": "USD",
     "created_at": "2026-11-12T11:00:00Z", "payment_type": "Bank transfer", "merchant": "Greenway"},
]
CASES = [
    {"id": "ambiguous", "title": "Two possible payments", "question": "Why did my $200 payment fail?"},
    {"id": "date", "title": "The date distinguishes the records", "question": "What happened to my payment?"},
    {"id": "explicit", "title": "Exact reference: skip clarification",
     "question": f"What is the recorded status of {BANK}?", "explicit_id": BANK},
    {"id": "premise", "title": "Mistaken failure assumption",
     "question": f"Why was {BANK} declined?", "explicit_id": BANK},
    {"id": "indistinguishable", "title": "Insufficient identifying details",
     "question": "What happened to my $200 payment?",
     "note": "Both card payments match on type, merchant and date, so no question can separate them."},
    {"id": "uninformative", "title": "Assumed replies carry no information",
     "question": "What happened to my $200 payment?",
     "note": "Replies are assumed to be no better than a coin flip, so asking cannot help."},
]


def case_catalogue() -> dict:
    return {"cases": copy.deepcopy(CASES), "strategies": list(STRATEGIES),
            "mode": "offline_scripted", "response_model": "assumed_synthetic"}


def make_case(case_id: str, strategy: str = "information_gain") -> tuple[dict, list[dict], ClarificationSession]:
    case = next((c for c in CASES if c["id"] == case_id), None)
    if case is None:
        raise ValueError("Unknown clarification case.")
    rows = copy.deepcopy(ROWS)
    if case_id in {"date", "indistinguishable"}:
        # The second record becomes another card payment, so its ID must not say BANK.
        rows[1]["txn_id"] = SECOND_CARD
        rows[1]["payment_type"], rows[1]["merchant"] = rows[0]["payment_type"], rows[0]["merchant"]
    if case_id == "date":
        rows[1]["created_at"] = "2026-11-13T11:00:00Z"
    candidates = tuple(Candidate(r["txn_id"], r["tenant_id"], {
        "kind": r["payment_type"], "merchant": r["merchant"], "date": r["created_at"][:10]}) for r in rows)
    models = {"kind": ResponseModel(0.9, 0.1), "merchant": ResponseModel(0.8, 0.2),
              "date": ResponseModel(0.85, 0.15)}
    if case_id == "uninformative":
        models = {key: ResponseModel(0.5, 0.1) for key in models}
    state = ClarificationSession(candidates, TENANT, [0.6, 0.4], strategy, models)
    if case.get("explicit_id"):
        state.confirm(case["explicit_id"])
    return copy.deepcopy(case), rows, state


def run_clarification(request: dict) -> dict:
    from .demo import FAULTS, run_demo

    if not isinstance(request, dict) or set(request) - {"case_id", "strategy", "events", "fault"}:
        raise ValueError("Unexpected clarification fields.")
    case_id, strategy = request.get("case_id", "ambiguous"), request.get("strategy", "information_gain")
    fault, events = request.get("fault", "none"), request.get("events", [])
    if any(not isinstance(v, str) for v in (case_id, strategy, fault)) or fault not in FAULTS:
        raise ValueError("Invalid case, strategy or fault.")
    if not isinstance(events, list) or len(events) > 8:
        raise ValueError("Supply at most eight dialogue events.")
    case, rows, state = make_case(case_id, strategy)
    state.next_question()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Invalid event.")
        kind = event.get("type")
        if kind == "reply" and set(event) == {"type", "template", "text"}:
            state.reply(event["template"], event["text"])
        elif kind == "confirm" and set(event) == {"type", "record_id"} and isinstance(event["record_id"], str):
            state.confirm(event["record_id"])
        elif kind == "none" and set(event) == {"type"}:
            state.reject_candidates()
        else:
            raise ValueError("Unknown or malformed event.")
        state.next_question()
    financial = None
    if state.selected_id:
        # A new session is deliberate: previous record evidence and drafts cannot
        # enter a corrected answer. The gateway still enforces scope and the
        # pipeline refetches the confirmed record on every financial run.
        question = f"What are the recorded status and details of {state.selected_id}?"
        financial = run_demo(question, fault, records=rows)
    status = "answered" if financial else "clarifying" if state.pending else "unresolved"
    if financial and financial["final"]["blocked_by"]:
        status = "blocked"
    return mask_value({
        "schema_version": 1, "mode": "offline_scripted", "synthetic_data": True,
        "response_model_source": "assumed_synthetic_not_calibrated", "case": case, "strategy": strategy,
        "status": status, "revision": state.revision, "selected_id": state.selected_id,
        "belief_source": ("catalogue_rejected" if state.stopped else "user_selection" if state.selected_id
                          else "assumed_response_model"),
        "candidates": [{"record_id": c.record_id, **c.attributes,
                        "probability": p if not state.stopped and not state.selected_id else None}
                       for c, p in zip(state.candidates, state.belief, strict=True)],
        "pending": asdict(state.pending) if state.pending else None,
        "questions_asked": len(state.asked), "question_budget": state.max_questions,
        "response_models": {k: asdict(v) for k, v in state.models.items()}, "trace": state.trace,
        "financial": financial,
        "limits": "Template selection over a server-owned synthetic catalogue; no automatic record discovery "
                  "or LLM question generation. Explicit record confirmation is required regardless of posterior. "
                  "Fresh Finbot retrieval and verification run after confirmation. These probabilities are assumed, "
                  "not calibrated on people. The fixed task is explaining the selected record's status and details.",
    })
