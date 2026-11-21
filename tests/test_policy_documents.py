"""Policy claims: citations, conditions, evidence coverage and bounded recovery."""
import copy
import json
import unittest
from types import SimpleNamespace as NS

from finbot.config import Settings
from finbot.guardrails import LocalGuardrail
from finbot.knowledge import Index
from finbot.llm import FakeLLM
from finbot.orchestrator import Chatbot
from finbot.policy_documents import REVIEW_SYSTEM, PolicyDocumentVerifier
from finbot.tools import DEMO_DOCS, InMemoryLogs, InMemoryTxns, ToolBox
from finbot.verification import HallucinationGate

URL = "https://help.example.com/retry"
RULE = "Retry only after confirming the original payment was not processed."
LOG = [{"name": "search_knowledge_base", "input": {"query": "retry policy"}, "result": {
    "status": "found", "source": "knowledge_base", "data": [
        {"chunk_id": "retry:v2:0", "version": 2, "text": RULE, "source_url": URL}]}}]


def answer(text=RULE, url=URL):
    return f"{text} (source: {url})"


def verdict(kind="supported", quote=RULE, source="doc:0", claim=0):
    return {"id": claim, "verdict": kind, "evidence": [{"source_id": source, "quote": quote}]}


class ExtractivePolicy(unittest.TestCase):
    def setUp(self):
        self.verifier = PolicyDocumentVerifier("extractive")

    def test_exact_source_sentence_has_inspectable_evidence(self):
        result = self.verifier.check(answer(), LOG, None)
        self.assertEqual(result.action, "allow")
        self.assertEqual(result.checks[0]["evidence"][0]["chunk_id"], "retry:v2:0")
        self.assertEqual(result.checks[0]["evidence"][0]["version"], 2)

    def test_real_citation_does_not_support_reversed_or_missing_conditions(self):
        for text in ("Retry before confirming the original payment was not processed.",
                     "Retry only after confirming the original payment was processed.",
                     "The original payment was not processed.", "Retry."):
            with self.subTest(text=text):
                result = self.verifier.check(answer(text), LOG, None)
                self.assertEqual(result.action, "block")
                self.assertEqual(result.reasons, ["policy_unsupported:statement_0"])

    def test_source_must_be_cited_in_the_same_paragraph(self):
        for text in (RULE, answer(url="https://other.example.com"), f"{RULE}\n\n(source: {URL})"):
            self.assertEqual(self.verifier.check(text, LOG, None).action, "block")

    def test_a_source_question_cannot_support_an_assertion(self):
        log = copy.deepcopy(LOG)
        log[0]["result"]["data"][0]["text"] = "Refunds are guaranteed?"
        self.assertEqual(self.verifier.check(answer("Refunds are guaranteed."), log, None).action, "block")

    def test_a_citation_cannot_launder_a_claim_in_its_link_label(self):
        text = f"{RULE} [Refunds are guaranteed]({URL})"
        self.assertEqual(self.verifier.check(text, LOG, None).action, "block")

    def test_only_complete_abstentions_are_exempt(self):
        abstain = "I don't have documentation on that, so I won't guess."
        self.assertEqual(self.verifier.check(abstain, LOG, None).action, "allow")
        self.assertEqual(self.verifier.check(abstain + " Refunds are guaranteed.", LOG, None).action, "block")

    def test_empty_answer_and_bare_citation_are_rejected(self):
        for text in ("", f"(source: {URL})"):
            self.assertEqual(self.verifier.check(text, LOG, None).reasons, ["policy_empty_answer"])

    def test_record_only_turn_does_not_invoke_document_review(self):
        def forbidden(_):
            self.fail("reviewer should not be called")
        result = PolicyDocumentVerifier("model", forbidden).check("Record answer", [], None)
        self.assertEqual(result.action, "allow")

    def test_budget_exhaustion_blocks_instead_of_checking_only_a_prefix(self):
        text = answer(" ".join([RULE] * 25))
        self.assertEqual(self.verifier.check(text, LOG, None).reasons, ["policy_review_budget_exceeded"])

    def test_repair_uses_newly_retrieved_version_and_reports_both_checks(self):
        updated = copy.deepcopy(LOG)
        updated[0]["result"]["data"][0].update(text="Do not retry this payment.", version=3)
        steps, feedback = [], []
        gate = HallucinationGate(observer=steps.append)

        def repair(message):
            feedback.append(message)
            return answer("Do not retry this payment."), updated

        result = gate.run(answer("You can retry this payment."), LOG, lambda: None, repair,
                          extra_verifiers=(self.verifier,))
        self.assertTrue(result.repaired)
        self.assertEqual(len(feedback), 1)
        self.assertIn("approved knowledge base", feedback[0])
        self.assertEqual(steps[1].checks[0]["evidence"][0]["version"], 3)
        self.assertEqual(steps[1].evidence, updated)


