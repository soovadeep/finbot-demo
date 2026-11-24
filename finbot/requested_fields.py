"""What the customer asked for, and whether an answer covers it.

The factual checks ask "is every recognized claim supported by the record?". They cannot
see an answer that is true but beside the point: asked "How much was refunded?", the reply
"Your payment was $200." states nothing false and passes them. This module adds the other
half for single-record answers:

    requested_roles(question)      the financial fields a question explicitly asks about
    RequestedInformationVerifier   each requested field is stated with its role, or, when
                                   the record has no such field, the answer says so
    missing_statements(...)        fixed sentences for absent fields, shared by the scripted
                                   writer and the record-built fallback

Coverage is finite: the triggers are a small set of English phrasings, and a requested
field counts as covered only when the role parser in finbot/financial_roles.py recognizes
it. That is strict on purpose: a refund stated in an unrecognized phrasing is sent back for
repair rather than released unchecked. Multi-record comparisons have their own coverage
check (finbot/comparison.py), so this one only applies when exactly one record was read.
"""
from __future__ import annotations

import re

from .binding import segments
from .financial_roles import PATHS, _field, _normalized, claims
from .guardrails import AMOUNT, BLOCKED_OUTPUT_MSG, MONEY, GuardResult
from .provenance import trusted_log

# Ordered: the label used in reasons, the trigger phrasings, and the words a "not recorded"
# statement must name. Triggers look for an explicit request, not a passing mention.
ROLES = {
    "refund_amount": (
        r"\bhow much\b[^.?!]{0,40}\brefund|\brefund(?:ed)?\s+amount\b|\brefund details\b|"
        r"\b(?:was|were|has|have|did)\s+(?:i|it|this|that|the payment|my payment)\s+(?:been\s+)?refund|"
        r"\b(?:any|a|my|the)\s+refund\b|\brefunded\b",
        r"refund"),
    "expected_settlement_date": (
        r"\bwhen will\b|\bhow long\b|\bexpected\b[^.?!]{0,25}\b(?:settle|arriv|clear|land)|"
        r"\bwhen (?:should|is it expected|do i expect)\b|\bsettlement (?:details|dates?)\b|\bwhen\b[^.?!]{0,30}\bsettle\b",
        r"expected settlement(?: date)?|expected date"),
    "actual_settlement_date": (
        r"\bwhen did\b[^.?!]{0,30}\b(?:settle|clear|arrive|go through|complete)|"
        r"\b(?:has|did|have)\s+(?:it|the payment|this|my payment|the transfer)\s+(?:already\s+)?(?:settle|clear)|"
        r"\bactual settlement\b|\bsettlement (?:details|dates?)\b|\bsettled on\b",
        r"actual settlement(?: date)?|settlement date"),
    "payment_amount": (
        r"\bhow much (?:was|did|is|were)\b(?![^.?!]*\brefund)|\bpayment amount\b|\bpayment and refund\b|"
        r"\bwhat (?:was|is) the amount\b",
        r""),
    "decline_reason": (
        r"\bwhy\b[^.?!]{0,40}\b(?:declin|fail|reject|refus|bounc)",
        r"reason|decline code|cause"),
}
LABELS = {"refund_amount": "a refund amount", "expected_settlement_date": "an expected settlement date",
          "actual_settlement_date": "an actual settlement date", "payment_amount": "a payment amount",
          "decline_reason": "a decline reason"}
_NOT = r"(?:\bno\b|\bnot\b|n't\b|\bnone\b|\bwithout\b)"
_ABSENT = r"(?:recorded|shown|available|listed|known|present|included|on (?:the|this) record)"


def requested_roles(question: str) -> tuple[str, ...]:
    """Fields the question explicitly asks about, in a fixed order (possibly none)."""
    q = question.casefold().replace("’", "'")
    return tuple(role for role, (trigger, _) in ROLES.items() if re.search(trigger, q))


def _states_absent(text: str, role: str) -> bool:
    words = ROLES[role][1]
    if not words:
        return False
    lowered = text.casefold()
    return bool(re.search(rf"{_NOT}[^.!?]{{0,40}}\b(?:{words})\b", lowered)
                or re.search(rf"\b(?:{words})\b[^.!?]{{0,40}}{_NOT}[^.!?]{{0,12}}{_ABSENT}", lowered))


