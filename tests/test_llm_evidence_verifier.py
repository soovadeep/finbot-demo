"""The direct LLM evidence review: strict schema, fail-closed, never a silent pass."""
import json
import unittest
from types import SimpleNamespace as NS

from finbot.demo import ROLE_RECORD
from finbot.semantic_verification import LLMEvidenceVerifier, configured_verifier

LOG = [{"name": "get_transaction", "input": {"txn_id": "txn_ROLE0001"},
        "result": {"status": "found", "source": "txn_db", "data": ROLE_RECORD}}]


class Reply:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.seen = text, error, []

    def create(self, system, messages, tools):
        self.seen.append(json.loads(messages[0]["content"]))
        if self.error:
            raise self.error
        return NS(stop_reason="end_turn", content=[NS(type="text", text=self.text)],
                  usage=NS(input_tokens=10, output_tokens=5))


def verdict(text=None, error=None):
    client = Reply(text, error)
    result = LLMEvidenceVerifier("test/model", "How much was refunded?", client=client).check(
        "Refund amount: 50.00.", LOG, None)
    return result, client


class LLMEvidence(unittest.TestCase):
    def test_supported_and_complete_allows(self):
        result, client = verdict('{"support": "supported", "complete": "complete", "problems": []}')
        self.assertEqual(result.action, "allow")
        self.assertEqual(result.checks[0]["usage"], {"input_tokens": 10, "output_tokens": 5})
        self.assertEqual(client.seen[0]["question"], "How much was refunded?")
        self.assertEqual(client.seen[0]["evidence"][0]["input"], {"txn_id": "txn_ROLE0001"})

    def test_unsupported_or_incomplete_blocks_with_separate_reasons(self):
        result, _ = verdict('```json\n{"support": "unsupported", "complete": "incomplete", '
                            '"problems": [{"type": "unsupported", "text": "x"}]}\n```')
        self.assertEqual(result.action, "block")
        self.assertEqual(result.reasons, ["semantic_unsupported", "semantic_incomplete"])

    def test_malformed_or_failed_review_is_unavailable_not_a_detection(self):
        for text, error, reason in (("looks fine to me", None, "semantic_unavailable:malformed_assessment"),
                                    ('{"support": "maybe", "complete": "complete"}', None,
                                     "semantic_unavailable:malformed_assessment"),
                                    (None, TimeoutError("slow"), "semantic_unavailable:provider_error")):
            result, _ = verdict(text, error)
            self.assertEqual(result.action, "block")
            self.assertEqual(result.reasons, [reason])
            self.assertEqual(result.checks[0]["verdict"], "unavailable")
            self.assertNotIn("slow", json.dumps(result.checks))

    def test_configuration(self):
        settings = NS(semantic_verification="llm", semantic_model="test/model")
        self.assertIsInstance(configured_verifier(settings, "q")[0], LLMEvidenceVerifier)
        self.assertEqual(configured_verifier(NS(semantic_verification="off"), "q"), ())
        with self.assertRaises(ValueError):
            configured_verifier(NS(semantic_verification="nemo"), "q")


if __name__ == "__main__":
    unittest.main()