class ModelPolicy(unittest.TestCase):
    def check_rows(self, rows):
        return PolicyDocumentVerifier("model", lambda _: json.dumps({"claims": rows})).check(answer(), LOG, None)

    def test_model_supported_paraphrase_requires_a_real_source_quote(self):
        result = PolicyDocumentVerifier("model", lambda _: json.dumps({"claims": [verdict()]})).check(
            answer("Check that the first payment was not processed before retrying."), LOG, None)
        self.assertEqual(result.action, "allow")
        self.assertEqual(result.checks[0]["method"], "model")

    def test_missing_duplicate_foreign_and_invented_evidence_cannot_pass(self):
        for rows in ([], [verdict(), verdict()], [verdict(claim=1)], [verdict(claim=True)],
                     [verdict(quote="Refunds are guaranteed")], [verdict(quote="")],
                     [verdict(source="doc:99")], [{**verdict(), "evidence": []}],
                     [{**verdict(), "verdict": "probably"}]):
            with self.subTest(rows=rows):
                self.assertEqual(self.check_rows(rows).reasons, ["policy_review_invalid"])

    def test_uncertain_and_unsupported_verdicts_fail_closed(self):
        for kind in ("uncertain", "unsupported"):
            self.assertEqual(self.check_rows([verdict(kind)]).reasons, [f"policy_{kind}:statement_0"])

    def test_reviewer_cannot_use_an_uncited_document(self):
        verifier = PolicyDocumentVerifier("model", lambda _: json.dumps({"claims": [verdict()]}))
        self.assertEqual(verifier.check(RULE, LOG, None).reasons, ["policy_review_invalid"])

    def test_malformed_and_missing_reviewer_fail_closed(self):
        for raw in ("not JSON", "[]", '{"claims": []}', "x" * 24001):
            verifier = PolicyDocumentVerifier("model", lambda _, raw=raw: raw)
            self.assertEqual(verifier.check(answer(), LOG, None).action, "block")
        self.assertEqual(PolicyDocumentVerifier("model").check(answer(), LOG, None).reasons,
                         ["policy_reviewer_unavailable"])

    def test_timeout_does_not_release_the_candidate(self):
        def timeout(_):
            raise TimeoutError("provider details must not enter trace")
        result = PolicyDocumentVerifier("model", timeout).check(answer(), LOG, None)
        self.assertEqual(result.reasons, ["policy_reviewer_unavailable"])
        self.assertNotIn("provider details", str(result))

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            PolicyDocumentVerifier("modle")


class PolicyLoopIntegration(unittest.TestCase):
    def test_review_is_tool_free_and_bounded_and_repair_fetches_again(self):
        class Model(FakeLLM):
            def __init__(self):
                super().__init__()
                self.reviews = []
                self.drafts = 0

            def create(self, system, messages, tools):
                if system == REVIEW_SYSTEM:
                    self.reviews.append((messages, tools))
                    payload = json.loads(messages[0]["content"])
                    rows = []
                    for claim in payload["claims"]:
                        unsupported = "cards can be surcharged" in claim["text"]
                        source = next(s for s in payload["sources"] if s["id"] in claim["source_ids"])
                        rows.append({"id": claim["id"], "verdict": "unsupported" if unsupported else "supported",
                                     "evidence": [{"source_id": source["id"], "quote": source["text"]}]})
                    return NS(stop_reason="end_turn", content=[NS(type="text", text=json.dumps({"claims": rows}))])
                response = super().create(system, messages, tools)
                if response.stop_reason == "end_turn":
                    self.drafts += 1
                    if self.drafts == 1:
                        response.content[0].text = response.content[0].text.replace("cards cannot", "cards can")
                return response

        kb = Index()
        for page in DEMO_DOCS:
            kb.upsert_page(page)
        model = Model()
        bot = Chatbot(model, LocalGuardrail(), ToolBox(InMemoryTxns([]), InMemoryLogs([]), kb),
                      Settings(policy_verification="model", repair_attempts=1, record_fallback=True))
        result = bot.ask(bot.new_session("m_100", ["support"]), "What are the surcharge rules?")
        self.assertTrue(result.repaired)
        self.assertIn("cards cannot be surcharged", result.answer)
        self.assertEqual(len(model.reviews), 2)
        self.assertTrue(all(len(messages) == 1 and tools == [] for messages, tools in model.reviews))
        self.assertEqual(len(result.tools_called), 2)
        self.assertEqual(len(result.models_used), 6)  # retrieve, draft, review, repeated once


if __name__ == "__main__":
    unittest.main()
