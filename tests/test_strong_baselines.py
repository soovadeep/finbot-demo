import json
import tempfile
import unittest
from pathlib import Path

from finbot.clarification import Candidate, ClarificationSession
from scripts.naacl2027.compare_baselines import MissingCachedReply, ReadOnlyCache, paired_difference, rates


class BaselineEvaluation(unittest.TestCase):
    def test_amount_first_skips_constant_amount_and_retains_confirmation(self):
        candidates = tuple(Candidate(f"txn_{i}", "tenant", {"kind": "Card payment", "merchant": str(i),
                           "date": "2026-11-15", "amount": "200.00"}) for i in range(3))
        state = ClarificationSession(candidates, "tenant", strategy="amount_first", max_questions=1)
        q = state.next_question()
        self.assertEqual(q.template, "merchant")
        state.reply(q.template, q.options[0])
        self.assertIsNone(state.next_question())
        self.assertIsNone(state.selected_id)

    def test_most_distinct_uses_cardinality_not_fixed_order(self):
        candidates = tuple(Candidate(f"txn_{i}", "tenant", {"kind": str(i % 2), "merchant": str(i),
                           "date": "2026-11-15", "amount": "200.00"}) for i in range(4))
        state = ClarificationSession(candidates, "tenant", strategy="most_distinct")
        self.assertEqual(state.next_question().template, "merchant")

    def test_missing_cache_never_runs_compute_or_changes_outcome_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.jsonl"; path.write_text("")
            cache = ReadOnlyCache(path)
            with self.assertRaises(MissingCachedReply):
                cache.get_or("missing", lambda: self.fail("Must never call provider"))
            self.assertEqual(path.read_text(), "")
        result = rates([{"complete": False}])
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["unresolved"], 0)
        self.assertIsNone(result["correct_rate"])

    def test_paired_comparison_uses_only_shared_complete_episodes(self):
        left = [{"episode": "a", "complete": True, "correct": True},
                {"episode": "b", "complete": True, "correct": False}]
        right = [{"episode": "a", "complete": True, "correct": False},
                 {"episode": "b", "complete": False}]
        result = paired_difference(left, right, {"a": {"target_id": "one"}}, "correct")
        self.assertEqual(result["common_episodes"], 1)
        self.assertEqual(result["decision_value_minus_baseline"], 1)
