"""Finite question-to-evidence contracts for payment support.

An amount is not a refund-progress answer, nor is an expected date a cause.
Contracts describe fields, schema meaning and explicit limits separately. The
same plan supplies writer guidance, verification and code-built recovery. This
is an inspectable English parser, not a general semantic relevance guarantee.
"""
from __future__ import annotations

import re

from .missing_information import states_absent, value_for_field

REFUND = re.compile(r"\b(?:refund\w*|reimburse\w*|money back|return(?:ed)?(?:\s+(?:show|clear|appear|from|on|to|in|of|a purchase)))\b", re.I)
PENDING = re.compile(r"\b(?:pending|processing|stuck|not (?:yet )?(?:cleared|complete|completed|processed|go(?:ne)? through)|"
                     r"(?:hasn['’]t|has not|didn['’]t|did not)\s+(?:(?:it|this|that|the payment|my payment)\s+)?"
                     r"(?:cleared|clear|gone through|go through|completed)|still[^.?!]{0,25}(?:clear\w*|through)|taking[^.?!]{0,20}long)\b", re.I)
TIMING = re.compile(r"\b(?:when|how long|how many days|how much time|time frame|timeframe|date|eta)\b", re.I)
WHY = re.compile(r"\b(?:why|how come|reason|cause|explain|what(?:'s| is) (?:wrong|happening|going on))\b", re.I)
DECLINE = re.compile(r"\b(?:declin\w*|fail\w*|reject\w*|refus\w*|bounc\w*)\b", re.I)
RETURNED = re.compile(r"\breturned\s+(?:transaction|payment|transfer)\b|"
                      r"\b(?:transaction|payment|transfer)\s+(?:(?:was|has been|is)\s+)?returned\b", re.I)
RESOLUTION = re.compile(r"\b(?:fix\w*|resolv\w*|resolution|repair\w*|working again)\b", re.I)
AMOUNT = re.compile(r"\b(?:how much|amount|total)\b", re.I)
STATUS_QUERY = re.compile(r"\b(?:where|status|progress|await|waiting|still|yet)\b", re.I)
MEANING = re.compile(r"\b(?:mean\w*|what (?:is|are)|explain|why)\b", re.I)
_VIEW = r"(?:check|see|find|view|locate|look|access)"
_INTERFACE = r"(?:statement|app|account history|transaction history)"
NAVIGATION = re.compile(rf"\bwhere\b[^.?!]{{0,35}}\b{_VIEW}\b|"
                        rf"\b{_VIEW}\b[^.?!]{{0,65}}\b{_INTERFACE}\b|"
                        rf"\b{_INTERFACE}\b[^.?!]{{0,35}}\b{_VIEW}\b", re.I)
HELP = re.compile(r"\b(?:help|what can you do|what (?:do|should|can) i do|how (?:do|can) (?:i|you) (?:fix|resolve))\b|"
                  r"\b(?:can|could|would|will) you\b[^.?!]{0,25}\b(?:fix|resolve|sort out)\b|"
                  r"\bplease\s+(?:fix|resolve|sort out)\b", re.I)

PATHS = {"refund_status": "refund.status", "settlement_status": "settlement.status",
         "payment_status": "status", "refund_reason": "refund.reason", "settlement_reason": "settlement.reason",
         "expected_refund_date": "refund.expected_date"}
LABELS = {"refund_status": "refund status", "settlement_status": "settlement status",
          "payment_status": "payment status", "refund_reason": "refund reason",
          "settlement_reason": "settlement reason", "expected_refund_date": "expected refund date"}
MEANING_TEXT = "In these records, a pending status means completion is not confirmed."
NAVIGATION_TEXT = ("I cannot access your account statement or app. "
                   "This record does not describe what they display or where to find the payment.")
CAPABILITY_TEXT = "I can explain the retrieved record, but I cannot move money or change your account."
RESOLUTION_TEXT = "I cannot determine when this issue will be resolved from the available payment information."
RETURN_TEXT = "Do you mean a merchant refund or a payment returned to its sender?"
LIMITS = {"pending_meaning": MEANING_TEXT, "account_instructions": NAVIGATION_TEXT,
          "assistant_capabilities": CAPABILITY_TEXT, "resolution_timing": RESOLUTION_TEXT,
          "return_clarification": RETURN_TEXT}
STATES = {"pending", "processing", "succeeded", "settled", "completed", "failed", "cancelled",
          "canceled", "unknown", "approved", "declined", "reversed", "refunded"}
