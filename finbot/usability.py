"""Local, export-only usability pilot over the deployed four-record conversation.

No participant results are bundled. The researcher controls recruitment, consent,
assignment and custody of downloaded exports; the demo does not persist them.
"""
from __future__ import annotations

import math
import re
from statistics import mean, median

from .clarification_conversation import run_conversation

PROTOCOL = "finbot-usability-pilot-v1"
ARMS = ("clarify", "full_list")
TASKS = {
    "transfer": {
        "opening": "My $200 payment hasn't arrived.",
        "memory": "You paid Willow Repairs by bank transfer in November 2026, for $200. "
                  "You do not remember the exact day. Find that payment and check its status.",
        "target": "txn_EMIX0001",
    },
    "card": {
        "opening": "Can you check my $200 payment?",
        "memory": "You paid Willow Repairs by card in November 2026, for $200. "
                  "You do not remember the exact day. Find that payment and check its status.",
        "target": "txn_EMIX0002",
    },
}


def public_tasks() -> dict:
    return {"protocol": PROTOCOL, "arms": list(ARMS),
            "tasks": {key: {k: v for k, v in task.items() if k != "target"} for key, task in TASKS.items()}}


def validate_export(entry: dict, *, allow_rehearsal: bool = False) -> dict:
    if not isinstance(entry, dict) or entry.get("protocol") != PROTOCOL:
        raise ValueError("Wrong pilot protocol.")
    mode, code, task, arm = (entry.get(k) for k in ("mode", "participant_code", "task", "arm"))
    if mode not in ("participant", "rehearsal") or (mode == "rehearsal" and not allow_rehearsal):
        raise ValueError("Rehearsal exports are excluded from participant analyses.")
    if not isinstance(code, str) or not re.fullmatch(r"P[0-9]{3,8}", code):
        raise ValueError("Use an assigned opaque participant code.")
    if entry.get("consent") is not True or task not in TASKS or arm not in ARMS:
        raise ValueError("Consent and a valid task/arm assignment are required.")
    effort = entry.get("effort")
    if type(effort) is not int or not 1 <= effort <= 7:
        raise ValueError("Effort must be an integer from 1 (very low) to 7 (very high).")
    elapsed = entry.get("elapsed_ms")
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 < elapsed <= 1_800_000:
        raise ValueError("Invalid elapsed time; interrupted sessions need separate review.")
    timed = entry.get("events")
    if not isinstance(timed, list) or not 2 <= len(timed) <= 12:
        raise ValueError("Supply 2–12 recorded events.")
    previous = -1
    events = []
    for item in timed:
        if not isinstance(item, dict) or set(item) != {"at_ms", "event"}:
            raise ValueError("Malformed timed event.")
        at = item["at_ms"]
        if type(at) not in (int, float) or not math.isfinite(at) or not 0 <= at <= elapsed or at < previous:
            raise ValueError("Event times must be finite, monotonic and within the session.")
        if not isinstance(item["event"], dict):
            raise ValueError("Malformed customer event.")
        previous = at
        events.append(item["event"])
    if events[0] != {"type": "message", "text": TASKS[task]["opening"]}:
        raise ValueError("Opening must match the assigned task.")
    if arm == "full_list" and any(e.get("type") == "message" for e in events[1:]):
        raise ValueError("The full-list arm does not ask clarification questions.")
    result = run_conversation({"events": events, "live": False, "fault": "none"})
    if not result["selected_id"] and not result["unresolved"]:
        raise ValueError("Finish with confirmation or an explicit unresolved choice.")
    if entry.get("selected_id") != result["selected_id"]:
        raise ValueError("Exported selection does not match replayed customer events.")
    selected = result["selected_id"]
    outcome = "correct" if selected == TASKS[task]["target"] else "wrong" if selected else "unresolved"
    final_choice = max(i for i, e in enumerate(events) if e["type"] in ("confirm", "unresolved")
                       or (e["type"] == "resolve_selection" and e["choice"] == "use_record"))
    return {"participant_code": code, "mode": mode, "task": task, "arm": arm, "outcome": outcome,
            "decision_ms": timed[final_choice]["at_ms"], "elapsed_ms": elapsed, "effort": effort,
            "questions": result["questions_asked"] if arm == "clarify" else 0,
            "selection_changes": max(0, sum(e["event"] == "confirm" for e in result["trace"]) - 1)}


def summarize(exports: list[dict], *, allow_rehearsal: bool = False) -> dict:
    if not exports:
        raise ValueError("No participant data supplied; do not manufacture study results.")
    rows = [validate_export(e, allow_rehearsal=allow_rehearsal) for e in exports]
    if len({r["participant_code"] for r in rows}) != len(rows):
        raise ValueError("One primary task per participant; duplicate participant code.")
    if len({r["mode"] for r in rows}) != 1:
        raise ValueError("Do not mix rehearsal and participant exports.")
    groups = []
    for arm in ARMS:
        for task in ("all", *TASKS):
            group = [r for r in rows if r["arm"] == arm and (task == "all" or r["task"] == task)]
            if not group:
                continue
            correct = [r for r in group if r["outcome"] == "correct"]
            groups.append({"arm": arm, "task": task, "participants": len(group),
                **{k: sum(r["outcome"] == k for r in group) for k in ("correct", "wrong", "unresolved")},
                "median_decision_seconds_all": median(r["decision_ms"] for r in group) / 1000,
                "median_decision_seconds_correct": median(r["decision_ms"] for r in correct) / 1000 if correct else None,
                "mean_effort": mean(r["effort"] for r in group),
                "mean_questions": mean(r["questions"] for r in group)})
    return {"protocol": PROTOCOL, "mode": rows[0]["mode"], "participants": len(rows), "groups": groups,
            "limitations": "Descriptive pilot only; no significance or non-inferiority conclusion. "
                "Four synthetic records, scripted answers, no voice condition. Participant provenance and "
                "assignment adherence require researcher records. No independent answer-quality labels."}
