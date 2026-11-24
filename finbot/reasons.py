"""Plain-word reasons, checked against the record.

The evidence check compares numbers, codes and statuses. It does not notice an answer
that quotes the right code and then explains it wrongly: "declined with code 05 because
the card had expired". This module closes part of that gap. Each known failure key maps
to one cause, each cause to the phrases people use for it, and an answer that affirms a
cause the records of this turn don't carry is blocked.

It is still a phrase table. A cause worded in a way the table doesn't know gets through,
which is why free-text answers also go through the output guardrail's grounding check.
"""
from __future__ import annotations

import re
from typing import Any

from .guardrails import _affirmed, _sentences

# failure key (decline code or gateway error) -> cause
KEY_CAUSE: dict[str, str] = {
    "05": "no_reason_given", "51": "insufficient_funds", "54": "expired_card", "14": "invalid_card",
    "61": "limit", "65": "limit", "N7": "security_code", "59": "fraud", "91": "issuer_unavailable",
    "R1": "revoked", "RISK_BLOCKED": "risk_block", "3DS_FAILED": "three_ds", "AVS_MISMATCH": "address",
    "PROCESSOR_TIMEOUT": "timeout", "PROCESSOR_ERROR": "processor_error", "NO_ROUTE": "no_route",
    "DUPLICATE_REQUEST": "duplicate",
}

_SEC = r"(cvv2?|cvc|security code)"
CAUSE_PHRASES: dict[str, re.Pattern[str]] = {k: re.compile(v, re.I) for k, v in {
    "insufficient_funds": r"\b(insufficient funds|not enough (money|funds|balance)|lack of funds|low balance|"
                          r"ran out of (money|funds))\b",
    "expired_card": r"\b(card (has |had |is |was )?expired|expired card|expiry date (has |had )?passed)\b",
    "invalid_card": r"\b(invalid card number|card number (is|was) (invalid|wrong|incorrect|mistyped)|"
                    r"(wrong|incorrect) card number)\b",
    "security_code": rf"\b({_SEC} (mismatch|did ?n[o']t match|(is|was) (wrong|incorrect))|"
                     rf"(wrong|incorrect) {_SEC})\b",
    # A fraud check that passed, or 3-D Secure that "wasn't required", is not a cause: live drafts
    # mention both routinely while explaining a different decline, so the phrase must say it failed.
    "fraud": r"\b(suspected fraud|suspects? fraud|fraud (suspicion|block(ed)?)|blocked (it )?(as|for) fraud|"
             r"flagged (it |this |the payment )?as (fraud|fraudulent|suspicious)|"
             r"(failed|tripped|did ?n[o']t pass) (the |a |our |its )?fraud (check|screening)|"
             r"fraud (check|screening) (failed|flagged|blocked|stopped|returned [\"'`]?block))\b",
    "limit": r"\b(exceed(s|ed)?|over|above|reached|hit) (the |its |their |a )?"
             r"((card|withdrawal|spending|daily|amount|frequency) )*limit\b",
    "issuer_unavailable": r"\b(issuer|issuing bank|bank) (was|is) (temporarily )?(unavailable|unreachable|offline)\b",
    "revoked": r"\b(revoked (the |their )?authori[sz]ation|revocation of authori[sz]ation|"
               r"cancell?ed the (subscription|recurring))\b",
    "risk_block": r"\b(blocked by (the merchant's |your |a |the )?(own )?risk|risk (rule|rules|settings) blocked)\b",
    "three_ds": r"\b((3-?d ?secure|3ds)( authentication| verification| check| challenge| step)? "
                r"(failed|was failed|did ?n[o']t (complete|succeed|pass)|was (abandoned|not completed)|"
                r"returned [\"'`]?authentication_fail)|"
                r"fail(ed|ure of)? (or abandoned )?(the )?(3-?d ?secure|3ds)|(3-?d ?secure|3ds) failure|"
                r"abandoned (the )?(3-?d ?secure|3ds))",
    "address": r"\b(billing )?address (mismatch|did ?n[o']t match)\b",
    "timeout": r"\b(timed out|time-?out|did not respond in time)\b",
    "processor_error": r"\bprocessor (error|fault|failure)\b",
    "duplicate": r"\b(duplicate (request|payment)|idempotency key (was )?reused)\b",
}.items()}

_KEY_FIELDS = {"decline_code", "error", "code", "final_code", "reason_key"}
_TXN_TOOLS = {"get_transaction", "search_transaction_logs", "get_routing_trace"}


def _keys(v: Any) -> set[str]:
    """Every failure key anywhere in a tool result (record, log events, routing attempts)."""
    if isinstance(v, dict):
        own = {str(x) for k, x in v.items() if k in _KEY_FIELDS and isinstance(x, str)}
        return own.union(*(_keys(x) for x in v.values()))
    if isinstance(v, list):
        return set().union(*(_keys(x) for x in v)) if v else set()
    return set()


