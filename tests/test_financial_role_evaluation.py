import json
import unittest

from scripts.naacl2027.evaluate_financial_roles import ROOT, cases, evaluate


class FinancialRoleDiagnostics(unittest.TestCase):
    def test_fixture_labels_and_equal_value_controls_are_explicit(self):
        for case in cases():
            self.assertEqual(case["expected_changed_supported"], case["clean"] == case["changed"])
            # Every substituted value is present in the evidence; detection must
            # distinguish roles/owners, not merely find an invented number.
            import re
            blob = json.dumps(case["evidence"])
            for value in re.findall(r"\d{4}-\d{2}-\d{2}|\d+\.\d{2}", case["changed"]):
                self.assertIn(value, blob)

    def test_current_outcomes_match_historical_report_and_preserve_known_boundaries(self):
        actual = evaluate()
        saved = json.loads((ROOT / "results/naacl2027/financial-roles.json").read_text())
        # Compare all measurements while retaining the original source manifest. The later
        # requested-information check adds its own entries to each step's check list; the
        # historical report predates it, so those entries are set aside and every verdict,
        # reason and answer must still match.
        def historical(value):
            if isinstance(value, dict):
                return {k: historical(v) for k, v in value.items()}
            if isinstance(value, list):
                return [historical(v) for v in value
                        if not (isinstance(v, dict) and v.get("kind") == "requested_information")]
            return value
        actual = historical(actual)
        self.assertEqual({k: v for k, v in actual.items() if k != "sources"},
                         {k: v for k, v in saved.items() if k != "sources"})
        self.assertEqual(actual["new_model_calls"], 0)
        self.assertTrue(all(r["required_fixture_details_present"] for r in actual["workflows"]))
        self.assertEqual(actual["historical_replay"]["known_omissions_still_allowed"], 1)
        self.assertTrue(all(r["full_check"]["action"] == "allow" for r in actual["boundary_probes"]))


if __name__ == "__main__":
    unittest.main()
