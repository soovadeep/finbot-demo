import copy
import unittest
from unittest.mock import patch

from finbot.comparison import ComparisonCoverageVerifier, comparison_record_answer
from finbot.demo import run_demo
from finbot.llm import FakeLLM
from test_currency_binding import evidence

QUESTION = "Compare txn_CURR0001 and txn_CURR0002: amounts, currencies and statuses?"
COMPLETE = "Transaction txn_CURR0001 was approved for 210.00 EUR. Transaction txn_CURR0002 was approved for 47.25 GBP."


class ComparisonCoverage(unittest.TestCase):
    def setUp(self):
        self.checker = ComparisonCoverageVerifier(QUESTION)

    def test_omission_missing_lookup_and_bare_heading_do_not_pass(self):
        tests = [(COMPLETE.split('. Transaction')[0] + '.', evidence(), "comparison_missing_record:"),
                 (COMPLETE, evidence()[:1], "comparison_missing_evidence:"),
                 ("txn_CURR0001 and txn_CURR0002", evidence(), "comparison_missing_field:")]
        for answer, log, reason in tests:
            with self.subTest(reason=reason):
                result = self.checker.check(answer, log, None)
                self.assertEqual(result.action, "block")
                self.assertTrue(any(r.startswith(reason) for r in result.reasons))

    def test_required_fields_and_negated_status_are_not_complete(self):
        for answer in (COMPLETE.replace("47.25 GBP", "47.25"), COMPLETE.replace("210.00 EUR", "EUR"),
                       COMPLETE.replace("was approved", "was not approved", 1)):
            self.assertEqual(self.checker.check(answer, evidence(), None).action, "block")
        self.assertEqual(self.checker.check(COMPLETE, evidence(), None).action, "allow")

    def test_unrequested_lookup_and_single_record_correction_do_not_expand_scope(self):
        extra = copy.deepcopy(evidence()[0])
        extra["input"]["txn_id"] = extra["result"]["data"]["txn_id"] = "txn_UNUSED01"
        self.assertEqual(self.checker.check(COMPLETE, [*evidence(), extra], None).action, "allow")
        checker = ComparisonCoverageVerifier("I meant the amount of txn_CURR0002, not txn_CURR0001.")
        self.assertEqual(checker.required_ids, ())

    def test_only_requested_fields_are_required(self):
        checker = ComparisonCoverageVerifier("Compare the statuses of txn_CURR0001 and txn_CURR0002.")
        self.assertEqual(checker.check("txn_CURR0001 was approved. txn_CURR0002 was approved.", evidence(), None).action, "allow")

    def test_unavailable_record_must_be_explicit_and_cannot_carry_money_claim(self):
        log = evidence()
        log[1]["result"] = {"status": "not_found", "source": "txn_db", "data": None}
        first = COMPLETE.split('. Transaction')[0] + ". "
        valid = first + "I could not find transaction txn_CURR0002 for your account."
        self.assertEqual(self.checker.check(valid, log, None).action, "allow")
        self.assertEqual(self.checker.check(valid + " Its amount is 47.25 GBP.", log, None).action, "block")
        self.assertEqual(self.checker.check(first + "I could not find that transaction.", log, None).action, "block")

    def test_fallback_covers_all_ids_and_does_not_reuse_stale_success(self):
        log = evidence()
        answer = comparison_record_answer(log, self.checker.required_ids)
        self.assertEqual(self.checker.check(answer, log, None).action, "allow")
        error = copy.deepcopy(log[-1])
        error["result"] = {"status": "error", "source": "txn_db", "data": None}
        self.assertIsNone(comparison_record_answer([*log, error], self.checker.required_ids))

    def test_real_workflow_repairs_or_uses_complete_fallback_after_omission(self):
        original = FakeLLM._answer
        records = [{**c["result"]["data"], "tenant_id": "m_100"} for c in evidence()]
        for persistent in (False, True):
            calls = []
            def omit(model, results):
                calls.append(1)
                return original(model, results[:1] if persistent or len(calls) == 1 else results)
            with self.subTest(persistent=persistent), patch.object(FakeLLM, "_answer", omit):
                result = run_demo(QUESTION, records=records)
            self.assertEqual(result["outcome"], "record_fallback" if persistent else "repaired")
            self.assertIn("comparison_missing_record:txn_CURR0002", result["steps"][0]["reasons"])
            self.assertEqual(self.checker.check(result["final"]["answer"], result["evidence"], None).action, "allow")


if __name__ == "__main__":
    unittest.main()
