import copy
import unittest

from finbot.demo import ROLE_RECORD, run_demo
from finbot.financial_roles import FinancialRoleVerifier, claims
from finbot.recordanswer import record_answer


def envelope(record):
    return {"name": "get_transaction", "input": {"txn_id": record["txn_id"]},
            "result": {"status": "found", "source": "txn_db", "data": record}}


class FinancialRoles(unittest.TestCase):
    def setUp(self):
        self.record = copy.deepcopy(ROLE_RECORD)
        self.log = [envelope(self.record)]
        self.verifier = FinancialRoleVerifier()

    def check(self, text, expected):
        result = self.verifier.check(text, self.log)
        self.assertEqual(result.action, expected, result)
        return result

    def test_same_value_does_not_support_expected_as_actual(self):
        self.check("Expected settlement date: 2026-11-20.", "allow")
        result = self.check("The transaction was settled on 2026-11-20.", "block")
        self.assertEqual(result.checks[0]["path"], "settlement.actual_date")
        self.assertIsNone(result.checks[0]["evidence_value"])
        self.assertEqual(self.record["settlement"]["status"], "settled")

    def test_actual_date_requires_its_own_field_and_settled_status(self):
        self.record["settlement"]["actual_date"] = "2026-11-21"
        self.check("Expected settlement date: 2026-11-20; actual settlement date: 2026-11-21.", "allow")
        self.check("Expected settlement date: 2026-11-21; actual settlement date: 2026-11-20.", "block")
        self.record["settlement"]["status"] = "pending"
        self.check("Actual settlement date: 2026-11-21.", "block")

    def test_refund_and_payment_amounts_have_distinct_roles(self):
        for text in ("Refund amount: 50.00.", "A refund of $50.00 was processed.",
                     "Refund amount is USD 50.", "Payment amount: 200.00."):
            self.check(text, "allow")
        for text in ("Refund amount: 200.00.", "A refund of $200.00 was processed.",
                     "Payment amount: 50.00.", "Refund amount: 50.01."):
            self.check(text, "block")

    def test_equal_values_are_valid_and_expected_role_is_not_double_counted(self):
        self.record["refund"]["amount"] = "200.00"
        self.record["settlement"]["actual_date"] = "2026-11-20"
        self.check("Refund amount: 200.00; payment amount: 200.00.", "allow")
        self.check("Actual settlement date: 2026-11-20.", "allow")
        roles = claims("**Expected settlement date:** 2026-11-20. **Refund amount:** 200.00.")
        self.assertEqual([r[0] for r in roles], ["expected_settlement_date", "refund_amount"])

    def test_unknown_date_does_not_assert_settlement_did_not_happen(self):
        self.check("Settlement status is settled. An actual settlement date is not recorded.", "allow")
        self.check("The transaction was not settled on 2026-11-21.", "allow")

    def test_other_record_or_policy_cannot_supply_role_evidence(self):
        other = copy.deepcopy(self.record)
        other["txn_id"] = "txn_OTHER123"
        other["refund"]["amount"] = "200.00"
        self.log.append(envelope(other))
        self.log.append({"name": "search_knowledge_base", "input": {"query": "refund"},
                         "result": {"status": "found", "data": [{"text": "Refund amount: 200.00"}]}})
        self.check("txn_ROLE0001: refund amount: 200.00.", "block")
        self.check("txn_OTHER123: refund amount: 200.00.", "allow")
        self.check("Refund amount: 200.00.", "block")

    def test_latest_failure_invalidates_old_role_evidence(self):
        self.log.append({"name": "get_transaction", "input": {"txn_id": "txn_ROLE0001"},
                         "result": {"status": "error", "data": None}})
        self.check("Refund amount: 50.00.", "block")

    def test_id_mismatch_and_untrusted_text_cannot_supply_field(self):
        self.record["txn_id"] = "txn_OTHER123"
        self.check("Refund amount: 50.00.", "block")
        self.record["txn_id"] = "txn_ROLE0001"
        del self.record["refund"]
        self.record["memo"] = {"refund": {"amount": "50.00"}}
        self.check("Refund amount: 50.00.", "block")

    def test_repair_and_fallback_preserve_role_details(self):
        for fault in ("settlement_once", "refund_once", "amount_always"):
            result = run_demo("What are the settlement and refund details for txn_ROLE0001?", fault)
            self.assertEqual(result["outcome"], "record_fallback" if fault == "amount_always" else "repaired")
            self.assertIn("Expected settlement date: 2026-11-20", result["final"]["answer"])
            self.assertIn("Refund amount: 50.00", result["final"]["answer"])
            self.assertTrue(any(c.get("kind") == "financial_role" for c in result["steps"][0]["checks"]))
        self.check(record_answer(self.log, "txn_ROLE0001"), "allow")


if __name__ == "__main__":
    unittest.main()
