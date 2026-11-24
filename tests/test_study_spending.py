import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from finbot.resilience import ServiceUnavailable
from scripts.naacl2027.budgeted_conversation_study import BASE, ENDPOINT, MODEL, SpendBudget, local_key, price


class StudySpending(unittest.TestCase):
    def writer(self):
        return {"budget_usd": "1.00", "max_tokens": 600,
                "endpoint": {"tag": ENDPOINT, "context_length": 131072,
                             "pricing": {"prompt": "0.0000001", "completion": "0.00000032"}}}

    def body(self):
        return {"model": MODEL, "max_tokens": 600, "temperature": 0,
                "messages": [{"role": "user", "content": "A synthetic payment question."}]}

    def response(self, cost=0.0002):
        return {"id": "fake-generation", "usage": {"cost": cost},
                "choices": [{"message": {"content": "Synthetic test answer"}}]}

    def test_price_ceiling_and_full_window_reservation_precede_network(self):
        with tempfile.TemporaryDirectory() as folder:
            budget = SpendBudget(self.writer(), Path(folder), {"exhausted": False})
            def send(url, body, headers):
                self.assertEqual(budget.held, Decimal("0.0132992"))
                self.assertIn('"event": "reserve"', budget.journal.read_text())
                self.assertEqual(body["provider"]["only"], [ENDPOINT])
                self.assertFalse(body["provider"]["allow_fallbacks"])
                self.assertEqual(body["provider"]["max_price"], {"prompt": 0.1, "completion": 0.32, "request": 0})
                return self.response()
            budget.send(send, BASE + "/chat/completions", self.body(), {"Authorization": "secret-test-only"})
            self.assertEqual(budget.held, Decimal("0.0002"))
            self.assertNotIn("secret-test-only", budget.journal.read_text())

    def test_no_request_when_remaining_budget_cannot_cover_worst_case(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = {"exhausted": False}
            budget = SpendBudget(self.writer(), Path(folder), calls)
            budget.held = Decimal("0.99")
            send = Mock()
            with self.assertRaisesRegex(ServiceUnavailable, "dollar_limit"):
                budget.send(send, BASE + "/chat/completions", self.body(), {})
            send.assert_not_called()
            self.assertTrue(calls["exhausted"])
            self.assertEqual(budget.held, Decimal("0.99"))

    def test_unknown_cost_retains_reservation_and_stops_subsequent_calls(self):
        for outcome in (TimeoutError(), {"choices": []}, self.response(float("nan"))):
            with self.subTest(outcome=type(outcome).__name__), tempfile.TemporaryDirectory() as folder:
                budget = SpendBudget(self.writer(), Path(folder), {"exhausted": False})
                send = Mock(side_effect=outcome) if isinstance(outcome, Exception) else Mock(return_value=outcome)
                with self.assertRaises(ServiceUnavailable):
                    budget.send(send, BASE + "/chat/completions", self.body(), {})
                self.assertEqual(budget.held, Decimal("0.0132992"))
                with self.assertRaises(ServiceUnavailable):
                    budget.send(send, BASE + "/chat/completions", self.body(), {})
                self.assertEqual(send.call_count, 1)

    def test_unexpected_charge_stops_and_records_reported_cost(self):
        with tempfile.TemporaryDirectory() as folder:
            budget = SpendBudget(self.writer(), Path(folder), {"exhausted": False})
            with self.assertRaisesRegex(ServiceUnavailable, "pricing_contract_changed"):
                budget.send(Mock(return_value=self.response(0.02)), BASE + "/chat/completions", self.body(), {})
            self.assertEqual(budget.report()["provider_reported_usd"], "0.02")
            self.assertEqual(budget.stopped, "provider_charge_exceeded_reservation")

    def test_other_endpoints_and_paid_options_are_rejected_without_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            budget = SpendBudget(self.writer(), Path(folder), {"exhausted": False})
            send = Mock()
            for url, body in (("https://example.test/chat", self.body()),
                              (BASE + "/chat/completions", {**self.body(), "max_tokens": 601}),
                              (BASE + "/chat/completions", {**self.body(), "plugins": [{"id": "web"}]})):
                with self.assertRaises(ValueError):
                    budget.send(send, url, body, {})
            send.assert_not_called()

    def test_key_file_is_parsed_as_data_and_required(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            path = Path(folder) / ".env.local"
            with self.assertRaisesRegex(ValueError, "No local"):
                local_key(path)
            path.write_text('UNRELATED=ignored\nexport FINBOT_OPENAI_API_KEY="not-a-real-key"\n')
            self.assertEqual(local_key(path), "not-a-real-key")
            for value in (float("nan"), float("inf"), -1):
                with self.assertRaises(ValueError):
                    price(value)


if __name__ == "__main__":
    unittest.main()
