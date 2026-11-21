"""Demo acceptance paths, diagnostic evidence fidelity, and the local HTTP boundary."""
import io
import json
import unittest
from unittest.mock import patch

from finbot.demo import PAIR, SCENARIOS, DemoApp, run_demo
from finbot.verification import HallucinationGate


class DemoScenarios(unittest.TestCase):
    def test_all_presets_reach_the_advertised_outcome(self):
        expected = {"correct": "passed", "repair": "repaired", "fallback": "record_fallback",
                    "timeout": "passed", "pair": "passed", "binding": "repaired", "refusal": "blocked",
                    "policy": "repaired"}
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario["id"]):
                result = run_demo(scenario["question"], scenario["fault"])
                self.assertEqual(result["outcome"], expected[scenario["id"]])
                self.assertEqual(result["mode"], "offline_scripted")
                self.assertTrue(result["synthetic_data"])
                self.assertNotIn("12.34", result["final"]["answer"])

    def test_rejected_draft_is_distinct_from_customer_answer(self):
        result = run_demo("Why was txn_A1B2C3D4 declined?", "status_once")
        self.assertIn("was approved", result["steps"][0]["answer"])
        self.assertIn("status_mismatch:record=declined", result["steps"][0]["reasons"])
        self.assertIn("was declined", result["final"]["answer"])
        self.assertNotIn("was approved", result["final"]["answer"])
        self.assertEqual([s["stage"] for s in result["steps"]], ["draft", "repair"])
        self.assertEqual([i["stage"] for i in result["injections"]], ["draft"])

    def test_failed_repair_uses_verified_record_summary(self):
        result = run_demo("What is the status of txn_A1B2C3D4?", "amount_always")
        self.assertEqual([(s["stage"], s["action"]) for s in result["steps"]],
                         [("draft", "block"), ("repair", "block"), ("fallback", "allow")])
        self.assertEqual(result["final"]["answer"], result["steps"][-1]["answer"])
        self.assertEqual([i["stage"] for i in result["injections"]], ["draft", "repair"])
        self.assertFalse(result["final"]["repaired"])

    def test_unknown_outcome_keeps_status_check_before_retry(self):
        result = run_demo("What happened to txn_TIMEOUT01?")
        answer = result["final"]["answer"]
        self.assertIn("unknown", answer)
        self.assertIn("Do NOT retry yet", answer)
        self.assertNotIn("was approved", answer)
        self.assertNotIn("was declined", answer)

    def test_binding_rejects_amounts_from_the_other_record(self):
        result = run_demo(PAIR, "swap_once")
        self.assertTrue(any(r.startswith("value_from_other_record:amount:")
                            for r in result["steps"][0]["reasons"]))
        answer = result["final"]["answer"]
        self.assertIn("txn_A1B2C3D4 was declined for 129.00 USD", answer)
        self.assertIn("txn_E5F6G7H8 was approved for 54.20 USD", answer)
        self.assertEqual(len(result["steps"][0]["evidence"]), 2)

    def test_policy_refusal_has_no_record_fallback(self):
        result = run_demo("What are the surcharge rules?", "amount_always")
        self.assertEqual(result["final"]["blocked_by"], "evidence_guard")
        self.assertEqual([s["stage"] for s in result["steps"]], ["draft", "repair"])

    def test_policy_repair_retains_the_citation_and_restores_the_rule(self):
        result = run_demo("What are the surcharge rules?", "policy_once")
        self.assertEqual(result["outcome"], "repaired")
        draft, repair = result["steps"]
        self.assertIn("cards can be surcharged", draft["answer"])
        self.assertIn("cards cannot be surcharged", repair["answer"])
        self.assertIn("https://wiki.example.com/surcharge", draft["answer"])
        self.assertTrue(any(c["verdict"] == "unsupported" for c in draft["checks"]))
        self.assertTrue(all(c["verdict"] == "supported" for c in repair["checks"]))
        self.assertEqual(result["schema_version"], 2)

    def test_unapplicable_fault_does_not_claim_an_injection(self):
        result = run_demo("What is the status of txn_A1B2C3D4?", "swap_once")
        self.assertEqual(result["injections"], [])
        self.assertEqual(result["outcome"], "passed")

    def test_cross_tenant_record_is_not_exposed(self):
        result = run_demo("What is the status of txn_OTHER999?")
        self.assertNotIn("9999.00", json.dumps(result))
        self.assertTrue(all(c["result"]["status"] == "not_found" for c in result["evidence"]))

    def test_user_card_data_is_masked_in_export(self):
        result = run_demo("My card is 4111 1111 1111 1111. What is the status of txn_A1B2C3D4?")
        self.assertNotIn("4111 1111 1111 1111", json.dumps(result))

    def test_environment_cannot_switch_the_demo_to_live_adapters(self):
        with patch.dict("os.environ", {"FINBOT_LLM_PROVIDER": "anthropic", "FINBOT_STORE_PROVIDER": "dynamodb",
                                       "FINBOT_GUARDRAIL": "bedrock", "FINBOT_MODEL_CHAIN": "anthropic:unused",
                                       "FINBOT_POLICY_VERIFICATION": "model",
                                       "FINBOT_DATA_DIR": "/no/such/dataset", "FINBOT_REPAIR_ATTEMPTS": "0",
                                       "FINBOT_RECORD_FALLBACK": "0", "FINBOT_TOOL_POLICY": "/no/such/policy"}):
            self.assertEqual(run_demo("What is the status of txn_A1B2C3D4?", "amount_always")["outcome"],
                             "record_fallback")


