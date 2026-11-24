import hashlib
import json
import unittest

from scripts.naacl2027.evaluate_fresh_wording import DATA, conversation_score, pair_counts, same_measurement


class FreshWordingScoring(unittest.TestCase):
    def test_case_labels_and_text_match_the_precommitted_manifest(self):
        protocol = json.loads((DATA / "protocol.json").read_text())
        self.assertEqual(hashlib.sha256((DATA / "cases.json").read_bytes()).hexdigest(), protocol["cases_sha256"])
        fixtures = json.loads((DATA / "cases.json").read_text())
        self.assertEqual(len(fixtures["draft_pairs"]), 32)
        self.assertEqual(len(fixtures["conversation_cases"]), 16)
        for case in fixtures["draft_pairs"]:
            self.assertTrue(case["expected_clean_supported"])
            self.assertFalse(case["expected_corrupted_supported"])
            self.assertNotEqual(case["clean"], case["corrupted"])
            self.assertTrue(case["label_basis"])

    def test_preexisting_rejection_is_not_counted_as_new_detection(self):
        row = {"checks": {"test": {"clean": {"action": "block"}, "corrupted": {"action": "block"}}},
               "targeted_role_rejection": {"test": False}}
        counts = pair_counts([row], "test")
        self.assertEqual(counts["corrupted_rejected"], 1)
        self.assertEqual(counts["clean_rejected"], 1)
        self.assertEqual(counts["new_rejections"], 0)
        self.assertEqual(counts["targeted_role_rejections"], 0)

    def test_extra_candidates_and_wrong_exclusions_are_distinct(self):
        case = {"expected_matching_ids": ["a", "b"]}
        result = {"selected_id": None, "financial": None, "candidates": [
            {"record_id": rid, "matches_supplied": True} for rid in ("a", "b", "c")]}
        score = conversation_score(case, result)
        self.assertFalse(score["exact_candidate_set"])
        self.assertTrue(score["all_compatible_candidates_retained"])
        result["candidates"] = result["candidates"][:1]
        score = conversation_score(case, result)
        self.assertFalse(score["all_compatible_candidates_retained"])
        self.assertEqual(score["excluded_compatible_ids"], ["b"])

    def test_correct_candidates_do_not_excuse_answer_before_confirmation(self):
        score = conversation_score({"expected_matching_ids": ["a"]}, {
            "selected_id": None, "financial": {"answer": "unconfirmed"},
            "candidates": [{"record_id": "a", "matches_supplied": True}]})
        self.assertTrue(score["exact_candidate_set"])
        self.assertFalse(score["no_answer_before_confirmation"])

    def test_replay_comparison_normalizes_json_without_ignoring_changed_results(self):
        first = {"evaluator_sha256": "first", "cases_sha256": "cases", "options": ["a", "b"], "detected": 12}
        replay = {**first, "evaluator_sha256": "new-harness", "options": ("a", "b")}
        self.assertTrue(same_measurement(first, replay))
        self.assertFalse(same_measurement(first, {**replay, "detected": 13}))
        self.assertFalse(same_measurement(first, {**replay, "cases_sha256": "changed-cases"}))


if __name__ == "__main__":
    unittest.main()
