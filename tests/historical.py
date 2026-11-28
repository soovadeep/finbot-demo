"""Compare a fresh evaluation with a saved historical report.

Later additions put new entries into the same structures without changing any verdict:
the requested-information and supported missing-information checks add trace items, and every demo
result now says which writer produced it. Those additions are set aside here, so every
original verdict, reason and answer must still match exactly.
"""

ADDED_KEYS = {"writer_source", "writer_label"}


def historical(value):
    if isinstance(value, dict):
        return {k: historical(v) for k, v in value.items() if k not in ADDED_KEYS}
    if isinstance(value, list):
        return [historical(v) for v in value
                if not (isinstance(v, dict) and (v.get("kind") == "requested_information"
                        or (v.get("kind") == "missing_information" and v.get("verdict") == "supported")))]
    return value
