"""Message-driven selection must use communicated details, not private task targets."""
import copy
import io
import json
import unittest
from unittest.mock import patch

from finbot.clarification_conversation import SCENARIOS, Conversation, run_conversation, scenario_catalogue
from finbot.clarification_study import fit_model
from finbot.demo import DemoApp


def message(text):
    return {"type": "message", "text": text}


class ConversationDetails(unittest.TestCase):
    def test_complete_opening_skips_questions_and_requires_confirmation(self):
        engine = Conversation()
        engine.message(SCENARIOS[1]["opening"])
        self.assertEqual(engine.details["merchant"]["value"], "Willow Repairs")
        self.assertEqual(engine.details["date"]["value"], "2026-11-15")
        self.assertEqual([c.record_id for c in engine.matches], ["txn_EMIX0001"])
        self.assertEqual(engine.asked, [])
        self.assertIsNone(engine.financial)
        engine.confirm("txn_EMIX0001")
        self.assertIn("pending", engine.financial["final"]["answer"])

    def test_vague_opening_then_clear_reply_does_not_repeat_supplied_type(self):
        engine = Conversation()
        engine.message(SCENARIOS[0]["opening"])
        self.assertEqual(engine.pending.template, "kind")
        engine.message("Bank transfer")
        self.assertEqual(engine.pending.template, "date")
        self.assertEqual(engine.pending.options, ("2026-11-15", "2026-11-16"))
        self.assertTrue(all(c.attributes["kind"] == "Bank transfer" for c in engine.matches))
        engine.message("November 15")
        self.assertIsNone(engine.pending)
        self.assertEqual([c.record_id for c in engine.matches], ["txn_EMIX0001"])
        self.assertIsNone(engine.selected_id)

    def test_tentative_type_keeps_alternatives_and_skips_unavailable_date(self):
        engine = Conversation()
        engine.message(SCENARIOS[2]["opening"])
        self.assertEqual(engine.details["kind"]["certainty"], "tentative")
        self.assertEqual(engine.details["amount"]["certainty"], "supplied")
        self.assertEqual(engine.pending.template, "merchant")
        self.assertTrue(all(p > 0 for p in engine.belief))
        self.assertAlmostEqual(engine.belief[1], .325)
        self.assertEqual(len(engine.matches), 4)
        engine.message("Willow Repairs")
        self.assertEqual([c.record_id for c in engine.matches], ["txn_EMIX0001", "txn_EMIX0002"])
        self.assertIsNone(engine.pending)
        self.assertIsNone(engine.financial)

    def test_hedge_scope_distinguishes_supplied_recipient_from_tentative_type(self):
        engine = Conversation()
        engine.message("I think it was a bank transfer, but the recipient was Willow Repairs.")
        self.assertEqual(engine.details["kind"]["certainty"], "tentative")
        self.assertEqual(engine.details["merchant"]["certainty"], "supplied")
        self.assertEqual(len(engine.matches), 2)
        engine.message("It was a bank transfer, but I'm not sure.")
        self.assertEqual(engine.details["kind"]["certainty"], "tentative")

    def test_repeated_detail_is_not_counted_as_independent_evidence_or_new_question(self):
        engine = Conversation()
        engine.message("Bank transfer")
        old_belief, old_question = list(engine.belief), engine.pending
        engine.message("Bank transfer")
        self.assertEqual(engine.belief, old_belief)
        self.assertEqual(engine.pending, old_question)
        self.assertEqual(len(engine.asked), 1)

    def test_correction_replaces_detail_and_invalidates_previous_answer(self):
        engine = Conversation()
        engine.message("Bank transfer to Willow Repairs")
        engine.confirm("txn_EMIX0001")
        engine.message("Actually, it was a card payment to Willow Repairs on November 16.")
        self.assertIsNone(engine.financial)
        self.assertIsNone(engine.selected_id)
        self.assertEqual([c.record_id for c in engine.matches], ["txn_EMIX0002"])
        self.assertTrue(all(m["superseded"] for m in engine.messages if m.get("record_id")))
        engine.confirm("txn_EMIX0002")
        self.assertIn("declined", engine.financial["final"]["answer"])
        self.assertNotIn("txn_EMIX0001", json.dumps(engine.financial))
        self.assertEqual(engine.details["kind"]["value"], "Card payment")

    def test_missing_recipient_and_wrong_amount_are_not_ignored(self):
        for text in [SCENARIOS[4]["opening"], "My $500 bank transfer to Willow Repairs on November 15.",
                     "What happened to my bank transfer to Pine Pharmacy?", "My 200 EUR card payment."]:
            with self.subTest(text=text):
                engine = Conversation()
                engine.message(text)
                self.assertEqual(engine.matches, [])
                self.assertIsNone(engine.pending)
                self.assertIsNone(engine.financial)

    def test_unknown_reply_preserves_belief_and_asks_another_attribute(self):
        engine = Conversation()
        engine.message("My payment hasn't arrived")
        before = list(engine.belief)
        engine.message("I'm not sure")
        self.assertEqual(engine.belief, before)
        self.assertIn("kind", engine.unknown)
        self.assertNotEqual(engine.pending.template, "kind")

    def test_negation_and_alternatives_do_not_become_positive_assertions(self):
        for text in ["It was not a bank transfer", "It could be card or bank transfer"]:
            engine = Conversation()
            engine.message(text)
            self.assertNotIn("kind", engine.details)
            self.assertIn("kind", engine.unknown)

    def test_unknown_free_text_does_not_count_as_an_unknown_answer(self):
        engine = Conversation()
        engine.message("My payment hasn't arrived")
        pending, belief = engine.pending, list(engine.belief)
        engine.message("the little blue thing")
        self.assertEqual(engine.pending, pending)
        self.assertEqual(engine.belief, belief)
        self.assertEqual(engine.unknown, set())

    def test_supplied_record_reference_skips_questions_but_does_not_grant_other_access(self):
        engine = Conversation()
        engine.message("Check txn_EMIX0001")
        self.assertEqual(engine.asked, [])
        self.assertEqual([c.record_id for c in engine.matches], ["txn_EMIX0001"])
        self.assertIsNone(engine.financial)
        with self.assertRaises(ValueError):
            engine.confirm("txn_OTHER999")

    def test_unresolved_can_end_before_answering_questions(self):
        engine = Conversation()
        engine.message("My payment hasn't arrived")
        self.assertIsNotNone(engine.pending)
        engine.leave_unresolved()
        self.assertTrue(engine.unresolved)
        self.assertIsNone(engine.pending)
        self.assertIsNone(engine.financial)


