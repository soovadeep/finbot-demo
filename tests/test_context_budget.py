"""Offline contracts for actual prompt admission and conversation rollover."""
import copy
import unittest
from types import SimpleNamespace as NS

from finbot.config import Settings
from finbot.context import ContextBudget, ContextBudgetExceeded, estimate_tokens
from finbot.guardrails import LocalGuardrail
from finbot.knowledge import Index
from finbot.llm import FakeLLM
from finbot.memory import SessionMemory
from finbot.orchestrator import Chatbot, SYSTEM_PROMPT
from finbot.resilience import ServiceUnavailable
from finbot.tools import InMemoryLogs, InMemoryTxns, ToolBox


RECORD = {"txn_id": "txn_CTX00001", "tenant_id": "m_100", "status": "approved",
          "amount": "66.50", "currency": "USD", "refund": {"status": "succeeded", "amount": "14.50"}}


class RecordingModel(FakeLLM):
    max_tokens = 1024

    def __init__(self):
        super().__init__()
        self.requests = []

    def create(self, system, messages, tools):
        self.requests.append(copy.deepcopy((system, messages, tools)))
        return super().create(system, messages, tools)


def make_bot(model=None, record=None, **kwargs):
    settings = Settings(**dict({"context_window_tokens": 50000, "context_output_reserve_tokens": 1024,
                                "context_margin_tokens": 512, "max_history_chars": 1_000_000,
                                "llm_retry_attempts": 1}, **kwargs))
    toolbox = ToolBox(InMemoryTxns([copy.deepcopy(record or RECORD)]), InMemoryLogs([]), Index(),
                      domains=["payments"])
    bot = Chatbot(model or RecordingModel(), LocalGuardrail(), toolbox, settings)
    bot.sleep = lambda _: None
    return bot, bot.new_session("m_100", ["support"], "support")


class ContextAdmission(unittest.TestCase):
    def test_count_includes_system_tools_blocks_and_utf8(self):
        plain = estimate_tokens("", [{"role": "user", "content": "abc"}], [])
        unicode = estimate_tokens("", [{"role": "user", "content": "漢字🙂"}], [])
        self.assertGreater(unicode, plain)
        full = estimate_tokens("system" * 100, [{"role": "assistant", "content": [
            NS(type="tool_use", id="a", name="lookup", input={"id": "x"})]}],
            [{"name": "lookup", "input_schema": {"description": "x" * 500}}])
        self.assertGreater(full, plain + 1000)
        with self.assertRaises(ContextBudgetExceeded):
            ContextBudget(full, 1, 0).require_fit("system" * 100, [{"role": "assistant", "content": [
                NS(type="tool_use", id="a", name="lookup", input={"id": "x"})]}],
                [{"name": "lookup", "input_schema": {"description": "x" * 500}}])

    def test_invalid_reservation_is_configuration_error(self):
        with self.assertRaises(ValueError):
            Settings(context_window_tokens=100, context_output_reserve_tokens=90, context_margin_tokens=10)

    def test_rollover_preserves_focus_and_refetches_current_record(self):
        bot, session = make_bot()
        session.history = [{"role": "user", "content": "Previous request " + "x" * 60000},
                           {"role": "assistant", "content": "Earlier answer"}]
        session.memory.focus = RECORD["txn_id"]
        session.memory.user_ids = [RECORD["txn_id"]]
        turn = bot.ask(session, "How much was refunded on txn_CTX00001?")
        self.assertIsNone(turn.blocked_by)
        self.assertIn("14.50", turn.answer)
        self.assertEqual(session.memory.focus, RECORD["txn_id"])
        self.assertTrue(session.memory.recap)
        self.assertEqual(session.memory.turns_in_thread, 1)
        for system, messages, tools in bot.llm.requests:
            self.assertTrue(bot._context_budget().fits(system, messages, tools))
            self.assertNotIn("x" * 1000, str(messages))
        self.assertTrue(any(c["name"] == "get_transaction" for c in turn.tools_called))

    def test_tool_growth_stops_before_next_provider_call_without_truncation(self):
        bot, session = make_bot(context_window_tokens=8000)  # first prompt fits; tool results do not
        before = copy.deepcopy(session.history)
        turn = bot.ask(session, "How much was refunded on txn_CTX00001?")
        self.assertEqual(turn.blocked_by, "context_budget")
        self.assertEqual(len(bot.llm.requests), 1)
        self.assertEqual(session.history, before)
        self.assertEqual(session.memory.entities, {})

    def test_single_oversized_request_is_not_silently_shortened(self):
        bot, session = make_bot()
        turn = bot.ask(session, "Tell me about txn_CTX00001. " + "detail " * 12000)
        self.assertEqual(turn.blocked_by, "context_budget")
        self.assertEqual(bot.llm.requests, [])
        self.assertIn("narrow the question", turn.answer)

    def test_failed_call_after_rollover_restores_whole_previous_thread(self):
        class Down(RecordingModel):
            def create(self, *args):
                raise ServiceUnavailable("test outage")
        bot, session = make_bot(Down(), max_turns_per_thread=1)
        session.history = [{"role": "user", "content": "Earlier request"},
                           {"role": "assistant", "content": "Earlier answer"}]
        session.memory.turns_in_thread = 1
        before = copy.deepcopy(session.history)
        turn = bot.ask(session, "How much was refunded on txn_CTX00001?")
        self.assertEqual(turn.blocked_by, "unavailable")
        self.assertEqual(session.history, before)
        self.assertEqual(session.memory.turns_in_thread, 1)

    def test_output_reservation_honours_client_cap(self):
        bot, _ = make_bot()
        bot.llm.max_tokens = 8000
        self.assertEqual(bot._context_budget().output_tokens, 8000)


class MemoryContinuity(unittest.TestCase):
    def test_missing_then_reintroduced_field_replaces_snapshot(self):
        memory = SessionMemory(focus=RECORD["txn_id"])
        def ingest(record):
            memory.ingest_tool_result("get_transaction", {"txn_id": RECORD["txn_id"]},
                                      {"status": "found", "source": "txn_db", "data": record})
        ingest(RECORD)
        ingest({k: v for k, v in RECORD.items() if k != "refund"})
        self.assertNotIn("refund", memory.entities[RECORD["txn_id"]].current())
        ingest(RECORD)
        self.assertEqual(memory.entities[RECORD["txn_id"]].current()["refund"]["amount"], "14.50")

    def test_large_ledger_renders_bounded_state_without_partial_financial_facts(self):
        memory = SessionMemory(focus=RECORD["txn_id"])
        memory.ingest_tool_result("get_transaction", {"txn_id": RECORD["txn_id"]},
                                  {"status": "found", "source": "txn_db", "data": {**RECORD, "extra": "x" * 50000}})
        text = memory.render()
        self.assertIn(RECORD["txn_id"], text)
        self.assertIn("fetch the focused record again", text)
        self.assertNotIn("14.50", text)
        self.assertLess(len(text), 1000)


if __name__ == "__main__":
    unittest.main()
