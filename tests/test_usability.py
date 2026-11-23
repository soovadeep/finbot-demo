import copy
import unittest
from collections import Counter

from finbot.usability import PROTOCOL, TASKS, public_tasks, summarize, validate_export
from scripts.naacl2027.user_study import allocate


def export(code="P001", mode="rehearsal"):
    return {"protocol": PROTOCOL, "participant_code": code, "mode": mode, "consent": True,
            "task": "transfer", "arm": "full_list", "effort": 3, "elapsed_ms": 5000,
            "selected_id": "txn_EMIX0001", "events": [
                {"at_ms": 0, "event": {"type": "message", "text": TASKS["transfer"]["opening"]}},
                {"at_ms": 4000, "event": {"type": "confirm", "record_id": "txn_EMIX0001"}}]}


class UsabilityProtocol(unittest.TestCase):
    def test_conflict_resolution_time_is_final_decision_and_pending_cannot_finish(self):
        row = export()
        row["arm"] = "clarify"
        row["events"][1:1] = [{"at_ms": 1000, "event": {"type": "message", "text": "Card payment to Willow Repairs"}}]
        row["selected_id"] = None
        with self.assertRaises(ValueError):
            validate_export(row, allow_rehearsal=True)
        row["events"].append({"at_ms": 4500, "event": {"type": "resolve_selection",
            "record_id": "txn_EMIX0001", "choice": "use_record", "conflict_id": 1}})
        row["selected_id"] = "txn_EMIX0001"
        scored = validate_export(row, allow_rehearsal=True)
        self.assertEqual(scored["decision_ms"], 4500)
        self.assertEqual(scored["selection_changes"], 0)

    def test_rehearsals_and_duplicates_cannot_become_participant_evidence(self):
        with self.assertRaises(ValueError):
            summarize([export()])
        with self.assertRaises(ValueError):
            summarize([export(mode="participant"), export(mode="participant")])
        with self.assertRaises(ValueError):
            summarize([export(mode="participant"), export("P002")], allow_rehearsal=True)
        with self.assertRaises(ValueError):
            summarize([])

    def test_scoring_replays_events_instead_of_trusting_exported_selection(self):
        row = export()
        row["selected_id"] = "txn_EMIX0002"
        with self.assertRaises(ValueError):
            validate_export(row, allow_rehearsal=True)
        row["events"][-1]["event"]["record_id"] = "txn_EMIX0002"
        result = validate_export(row, allow_rehearsal=True)
        self.assertEqual(result["outcome"], "wrong")
        self.assertEqual(result["questions"], 0)  # hidden controller question is not shown in list arm

    def test_invalid_times_and_missing_consent_are_rejected(self):
        for changes in ({"consent": False}, {"effort": True}, {"elapsed_ms": float("nan")}):
            row = export(); row.update(changes)
            with self.assertRaises(ValueError):
                validate_export(row, allow_rehearsal=True)
        for value in (-1, float("nan"), 6000):
            row = export(); row["events"][1]["at_ms"] = value
            with self.assertRaises(ValueError):
                validate_export(row, allow_rehearsal=True)

    def test_allocation_is_balanced_and_targets_are_not_public(self):
        plan = allocate(24, 2027)
        self.assertEqual(set(Counter((s["arm"], s["task"]) for s in plan["slots"]).values()), {6})
        self.assertEqual(plan["status"], "planned_not_collected")
        self.assertTrue(all("target" not in task for task in public_tasks()["tasks"].values()))

    def test_descriptive_report_keeps_failure_denominator(self):
        unresolved = copy.deepcopy(export("P002"))
        unresolved["selected_id"] = None
        unresolved["events"][-1]["event"] = {"type": "unresolved"}
        report = summarize([export(), unresolved], allow_rehearsal=True)
        group = next(g for g in report["groups"] if g["task"] == "all")
        self.assertEqual((group["participants"], group["correct"], group["unresolved"]), (2, 1, 1))
