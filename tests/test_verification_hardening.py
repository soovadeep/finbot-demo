"""Regression checks for strict evidence coverage and labelled record selection.

These authored cases exercise contracts; they are not an independent accuracy study.
"""
import copy
import unittest
from datetime import date
from types import SimpleNamespace as NS

from finbot.config import Settings
from finbot.evalkit import score
from finbot.guardrails import LocalGuardrail
from finbot.knowledge import Index
from finbot.llm import FakeLLM
from finbot.orchestrator import Chatbot
from finbot.policy_documents import STRICT_INSTRUCTION, PolicyDocumentVerifier
from finbot.recordanswer import record_answer
from finbot.tools import DEMO_DOCS, InMemoryLogs, InMemoryTxns, ToolBox
from finbot.verification import EvidenceVerifier, HallucinationGate, RecordIdentityVerifier, VerifierChain

TODAY = date(2026, 11, 19)
URL = "https://policy.example.com/refunds"
PASSAGE = "Domestic transfers qualify for a fee refund. International transfers are excluded."
SOURCE = {"text": PASSAGE, "source_url": URL, "chunk_id": "refund:v2:0", "version": 2,
          "updated": "2026-11-01"}
TXN = {"txn_id": "txn_AAAA1111", "status": "declined", "amount": "12.66", "currency": "USD"}


def lookup(*sources):
    return [{"name": "search_knowledge_base", "input": {"query": "refund rules"},
             "result": {"status": "found", "data": list(sources)}}]


def record():
    return {"name": "get_transaction", "input": {"txn_id": TXN["txn_id"]},
            "result": {"status": "found", "data": dict(TXN)}}


def cited(text=PASSAGE, url=URL):
    return f"{text} (source: {url})"


