import copy
import unittest

from scripts.naacl2027.verification_challenge import blind_form, evaluate, summarize


class ChallengeScoring(unittest.TestCase):
    def test_preexisting_rejection_is_not_detection_and_omissions_are_separate(self):
        rows = [
            {"id": "preexisting", "clean": {"action": "block"},
             "corrupted": {"action": "block", "supported": False, "complete": True}},
            {"id": "detected", "clean": {"action": "allow"},
             "corrupted": {"action": "block", "supported": False, "complete": True}},
            {"id": "omission", "clean": {"action": "allow"},
             "corrupted": {"action": "allow", "supported": True, "complete": False}},
        ]
        score = summarize(rows)
        self.assertEqual(score["incorrect_blocked"], 2)
        self.assertEqual(score["correct_rejected"], 1)
        self.assertEqual(score["eligible_clean_accepted_pairs"], 2)
        self.assertEqual(score["paired_new_rejections"], 1)
        self.assertEqual(score["unsupported_released"], [])
        self.assertEqual(score["incomplete_released"], ["omission"])

    def pair(self):
        return {"id": "secret-id", "family": "secret-mutation", "question": "What is the policy?",
                "evidence": [], "label_basis": "secret-expected-label",
                "clean": {"answer": "A", "supported": True, "complete": True},
                "corrupted": {"answer": "B", "supported": False, "complete": True}}

    def test_blind_form_hides_labels_and_pairing_and_deduplicates_answers(self):
        pair = self.pair()
        form = blind_form({"pairs": [pair, copy.deepcopy(pair)]})
        self.assertEqual(len(form["items"]), 2)
        self.assertNotIn("secret-", str(form))
        for item in form["items"]:
            self.assertIsNone(item["supported"])
            self.assertIsNone(item["complete"])
            self.assertNotIn("action", item)

    def test_unchanged_answer_cannot_count_as_corruption(self):
        pair = self.pair()
        pair["corrupted"]["answer"] = pair["clean"]["answer"]
        with self.assertRaisesRegex(ValueError, "unchanged"):
            evaluate({"pairs": [pair]})


if __name__ == "__main__":
    unittest.main()