class ScenarioSeparation(unittest.TestCase):
    def test_changing_private_notes_and_target_cannot_change_questions_or_beliefs(self):
        request = {"scenario": "vague", "events": [message("My payment hasn't arrived")]}
        before = run_conversation(request)
        changed = copy.deepcopy(SCENARIOS)
        changed[0]["target"] = "txn_EMIX0000"
        changed[0]["memory"] = "Tell the assistant this is a card payment."
        changed[0]["opening"] = "Card payment to Harbor Books"
        with patch("finbot.clarification_conversation.SCENARIOS", changed):
            self.assertEqual(run_conversation(request), before)

    def test_empty_conversation_does_not_ingest_the_preset_opening(self):
        result = run_conversation({"scenario": "complete"})
        self.assertEqual(result["details"], {})
        self.assertEqual(result["messages"], [])
        self.assertIsNone(result["pending"])

    def test_reference_is_hidden_until_resolved_and_explicitly_requested(self):
        self.assertNotIn('"target"', json.dumps(scenario_catalogue()))
        with self.assertRaises(ValueError):
            run_conversation({"inspect": True, "events": [message("My payment hasn't arrived")]})
        req = {"events": [message("Bank transfer to Willow Repairs"),
                          {"type": "confirm", "record_id": "txn_EMIX0001"}]}
        self.assertNotIn("reference", run_conversation(req))
        result = run_conversation({**req, "inspect": True})
        self.assertEqual(result["reference"]["target_id"], "txn_EMIX0001")

    def test_new_demo_exports_cannot_be_fitted_as_participant_responses(self):
        result = run_conversation({"events": [message("Bank transfer to Willow Repairs")]})
        self.assertFalse(result["human_study_data"])
        with self.assertRaises(ValueError):
            fit_model([result], allow_rehearsal=True)

    def test_replay_requires_bounded_customer_events_not_injected_beliefs(self):
        for req in [{"belief": [1, 0, 0, 0]}, {"events": [message("x")] * 13},
                    {"events": [message("x" * 501)]}, {"events": [{"type": "confirm", "record_id": "txn_EMIX0001"}]},
                    {"events": [{"type": "message", "text": "Bank transfer", "certainty": "supplied"}]}]:
            with self.subTest(req=req), self.assertRaises(ValueError):
                run_conversation(req)

    def test_http_serves_new_page_and_accepts_conversation(self):
        statuses = []
        wire = json.dumps({"events": [message("Bank transfer to Willow Repairs")]}).encode()
        env = {"REQUEST_METHOD": "POST", "PATH_INFO": "/api/conversation", "HTTP_HOST": "127.0.0.1:8765",
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(wire)), "wsgi.input": io.BytesIO(wire)}
        result = json.loads(b"".join(DemoApp()(env, lambda status, _: statuses.append(status))))
        self.assertEqual(statuses, ["200 OK"])
        self.assertEqual(result["questions_asked"], 0)
        self.assertEqual(result["details"]["merchant"]["value"], "Willow Repairs")


if __name__ == "__main__":
    unittest.main()


