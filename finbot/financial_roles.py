"""Finite, schema-bound financial claim checks, not general semantic verification.

A value may be on the right record but in the wrong field. Recognized English
claims bind to (record ID, financial role, value), with field paths exposed to
the inspector. Only the latest transaction lookup can support a claim; policy
prose, logs, and an expected date cannot establish an actual settlement date.

Supported roles: payment amount, refund amount, expected settlement date and
actual settlement date. Dates use ISO calendar format; arbitrary paraphrases,
implicit roles, omissions and other lifecycle facts are outside this parser.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .binding import segments
from .guardrails import BLOCKED_OUTPUT_MSG, GuardResult, NEGATION
from .provenance import trusted_log

PATHS = {
    "payment_amount": "amount",
    "refund_amount": "refund.amount",
    "expected_settlement_date": "settlement.expected_date",
    "actual_settlement_date": "settlement.actual_date",
}
_DATE = r"(?P<value>\d{4}-\d{2}-\d{2})(?![\dT])"
_MONEY = r"(?:[A-Z]{3}\s+|[$£€]\s*)?(?P<value>\d+(?:\.\d{2})?)(?!\d|[./-]\d)"
_JOIN = r"\s*(?:(?:is|was|of|on|by|for|at)\s+|:\s*)*"
_PATTERNS = [
    ("expected_settlement_date", re.compile(
        r"\b(?:(?:expected|estimated|scheduled)\s+settlement(?:\s+date)?|"
        r"settlement(?:\s+date)?\s+(?:(?:is|was)\s+)?(?:expected|estimated|scheduled)|"
        r"(?:expected|scheduled)\s+to\s+(?:settle|be settled))" + _JOIN + _DATE, re.I)),
    ("actual_settlement_date", re.compile(
        r"\b(?:(?:(?:actual|recorded)\s+)?settlement\s+date|settled|settlement\s+completed)"
        + _JOIN + _DATE, re.I)),
    ("refund_amount", re.compile(
        r"\b(?:refund(?:\s+amount)?|refunded)" + _JOIN + _MONEY, re.I)),
    ("payment_amount", re.compile(
        r"\b(?:(?:original\s+)?(?:payment|transaction)\s+amount|amount)" + _JOIN + _MONEY, re.I)),
]


def _field(data: dict, path: str):
    value = data
    for key in path.split("."):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _normalized(value, role: str):
    if value is None or isinstance(value, bool):
        return None
    try:
        if role.endswith("date"):
            return date.fromisoformat(str(value)).isoformat()
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount >= 0 else None
    except (ValueError, InvalidOperation):
        return None


def claims(text: str):
    """Recognize specific role/value phrases, preserving their exact source span.

    Specific roles consume their span before generic 'settlement date'/'amount'
    patterns. This prevents 'expected settlement date' being read as actual.
    Negated phrases are outside this affirmative-claim check.
    """
    text = re.sub(r"[*_`]", "", text)
    occupied = []
    found = []
    for role, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in occupied):
                continue
            occupied.append(match.span())
            before = re.split(r"[.!?;,]\s", text[max(0, match.start() - 40):match.start()])[-1]
            if NEGATION.search(before):
                continue
            found.append((match.start(), role, match.group("value"), match.group(0)))
    return [(role, value, phrase) for _, role, value, phrase in sorted(found)]


class FinancialRoleVerifier:
    name = "financial_roles"

    def check(self, answer, tool_log, focus=None):
        latest = {}
        for call in trusted_log(tool_log):
            if call["name"] == "get_transaction":
                rid = call.get("input", {}).get("txn_id")
                if isinstance(rid, str) and rid:
                    latest[rid] = call["result"]
        # General policy answers have no transaction scope.
        if not latest:
            return GuardResult("allow", answer)
        checks, reasons = [], []
        for clause, rid in segments(answer, set(latest)):
            # An unnamed claim is unambiguous only when exactly one ID was read.
            if rid is None and len(latest) == 1:
                rid = next(iter(latest))
            for role, value, phrase in claims(clause):
                result = latest.get(rid, {})
                data = result.get("data")
                valid = (result.get("status") == "found" and isinstance(data, dict)
                         and data.get("txn_id") == rid)
                path = PATHS[role]
                expected = _field(data, path) if valid else None
                norm = _normalized(expected, role)
                supported = norm is not None and norm == _normalized(value, role)
                if role == "actual_settlement_date" and valid:
                    supported = supported and _field(data, "settlement.status") == "settled"
                verdict = "supported" if supported else "unsupported"
                checks.append({"kind": "financial_role", "record_id": rid, "role": role,
                               "path": path, "claimed_value": value, "evidence_value": expected,
                               "text": phrase, "verdict": verdict,
                               "method": "schema_field_match"})
                if not supported:
                    reasons.append(f"financial_role_mismatch:{rid or 'unresolved'}:{role}")
        return GuardResult("block" if reasons else "allow", BLOCKED_OUTPUT_MSG if reasons else answer,
                           list(dict.fromkeys(reasons)), checks)


def lifecycle_summary(data: dict) -> str:
    """Validated role-labelled details for the scripted writer and record fallback."""
    lines = []
    for role, label in (("expected_settlement_date", "Expected settlement date"),
                        ("actual_settlement_date", "Actual settlement date"),
                        ("refund_amount", "Refund amount")):
        value = _field(data, PATHS[role])
        if _normalized(value, role) is None:
            continue
        if role == "actual_settlement_date" and _field(data, "settlement.status") != "settled":
            continue
        lines.append(f"{label}: {value}.")
    if _field(data, "settlement.expected_date") and _field(data, "settlement.actual_date") is None:
        lines.append("An actual settlement date is not recorded.")
    return " ".join(lines)
