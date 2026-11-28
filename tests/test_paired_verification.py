import random
import unittest

from scripts.naacl2027.check_injection import DraftPair, held_injected, held_pairs
from scripts.naacl2027.paired_verification import summarize, transition


class MatchedControls(unittest.TestCase):
    def test_preexisting_false_rejection_is_not_credited_to_mutation(self):
        result = summarize([{"eligible": True, "transition": transition("block", "block")},
                            {"eligible": True, "transition": transition("allow", "allow")}])
        self.assertEqual(result["raw_corrupted_rejection_rate"], .5)
        self.assertEqual(result["mutation_rejection_given_clean_allowed"], 0)
        self.assertEqual(result["paired_rejection_lift"], 0)

    def test_zero_accepted_controls_is_undefined_not_perfect_detection(self):
        result = summarize([{"eligible": True, "transition": "block_to_block"}])
        self.assertIsNone(result["mutation_rejection_given_clean_allowed"])

    def test_supported_mutations_are_excluded_from_error_denominator(self):
        result = summarize([{"eligible": False, "transition": "allow_to_allow"},
                            {"eligible": True, "transition": "allow_to_block"}])
        self.assertEqual(result["eligible_pairs"], 1)
        self.assertEqual(result["excluded_pairs"], 1)

    def test_controls_preserve_wording_and_legacy_corrupt_texts(self):
        record = {"status": "pending", "amount": "200.00", "currency": "USD", "record_id": "txn_ONE",
                  "merchant": "Shop", "date": "2026-11-15"}
        pairs = held_pairs(record, {"record_id": "txn_TWO"}, random.Random(2028))
        legacy = held_injected(record, {"record_id": "txn_TWO"}, random.Random(2028))
        self.assertEqual({k: [p.corrupted for p in v] for k, v in pairs.items()}, legacy)
        link = pairs["link"][0]
        self.assertEqual(link.corrupted, link.clean + " More at www.example.com/help.")
        self.assertIn("has not settled yet", link.clean)
