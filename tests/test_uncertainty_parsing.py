"""A hedge qualifies only the detail in its own clause (next-steps item 3).

The fresh-wording challenge (results/naacl2027/fresh-wording-v1.json) found that
"It may have gone to Harbor Books. I am certain it was a card payment." treated Harbor
Books as definite and excluded the Willow Repairs card record. That report stays as it
was; these wordings are development regressions, not a new evaluation.
"""
import unittest

from finbot.clarification_conversation import Conversation, extract_details

CARDS = {"txn_EMIX0000", "txn_EMIX0002"}


def matches(text):
    engine = Conversation()
    engine.message(text)
    return {c.record_id for c in engine.matches}, engine.details


class Uncertainty(unittest.TestCase):
    def test_reported_failure(self):
        ids, details = matches("It may have gone to Harbor Books. I am certain it was a card payment.")
        self.assertEqual(ids, CARDS)
        self.assertEqual(details["merchant"]["certainty"], "tentative")
        self.assertEqual(details["kind"]["certainty"], "supplied")

    def test_clause_order_and_punctuation_controls(self):
        for text in ("I am certain it was a card payment. It may have gone to Harbor Books.",
                     "I'm certain it was a card payment, but it may have gone to Harbor Books.",
                     "It may have gone to Harbor Books; I'm sure it was a card payment.",
                     "It possibly went to Harbor Books, and I'm sure it was a card payment",
                     "I'm sure it was a card payment and it might have been Harbor Books",
                     "It was a card payment. I believe it went to Harbor Books"):
            with self.subTest(text=text):
                ids, details = matches(text)
                self.assertEqual(ids, CARDS)
                self.assertEqual(details["merchant"]["certainty"], "tentative")

    def test_definite_details_still_filter(self):
        ids, _ = matches("It was a card payment to Harbor Books.")
        self.assertEqual(ids, {"txn_EMIX0000"})
        ids, _ = matches("I'm certain it was a card payment to Harbor Books on May 3.")
        self.assertEqual(ids, set())        # a definite date that matches nothing stays definite

    def test_month_may_is_not_a_hedge(self):
        fields, _, _ = extract_details("My card payment on May 3", None)
        self.assertEqual(fields["kind"]["certainty"], "supplied")
        self.assertEqual(fields["date"]["certainty"], "supplied")

    def test_contradictions_are_still_unresolved(self):
        _, unknown, issues = extract_details("It was not a card payment, it was a bank transfer.", None)
        self.assertIn("kind", unknown)
        self.assertTrue(issues)


if __name__ == "__main__":
    unittest.main()
