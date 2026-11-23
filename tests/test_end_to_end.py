import unittest

from scripts.naacl2027.score_end_to_end import prepare, score


class IndependentAnswerScoring(unittest.TestCase):
    def row(self):
        return {"case": "one", "fault": "none", "target_id": "txn_A", "selected_id": "txn_A",
                "answer": "An answer", "answer_outcome": "passed", "answer_field_checks": {"all": True}}

    def test_passing_gate_and_field_checks_do_not_supply_independent_labels(self):
        report = score([self.row()], [])
        self.assertEqual(report["unassessed_answers"], 1)
        self.assertIsNone(report["end_to_end_success_rate"])
        with self.assertRaises(ValueError):
            score([self.row()], prepare([self.row()]))

    def test_supported_but_incomplete_answer_fails(self):
        row = self.row()
        audit = prepare([row])[0]
        audit.update(reviewer="R1", supported=True, complete=False)
        self.assertEqual(score([row], [audit])["end_to_end_success_rate"], 0)

    def test_correct_answer_about_wrong_record_is_not_success(self):
        row = self.row(); row["selected_id"] = "txn_B"
        audit = prepare([row])[0]
        audit.update(reviewer="R1", supported=True, complete=True)
        self.assertEqual(score([row], [audit])["outcomes"][0]["outcome"], "wrong_record")

    def test_changed_answer_invalidates_previous_audit(self):
        row = self.row()
        audit = prepare([row])[0]; audit.update(reviewer="R1", supported=True, complete=True)
        row["answer"] = "Different answer"
        with self.assertRaises(ValueError):
            score([row], [audit])
