"""Every demo answer says who wrote it: script, new live answer, cached replay, or fallback."""
import io
import json
import os
import unittest
from unittest import mock

from finbot import demo
from finbot.llm import FakeLLM

LIVE_ENV = {"FINBOT_DEMO_WRITER": "live", "FINBOT_LLM_PROVIDER": "openai", "FINBOT_MODEL": "test/model",
            "FINBOT_DEMO_LIVE_NAME": "Test model", "FINBOT_DEMO_LIVE_DAILY": "100", "FINBOT_DEMO_LIVE_PER_CLIENT": "2"}


class Broken:
    def create(self, *_):
        raise RuntimeError("provider down")


class TimesOut:
    def create(self, *_):
        raise TimeoutError("provider timed out")


class WriterLabels(unittest.TestCase):
    def setUp(self):
        demo.LIVE_CACHE.clear()
        demo.LIVE_BUDGET.__init__()

    def test_scripted_by_default(self):
        result = demo.run_demo("Why was txn_A1B2C3D4 declined?", live=True)
        self.assertEqual(result["writer_source"], "scripted")
        self.assertEqual(result["writer_label"], "Scripted writer")

    def test_generated_then_cached_then_limited(self):
        with mock.patch.dict(os.environ, LIVE_ENV), mock.patch("finbot.llm.make_client", lambda *_: FakeLLM()):
            first = demo.run_demo("Why was txn_A1B2C3D4 declined?", live=True, client="a")
            self.assertEqual(first["writer_source"], "live_generated")
            self.assertIn("Test model", first["writer_label"])
            again = demo.run_demo("Why was txn_A1B2C3D4 declined?", live=True, client="a")
            self.assertEqual(again["writer_source"], "live_cached")
            self.assertIn("replayed", again["writer_label"])
            demo.run_demo("What is the status of txn_TIMEOUT01?", live=True, client="a")
            limited = demo.run_demo("How much was refunded on txn_ROLE0001?", live=True, client="a")
            self.assertEqual(limited["writer_source"], "scripted_after_limit")
            self.assertIn("limit", limited["writer_note"])

    def test_provider_failure_is_labelled(self):
        with mock.patch.dict(os.environ, LIVE_ENV), mock.patch("finbot.llm.make_client", lambda *_: Broken()):
            result = demo.run_demo("Why was txn_A1B2C3D4 declined?", live=True, client="b")
        self.assertEqual(result["writer_source"], "scripted_after_provider_error")
        self.assertEqual(result["mode"], "offline_scripted")

    def test_provider_timeout_falls_back_and_is_not_cached(self):
        # A timeout reaches run_demo as a normal "unavailable" turn, not as an exception.
        with mock.patch.dict(os.environ, LIVE_ENV), mock.patch("finbot.llm.make_client", lambda *_: TimesOut()):
            for _ in range(2):
                result = demo.run_demo("Why was txn_A1B2C3D4 declined?", live=True, client="c")
                self.assertEqual(result["writer_source"], "scripted_after_provider_error")
                self.assertEqual(result["mode"], "offline_scripted")
                self.assertNotEqual(result["final"]["blocked_by"], "unavailable")
                self.assertIn("did not answer", result["writer_note"])
        self.assertEqual(len(demo.LIVE_CACHE), 0)

    def test_conversation_answers_carry_the_label(self):
        from finbot.clarification_conversation import run_conversation
        result = run_conversation({"events": [{"type": "message", "text": "My bank transfer to Willow Repairs on "
                                                                          "November 15."},
                                              {"type": "confirm", "record_id": "txn_EMIX0001"}]})
        answer = next(m for m in result["messages"] if m.get("record_id"))
        self.assertEqual(answer["writer_source"], "scripted")


def call(app, method, path, body=None):
    raw = json.dumps(body).encode() if body is not None else b""
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "CONTENT_TYPE": "application/json",
               "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw), "HTTP_HOST": "127.0.0.1:8765",
               "REMOTE_ADDR": "127.0.0.1", "SERVER_NAME": "127.0.0.1", "SERVER_PORT": "8765"}
    seen = {}
    body = b"".join(app(environ, lambda status, headers: seen.setdefault("status", status)))
    return seen["status"], body


class Routes(unittest.TestCase):
    def test_pilot_is_off_unless_enabled(self):
        app = demo.DemoApp()
        self.assertTrue(call(app, "GET", "/pilot")[0].startswith("404"))
        self.assertTrue(call(app, "GET", "/api/pilot/tasks")[0].startswith("404"))
        with mock.patch.dict(os.environ, {"FINBOT_DEMO_PILOT": "1"}):
            self.assertTrue(call(app, "GET", "/pilot")[0].startswith("200"))

    def test_inspector_accepts_live_flag_and_rejects_bad_values(self):
        app = demo.DemoApp()
        status, body = call(app, "POST", "/api/run", {"question": "Why was txn_A1B2C3D4 declined?", "live": True})
        self.assertTrue(status.startswith("200"))
        self.assertEqual(json.loads(body)["writer_source"], "scripted")   # server not in live mode
        self.assertTrue(call(app, "POST", "/api/run", {"question": "x", "live": "yes"})[0].startswith("400"))
        scenarios = json.loads(call(app, "GET", "/api/scenarios")[1])
        self.assertIsNone(scenarios["live_writer"])


if __name__ == "__main__":
    unittest.main()