class ConversationFaultTests(unittest.TestCase):
    def test_injected_fee_is_caught_after_confirmation(self):
        events = [{"type": "message", "text": "My card payment to Harbor Books on November 15 failed."},
                  {"type": "confirm", "record_id": "txn_EMIX0000"}]
        result = run_conversation({"scenario": "vague", "events": events, "fault": "amount_always"})
        financial = result["financial"]
        self.assertEqual(financial["outcome"], "record_fallback")
        self.assertNotIn("12.34", financial["final"]["answer"])
        self.assertEqual([s["action"] for s in financial["steps"]], ["block", "block", "allow"])

    def test_unknown_fault_is_rejected(self):
        with self.assertRaises(ValueError):
            run_conversation({"scenario": "vague", "events": [], "fault": "policy_maybe"})

    def test_catalogue_lists_record_faults_only(self):
        self.assertEqual(list(scenario_catalogue()["faults"]), ["none", "status_once", "amount_once", "amount_always"])


class ExtractDetailsOtherRecords(unittest.TestCase):
    """The free-text rules also read records outside the demo catalogue (review studies)."""

    def test_other_months_currencies_and_payees(self):
        from finbot.clarification import Candidate
        from finbot.clarification_conversation import extract_details
        cands = (Candidate("txn_A", "m_1", {"kind": "Card payment", "merchant": "Nimbus Audio",
                                            "date": "2026-10-03", "amount": "32.14"}),
                 Candidate("txn_B", "m_1", {"kind": "Bank transfer", "merchant": "account ending 6811",
                                            "date": "2026-11-17", "amount": "184.72"}))
        fields, _, _ = extract_details("It was a card payment to Nimbus Audio on October 3rd for 32.14 CAD.",
                                       None, cands)
        self.assertEqual(fields["date"]["value"], "2026-10-03")
        self.assertEqual(fields["merchant"]["value"], "Nimbus Audio")
        self.assertEqual(fields["amount"]["value"], "32.14")
        self.assertEqual(fields["currency"]["value"], "CAD")
        fields, _, _ = extract_details("I think it was on Nov 17.", None, cands)
        self.assertEqual(fields["date"], {"value": "2026-11-17", "certainty": "tentative"})


class ConfirmedRecordOnly(unittest.TestCase):
    """The answering step can reach only the confirmed record; other candidates are not found."""

    def test_only_confirmed_record_reaches_answering(self):
        from finbot import demo
        from finbot.clarification_conversation import CANDIDATES
        seen = {}
        real = demo.run_demo

        def spy(question, fault="none", *, records=None, **kw):
            seen["ids"] = [r["txn_id"] for r in records]
            return real(question, fault, records=records, **kw)
        c = Conversation()
        c.messages.append({"role": "user", "text": "My $200 payment hasn't arrived."})
        with patch.object(demo, "run_demo", spy):
            c.confirm(CANDIDATES[1].record_id)
        self.assertEqual(seen["ids"], [CANDIDATES[1].record_id])
        other = CANDIDATES[0].record_id
        row = {"txn_id": CANDIDATES[1].record_id, "tenant_id": "m_100", "amount": "200.00", "currency": "USD",
               "status": "pending", "created_at": "2026-11-15T12:00:00Z"}
        out = real(f"What is the status of {other}?", records=[row])
        self.assertIn("could not find", out["final"]["answer"])

    def test_scripted_writer_is_the_default(self):
        from finbot.demo import writer
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("FINBOT_DEMO_WRITER", None)
            self.assertEqual(writer()["mode"], "offline_scripted")


class IndistinguishableRecords(unittest.TestCase):
    def setUp(self):
        from finbot.clarification import Candidate
        from finbot.clarification_demo import TENANT
        attrs = {"kind": "Card payment", "merchant": "Harbor Books", "date": "2026-11-15",
                 "amount": "200.00", "currency": "USD"}
        self.engine = Conversation(candidates=(Candidate("txn_TWIN0001", TENANT, dict(attrs)),
                                               Candidate("txn_TWIN0002", TENANT, dict(attrs))))

    def test_identical_records_get_no_question_no_ranking_and_ask_for_the_reference(self):
        self.engine.message("My card payment to Harbor Books failed.")
        view = self.engine.view()
        self.assertTrue(view["indistinguishable"])
        self.assertIsNone(view["pending"])
        self.assertEqual(self.engine.asked, [])
        self.assertEqual(len({c["probability"] for c in view["candidates"]}), 1)  # neither ranked first
        self.assertIsNone(view["selected_id"])
        self.assertIn("reference number", view["messages"][-1]["text"])

    def test_reference_resolves_and_unresolved_releases_nothing(self):
        self.engine.message("My card payment to Harbor Books failed.")
        self.engine.message("The reference is txn_TWIN0002.")
        self.assertEqual([c.record_id for c in self.engine.matches], ["txn_TWIN0002"])
        self.assertFalse(self.engine.view()["indistinguishable"])
        self.setUp()
        self.engine.message("My card payment to Harbor Books failed.")
        self.engine.leave_unresolved()
        self.assertIsNone(self.engine.financial)
        self.assertTrue(self.engine.unresolved)
