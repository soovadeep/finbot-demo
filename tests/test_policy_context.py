import unittest
from unittest.mock import patch

from finbot.demo import run_demo
from finbot.llm import FakeLLM
from finbot.policy_documents import PolicyDocumentVerifier

URL = "https://example.com/policy"
RULE = "Credit cards may carry a surcharge."
EXCEPTION = "Debit and prepaid cards are excluded."


def log(text=RULE + " " + EXCEPTION):
    return [{"name": "search_knowledge_base", "input": {"query": "surcharges"}, "result": {
        "status": "found", "source": "knowledge_base", "data": [{"text": text, "source_url": URL}]}}]


class PolicyContext(unittest.TestCase):
    def setUp(self):
        self.checker = PolicyDocumentVerifier("extractive")

    def test_source_matching_rule_without_exception_is_rejected(self):
        result = self.checker.check(f"{RULE} (source: {URL})", log(), None)
        self.assertEqual(result.reasons, ["policy_incomplete_context:statement_0"])
        self.assertFalse(result.checks[0]["context_complete"])

    def test_full_context_can_span_cited_paragraphs(self):
        for text in (f"{RULE} {EXCEPTION} (source: {URL})",
                     f"{EXCEPTION} (source: {URL})\n\n{RULE} (source: {URL})"):
            self.assertEqual(self.checker.check(text, log(), None).action, "allow")

    def test_exception_without_its_citation_cannot_complete_context(self):
        text = f"{RULE} (source: {URL})\n\n{EXCEPTION}"
        self.assertEqual(self.checker.check(text, log(), None).action, "block")

    def test_other_hits_need_not_be_quoted_but_duplicate_sentence_context_is_preserved(self):
        evidence = log()
        evidence[0]["result"]["data"].append({"text": "Call support for help.", "source_url": "https://example.com/help"})
        self.assertEqual(self.checker.check(f"{RULE} {EXCEPTION} (source: {URL})", evidence, None).action, "allow")
        # Same sentence can be supported by a different, complete source passage.
        evidence[0]["result"]["data"].append({"text": RULE, "source_url": "https://example.com/rule"})
        self.assertEqual(self.checker.check(f"{RULE} (source: https://example.com/rule)", evidence, None).action, "allow")

    def test_absent_evidence_allows_explicit_abstention_and_paraphrases_stay_restricted(self):
        self.assertEqual(self.checker.check("I couldn't verify that from the retrieved policy documents.", log(), None).action, "allow")
        self.assertEqual(self.checker.check(f"Only credit cards qualify. (source: {URL})", log(), None).action, "block")

    def test_real_workflow_repairs_or_refuses_missing_exception(self):
        original = FakeLLM._answer
        for persistent in (False, True):
            calls = []
            def omit(model, results):
                response = original(model, results)
                calls.append(1)
                if persistent or len(calls) == 1:
                    response.content[0].text = response.content[0].text.replace(
                        "Debit and prepaid cards cannot be surcharged.", "")
                return response
            with self.subTest(persistent=persistent), patch.object(FakeLLM, "_answer", omit):
                result = run_demo("What are the surcharge rules?")
            self.assertEqual(result["outcome"], "policy_fallback" if persistent else "repaired")
            self.assertTrue(any(r.startswith("policy_incomplete_context:") for r in result["steps"][0]["reasons"]))
            # Repaired or quoted, the released answer keeps the exception.
            self.assertIn("Debit and prepaid cards cannot be surcharged.", result["final"]["answer"])


if __name__ == "__main__":
    unittest.main()
