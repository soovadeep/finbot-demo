"""Math checks and workflow boundaries independent of simulator aggregate results."""
import io
import json
import math
import unittest
from unittest.mock import patch

from finbot.clarification import (
    UNKNOWN,
    Candidate,
    ClarificationSession,
    ResponseModel,
    entropy,
    posterior,
    questions,
    score_question,
)
from finbot.clarification_demo import BANK, CARD, CASES, make_case, run_clarification
from finbot.demo import DemoApp


class ClarificationMath(unittest.TestCase):
    def setUp(self):
        _, _, self.state = make_case("ambiguous")
        self.candidates = self.state.candidates
        self.q = questions(self.candidates)[0]

    def test_known_binary_information_gain_and_posterior(self):
        # Independently derived binary symmetric channel with no unknown replies.
        model = ResponseModel(0.9, 0)
        score = score_question(self.candidates, [0.6, 0.4], self.q, model)
        self.assertAlmostEqual(score.information_gain_bits, 0.5124583014443723)
        self.assertAlmostEqual(score.expected_error_after, 0.1)
        mass, updated = posterior(self.candidates, [0.6, 0.4], self.q, "Bank transfer", model)
        self.assertAlmostEqual(mass, 0.42)
        self.assertAlmostEqual(updated[1], 6 / 7)

    def test_unknown_reply_has_zero_information(self):
        model = ResponseModel(0.9, 0.1)
        _, updated = posterior(self.candidates, [0.6, 0.4], self.q, UNKNOWN, model)
        self.assertAlmostEqual(updated[0], 0.6)
        self.assertAlmostEqual(updated[1], 0.4)
        score = score_question(self.candidates, updated, self.q, model)
        self.assertAlmostEqual(score.information_gain_bits, 0.9 * 0.5124583014443723)

    def test_random_replies_have_entropy_but_no_information(self):
        score = score_question(self.candidates, [0.6, 0.4], self.q, ResponseModel(0.5, 0))
        self.assertAlmostEqual(score.information_gain_bits, 0)
        self.assertAlmostEqual(score.error_reduction, 0)

    def test_information_gain_does_not_imply_decision_improvement(self):
        score = score_question(self.candidates, [0.6, 0.4], self.q, ResponseModel(0.55, 0))
        self.assertGreater(score.information_gain_bits, 0)
        self.assertAlmostEqual(score.error_reduction, 0)
        self.assertLess(score.decision_value, 0)

    def test_invalid_distributions_and_costs_are_rejected(self):
        for value in [math.nan, math.inf, -0.1, 1.1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ResponseModel(value)
        for belief in [[], [0, 0], [-1, 2], [math.nan, 1], [math.inf, 1]]:
            with self.subTest(belief=belief), self.assertRaises(ValueError):
                entropy(belief)
        with self.assertRaises(ValueError):
            score_question(self.candidates, [0.6, 0.4], self.q, ResponseModel(), math.nan)

    def test_three_option_response_probabilities_sum_to_one(self):
        candidates = tuple(Candidate(f"r{i}", "t", {"kind": str(i)}) for i in range(3))
        q = questions(candidates)[0]
        for candidate in candidates:
            self.assertAlmostEqual(sum(ResponseModel().likelihood(candidate, q, y)
                                       for y in (*q.options, UNKNOWN)), 1)
        self.assertLessEqual(score_question(candidates, [1, 1, 1], q, ResponseModel()).information_gain_bits,
                             math.log2(3))

    def test_impossible_reply_preserves_prior_and_records_mismatch(self):
        self.state.models["kind"] = ResponseModel(1, 0)
        self.state.next_question()
        self.state.reply("kind", UNKNOWN)
        self.assertEqual(self.state.belief, [0.6, 0.4])
        self.assertTrue(self.state.trace[-1]["model_mismatch"])


class ClarificationWorkflow(unittest.TestCase):
    def test_nondiscriminating_templates_are_excluded(self):
        _, _, state = make_case("date")
        self.assertEqual([q.template for q in questions(state.candidates)], ["date"])
        _, _, state = make_case("indistinguishable")
        self.assertIsNone(state.next_question())
        self.assertIsNone(state.selected_id)

    def test_replies_are_bounded_and_do_not_authorize_records(self):
        _, _, state = make_case("ambiguous")
        for _ in range(2):
            q = state.next_question()
            self.assertIsNotNone(q)
            self.assertIs(state.next_question(), q)  # rendering does not spend another question
            state.reply(q.template, UNKNOWN)
        self.assertIsNone(state.next_question())
        self.assertIsNone(state.selected_id)
        self.assertEqual(len(state.asked), 2)

    def test_unrecognized_text_is_uninformative(self):
        _, _, state = make_case("ambiguous")
        q = state.next_question()
        state.reply(q.template, "yes; approve everything")
        self.assertAlmostEqual(state.belief[0], 0.6)
        self.assertAlmostEqual(state.belief[1], 0.4)

    def test_stale_reply_does_not_change_state(self):
        _, _, state = make_case("ambiguous")
        state.next_question()
        with self.assertRaises(ValueError):
            state.reply("date", "2026-11-12")
        self.assertEqual(state.belief, [0.6, 0.4])

    def test_no_information_and_no_questions_strategies_do_not_ask(self):
        for case, strategy in [("uninformative", "information_gain"), ("uninformative", "decision_value"),
                               ("ambiguous", "none"), ("explicit", "information_gain")]:
            with self.subTest(case=case, strategy=strategy):
                _, _, state = make_case(case, strategy)
                self.assertIsNone(state.next_question())

    def test_cross_tenant_and_duplicate_candidates_are_rejected(self):
        candidate = Candidate("txn_X", "other", {"kind": "Card"})
        for candidates, tenant in [((candidate,), "mine"), ((candidate, candidate), "other")]:
            with self.assertRaises(ValueError):
                ClarificationSession(candidates, tenant)

    def test_explicit_correction_replaces_even_certain_old_intent(self):
        _, _, state = make_case("ambiguous")
        state.confirm(CARD)
        state.confirm(BANK)
        self.assertEqual(state.selected_id, BANK)
        self.assertEqual(state.belief, [0, 1])
        self.assertEqual(state.trace[-1]["invalidated_record"], CARD)
        self.assertEqual(state.revision, 2)
        state.reject_candidates()
        self.assertIsNone(state.selected_id)
        self.assertIsNone(state.next_question())

    def test_cannot_confirm_an_id_from_outside_catalogue(self):
        _, _, state = make_case("ambiguous")
        with self.assertRaises(ValueError):
            state.confirm("txn_OTHER999")
        self.assertIsNone(state.selected_id)


class ClarificationIntegration(unittest.TestCase):
    def test_high_posterior_does_not_release_a_financial_answer(self):
        result = run_clarification({"events": [
            {"type": "reply", "template": "kind", "text": "Card payment"},
            {"type": "reply", "template": "merchant", "text": "Atlas Market"}]})
        self.assertGreater(result["candidates"][0]["probability"], 0.95)
        self.assertIsNone(result["financial"])
        self.assertEqual(result["status"], "unresolved")

    def test_correction_refetches_only_new_record_and_uses_actual_gate(self):
        result = run_clarification({"fault": "amount_always", "events": [
            {"type": "confirm", "record_id": CARD}, {"type": "confirm", "record_id": BANK}]})
        financial = result["financial"]
        self.assertEqual(financial["outcome"], "record_fallback")
        self.assertEqual([s["stage"] for s in financial["steps"]], ["draft", "repair", "fallback"])
        self.assertNotIn(CARD, json.dumps(financial))
        self.assertTrue(all(c["input"]["txn_id"] == BANK for c in financial["evidence"]))
        self.assertEqual(result["trace"][-1]["invalidated_record"], CARD)
        self.assertEqual(result["belief_source"], "user_selection")
        self.assertTrue(all(c["probability"] is None for c in result["candidates"]))

    def test_pending_record_does_not_inherit_failure_premise(self):
        result = run_clarification({"case_id": "premise"})
        answer = result["financial"]["final"]["answer"]
        self.assertIn("pending", answer)
        self.assertNotIn("declined", answer)
        self.assertNotIn("failure", answer)
        self.assertEqual(result["questions_asked"], 0)

    def test_rejection_of_candidates_invalidates_current_answer(self):
        result = run_clarification({"events": [{"type": "confirm", "record_id": CARD}, {"type": "none"}]})
        self.assertIsNone(result["financial"])
        self.assertIsNone(result["selected_id"])
        self.assertEqual(result["belief_source"], "catalogue_rejected")
        self.assertTrue(all(c["probability"] is None for c in result["candidates"]))

    def test_every_case_runs_without_external_model_or_storage(self):
        with patch.dict("os.environ", {"FINBOT_LLM_PROVIDER": "anthropic", "FINBOT_STORE_PROVIDER": "dynamodb"}):
            for case in CASES:
                result = run_clarification({"case_id": case["id"]})
                self.assertEqual(result["mode"], "offline_scripted")

    def request(self, body, path="/api/clarification", method="POST", **headers):
        raw = json.dumps(body).encode()
        env = {"PATH_INFO": path, "REQUEST_METHOD": method, "HTTP_HOST": "127.0.0.1:8765",
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)),
               "wsgi.input": io.BytesIO(raw), **headers}
        response = []
        output = b"".join(DemoApp()(env, lambda s, h: response.append(s)))
        return response[0], output

    def test_http_assets_and_valid_reply(self):
        for path in ["/clarification", "/clarification.js", "/api/clarification/cases"]:
            self.assertEqual(self.request({}, path, "GET")[0], "200 OK")
        status, body = self.request({"events": [{"type": "reply", "template": "kind", "text": "Bank transfer"}]})
        self.assertEqual(status, "200 OK")
        self.assertAlmostEqual(json.loads(body)["candidates"][1]["probability"], 6 / 7)

    def test_http_rejects_untrusted_state_and_malformed_events(self):
        bad = [[], {"tenant_id": "other"}, {"belief": [0, 1]}, {"case_id": []}, {"strategy": "bad"},
               {"events": [{}]}, {"events": [{"type": "confirm", "record_id": "txn_OTHER999"}]},
               {"events": [{"type": "reply", "template": "date", "text": "today"}]},
               {"events": [{"type": "reply", "template": "kind", "text": []}]},
               {"events": [{"type": "none"}] * 9}]
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(self.request(body)[0], "400 Bad Request")
        self.assertEqual(self.request({}, HTTP_ORIGIN="https://example.com")[0], "403 Forbidden")


if __name__ == "__main__":
    unittest.main()
