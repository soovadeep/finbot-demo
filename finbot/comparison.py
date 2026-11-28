"""Bounded coverage for explicit payment comparisons, separate from factuality checks.

Require each named record's lookup and requested amount/currency/status, or an explicit
not-found statement. This checks recognized fields and ID-bound prose, not arbitrary
semantic completeness, inferred references, or the relevance of every sentence.
"""
from __future__ import annotations

import re
from decimal import Decimal

from .binding import segments, stated_currencies
from .guardrails import AMOUNT, BLOCKED_OUTPUT_MSG, MONEY, GuardResult, _affirmed
from .tools import TXN_ID

_COMPARE = re.compile(r"\b(compare|comparison|versus|vs|differences?|both|each)\b", re.I)
_MISSING = re.compile(r"\b(not found|could(?: not|n't) find|no record|does(?: not|n't) exist)\b", re.I)


def latest_records(tool_log: list[dict]) -> dict[str, dict]:
    return {c["input"]["txn_id"]: c for c in tool_log
            if c["name"] == "get_transaction" and c.get("input", {}).get("txn_id")}


class ComparisonCoverageVerifier:
    name = "comparison_coverage"

    def __init__(self, question: str):
        fields = []
        if re.search(r"\bamounts?\b", question, re.I):
            fields.extend(("amount", "currency"))
        elif re.search(r"\bcurrenc(?:y|ies)\b", question, re.I):
            fields.append("currency")
        if re.search(r"\b(status(?:es)?|outcomes?)\b", question, re.I):
            fields.append("status")
        ids = tuple(dict.fromkeys(TXN_ID.findall(question)))
        requested = _COMPARE.search(question) or (fields and re.search(r"\band\b", question, re.I))
        self.required_ids = ids if len(ids) > 1 and requested else ()
        self.fields = tuple(fields)  # No inferred field requirements for other comparison tasks.

    def check(self, answer: str, tool_log: list[dict], focus: str | None) -> GuardResult:
        if not self.required_ids:
            return GuardResult("allow", answer)
        snapshots = latest_records(tool_log)
        clauses = segments(answer, set(self.required_ids))
        reasons = []
        for rid in self.required_ids:
            call = snapshots.get(rid)
            if call is None:
                reasons.append(f"comparison_missing_evidence:{rid}")
                continue
            text = " ".join(clause for clause, subject in clauses if subject == rid)
            if not text:
                reasons.append(f"comparison_missing_record:{rid}")
                continue
            result = call["result"]
            if result["status"] == "not_found":
                if not _MISSING.search(text):
                    reasons.append(f"comparison_missing_unavailable_notice:{rid}")
                if AMOUNT.search(text) or MONEY.search(text) or stated_currencies(text):
                    reasons.append(f"comparison_claim_for_unavailable_record:{rid}")
                continue
            if result["status"] != "found":
                reasons.append(f"comparison_unavailable_evidence:{rid}")
                continue
            data = result.get("data") or {}
            # An ID in a heading alone does not count as a record summary.
            fields = self.fields or ("status",)
            for field in fields:
                value = str(data.get(field, ""))
                if field == "amount":
                    values = set(AMOUNT.findall(text)) | {m[0] or m[1] for m in MONEY.findall(text)}
                    present = bool(re.fullmatch(r"\d+(?:\.\d+)?", value)) and any(
                        Decimal(v.replace(",", "")) == Decimal(value) for v in values)
                elif field == "currency":
                    present = bool(value) and value in stated_currencies(text)
                else:
                    present = bool(value) and _affirmed(re.compile(rf"\b{re.escape(value)}\b", re.I), text)
                if not present:
                    reasons.append(f"comparison_missing_field:{rid}:{field}")
        return GuardResult("block", BLOCKED_OUTPUT_MSG, reasons) if reasons else GuardResult("allow", answer)


def comparison_record_answer(tool_log: list[dict], record_ids: tuple[str, ...]) -> str | None:
    """Build all requested summaries or decline fallback; never silently summarize only focus."""
    from .recordanswer import record_answer
    from .replies import RECORD_ONLY

    snapshots = latest_records(tool_log)
    parts = []
    for rid in record_ids:
        call = snapshots.get(rid)
        if call is None or call["result"]["status"] not in {"found", "not_found"}:
            return None
        part = record_answer([call], rid)
        if part is None:
            return None
        parts.append(part.removeprefix(RECORD_ONLY).strip())
    return RECORD_ONLY + " " + "\n\n".join(parts) if parts else None
