"""Explicit code obligations for policy quotations; not a semantic relevance model.

Only identifiers introduced by 'code'/'codes' are parsed. Numeric amounts, dates,
URL fragments and arbitrary keyword overlap cannot establish applicability.
"""
from __future__ import annotations

import re

_LABEL = re.compile(r"\bcodes?\b\s*(?:numbers?\s*)?[:#]?\s*", re.I)
_ID = re.compile(r"[\"'`“]?([a-z0-9][a-z0-9_-]{0,23})(?![a-z0-9_-])[\"'`”]?", re.I)
_JOIN = re.compile(r"\s*(?:,\s*(?:and\s+|or\s+)?|and\s+|or\s+|versus\s+|vs\.?\s+|[&/]\s*)", re.I)


def policy_codes(text: str) -> set[str]:
    """Recognize code 51, code R-72, codes E05 and Q17, etc.; preserve zeroes."""
    codes = set()
    for label in _LABEL.finditer(text):
        pos = label.end()
        while match := _ID.match(text, pos):
            value = match[1]
            if not any(c.isdigit() for c in value):
                break
            codes.add(value.upper())
            join = _JOIN.match(text, match.end())
            if not join:
                break
            pos = join.end()
    return codes


def passage_codes(source: dict) -> set[str]:
    """A section can identify a code even when its body contains only a definition.

    Prefer the leaf section over a page title listing all available codes. A body
    explicitly identifying another code cannot borrow relevance from its heading.
    """
    section = next((source[k] for k in ("section", "title")
                    if isinstance(source.get(k), str) and source[k].strip()), "")
    heading = policy_codes(section.split(" > ")[-1])
    body = policy_codes(source["text"])
    return body if body else heading