def _value(data: dict, role: str):
    """The record's value for a role, or None when the record does not establish it."""
    if role == "payment_amount":
        return data.get("amount")
    if role == "decline_reason":
        return data.get("decline_code") or data.get("error")
    value = _field(data, PATHS[role])
    if _normalized(value, role) is None:
        return None
    if role == "actual_settlement_date" and _field(data, "settlement.status") != "settled":
        return None
    return value


def _covered(text: str, role: str, data: dict) -> bool:
    if role == "payment_amount":
        amount = str(data.get("amount", ""))
        stated = set(AMOUNT.findall(text)) | {m[0] or m[1] for m in MONEY.findall(text)}
        return any(v.replace(",", "") == amount for v in stated)
    if role == "decline_reason":
        code, message = str(data.get("decline_code") or data.get("error") or ""), str(data.get("processor_response") or "")
        return bool(code and re.search(rf"\b{re.escape(code)}\b", text)) or bool(
            message and message.casefold() in text.casefold())
    return any(r == role for r, _, _ in claims(text))


def missing_statements(data: dict, roles: tuple[str, ...]) -> str:
    """Fixed sentences for requested fields the record does not establish."""
    lines = []
    for role in roles:
        if role in {"payment_amount", "decline_reason"} or _value(data, role) is not None:
            continue
        if role == "decline_reason" or (role == "actual_settlement_date" and _field(data, "settlement.expected_date")):
            continue  # lifecycle_summary already says an actual date is not recorded
        lines.append(f"The record does not show {LABELS[role]}.")
    return " ".join(lines)


class RequestedInformationVerifier:
    """A single-record answer must address each field the question asked for."""
    name = "requested_information"

    def __init__(self, question: str):
        self.roles = requested_roles(question)

    def check(self, answer: str, tool_log: list[dict], focus: str | None) -> GuardResult:
        if not self.roles:
            return GuardResult("allow", answer)
        latest: dict[str, dict] = {}
        for call in trusted_log(tool_log):
            rid = call.get("input", {}).get("txn_id")
            if call["name"] == "get_transaction" and isinstance(rid, str) and rid:
                latest[rid] = call["result"]
        if len(latest) != 1:
            return GuardResult("allow", answer)   # none read, or a comparison (own coverage check)
        rid, result = next(iter(latest.items()))
        if result.get("status") != "found" or not isinstance(result.get("data"), dict):
            return GuardResult("allow", answer)   # a not-found answer has nothing to cover
        data = result["data"]
        about = " ".join(clause for clause, subject in segments(answer, {rid}) if subject in (rid, None)) or answer
        reasons, checks = [], []
        for role in self.roles:
            if role == "decline_reason" and str(data.get("status", "")).lower() not in {"declined", "failed"}:
                continue   # nothing was declined; the status answers the question
            present = _value(data, role) is not None
            covered = _covered(about, role, data)
            absent_stated = _states_absent(about, role)
            if present and absent_stated and not covered:
                verdict = "denied"
                reasons.append(f"requested_information_denied:{rid}:{role}")
            elif present and not covered:
                verdict = "missing"
                reasons.append(f"requested_information_missing:{rid}:{role}")
            elif not present and not (absent_stated or (role == "actual_settlement_date"
                                                        and "actual settlement date is not recorded" in about.casefold())):
                verdict = "missing_unavailable_notice"
                reasons.append(f"requested_information_unavailable_unstated:{rid}:{role}")
            else:
                verdict = "covered" if present else "absence_stated"
            checks.append({"kind": "requested_information", "record_id": rid, "role": role,
                           "record_has_value": present, "verdict": verdict, "method": "role_coverage"})
        return GuardResult("block" if reasons else "allow", BLOCKED_OUTPUT_MSG if reasons else answer,
                           reasons, checks)


def complete_record_answer(tool_log: list[dict], focus: str | None, roles: tuple[str, ...]) -> str | None:
    """The record-built fallback plus explicit statements for requested fields it lacks."""
    from .recordanswer import record_answer
    built = record_answer(tool_log, focus)
    if not built or not roles:
        return built
    calls = [c for c in tool_log if c["name"] == "get_transaction" and c["result"].get("status") == "found"
             and (focus is None or c["input"].get("txn_id") == focus)]
    if not calls:
        return built
    extra = missing_statements(calls[-1]["result"]["data"], roles)
    return f"{built} {extra}" if extra else built
