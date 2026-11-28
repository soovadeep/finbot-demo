import copy
import unittest

from finbot.guardrails import evidence_check
from finbot.missing_information import absence_field, states_absent
from finbot.requested_fields import RequestedInformationVerifier

RECORD = {"txn_id": "txn_MISS0001", "status": "approved", "amount": "80.00", "currency": "USD"}


def log(*records):
    return [{"name": "get_transaction", "input": {"txn_id": r["txn_id"]},
             "result": {"status": "found", "source": "txn_db", "data": r}} for r in records]


class MissingInformation(unittest.TestCase):
    def test_live_missing_refund_wordings_share_the_same_interpretation(self):
        answers = ["The refund amount for this payment is not available in the data.",
                   "The record for payment txn_MISS0001 does not show a refund amount.",
                   "The refund details for this payment are not available.",
                   "The current information on the payment txn_MISS0001 does not include a refund amount."]
        checker = RequestedInformationVerifier("How much was refunded?")
        for answer in answers:
            with self.subTest(answer=answer):
                self.assertTrue(states_absent(answer, "refund_amount"))
                self.assertEqual(evidence_check(answer, log(RECORD), None).action, "allow")
                self.assertEqual(checker.check(answer, log(RECORD), None).action, "allow")

    def test_shared_grammar_applies_to_other_financial_fields(self):
        for answer, field in [("The actual settlement date for this payment is unknown.", "actual_settlement_date"),
                              ("No expected settlement date is documented in the retrieved record.", "expected_settlement_date"),
                              ("The record contains no dispute information.", "dispute"),
                              ("There is no refund status in the record.", "refund_status")]:
            self.assertEqual(absence_field(answer), field)
            self.assertEqual(evidence_check(answer, log(RECORD), None).action, "allow")

    def test_absence_does_not_establish_zero_or_nonoccurrence_or_ineligibility(self):
        for answer in ("The transaction was not refunded.", "There was no refund.",
                       "Your refund is $0.", "A refund is unavailable."):
            self.assertIsNone(absence_field(answer))
            self.assertEqual(evidence_check(answer, log(RECORD), None).action, "block")

    def test_known_value_including_zero_cannot_be_denied(self):
        for value in ("50.00", "0.00"):
            record = {**RECORD, "refund": {"status": "succeeded", "amount": value}}
            answer = "The refund amount for this payment is not available in the data."
            self.assertEqual(evidence_check(answer, log(record), None).action, "block")
            self.assertEqual(RequestedInformationVerifier("How much was refunded?").check(answer, log(record), None).action, "block")

    def test_correct_value_does_not_excuse_a_contradictory_missing_field_claim(self):
        record = {**RECORD, "refund": {"status": "succeeded", "amount": "50.00"}}
        answer = "Refund amount: $50.00. The refund amount is not recorded."
        self.assertEqual(RequestedInformationVerifier("How much was refunded?").check(answer, log(record), None).action, "block")

    def test_only_complete_missing_information_clauses_are_exempted(self):
        for answer in ("The refund amount is not recorded, but you were refunded $80.00.",
                       "The refund amount is not recorded. You were refunded $80.00.",
                       "The refund amount is not recorded and the payment was refunded.",
                       "The refund amount is not recorded?"):
            self.assertEqual(evidence_check(answer, log(RECORD), None).action, "block")

    def test_absence_requires_a_fresh_successful_lookup(self):
        answer = "The record does not show a refund amount."
        self.assertEqual(evidence_check(answer, [], None).action, "block")
        failure = {"name": "get_transaction", "input": {"txn_id": RECORD["txn_id"]},
                   "result": {"status": "not_found", "source": "txn_db", "data": None}}
        self.assertEqual(evidence_check(answer, [*log(RECORD), failure], None).action, "block")

    def test_latest_snapshot_and_record_identity_control_absence(self):
        present = {**RECORD, "refund": {"status": "succeeded", "amount": "50.00"}}
        answer = "The record does not show a refund amount."
        self.assertEqual(evidence_check(answer, log(present, RECORD), None).action, "allow")
        self.assertEqual(evidence_check(answer, log(RECORD, present), None).action, "block")
        other = {**copy.deepcopy(RECORD), "txn_id": "txn_MISS0002"}
        for answer in ("The record for payment txn_MISS0001 does not show a refund amount.",
                       "The refund amount is not recorded."):
            self.assertEqual(evidence_check(answer, log(present, other), None).action, "block")
        self.assertEqual(evidence_check("The record for payment txn_MISS0002 does not show a refund amount.",
                                       log(present, other), None).action, "allow")


if __name__ == "__main__":
    unittest.main()
