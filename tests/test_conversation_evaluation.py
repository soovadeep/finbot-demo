import unittest

from finbot.clarification_conversation import run_conversation
from scripts.naacl2027.evaluate_conversation import cases, score


class EvaluationLabels(unittest.TestCase):
    def test_passing_answer_about_wrong_confirmed_record_is_not_success(self):
        case = next(c for c in cases() if c["id"] == "confident-wrong-confirmation")
        result = run_conversation({"events": case["events"], "fault": "none", "live": False})
        row = score(case, result)
        self.assertEqual(row["answer_outcome"], "passed")
        self.assertEqual(row["selection_outcome"], "wrong")
        self.assertFalse(row["correct_selection_and_expected_fields"])

    def test_unresolved_target_is_distinct_from_appropriate_abstention(self):
        rows = []
        for name in ("missing", "cannot-recall"):
            case = next(c for c in cases() if c["id"] == name)
            result = run_conversation({"events": case["events"], "fault": "none", "live": False})
            rows.append(score(case, result))
        self.assertEqual([r["selection_outcome"] for r in rows], ["appropriate_unresolved", "unresolved"])
        self.assertTrue(all(r["answer"] is None for r in rows))

    def test_field_scoring_does_not_trust_a_passing_gate(self):
        case = next(c for c in cases() if c["id"] == "complete")
        result = run_conversation({"events": case["events"], "fault": "none", "live": False})
        result["financial"]["final"]["answer"] = "Your payment succeeded."
        self.assertFalse(score(case, result)["correct_selection_and_expected_fields"])
