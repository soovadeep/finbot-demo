"""Shared, finite interpretation of missing-record-information statements.

Absence of evidence is different from an event not occurring. Whole clauses must
describe a field being unavailable/undocumented; a nearby 'not' is insufficient.
This is a conservative English grammar, not unrestricted semantic inference.
"""
from __future__ import annotations

import re

_ID = r"(?:[a-z]+_[A-Za-z0-9]{6,})"
_OBJECT = rf"(?:(?:the|this|that|your|my)\s+)?(?:payment|transaction|transfer|record)(?:\s+{_ID})?"
_ABOUT = rf"(?:\s+(?:for|on|of)\s+{_OBJECT})?"
_SOURCE = rf"(?:(?:the|this|that|our|current|retrieved|available|latest)\s+){{0,2}}(?:records?|data|information){_ABOUT}"
_TAIL = rf"(?:\s+(?:in|on|from)\s+{_SOURCE})?"
_ARTICLE = r"(?:(?:the|a|an|any|its|your)\s+)?"
_FIELDS = {
    "expected_settlement_date": r"(?:expected|estimated|scheduled)\s+(?:settlement\s+)?date",
    "actual_settlement_date": r"(?:actual\s+)?settlement\s+date|actual\s+date",
    "refund_amount": r"refund\s+amount",
    "refund_status": r"refund\s+status",
    "refund": r"refund(?:\s+(?:details|information))?",
    "settlement": r"settlement(?:\s+(?:details|information))?",
    "dispute": r"(?:dispute|chargeback)(?:\s+(?:details|information))?",
    "payment_amount": r"(?:payment|transaction|original)\s+amount",
    "decline_reason": r"decline\s+(?:reason|code)|reason\s+for\s+(?:the\s+)?decline",
}
_FIELD = "|".join(f"(?P<{name}>{pattern})" for name, pattern in _FIELDS.items())
_TARGET = rf"{_ARTICLE}(?:{_FIELD}){_ABOUT}"
_RECORDED = r"(?:recorded|shown|listed|included|documented|provided|known|present|available)"
_PATTERNS = [
    re.compile(rf"{_SOURCE}\s+(?:does not|doesn't|do not|don't)\s+(?:show|record|list|include|contain|provide)\s+{_TARGET}", re.I),
    re.compile(rf"{_SOURCE}\s+(?:shows?|records?|lists?|includes?|contains?|provides?)\s+no\s+{_TARGET}", re.I),
    re.compile(rf"{_TARGET}\s+(?:is|was|are|were)\s+(?:not\s+{_RECORDED}|unavailable|unknown|missing){_TAIL}", re.I),
    re.compile(rf"no\s+{_TARGET}\s+(?:(?:is|was|are|were)\s+)?{_RECORDED}{_TAIL}", re.I),
    re.compile(rf"there\s+(?:is|are)\s+no\s+{_TARGET}\s+(?:in|on)\s+{_SOURCE}", re.I),
]
_COVERS = {"refund": {"refund_amount", "refund_status"},
           "settlement": {"actual_settlement_date", "expected_settlement_date"}}


def absence_field(clause: str) -> str | None:
    text = clause.strip().replace("’", "'")
    if text.endswith("?"):
        return None
    text = re.sub(r"[*`]", "", text).strip().rstrip(".!;").strip()
    text = re.sub(rf"^(?:(?:transaction|payment|transfer)\s+)?{_ID}\s*:\s*", "", text, flags=re.I)
    for pattern in _PATTERNS:
        if match := pattern.fullmatch(text):
            field = next(name for name, value in match.groupdict().items() if value is not None)
            # 'A refund is unavailable' may assert ineligibility, not missing data.
            if field in {"refund", "settlement", "dispute"} and not re.search(
                    r"\b(record\w*|data|information|details|shown|listed|included|documented)\b", text, re.I):
                return None
            return field
    return None


def clauses(text: str) -> list[str]:
    # Keep conjunctions within a clause. A mixed claim must not inherit an exemption
    # merely because its opening mentions missing data. Other verifiers inspect it.
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", text) if s.strip()]


def states_absent(text: str, role: str) -> bool:
    return any((field := absence_field(clause)) == role or role in _COVERS.get(field, set())
               for clause in clauses(text))


def value_for_field(data: dict, field: str):
    # Lazy imports avoid a guardrails -> role parser -> guardrails import cycle.
    from .financial_roles import PATHS, _field, _normalized
    if field == "decline_reason":
        return data.get("decline_code") or data.get("error")
    if field in PATHS:
        value = _field(data, PATHS[field])
        if _normalized(value, field) is None:
            return None
        if field == "actual_settlement_date" and _field(data, "settlement.status") != "settled":
            return None
        return value
    value = _field(data, "refund.status" if field == "refund_status" else field)
    return value if value not in (None, "", {}, []) else None


def check_absence(answer: str, tool_log: list[dict]) -> tuple[str, list[str], list[dict]]:
    """Remove only verified absence clauses from broad lifecycle-mention checking.

    Use the latest scoped record, never matching keywords elsewhere in a tool blob.
    A not-found result supersedes an earlier snapshot and cannot establish absence
    of a field on a record that was not retrieved.
    """
    from .binding import segments
    from .domains import id_of, record_tools
    from .provenance import trusted_log
    latest = {}
    for call in trusted_log(tool_log):
        if call["name"] in record_tools() and (rid := id_of(call["input"])):
            latest[rid] = call["result"]
    remaining, reasons, checks = [], [], []
    for clause, rid in segments(answer, set(latest)):
        field = absence_field(clause)
        if field is None:
            remaining.append(clause)
            continue
        if rid is None and len(latest) == 1:
            rid = next(iter(latest))
        result = latest.get(rid, {})
        data = result.get("data")
        verified = result.get("status") == "found" and isinstance(data, dict) and id_of(data) == rid
        available = verified and value_for_field(data, field) is not None
        allowed = verified and not available
        if not allowed:
            reason = "recorded_information_denied" if available else "missing_information_without_record"
            reasons.append(f"{reason}:{rid or 'unresolved'}:{field}")
            remaining.append(clause)
        checks.append({"kind": "missing_information", "record_id": rid, "field": field,
                       "text": clause, "verdict": "supported" if allowed else "unsupported"})
    return " ".join(remaining), reasons, checks
