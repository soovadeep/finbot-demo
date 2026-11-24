"""The customer's question survives confirmation, and answers must cover what it asked for."""
import copy
import unittest

from finbot.clarification_conversation import record_rows, run_conversation, support_question
from finbot.demo import ROLE_RECORD, run_demo
from finbot.financial_roles import FinancialRoleVerifier
from finbot.requested_fields import (RequestedInformationVerifier, complete_record_answer,
                                     requested_roles)
from finbot.verification import VerifierChain


def envelope(record):
    return {"name": "get_transaction", "input": {"txn_id": record["txn_id"]},
            "result": {"status": "found", "source": "txn_db", "data": record}}


def message(text):
    return {"type": "message", "text": text}


def confirm(record_id):
    return {"type": "confirm", "record_id": record_id}


HARBOR_CARD, WILLOW_TRANSFER, WILLOW_CARD = "txn_EMIX0000", "txn_EMIX0001", "txn_EMIX0002"


class RefundRegression(unittest.TestCase):
    """The required regression: payment $200, refund $50, "How much was refunded?"."""

    def setUp(self):
        self.record = copy.deepcopy(ROLE_RECORD)   # amount 200.00, refund 50.00
        self.question = "How much was refunded on txn_ROLE0001?"

    def chain(self, question=None):
        return VerifierChain([FinancialRoleVerifier(), RequestedInformationVerifier(question or self.question)])

    def verdict(self, text, record=None):
        return self.chain().check(text, [envelope(record or self.record)], "txn_ROLE0001")

    def test_payment_amount_alone_does_not_answer_a_refund_question(self):
        result = self.verdict("Your payment was $200.")
        self.assertEqual(result.action, "block")
        self.assertIn("requested_information_missing:txn_ROLE0001:refund_amount", result.reasons)

    def test_payment_amount_presented_as_the_refund_is_rejected(self):
        result = self.verdict("Your refund amount was $200.")
        self.assertEqual(result.action, "block")
        self.assertIn("financial_role_mismatch:txn_ROLE0001:refund_amount", result.reasons)

    def test_correct_refund_amount_is_accepted(self):
        self.assertEqual(self.verdict("Your refund amount was $50.").action, "allow")

    def test_missing_refund_statement_only_when_the_record_has_none(self):
        text = "The record does not show a refund amount."
        result = self.verdict(text)
        self.assertEqual(result.action, "block")       # a refund exists: denying it is wrong
        self.assertIn("requested_information_denied:txn_ROLE0001:refund_amount", result.reasons)
        no_refund = {k: v for k, v in self.record.items() if k != "refund"}
        self.assertEqual(self.verdict(text, no_refund).action, "allow")
        self.assertEqual(self.verdict("Your payment was $200.", no_refund).action, "block")

    def test_unrecognized_refund_phrasing_is_sent_back_not_released(self):
        # "came to" is outside the role parser; coverage fails closed instead of passing it.
        self.assertEqual(self.verdict("Your refund came to 200.00 USD.").action, "block")

    def test_whole_workflow_repairs_or_falls_back_to_a_complete_answer(self):
        for fault in ("none", "refund_once", "amount_always"):
            result = run_demo("How much was refunded on txn_ROLE0001?", fault)
            self.assertIn("Refund amount: 50.00", result["final"]["answer"], fault)
            self.assertIsNone(result["final"]["blocked_by"], fault)

    def test_fallback_adds_explicit_absence(self):
        no_refund = {k: v for k, v in self.record.items() if k != "refund"}
        built = complete_record_answer([envelope(no_refund)], "txn_ROLE0001", ("refund_amount",))
        self.assertIn("The record does not show a refund amount.", built)
        self.assertEqual(self.chain().check(built, [envelope(no_refund)], "txn_ROLE0001").action, "allow")


class Settlement(unittest.TestCase):
    def test_expected_is_required_when_asked_when_it_will_settle(self):
        record = copy.deepcopy(ROLE_RECORD)
        chain = VerifierChain([FinancialRoleVerifier(), RequestedInformationVerifier("When will it settle?")])
        self.assertEqual(chain.check("Transaction txn_ROLE0001 was approved for 200.00 USD.",
                                     [envelope(record)], None).action, "block")
        self.assertEqual(chain.check("Expected settlement date: 2026-11-20.", [envelope(record)], None).action, "allow")

    def test_actual_date_question_needs_actual_date_or_not_recorded(self):
        record = copy.deepcopy(ROLE_RECORD)   # expected date only
        chain = VerifierChain([FinancialRoleVerifier(), RequestedInformationVerifier("When did it settle?")])
        self.assertEqual(chain.check("Expected settlement date: 2026-11-20.", [envelope(record)], None).action,
                         "block")
        self.assertEqual(chain.check("Expected settlement date: 2026-11-20. An actual settlement date is not "
                                     "recorded.", [envelope(record)], None).action, "allow")
        self.assertEqual(chain.check("It settled on 2026-11-20.", [envelope(record)], None).action, "block")