def evidence(status, amount):
    return [{"name": "get_transaction", "input": {"txn_id": "txn_A1B2C3D4"},
             "result": {"source": "txn_db", "status": "found", "data": {
                 "txn_id": "txn_A1B2C3D4", "status": status, "amount": amount, "currency": "USD"}}}]


class VerificationTrace(unittest.TestCase):
    def test_repair_snapshot_contains_only_the_refetched_evidence(self):
        old, fresh, steps = evidence("declined", "129.00"), evidence("approved", "54.20"), []
        gate = HallucinationGate(observer=steps.append)
        result = gate.run("The transaction was approved for 54.20 USD.", old, lambda: "txn_A1B2C3D4",
                          lambda _: ("The transaction was approved for 54.20 USD.", fresh))
        self.assertTrue(result.repaired)
        self.assertEqual(steps[0].evidence, old)
        self.assertEqual(steps[1].evidence, fresh)
        self.assertEqual(result.tool_log, old + fresh)
        fresh[0]["result"]["data"]["amount"] = "999.00"
        self.assertEqual(steps[1].evidence[0]["result"]["data"]["amount"], "54.20")

    def test_observer_cannot_mutate_gate_result_or_original_evidence(self):
        original = evidence("declined", "129.00")

        def observer(step):
            step.reasons.clear()
            step.evidence[0]["result"]["data"]["status"] = "approved"
            step.answer = "replaced"

        result = HallucinationGate(repair_attempts=0, observer=observer).run(
            "It was approved.", original, lambda: "txn_A1B2C3D4", lambda _: ("unused", []))
        self.assertEqual(result.action, "block")
        self.assertIn("status_mismatch:record=declined", result.reasons)
        self.assertEqual(original[0]["result"]["data"]["status"], "declined")

    def test_rejected_fallback_is_visible_but_never_returned(self):
        steps = []
        result = HallucinationGate(repair_attempts=0, observer=steps.append).run(
            "It was approved.", evidence("declined", "129.00"), lambda: "txn_A1B2C3D4",
            lambda _: ("unused", []), lambda _: "It was approved for 999.00 USD.")
        self.assertEqual([(s.stage, s.action) for s in steps], [("draft", "block"), ("fallback", "block")])
        self.assertEqual(result.action, "block")
        self.assertNotIn("999.00", result.answer)