class StrictPolicy(unittest.TestCase):
    def setUp(self):
        self.verifier = PolicyDocumentVerifier("strict", as_of=TODAY, max_age_days=30)

    def blocked(self, text, log, reason):
        result = self.verifier.check(text, log, None)
        self.assertEqual(result.action, "block")
        self.assertTrue(any(r.startswith(reason) for r in result.reasons), result.reasons)

    def test_missing_lookup_and_record_lookup_cannot_exempt_policy_claims(self):
        for log in ([], [record()], lookup(), lookup({"text": PASSAGE})):
            with self.subTest(log=log):
                self.blocked("All refunds are guaranteed.", log, "policy_missing_evidence")

    def test_missing_retrieval_can_recover_on_the_single_repair(self):
        feedback = []

        def repair(prompt):
            feedback.append(prompt)
            return cited(), lookup(SOURCE)

        gate = HallucinationGate(VerifierChain([]), repair_attempts=1)
        result = gate.run("All refunds are guaranteed.", [], lambda: None, repair,
                          extra_verifiers=(self.verifier,))
        self.assertTrue(result.repaired)
        self.assertEqual(result.answer, cited())
        self.assertEqual(len(feedback), 1)
        self.assertIn("policy_missing_evidence", feedback[0])

    def test_complete_context_passes_and_evidence_is_inspectable(self):
        result = self.verifier.check(cited(), lookup(SOURCE), None)
        self.assertEqual(result.action, "allow")
        self.assertEqual(result.checks[0]["evidence"][0]["quote"], PASSAGE)
        self.assertEqual(result.checks[0]["evidence"][0]["updated"], "2026-11-01")

    def test_whitespace_formatting_preserves_complete_context(self):
        text = cited(PASSAGE.replace(". International", ".\nInternational"))
        self.assertEqual(self.verifier.check(text, lookup(SOURCE), None).action, "allow")

    def test_adjacent_exception_and_historical_context_cannot_be_omitted(self):
        cases = [(PASSAGE, "Domestic transfers qualify for a fee refund."),
                 ("The previous policy is no longer valid. Refunds take 90 days. The current window is 30 days.",
                  "Refunds take 90 days.")]
        for passage, excerpt in cases:
            source = {**SOURCE, "text": passage}
            self.assertEqual(PolicyDocumentVerifier("extractive").check(cited(excerpt), lookup(source), None).action,
                             "allow")
            self.blocked(cited(excerpt), lookup(source), "policy_complete_passage_required")

    def test_new_conclusion_paraphrase_or_claim_in_link_label_is_not_a_quote(self):
        for text in (cited() + " You qualify.", cited("International transfers don't qualify for a fee refund."),
                     f"{PASSAGE} [You qualify]({URL})"):
            self.blocked(text, lookup(SOURCE), "policy_complete_passage_required")

    def test_abstention_cannot_hide_an_added_claim(self):
        abstain = "I couldn't verify that from the retrieved policy documents."
        self.assertEqual(self.verifier.check(abstain, [], None).action, "allow")
        for text in (abstain + " Refunds are guaranteed.", abstain + "\n\nRefunds are guaranteed."):
            self.blocked(text, [], "policy_missing_evidence")

    def test_every_paragraph_requires_its_own_support(self):
        self.blocked(PASSAGE + f"\n\n(source: {URL})", lookup(SOURCE), "policy_missing_citation")
        self.blocked(cited() + "\n\nYou qualify.", lookup(SOURCE), "policy_missing_citation")
        self.assertEqual(self.verifier.check(cited() + "\n\n" + cited(), lookup(SOURCE), None).action, "allow")

    def test_additional_unretrieved_citation_cannot_be_stripped_away(self):
        self.blocked(cited() + " (source: https://other.example.com)", lookup(SOURCE),
                     "policy_unretrieved_citation")

    def test_questions_and_negation_are_not_normalized_into_assertions(self):
        source = {**SOURCE, "text": "Are refunds guaranteed?"}
        self.blocked(cited("Are refunds guaranteed."), lookup(source), "policy_complete_passage_required")
        self.blocked(cited(PASSAGE.replace("excluded", "included")), lookup(SOURCE), "policy_complete_passage_required")

    def test_missing_malformed_future_and_old_metadata(self):
        for change, reason in (({"updated": None}, "policy_invalid_source_metadata"),
                               ({"updated": "2026-02-30"}, "policy_invalid_source_metadata"),
                               ({"updated": "2026-11-20"}, "policy_future_source"),
                               ({"updated": "2025-11-01"}, "policy_stale_source"),
                               ({"version": True}, "policy_invalid_source_metadata"),
                               ({"chunk_id": ""}, "policy_invalid_source_metadata")):
            with self.subTest(change=change):
                self.blocked(cited(), lookup({**SOURCE, **change}), reason)

    def test_metadata_age_boundary(self):
        for updated, expected in (("2026-10-20", "allow"), ("2026-10-19", "block")):
            result = self.verifier.check(cited(), lookup({**SOURCE, "updated": updated}), None)
            self.assertEqual(result.action, expected)

    def test_newer_retrieved_version_supersedes_old_one(self):
        old = {**SOURCE, "version": 1, "chunk_id": "refund:v1:0"}
        new = {**SOURCE, "text": "Fee refunds are unavailable."}
        self.blocked(cited(), lookup(old, new), "policy_superseded_source")
        self.assertEqual(self.verifier.check(cited(new["text"]), lookup(old, new), None).action, "allow")

    def test_conflicting_chunk_identity_fails_closed(self):
        self.blocked(cited(), lookup(SOURCE, {**SOURCE, "text": "All transfers qualify."}),
                     "policy_conflicting_source")

    def test_renderer_exemption_cannot_hide_added_prose(self):
        log = [record()]
        rendered = record_answer(log, TXN["txn_id"])
        self.assertIsNotNone(rendered)
        self.assertEqual(self.verifier.check(rendered, log, TXN["txn_id"]).action, "allow")
        self.blocked(rendered + " Refunds are guaranteed.", log, "policy_missing_evidence")
        gate = VerifierChain([EvidenceVerifier(), self.verifier])
        self.assertEqual(gate.check(rendered, log, TXN["txn_id"]).action, "allow")

    def test_empty_and_over_budget_responses_fail_closed(self):
        for text in ("", f"(source: {URL})"):
            self.blocked(text, lookup(SOURCE), "policy_empty_answer")
        self.blocked("\n\n".join([cited()] * 25), lookup(SOURCE), "policy_review_budget_exceeded")
        self.blocked("x" * 80001, [], "policy_review_budget_exceeded")

    def test_strict_requires_a_positive_freshness_limit(self):
        for limit in (0, -1, True):
            with self.assertRaises(ValueError):
                PolicyDocumentVerifier("strict", max_age_days=limit)


class StrictIntegration(unittest.TestCase):
    def test_writer_that_skips_retrieval_is_repaired_through_existing_gateway(self):
        class Model(FakeLLM):
            def __init__(self):
                super().__init__()
                self.prompts = []
                self.first = True

            def create(self, system, messages, tools):
                self.prompts.append(copy.deepcopy(messages))
                if self.first:
                    self.first = False
                    return NS(stop_reason="end_turn", content=[NS(type="text", text="Refunds are guaranteed.")])
                response = super().create(system, messages, tools)
                if response.stop_reason == "end_turn":
                    source = DEMO_DOCS[1]
                    # Match the actual retrieved passage, not a hand-labelled success token.
                    from finbot.knowledge import chunk_page
                    response.content[0].text = cited(chunk_page(source)[0].text, source["url"])
                return response

        kb = Index()
        for page in DEMO_DOCS:
            kb.upsert_page(page)
        model = Model()
        bot = Chatbot(model, LocalGuardrail(), ToolBox(InMemoryTxns([]), InMemoryLogs([]), kb),
                      Settings(policy_verification="strict", repair_attempts=1))
        bot.today = lambda: TODAY
        result = bot.ask(bot.new_session("m_100", ["support"]), "What are the surcharge rules?")
        self.assertTrue(result.repaired, result.reasons)
        self.assertIsNone(result.blocked_by)
        self.assertTrue(any(c["name"] == "search_knowledge_base" for c in result.tools_called))
        self.assertIn(STRICT_INSTRUCTION, str(model.prompts[0]))


