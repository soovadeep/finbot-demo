"""Protect independent labels, matched-pair denominators and report reproducibility."""
import copy
import json
import unittest

from finbot.guardrails import GuardResult
from scripts.naacl2027.evaluate_support import (
    ROOT, comparison_answer, comparison_cases, comparison_fields, evaluate,
    paired_result, pair_summary, policy_content_checks,
)


class FixedVerdict:
    def __init__(self, action):
        self.action = action

    def check(self, answer, evidence, focus):
        return GuardResult(self.action, answer, ["unrelated"] if self.action == "block" else [])


class IndependentSupportScoring(unittest.TestCase):
    def setUp(self):
        self.records = comparison_cases()[1]["records"]

    def test_wrong_binding_is_not_correct_because_both_values_occur(self):
        swapped = copy.deepcopy(self.records)
        swapped[0]["currency"], swapped[1]["currency"] = swapped[1]["currency"], swapped[0]["currency"]
        self.assertFalse(comparison_fields(comparison_answer(swapped), self.records)["all_requested_fields_correct"])

    def test_missing_record_duplicate_and_contradictory_assertion_fail(self):
        answer = comparison_answer(self.records)
        bad = copy.deepcopy(self.records)
        bad[0]["status"] = "failed"
        for text in (comparison_answer(self.records[:1]), answer + " " + answer,
                     answer + " " + comparison_answer(bad[:1])):
            with self.subTest(text=text):
                self.assertFalse(comparison_fields(text, self.records)["all_requested_fields_correct"])
        self.assertTrue(comparison_fields(comparison_answer(self.records[::-1]), self.records)["all_requested_fields_correct"])

    def test_allowed_abstention_does_not_satisfy_available_policy_question(self):
        result = {"final": {"answer": "I don't have documentation on that, so I won't guess.", "blocked_by": None}}
        checks = policy_content_checks(result, ["capped at 3 percent"])
        self.assertTrue(checks["answer_released"])
        self.assertFalse(checks["required_policy_content"])

    def pair(self, chain, *, noop=False):
        clean = comparison_answer(self.records)
        return paired_result(chain, case_id="test", family="comparison", mutation="omit_record",
            question="Compare both records.", evidence=[], clean=clean,
            changed=clean if noop else comparison_answer(self.records[:1]),
            target_reason="missing_record:", expected_complete=noop)

    def test_gate_allow_does_not_override_independent_incompleteness_label(self):
        row = self.pair(FixedVerdict("allow"))
        self.assertTrue(row["missed_error"])
        self.assertFalse(row["expected_changed_supported_and_complete"])
        self.assertEqual(pair_summary([row])["missed_errors"], 1)

    def test_preexisting_rejection_is_not_injected_error_detection(self):
        row = self.pair(FixedVerdict("block"))
        summary = pair_summary([row])
        self.assertEqual(summary["corrupted_drafts_blocked"], 1)
        self.assertEqual(summary["accepted_clean_controls"], 0)
        self.assertEqual(summary["new_rejections"], 0)
        self.assertFalse(row["target_reason_observed"])

    def test_equal_value_swap_is_a_control_not_a_detection_opportunity(self):
        summary = pair_summary([self.pair(FixedVerdict("allow"), noop=True)])
        self.assertEqual(summary["actual_mutations"], 0)
        self.assertEqual(summary["no_op_controls"], 1)
        self.assertEqual(summary["missed_errors"], 0)

    def test_committed_report_reproduces_without_model_calls(self):
        actual = evaluate()
        saved = json.loads((ROOT / "results/naacl2027/varied-support-roles.json").read_text())
        self.assertEqual(actual, saved)
        self.assertEqual(actual["new_model_calls"], 0)
        self.assertTrue(actual["baseline"]["same_paired_inputs"])
        self.assertTrue(actual["verifier_rules_changed"])
        self.assertTrue(all(row["result"]["mode"] == "offline_scripted" for row in actual["workflow_rows"]))


if __name__ == "__main__":
    unittest.main()
