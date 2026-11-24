import copy
import unittest
from unittest.mock import patch

from finbot.binding import binding_check
from finbot.demo import run_demo
from finbot.llm import FakeLLM


def evidence():
    return [{"name": "get_transaction", "input": {"txn_id": rid}, "result": {
        "status": "found", "source": "txn_db", "data": {
            "txn_id": rid, "amount": amount, "currency": currency, "status": "approved"}}}
        for rid, amount, currency in (("txn_CURR0001", "210.00", "EUR"), ("txn_CURR0002", "47.25", "GBP"))]


class CurrencyBinding(unittest.TestCase):
    def test_swaps_block_for_codes_and_unambiguous_symbols(self):
        for first, second in (("210.00 GBP", "47.25 EUR"), ("£210.00", "€47.25")):
            with self.subTest(first=first):
                reasons = binding_check(f"txn_CURR0001 was approved for {first}. "
                                        f"txn_CURR0002 was approved for {second}.", evidence())
                self.assertEqual(sum(r.startswith("value_from_other_record:currency:") for r in reasons), 2)

    def test_correct_bindings_and_equal_currencies_are_allowed(self):
        for second_currency in ("GBP", "EUR"):
            log = evidence()
            log[1]["result"]["data"]["currency"] = second_currency
            answer = f"txn_CURR0002 was approved for 47.25 {second_currency}. txn_CURR0001 was approved for 210.00 EUR."
            self.assertEqual(binding_check(answer, log), [])

    def test_shared_policy_or_third_party_text_cannot_excuse_wrong_currency(self):
        log = evidence()
        log[0]["result"]["data"]["merchant_name"] = {"currency": "GBP"}
        log.append({"name": "search_knowledge_base", "input": {"query": "currency"},
                    "result": {"status": "found", "source": "knowledge_base",
                               "data": [{"text": "GBP is available.", "source_url": "https://example.com/policy"}]}})
        self.assertIn("value_from_other_record:currency:txn_CURR0001<-txn_CURR0002",
                      binding_check("txn_CURR0001 was approved for 210.00 GBP.", log))

    def test_structured_settlement_currency_is_not_treated_as_a_swap(self):
        log = copy.deepcopy(evidence())
        log[0]["result"]["data"]["settlement_currency"] = "GBP"
        self.assertEqual(binding_check("txn_CURR0001 was approved for 210.00 EUR. Settlement currency is GBP.", log), [])

    def test_real_workflow_repairs_currency_swap_before_release(self):
        original = FakeLLM._answer
        calls = []
        def swap(model, results):
            response = original(model, results)
            calls.append(1)
            if len(calls) == 1:
                response.content[0].text = response.content[0].text.replace("EUR", "__SWAP__").replace("GBP", "EUR").replace("__SWAP__", "GBP")
            return response
        records = [{**c["result"]["data"], "tenant_id": "m_100"} for c in evidence()]
        with patch.object(FakeLLM, "_answer", swap):
            result = run_demo("Compare txn_CURR0001 and txn_CURR0002: amounts and statuses?", records=records)
        self.assertEqual(result["outcome"], "repaired")
        self.assertTrue(any(r.startswith("value_from_other_record:currency:") for r in result["steps"][0]["reasons"]))
        self.assertIn("txn_CURR0001 was approved for 210.00 EUR", result["final"]["answer"])
        self.assertIn("txn_CURR0002 was approved for 47.25 GBP", result["final"]["answer"])


if __name__ == "__main__":
    unittest.main()
