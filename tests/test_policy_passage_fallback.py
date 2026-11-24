import unittest

from finbot.policy_documents import PolicyDocumentVerifier, policy_passage_answer
from finbot.replies import POLICY_ONLY

A = {"text": "Surcharges apply to credit cards only. Debit cards cannot be surcharged.",
     "source_url": "https://wiki.example.com/surcharge", "chunk_id": "1:v1:0", "version": 1,
     "updated": "2026-09-15", "score": 2.4}
B = {"text": "The card has insufficient available balance.", "source_url": "https://wiki.example.com/decline-codes",
     "chunk_id": "2:v1:1", "version": 1, "updated": "2026-10-01", "score": 1.0}


def search(*hits):
    return {"name": "search_knowledge_base", "input": {"query": "q"},
            "result": {"status": "found", "source": "knowledge_base", "data": list(hits)}}


class PolicyPassageFallback(unittest.TestCase):
    def test_quotes_the_best_passage_verbatim_with_source_and_date(self):
        answer = policy_passage_answer([search(A, B)])
        self.assertTrue(answer.startswith(POLICY_ONLY))
        self.assertIn(A["text"] + " (source: https://wiki.example.com/surcharge, updated 2026-09-15)", answer)
        self.assertNotIn(B["text"], answer)  # far below the best score

    def test_keeps_close_runners_up(self):
        answer = policy_passage_answer([search(A, {**B, "score": 2.0})])
        self.assertIn(A["text"], answer)
        self.assertIn(B["text"], answer)

    def test_no_passage_or_a_record_turn_gives_none(self):
        self.assertIsNone(policy_passage_answer([search()]))
        self.assertIsNone(policy_passage_answer([]))
        record = {"name": "get_transaction", "input": {"txn_id": "txn_A1B2C3D4"},
                  "result": {"status": "found", "data": {"txn_id": "txn_A1B2C3D4"}}}
        self.assertIsNone(policy_passage_answer([record, search(A)]))

    def test_extractive_verifier_accepts_only_the_exact_rendering(self):
        log = [search(A, B)]
        checker = PolicyDocumentVerifier("extractive")
        answer = policy_passage_answer(log)
        self.assertEqual(checker.check(answer, log, None).action, "allow")
        altered = answer.replace("cannot", "can")
        self.assertEqual(checker.check(altered, log, None).action, "block")


if __name__ == "__main__":
    unittest.main()