class Triggers(unittest.TestCase):
    def test_requested_roles(self):
        self.assertEqual(requested_roles("How much was refunded?"), ("refund_amount",))
        self.assertEqual(requested_roles("Why was my card payment declined?"), ("decline_reason",))
        self.assertEqual(requested_roles("When will my transfer arrive?"), ("expected_settlement_date",))
        self.assertEqual(requested_roles("Has it settled yet?"), ("actual_settlement_date",))
        self.assertEqual(requested_roles("My $200 payment to Willow Repairs."), ())

    def test_details_only_reply_is_not_a_question(self):
        self.assertIsNone(support_question("Willow Repairs"))
        self.assertIsNone(support_question("It was a bank transfer."))
        self.assertTrue(support_question("How much was refunded?")["requested"])
        self.assertTrue(support_question("Can you cancel that payment?")["action_request"])
        self.assertTrue(support_question("Can you update my mailing address?")["off_topic"])


class ConversationKeepsTheQuestion(unittest.TestCase):
    def run_events(self, *events, fault="none"):
        return run_conversation({"events": list(events), "fault": fault, "live": False})

    def answer_event(self, result):
        return [t for t in result["trace"] if t["event"] == "answer"]

    def test_refund_question_reaches_the_writer_as_a_refund_question(self):
        result = self.run_events(message("How much was refunded for my Harbor Books card payment on November 15?"),
                                 confirm(HARBOR_CARD))
        writer_question = self.answer_event(result)[-1]["writer_question"]
        self.assertIn("How much was refunded", writer_question)
        self.assertIn(HARBOR_CARD, writer_question)
        self.assertIn("Refund amount: 50.00", result["financial"]["final"]["answer"])
        self.assertEqual(result["question"]["requested"], ["refund_amount"])

    def test_refund_question_about_a_record_without_refund_says_so(self):
        result = self.run_events(message("How much was refunded on my bank transfer to Willow Repairs?"), confirm(WILLOW_TRANSFER))
        answer = result["financial"]["final"]["answer"]
        self.assertIn("does not show a refund amount", answer)
        self.assertEqual(result["financial"]["outcome"], "passed")

    def test_expected_versus_actual_settlement(self):
        result = self.run_events(message("When will my bank transfer to Willow Repairs arrive?"),
                                 confirm(WILLOW_TRANSFER))
        answer = result["financial"]["final"]["answer"]
        self.assertIn("Expected settlement date: 2026-11-18", answer)
        self.assertNotIn("Actual settlement date", answer)
        result = self.run_events(message("When did my Harbor Books card payment on November 15 settle?"),
                                 confirm(HARBOR_CARD))
        self.assertIn("Actual settlement date: 2026-11-17", result["financial"]["final"]["answer"])

    def test_details_only_replies_do_not_replace_the_question(self):
        result = self.run_events(message("How much was refunded on my $200 payment?"), message("Harbor Books"),
                                 message("Card payment"), confirm(HARBOR_CARD))
        self.assertEqual(result["question"]["text"], "How much was refunded on my $200 payment?")
        self.assertIn("Refund amount: 50.00", result["financial"]["final"]["answer"])

    def test_follow_up_question_about_the_confirmed_record_keeps_the_selection(self):
        result = self.run_events(message("My card payment to Harbor Books on November 15."), confirm(HARBOR_CARD),
                                 message("How much was refunded?"))
        self.assertEqual(result["selected_id"], HARBOR_CARD)
        self.assertIn("Refund amount: 50.00", result["financial"]["final"]["answer"])
        self.assertTrue(self.answer_event(result)[-1]["follow_up"])

    def test_correction_invalidates_answer_and_requires_reconfirmation(self):
        result = self.run_events(message("How much was refunded on my bank transfer to Willow Repairs?"),
                                 confirm(WILLOW_TRANSFER),
                                 message("Actually, it was a card payment to Harbor Books on November 15."))
        self.assertIsNone(result["selected_id"])
        self.assertIsNone(result["financial"])
        self.assertTrue(all(m.get("superseded") for m in result["messages"] if m.get("record_id")))
        self.assertEqual(result["question"]["requested"], ["refund_amount"])   # question kept
        result = self.run_events(message("How much was refunded on my bank transfer to Willow Repairs?"),
                                 confirm(WILLOW_TRANSFER),
                                 message("Actually, it was a card payment to Harbor Books on November 15."),
                                 confirm(HARBOR_CARD))
        self.assertIn("Refund amount: 50.00", result["financial"]["final"]["answer"])

    def test_question_naming_another_record_cannot_authorize_it(self):
        from finbot.clarification_conversation import Conversation
        engine = Conversation()
        engine.question = support_question("Is txn_EMIX0003 refunded like this one?")
        writer_question = engine.writer_question(HARBOR_CARD)
        self.assertNotIn("txn_EMIX0003", writer_question)
        self.assertIn(HARBOR_CARD, writer_question)
        engine.messages.append({"role": "user", "text": "x"})
        engine.confirm(HARBOR_CARD)
        self.assertTrue(all(c["input"].get("txn_id") in (None, HARBOR_CARD) for c in engine.financial["evidence"]))

    def test_unrelated_request_is_declined_without_questions(self):
        result = self.run_events(message("Can you update my mailing address?"))
        self.assertIsNone(result["pending"])
        self.assertIn("only help with the payments", result["messages"][-1]["text"])

    def test_action_request_is_not_promised(self):
        result = self.run_events(message("Can you cancel my bank transfer to Willow Repairs on November 15?"),
                                 confirm(WILLOW_TRANSFER))
        texts = " ".join(m["text"] for m in result["messages"] if m["role"] == "assistant")
        self.assertIn("can't cancel", texts)
        self.assertNotRegex(result["financial"]["final"]["answer"].lower(), r"\b(?:cancelled|i have cancel)")

    def test_action_request_is_not_forwarded_to_the_writer(self):
        result = self.run_events(message("Can you cancel my card payment to Willow Repairs on November 16?"),
                                 confirm(WILLOW_CARD))
        writer_question = self.answer_event(result)[-1]["writer_question"]
        self.assertNotIn("cancel", writer_question.lower())
        self.assertNotIn("TCK-", result["financial"]["final"]["answer"])   # no ticket path from the demo

    def test_triggers_found_too_broad_in_the_fresh_study(self):
        # Post-study fixes (docs/papers/naacl-2027/evaluation/fresh-llm.md): development cases now.
        self.assertEqual(requested_roles("Has the refund for txn_X come through yet?"), ())
        self.assertEqual(requested_roles("Was txn_X refunded?"), ())
        self.assertEqual(requested_roles("When did txn_X actually settle?"), ("actual_settlement_date",))
        self.assertEqual(requested_roles("For txn_X: what was the payment amount, the refund, and the settlement date?"),
                         ("refund_amount", "actual_settlement_date", "payment_amount"))
        self.assertEqual(requested_roles("Did I get my money back for txn_X, and how much?"), ("refund_amount",))
        self.assertEqual(requested_roles("Compare the refunds on txn_A and txn_B."), ("refund_amount",))

    def test_not_refunded_states_the_absence(self):
        record = {k: v for k, v in ROLE_RECORD.items() if k != "refund"}
        from finbot.guardrails import evidence_check
        self.assertNotIn("ungrounded_refund_claim",
                         evidence_check("The transaction txn_ROLE0001 was not refunded.", [envelope(record)], None).reasons)
        self.assertIn("ungrounded_refund_claim",
                      evidence_check("The transaction txn_ROLE0001 was refunded.", [envelope(record)], None).reasons)

    def test_refunded_payment_gets_no_failure_guidance(self):
        from finbot.policy import guidance
        self.assertIsNone(guidance({"status": "refunded"}, "support"))

    def test_settle_and_when_asks_for_the_actual_date(self):
        self.assertEqual(requested_roles("Did my card payment settle, and when?"), ("actual_settlement_date",))
        self.assertEqual(requested_roles("What is its decline reason?"), ("decline_reason",))

    def test_fixture_fields_used_above(self):
        rows = {r["txn_id"]: r for r in record_rows()}
        self.assertEqual(rows[HARBOR_CARD]["refund"]["amount"], "50.00")
        self.assertEqual(rows[WILLOW_TRANSFER]["settlement"]["expected_date"], "2026-11-18")
        self.assertEqual(rows[WILLOW_CARD]["status"], "declined")


if __name__ == "__main__":
    unittest.main()