class DemoHttp(unittest.TestCase):
    def request(self, path="/api/run", method="POST", body=None, **headers):
        raw = json.dumps(body if body is not None else {"question": "What is txn_A1B2C3D4?"}).encode()
        env = {"PATH_INFO": path, "REQUEST_METHOD": method, "HTTP_HOST": "127.0.0.1:8765",
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)),
               "wsgi.input": io.BytesIO(raw), **headers}
        response = []
        data = b"".join(DemoApp()(env, lambda status, hdrs: response.extend([status, dict(hdrs)])))
        return response[0], response[1], data

    def test_http_run_and_static_assets(self):
        status, headers, body = self.request()
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(body)["mode"], "offline_scripted")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        for path in ["/", "/app.js", "/style.css", "/api/scenarios"]:
            with self.subTest(path=path):
                self.assertEqual(self.request(path, "GET")[0], "200 OK")

    def test_cross_origin_and_rebound_hosts_are_rejected(self):
        for headers in [{"HTTP_HOST": "attacker.example:8765"}, {"HTTP_ORIGIN": "https://attacker.example"},
                        {"HTTP_ORIGIN": "null"}]:
            self.assertEqual(self.request(**headers)[0], "403 Forbidden")

    def test_public_host_needs_https_origin_and_sends_hsts(self):
        app = DemoApp(public_host="finbot-demo.example.app")

        def call(**headers):
            raw = b'{"question": "What is txn_A1B2C3D4?"}'
            env = {"PATH_INFO": "/api/run", "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
                   "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw), **headers}
            response = []
            b"".join(app(env, lambda status, hdrs: response.extend([status, dict(hdrs)])))
            return response
        status, headers = call(HTTP_HOST="finbot-demo.example.app", HTTP_ORIGIN="https://finbot-demo.example.app")
        self.assertEqual(status, "200 OK")
        self.assertIn("max-age", headers["Strict-Transport-Security"])
        self.assertEqual(call(HTTP_HOST="finbot-demo.example.app",
                              HTTP_ORIGIN="http://finbot-demo.example.app")[0], "403 Forbidden")
        self.assertEqual(call(HTTP_HOST="other.example.app")[0], "403 Forbidden")
        self.assertEqual(call(HTTP_HOST="127.0.0.1:8765")[0], "200 OK")
        self.assertNotIn("Strict-Transport-Security", self.request()[1])

    def test_root_serves_conversation_and_inspector_moves(self):
        for path, marker in (("/", b"Which payment did you mean?"), ("/study", b"Which payment did you mean?"),
                             ("/inspector", b"evidence inspector")):
            status, headers, data = self.request(path, method="GET")
            self.assertEqual(status, "200 OK", path)
            self.assertIn(marker, data, path)

    def test_several_public_hosts(self):
        app = DemoApp(public_host="a.run.app, b.run.app")
        statuses = []
        for host in ("a.run.app", "b.run.app"):
            b"".join(app({"PATH_INFO": "/", "REQUEST_METHOD": "GET", "HTTP_HOST": host},
                         lambda status, hdrs: statuses.append(status)))
        self.assertEqual(statuses, ["200 OK", "200 OK"])

    def test_excess_concurrent_requests_get_503(self):
        app = DemoApp(max_concurrent=1)
        app.slots.acquire()
        response = []
        b"".join(app({"PATH_INFO": "/", "REQUEST_METHOD": "GET", "HTTP_HOST": "127.0.0.1:8765"},
                     lambda status, hdrs: response.append(status)))
        self.assertEqual(response, ["503 Service Unavailable"])
        app.slots.release()

    def test_invalid_input_and_extra_config_fields(self):
        for body in [{"question": []}, {"question": ""}, {"question": "x" * 2001}, {"question": "hello", "fault": []},
                     {"question": "hello", "fault": "invalid"}, {"question": "hello", "tenant_id": "m_200"},
                     {"question": "hello", "provider": "anthropic"}, ["hello"], 123]:
            with self.subTest(body=str(body)[:100]):
                self.assertEqual(self.request(body=body)[0], "400 Bad Request")

    def test_malformed_json_and_size_limits(self):
        self.assertEqual(self.request(**{"wsgi.input": io.BytesIO(b"{")})[0], "400 Bad Request")
        self.assertEqual(self.request(CONTENT_LENGTH="100000")[0], "413 Content Too Large")
        self.assertEqual(self.request(CONTENT_LENGTH="-1")[0], "413 Content Too Large")
        self.assertEqual(self.request(CONTENT_LENGTH="not-an-integer")[0], "400 Bad Request")
        self.assertEqual(self.request(CONTENT_TYPE="text/plain")[0], "415 Unsupported Media Type")

    def test_static_path_allowlist(self):
        for path in ["/../config.py", "/.env", "/api/run", "/v1/sessions"]:
            self.assertEqual(self.request(path, "GET")[0], "404 Not Found")


if __name__ == "__main__":
    unittest.main()