def reason_check(answer: str, tool_log: list[dict]) -> list[str]:
    """Reasons that contradict the record. Applies only when exactly one failed transaction
    was looked up this turn, so a help page listing many codes is not judged by it."""
    found = [c for c in tool_log if c["result"]["status"] == "found" and c["name"] in _TXN_TOOLS]
    records = [c["result"]["data"] for c in found if c["name"] == "get_transaction"]
    if len(records) != 1 or str(records[0].get("status", "")).lower() in ("approved", "succeeded", "settled"):
        return []
    keys = set().union(*(_keys(c["result"]["data"]) for c in found))
    supported = {KEY_CAUSE[k] for k in keys if k in KEY_CAUSE}
    if not supported:
        return []           # an unmapped failure: nothing to compare against
    if "risk_block" in supported:
        supported.add("fraud")   # the risk rule is a fraud screen: "the fraud check blocked it" is the same cause
    record_key = records[0].get("decline_code") or records[0].get("error") or "unknown"
    reasons = []
    for cause, pattern in CAUSE_PHRASES.items():
        if cause not in supported and any(_affirmed(pattern, s) for s in _sentences(answer)):
            reasons.append(f"reason_mismatch:record={record_key},claimed={cause}")
    return reasons


# ---------------------------------------------------------------- causes in other words

# A clause that gives a cause. "since" counts only when a clause follows ("since the card..."),
# not as a time ("since 2 November").
CAUSAL = re.compile(r"\b(because(?:\s+of)?|due to|owing to|as a result of|caused by|the reason (?:was|is) that|"
                    r"since(?=\s+(?:the|there|it|they|your|you|this|its|their|we|he|she|our)\b))\s+([^.;!?]{3,160})",
                    re.I)
_NEGATED_CAUSE = re.compile(r"\b(not|n't|never|no longer)\s*$", re.I)
_WORD = re.compile(r"[a-z][a-z'-]{3,}")
_STOP = frozenset("""that this there their they them then than with from into onto over under about after before
were been being have having does doing would could should might must will shall your yours ours what which while
when where whom whose also just only very more most much many some such same other another each every both
either neither because since card cards payment payments transaction transactions charge charges account accounts
bank banks issuer issuers customer customers merchant merchants request requests record records time day days
money amount it's didn't doesn't don't can't cannot wasn't isn't aren't weren't hasn't haven't hadn't won't
shouldn't couldn't wouldn't still currently moment again likely anything something ending need needs
cardholder cardholder's""".split())
# A clause about the assistant itself ("because I only have read-only access", "since our documentation
# doesn't cover it") explains what the bot can do, not why the record is in its state.
_ABOUT_ASSISTANT = re.compile(r"^\s*(i|i'm|i've|we|we're|my|our (documentation|docs|help pages|knowledge base))\b",
                              re.I)


def _stem(w: str) -> str:
    """Crude suffix stripping, enough for "released"/"release" and "reviews"/"review"."""
    for suffix in ("'s", "ing", "ed", "es", "s", "d"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            return w[: -len(suffix)]
    return w


def _content_words(text: str) -> set[str]:
    return {_stem(w.strip("'-")) for w in _WORD.findall(text.lower()) if w.strip("'-") not in _STOP} - _STOP


def cause_clause_check(answer: str, tool_log: list[dict]) -> list[str]:
    """A cause given in words the phrase table doesn't know must still rest on the records.

    The phrase table above catches a known cause that contradicts the record. It cannot judge
    "because the balance was too low" or "since the issuer's fraud team stopped it": those are
    causes in other words, and the randomized stress test (finbot/faultgen.py) showed they were
    most of what still reached users. Here, with a record in the turn, a causal clause passes only
    if it names a cause the record's own failure keys carry (in the table's words), or if every
    content word in it appears in this turn's trusted tool data (the policy meaning, the next
    step, a help page). Anything else is a cause the system cannot check, so it is not said."""
    from .domains import record_tools
    from .provenance import trusted_blob
    found = [c for c in tool_log if c["result"]["status"] == "found"]
    if not any(c["name"] in record_tools() for c in found):
        return []                       # help-page answers explain from the page; the citation check covers them
    keys = set().union(*(_keys(c["result"]["data"]) for c in found))
    supported = {KEY_CAUSE[k] for k in keys if k in KEY_CAUSE}
    blob_words = {_stem(w.strip("'-")) for w in _WORD.findall(trusted_blob(tool_log).lower().replace("_", " "))}
    reasons = []
    for m in CAUSAL.finditer(answer):
        if _NEGATED_CAUSE.search(answer[max(0, m.start() - 12):m.start()]):
            continue                    # "not because of ...": not a claim
        clause = m.group(2)
        if _ABOUT_ASSISTANT.search(clause):
            continue
        if any(CAUSE_PHRASES[c].search(clause) for c in supported if c in CAUSE_PHRASES):
            continue
        if _content_words(clause) <= blob_words:
            continue
        reasons.append("unverified_cause")
    return list(dict.fromkeys(reasons))
