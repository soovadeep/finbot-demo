import unittest
from datetime import date

from finbot.policy_documents import PolicyDocumentVerifier, policy_passage_answer
from finbot.policy_relevance import policy_codes
from scripts.naacl2027.verification_challenge import doc_log, page, quoted


class PolicyRelevance(unittest.TestCase):
    def test_identifier_lists_preserve_zeroes_without_matching_prices(self):
        self.assertEqual(policy_codes('Compare codes "E05", R-72 and 003; the payment was 200 USD.'),
                         {"E05", "R-72", "003"})
        self.assertEqual(policy_codes("What is the code for a $51 payment?"), set())
        self.assertEqual(policy_codes("Compare codes E05 / Q17 & 003."), {"E05", "Q17", "003"})

    def test_wrong_complete_quote_and_same_url_do_not_establish_relevance(self):
        for target, other in (("51", "54"), ("R-72", "E05"), ("003", "307")):
            good = page(f"Code {target} means the issuer needs a fresh authorization.", "codes")
            wrong = {**page(f"Code {other} means the card has expired.", "codes"), "chunk_id": "other"}
            log = doc_log(good, wrong)
            for mode in ("extractive", "strict"):
                checker = PolicyDocumentVerifier(mode, question=f"Please explain code {target}.", as_of=date(2026, 11, 24))
                self.assertEqual(checker.check(quoted(good), log, None).action, "allow")
                self.assertIn(f"policy_requested_code_missing:{target}", checker.check(quoted(wrong), log, None).reasons)

    def test_heading_is_evidence_but_a_page_title_or_url_cannot_label_every_chunk(self):
        good = {**page("The issuer needs a fresh authorization.", "codes-88"),
                "title": "Codes 88 and 93", "section": "Declines > Code 88"}
        wrong = {**good, "text": "The card has expired.", "section": "Declines > Code 93", "chunk_id": "other"}
        checker = PolicyDocumentVerifier(question="What does code 88 mean?")
        self.assertEqual(checker.check(quoted(good), doc_log(good, wrong), None).action, "allow")
        self.assertEqual(checker.check(quoted(wrong), doc_log(good, wrong), None).action, "block")
        # Explicit body identifiers override a misleading broad heading.
        misleading = {**good, "text": "Code 93 means the card has expired."}
        self.assertEqual(checker.check(quoted(misleading), doc_log(misleading), None).action, "block")

    def test_all_requested_codes_need_coverage_in_draft_and_fallback(self):
        a = page("Code E05 means the issuer needs a fresh authorization.", "e05", 10)
        b = page("Code Q17 means the card has expired.", "q17", 1)
        question = "Explain codes E05 and Q17."
        checker = PolicyDocumentVerifier(question=question)
        self.assertEqual(checker.check(quoted(a), doc_log(a, b), None).action, "block")
        answer = policy_passage_answer(doc_log(a, b), question)
        self.assertIn(a["text"], answer)
        self.assertIn(b["text"], answer)
        self.assertEqual(checker.check(answer, doc_log(a, b), None).action, "allow")
        self.assertIsNone(policy_passage_answer(doc_log(a), question))

    def test_fallback_filters_wrong_code_before_ranking_and_fast_path_checks_coverage(self):
        good = page("Code 88 means the issuer needs a fresh authorization.", "88", 1)
        wrong = page("Code 93 means the card has expired.", "93", 20)
        log = doc_log(good, wrong)
        question = "What does code 88 mean?"
        checker = PolicyDocumentVerifier(question=question)
        old_fallback = policy_passage_answer(log)
        self.assertEqual(checker.check(old_fallback, log, None).action, "block")
        answer = policy_passage_answer(log, question)
        self.assertIn(good["text"], answer)
        self.assertNotIn(wrong["text"], answer)
        self.assertEqual(checker.check(answer, log, None).action, "allow")
        self.assertIsNone(policy_passage_answer(log, "What does code 777 mean?"))

    def test_fallback_does_not_resurrect_a_failed_latest_search_or_invalid_scores(self):
        good = page("Credit cards may carry a surcharge.", "fees")
        miss = {"name": "search_knowledge_base", "input": {"query": "other"},
                "result": {"status": "not_found", "source": "knowledge_base", "data": []}}
        self.assertIsNone(policy_passage_answer([*doc_log(good), miss]))
        for score in (0, -1, float("nan"), float("inf"), True):
            self.assertIsNone(policy_passage_answer(doc_log({**good, "score": score})))

    def test_explicit_abstention_remains_available(self):
        checker = PolicyDocumentVerifier(question="What does code 777 mean?")
        self.assertEqual(checker.check("I couldn't verify that from the retrieved policy documents.", [], None).action, "allow")

    def test_real_controller_recovers_from_persistently_wrong_code_drafts(self):
        from finbot.config import Settings
        from finbot.guardrails import LocalGuardrail
        from finbot.llm import FakeLLM
        from finbot.orchestrator import Chatbot
        from finbot.tools import InMemoryLogs, InMemoryTxns, ToolBox
        good = page("Code 88 means the issuer needs a fresh authorization.", "88", 1)
        wrong = page("Code 93 means the card has expired.", "93", 20)
        class Retrieval:
            def search(self, *args, **kwargs):
                return [wrong, good]
        bot = Chatbot(FakeLLM(), LocalGuardrail(),
                      ToolBox(InMemoryTxns([]), InMemoryLogs([]), Retrieval(), domains=["payments"]),
                      Settings(policy_verification="extractive", semantic_verification="off", record_fallback=True))
        turn = bot.ask(bot.new_session("m_100", ["support"], "support"), "What does code 88 mean?")
        self.assertIsNone(turn.blocked_by)
        self.assertIn(good["text"], turn.answer)
        self.assertNotIn(wrong["text"], turn.answer)
        self.assertTrue(any("policy_requested_code_missing:88" in r for r in turn.reasons))


if __name__ == "__main__":
    unittest.main()