class RecordSelectionScoring(unittest.TestCase):
    def setUp(self):
        self.expected = {"name": "get_transaction", "input": {"txn_id": TXN["txn_id"]}, "turn": 0,
                         "result": {"status": "found", "data": {"txn_id": TXN["txn_id"]}}}
        self.case = {"expect": {"tools": ["get_transaction"], "tool_calls": [self.expected]}}

    def result(self, calls, case=None):
        return score(case or self.case, [NS(answer="Example", tools_called=calls)], NS())

    def test_correct_lookup_and_returned_record_pass(self):
        self.assertEqual(self.result([record()]), [])

    def test_wrong_argument_passes_legacy_but_fails_new_score(self):
        call = record()
        call["input"] = {"txn_id": "txn_BBBB2222"}
        self.assertEqual(self.result([call], {"expect": {"tools": ["get_transaction"]}}), [])
        self.assertTrue(self.result([call]))

    def test_wrong_result_missing_result_and_not_found_fail(self):
        for result in (None, {"status": "not_found"}, {"status": "found", "data": {"txn_id": "txn_BBBB2222"}}):
            with self.subTest(result=result):
                self.assertTrue(self.result([{**record(), "result": result}]))

    def test_an_earlier_turn_cannot_satisfy_a_later_lookup(self):
        self.expected["turn"] = 1
        turns = [NS(answer="A", tools_called=[record()]), NS(answer="B", tools_called=[])]
        self.assertTrue(score(self.case, turns, NS()))

    def test_invalid_expectations_are_errors_not_silent_passes(self):
        for bad in ({"name": "get_transaction"}, {**self.expected, "turn": -1},
                    {**self.expected, "turn": True}, {**self.expected, "typo": True}):
            with self.assertRaises(ValueError):
                self.result([record()], {"expect": {"tool_calls": [bad]}})

    def test_arguments_are_exact_and_result_fields_are_subsets(self):
        call = record()
        call["input"]["extra"] = "not expected"
        self.assertTrue(self.result([call]))
        self.assertEqual(self.result([record()]), [])  # returned amount/status are extra fields

    def test_expectation_types_cannot_silently_weaken_the_score(self):
        with self.assertRaises(ValueError):
            self.result([record()], {"expect": {"tool_calls": {}}})
        call = record()
        self.expected["result"]["data"]["flags"] = [1]
        call["result"]["data"]["flags"] = [True]
        self.assertTrue(self.result([call]))


class RecordIdentity(unittest.TestCase):
    def test_wrong_record_cannot_support_a_canonical_fallback(self):
        call = record()
        call["result"]["data"]["txn_id"] = "txn_BBBB2222"
        log = [call]
        rendered = record_answer(log, TXN["txn_id"])
        self.assertIsNotNone(rendered)
        gate = HallucinationGate(VerifierChain([RecordIdentityVerifier(), EvidenceVerifier()]), repair_attempts=0)
        result = gate.run(rendered, log, lambda: TXN["txn_id"], lambda _: self.fail("no repair budget"),
                          fallback=lambda evidence: record_answer(evidence, TXN["txn_id"]))
        self.assertEqual(result.action, "block")
        self.assertIn("record_identity_mismatch:get_transaction", result.reasons)

    def test_correct_id_passes_and_missing_id_blocks_across_domains(self):
        from finbot.domains import DOMAINS
        verifier = RecordIdentityVerifier()
        for domain in DOMAINS.values():
            rid = domain.prefix + "_AAAA1111"
            call = {"name": domain.tool, "input": {domain.id_arg: rid},
                    "result": {"status": "found", "data": {domain.id_arg: rid}}}
            with self.subTest(domain=domain.name):
                self.assertEqual(verifier.check("", [call], rid).action, "allow")
                call["result"]["data"] = {}
                self.assertEqual(verifier.check("", [call], rid).action, "block")

    def test_not_found_is_left_to_existing_answer_checks(self):
        call = {**record(), "result": {"status": "not_found", "data": None}}
        self.assertEqual(RecordIdentityVerifier().check("", [call], None).action, "allow")


if __name__ == "__main__":
    unittest.main()