ALIASES = {"successful": "succeeded", "successfully processed": "succeeded", "canceled": "cancelled"}


def ambiguous_return(question: str) -> bool:
    # A returned transfer need not be a merchant refund. Do not choose a date
    # role merely because one of those fields happens to be populated.
    return bool(RETURNED.search(question) and not REFUND.search(question))


def timing_requests(question: str) -> tuple[bool, bool]:
    """Resolution timing and financial-process timing, separately by clause.

    This finite grammar preserves both requests in e.g. 'When will it be fixed,
    and when will my refund arrive?' A retry interval is not a resolution ETA.
    """
    clauses = re.split(r"[.!?;]|\band\b", question, flags=re.I)
    timed = [clause for clause in clauses if TIMING.search(clause)]
    return (any(RESOLUTION.search(clause) for clause in timed),
            any(not RESOLUTION.search(clause) for clause in timed))


def requirements(question: str, data: dict) -> tuple[str, ...]:
    """Compose topic and facet triggers, without case IDs or dataset intent labels."""
    q = question.casefold().replace("’", "'")
    refund = bool(REFUND.search(q))
    pending = bool(PENDING.search(q))
    resolution_time, process_time = timing_requests(q)
    fields = []
    if refund:
        if not AMOUNT.search(q) or STATUS_QUERY.search(q) or TIMING.search(q):
            fields.append("refund_status")
        if process_time:
            fields.append("expected_refund_date")
        if WHY.search(q):
            fields.append("refund_reason")
    # Refund progress and payment settlement are different processes. Only an
    # explicit settlement request adds settlement obligations to a refund question.
    if (pending and (not refund or re.search(r"\bsettle\w*\b", q))
            and (data.get("status") not in {"declined", "failed"} or re.search(r"\bpending\b", q))):
        fields.append("payment_status" if not data.get("settlement") and data.get("status") in {"pending", "processing"}
                      else "settlement_status")
        if MEANING.search(q):
            fields.append("pending_meaning")
        if WHY.search(q):
            fields.append("settlement_reason")
    if NAVIGATION.search(q):
        fields.append("account_instructions")
    if HELP.search(q):
        fields.append("assistant_capabilities")
    if resolution_time:
        fields.append("resolution_timing")
    if ambiguous_return(q):
        fields.append("return_clarification")
    return tuple(dict.fromkeys(fields))


def instruction(question: str) -> str:
    """Code-owned hints from the same plan, never raw user text in system instructions."""
    fields = requirements(question, {})
    if not fields:
        return ""
    lines = ["Payment-support coverage requirements: " + ", ".join(fields) + ".",
             "Retrieve the current record. State each requested status with its subject, for example "
             "'Refund status: pending.' Use the actual value, never this example as evidence. "
             "If there is no settlement object and payment status is pending/processing, use payment status. "
             "A payment settlement date does not establish refund arrival. "
             "A retry interval or settlement date does not predict when a problem will be fixed. "
             "For return_clarification, ask which kind of return the customer means before assigning an arrival date. "
             "For an absent field, say 'The record does not show a refund status/reason' "
             "or 'The record does not show an expected refund date', selecting the actual absent field. "
             "Quote a recorded reason as 'Refund reason: ...' or 'Settlement reason: ...'; never infer a cause."]
    lines.extend(LIMITS[field] for field in fields if field in LIMITS)
    return "\n".join(lines)


def _normal(value):
    text = str(value).casefold().strip()
    return ALIASES.get(text, text)


def status_claims(text: str):
    """Subject-bound affirmative/negative lifecycle status statements.

    Merely mentioning a status, a question, or saying it is NOT a different state
    cannot satisfy an affirmative coverage requirement.
    """
    from .missing_information import clauses
    status = "|".join(sorted(STATES | set(ALIASES), key=len, reverse=True))
    about = r"(?:\s+(?:for|on|of)\s+(?:(?:the|this|your|my)\s+)?(?:transaction|payment|transfer)(?:\s+(?:txn|xfer)_[A-Za-z0-9]+)?)?"
    pattern = re.compile(rf"\b(?P<subject>refund|settlement|payment)\b(?:\s+status)?"
                         rf"{about}\s*"
                         rf"(?:(?:is|was|remains|has status)\s+|:\s*)"
                         rf"(?P<negative>not\s+)?(?:still\s+)?(?P<status>{status})\b", re.I)
    for clause in clauses(text):
        if clause.endswith("?"):
            continue
        for match in pattern.finditer(clause):
            yield match.group("subject").lower() + "_status", _normal(match.group("status")), bool(match.group("negative")), match.group(0)


