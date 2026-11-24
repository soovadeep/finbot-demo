import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finbot.llm import FakeLLM
from scripts.naacl2027.conversation_study import (
    SETTINGS, build_cases, freeze, normalized, probe_checks, read, review_form, run_arm,
    run_study, score, validate_cases, verify, write_new,
)


class ConversationStudy(unittest.TestCase):
    def test_actual_turns_roll_over_and_refetch_replaced_snapshot(self):
        case = build_cases()["cases"][0]
        case["filler"] = case["filler"][:4]
        run = run_arm(case, "long", FakeLLM(), {**SETTINGS, "max_turns_per_thread": 3},
                      {"remaining": 100, "exhausted": False}, "2026-11-24")
        self.assertTrue(run["completed"])
        self.assertEqual(len(run["trace"]), 8)
        self.assertGreater(run["rollovers"], 0)
        self.assertTrue(all(run["diagnostics"].values()))
        self.assertTrue(all(t["calls"] for t in run["trace"]))  # real model/tool turns, no preloaded history
        self.assertIn("24.60", run["trace"][0]["turn"]["answer"])
        self.assertIn("39.20", run["trace"][-1]["turn"]["answer"])
        form = review_form([run])
        for item in form["items"]:
            self.assertIsNone(item["supported"])
            self.assertNotIn("diagnostics", item)
            self.assertNotIn("blocked_by", item)
            self.assertNotIn("arm", item)

    def test_correct_numbers_about_wrong_record_do_not_pass_mechanical_identity_check(self):
        case = build_cases()["cases"][0]
        turn = {"answer": "Refund amount: 39.20", "blocked_by": None,
                "focus": "txn_LONG0002", "tools_called": []}
        checks = probe_checks(case["probe"], turn, {})
        self.assertTrue(checks["literal_required_strings"])
        self.assertFalse(checks["focused_record_matches"])
        self.assertFalse(checks["refetched_current_records"])

    def test_call_exhaustion_keeps_the_unfinished_arm_in_results(self):
        case = build_cases()["cases"][0]
        run = run_arm(case, "short", FakeLLM(), SETTINGS, {"remaining": 1, "exhausted": False}, "2026-11-24")
        self.assertFalse(run["completed"])
        self.assertIsNone(run["diagnostics"])
        self.assertEqual(review_form([run])["items"], [])

    def test_external_wording_requires_provenance_and_rejects_known_normalized_probe(self):
        bundle = build_cases()
        bundle["cases"] = bundle["cases"][:1]
        bundle["provenance"]["independent"] = True
        with self.assertRaisesRegex(ValueError, "Developer-authored"):
            validate_cases(bundle)
        bundle["provenance"]["author_role"] = "external"
        seen = {normalized(bundle["cases"][0]["probe"]["question"])}
        with self.assertRaisesRegex(ValueError, "overlaps"):
            validate_cases(bundle, seen)

    def test_rehearsal_is_network_free_and_blank_or_tampered_labels_cannot_score(self):
        with tempfile.TemporaryDirectory() as temp:
            study, out = Path(temp) / "study", Path(temp) / "results"
            bundle = build_cases()
            bundle["cases"] = bundle["cases"][:1]
            bundle["cases"][0]["filler"] = [bundle["cases"][0]["filler"][0]]
            write_new(study / "cases.json", bundle)
            freeze(study, {"model": "", "base_url": "", "max_tokens": 600, "temperature": 0})
            with patch("finbot.llm.OpenAICompatLLM", side_effect=AssertionError("No provider allowed")):
                report = run_study(study, out)
            self.assertEqual(report["provider_call_attempts"], 0)
            self.assertIsNone(report["semantic_success_rate"])
            self.assertEqual(report["completed_arms"], 2)
            labels = read(out / "review-form.json")
            labels.update(reviewer="unit-test-fixture", reviewer_relationship="test only")
            with self.assertRaisesRegex(ValueError, "Blank labels"):
                score(out, labels)
            for item in labels["items"]:
                item.update(correct_record=True, supported=True, complete=True)
            self.assertTrue(score(out, labels)["paired_comparison_ready"])
            tampered = copy.deepcopy(labels)
            tampered["items"][0]["answer"] = "A different answer"
            with self.assertRaisesRegex(ValueError, "changed during labeling"):
                score(out, tampered)
            with self.assertRaisesRegex(ValueError, "Freeze a named model"):
                run_study(study, Path(temp) / "live", live=True)
            (study / "cases.json").write_text('{}')
            with self.assertRaisesRegex(ValueError, "changed after freeze"):
                verify(study)


if __name__ == "__main__":
    unittest.main()