def covered(answer: str, field: str, data: dict) -> bool:
    if field in LIMITS:
        from .missing_information import clauses
        # A quoted or negated fragment must not satisfy a capability statement.
        actual = {clause.casefold() for clause in clauses(answer)}
        return all(clause.casefold() in actual for clause in clauses(LIMITS[field]))
    value = value_for_field(data, field)
    if value is None:
        return states_absent(answer, field)
    if field.endswith("status"):
        return any(role == field and status == _normal(value) and not neg
                   for role, status, neg, _ in status_claims(answer))
    if field == "expected_refund_date":
        from .financial_roles import claims
        return any(role == field and date == str(value) for role, date, _ in claims(answer))
    # Reasons are quoted record fields, not inferred from a status or a date.
    return bool(re.search(rf"\b{re.escape(LABELS[field])}\s*:\s*{re.escape(str(value))}(?=[.!?;]|$)", answer, re.I))


def supplement(question: str, data: dict, answer: str = "") -> str:
    """Validated record text and schema/capability explanations, shared by writers.

    Unknown causes/dates are explicit. Free text is copied only from designated
    trusted schema fields and with a bounded format; the whole answer is rechecked.
    """
    lines = []
    for field in requirements(question, data):
        if covered(answer, field, data):
            continue
        if field in LIMITS:
            lines.append(LIMITS[field])
            continue
        value = value_for_field(data, field)
        if value is None:
            lines.append(f"The record does not show a {LABELS[field]}." if not field.startswith("expected") else
                         f"The record does not show an {LABELS[field]}.")
        elif field.endswith("status") and _normal(value) in STATES:
            lines.append(f"{LABELS[field].capitalize()}: {value}.")
        elif field.endswith("date"):
            lines.append(f"{LABELS[field].capitalize()}: {value}.")
        elif isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9 ,'\-]{0,199}", value):
            lines.append(f"{LABELS[field].capitalize()}: {value}.")
    return " ".join(lines)


def check(answer: str, tool_log: list[dict], question: str):
    from .binding import segments
    from .guardrails import BLOCKED_OUTPUT_MSG, GuardResult
    from .provenance import trusted_log
    latest = {}
    for call in trusted_log(tool_log):
        if call["name"] == "get_transaction" and (rid := call["input"].get("txn_id")):
            latest[rid] = call["result"]
    reasons, checks = [], []
    # Validate every recognized assertion even if another clause gives the right status.
    for clause, rid in segments(answer, set(latest)):
        if rid is None and len(latest) == 1:
            rid = next(iter(latest))
        result = latest.get(rid, {})
        data = result.get("data")
        valid = result.get("status") == "found" and isinstance(data, dict) and data.get("txn_id") == rid
        for field, value, negative, phrase in status_claims(clause):
            expected = value_for_field(data, field) if valid else None
            supported = expected is not None and ((value == _normal(expected)) != negative)
            checks.append({"kind": "support_status", "record_id": rid, "field": field,
                           "path": PATHS[field], "text": phrase, "evidence_value": expected,
                           "verdict": "supported" if supported else "unsupported"})
            if not supported:
                reasons.append(f"support_status_mismatch:{rid or 'unresolved'}:{field}")
    # Multi-record coverage remains the comparison check's responsibility.
    if len(latest) == 1:
        rid, result = next(iter(latest.items()))
        data = result.get("data")
        if result.get("status") == "found" and isinstance(data, dict) and data.get("txn_id") == rid:
            own = " ".join(c for c, subject in segments(answer, {rid}) if subject in (None, rid))
            for field in requirements(question, data):
                ok = covered(own, field, data)
                if field not in LIMITS and value_for_field(data, field) is not None and states_absent(own, field):
                    ok = False
                checks.append({"kind": "support_coverage", "record_id": rid, "field": field,
                               "path": PATHS.get(field), "verdict": "covered" if ok else "missing"})
                if not ok:
                    reasons.append(f"support_information_missing:{rid}:{field}")
    return GuardResult("block" if reasons else "allow", BLOCKED_OUTPUT_MSG if reasons else answer,
                       list(dict.fromkeys(reasons)), checks)
