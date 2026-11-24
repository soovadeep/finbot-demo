"""Contract/flow tests with synthetic AWS responses, not Bedrock accuracy evidence."""
import copy
import json
import unittest
from unittest.mock import patch

from finbot.config import Settings
from finbot.demo import run_demo
from finbot.semantic_verification import BedrockGroundingVerifier, configured_verifier, grounding_source
from scripts.naacl2027.semantic_study import (
    combined, development_cases, digest, evaluate_cases, generate, labelled_cases, metrics,
)


CONFIG = {"guardrail_id": "fixture", "version": "1", "region": "us-east-1", "tier": "STANDARD",
          "grounding_threshold": .7, "relevance_threshold": .7}
EVIDENCE = [{"name": "get_transaction", "input": {"txn_id": "txn_TEST001"},
             "result": {"status": "found", "source": "txn_db", "data": {
                 "txn_id": "txn_TEST001", "amount": "200.00", "currency": "USD", "status": "approved",
                 "merchant_name": "UNTRUSTED FACTS"}}}]


def response(score=.9, relevance=.9, detect_only=False):
    filters = [{"type": kind, "score": value, "threshold": .7, "detected": value < .7,
                "action": "BLOCKED" if value < .7 and not detect_only else "NONE"}
               for kind, value in (("GROUNDING", score), ("RELEVANCE", relevance))]
    return {"action": "GUARDRAIL_INTERVENED" if any(f["action"] == "BLOCKED" for f in filters) else "NONE",
            "usage": {"contextualGroundingPolicyUnits": 2},
            "assessments": [{"contextualGroundingPolicy": {"filters": filters}}]}


class Stub:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def apply_guardrail(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return copy.deepcopy(result)


class SemanticContract(unittest.TestCase):
    def check(self, stub, *, answer="The payment was approved.", question="What happened?", evidence=None):
        return BedrockGroundingVerifier("fixture", "1", "us-east-1", question, client=stub).check(
            answer, EVIDENCE if evidence is None else evidence, "txn_TEST001")

    def test_disabled_needs_no_credentials_and_draft_version_rejected(self):
        self.assertEqual(configured_verifier(Settings(semantic_verification="off"), "q"), ())
        for version in ("", "DRAFT", "0"):
            with self.assertRaises(ValueError):
                BedrockGroundingVerifier("fixture", version, "us-east-1", "q")

    def test_scoped_evidence_and_qualifiers_and_original_answer(self):
        stub = Stub(response())
        result = self.check(stub)
        self.assertEqual(result.action, "allow")
        self.assertEqual(result.text, "The payment was approved.")
        request = stub.calls[0]
        self.assertEqual(request["outputScope"], "FULL")
        self.assertEqual([c["text"]["qualifiers"] for c in request["content"]],
                         [["grounding_source"], ["query"], ["guard_content"]])
        self.assertNotIn("UNTRUSTED FACTS", json.dumps(request))
        self.assertEqual(result.checks[0]["usage"]["contextualGroundingPolicyUnits"], 2)

    def test_latest_not_found_supersedes_old_found_without_mutating_log(self):
        fresh = copy.deepcopy(EVIDENCE[0])
        fresh["result"] = {"status": "not_found", "data": None}
        log = EVIDENCE + [fresh]
        source = grounding_source(log)
        self.assertNotIn("200.00", source)
        self.assertIn("not_found", source)
        self.assertIn("UNTRUSTED FACTS", json.dumps(EVIDENCE))

    def test_each_threshold_and_detect_only_are_enforced(self):
        for kwargs in ({"score": .3}, {"relevance": .3}, {"score": .3, "detect_only": True}):
            result = self.check(Stub(response(**kwargs)))
            self.assertEqual(result.action, "block")
            self.assertEqual(result.checks[0]["verdict"], "unsupported")
        self.assertEqual(self.check(Stub(response(.7, .7))).action, "allow")

    def test_missing_malformed_mixed_and_inconsistent_assessments_are_unavailable(self):
        bad = [{}, {"action": "NONE", "assessments": []},
               {"action": "NONE", "assessments": [{}]}]
        missing = response()
        missing["assessments"][0]["contextualGroundingPolicy"]["filters"].pop()
        bad.append(missing)
        for value in (float("nan"), float("inf"), True, "0.9", 2):
            invalid = response()
            invalid["assessments"][0]["contextualGroundingPolicy"]["filters"][0]["score"] = value
            bad.append(invalid)
        inconsistent = response()
        inconsistent["action"] = "GUARDRAIL_INTERVENED"
        bad.append(inconsistent)
        mixed = response()
        mixed["assessments"][0]["contentPolicy"] = {"filters": [{"action": "BLOCKED"}]}
        bad.append(mixed)
        for item in bad:
            with self.subTest(item=item):
                result = self.check(Stub(item))
                self.assertEqual(result.action, "block")
                self.assertEqual(result.checks[0]["verdict"], "unavailable")

    def test_outage_does_not_leak_exception_text_or_claim_detection(self):
        result = self.check(Stub(RuntimeError("private request text")))
        self.assertEqual(result.checks[0]["verdict"], "unavailable")
        self.assertNotIn("private request text", str(result))

    def test_oversize_or_missing_inputs_make_no_call_and_are_not_truncated(self):
        for kwargs in ({"question": "q" * 1001}, {"answer": "a" * 5001}, {"evidence": []},
                       {"question": ""}):
            stub = Stub()
            self.assertEqual(self.check(stub, **kwargs).checks[0]["verdict"], "unavailable")
            self.assertEqual(stub.calls, [])

    def test_actual_demo_rechecks_repair_and_fallback_and_renders_diagnostics(self):
        stub = Stub(response(.1), response(.1), response())
        with patch.dict("os.environ", {"FINBOT_DEMO_SEMANTIC": "bedrock",
                         "FINBOT_SEMANTIC_GUARDRAIL_ID": "fixture", "FINBOT_SEMANTIC_GUARDRAIL_VERSION": "1"}), \
                patch("finbot.semantic_verification.runtime_client", return_value=stub):
            result = run_demo("What is the status of txn_A1B2C3D4?")
        self.assertEqual(result["outcome"], "record_fallback")
        self.assertEqual([s["stage"] for s in result["steps"]], ["draft", "repair", "fallback"])
        self.assertEqual(len(stub.calls), 3)
        self.assertTrue(all(any(c["kind"] == "semantic_grounding" for c in s["checks"]) for s in result["steps"]))

    def test_outage_cannot_release_unchecked_fallback(self):
        with patch.dict("os.environ", {"FINBOT_DEMO_SEMANTIC": "bedrock",
                         "FINBOT_SEMANTIC_GUARDRAIL_ID": "fixture", "FINBOT_SEMANTIC_GUARDRAIL_VERSION": "1"}), \
                patch("finbot.semantic_verification.runtime_client", return_value=Stub(*[TimeoutError()] * 3)):
            result = run_demo("What is the status of txn_A1B2C3D4?")
        self.assertEqual(result["outcome"], "blocked")
        self.assertTrue(all(s["action"] == "block" for s in result["steps"]))


class SemanticStudy(unittest.TestCase):
    def test_paired_rejections_do_not_count_failed_clean_controls(self):
        rows = [{"id": side, "pair_id": "p", "side": side, "supported": side == "clean",
                 "methods": {"semantic": {"verdict": "reject"}}} for side in ("clean", "corrupted")]
        counts = metrics(rows, "semantic")
        self.assertEqual(counts["incorrect_detected"], 1)
        self.assertEqual(counts["correct_rejected"], 1)
        self.assertEqual(counts["paired_new_rejections"], 0)
        rows[1]["methods"]["semantic"]["verdict"] = "unavailable"
        counts = metrics(rows, "semantic")
        self.assertEqual(counts["incorrect_detected"], 0)
        self.assertIsNone(counts["incorrect_detection_rate_assessed"])

    def test_hybrid_distinguishes_operational_failure_from_deterministic_detection(self):
        self.assertEqual(combined({"verdict": "accept"}, {"verdict": "unavailable"}), "unavailable")
        self.assertEqual(combined({"verdict": "reject"}, {"verdict": "unavailable"}), "reject")

    def test_identical_semantic_call_reused_for_both_arms_and_unknown_cost_stays_unknown(self):
        cases = development_cases()[:2]
        client = Stub(response(), response(.1))
        report = evaluate_cases(cases, config=CONFIG, client=client)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(report["cost"]["known_contextual_grounding_units"], 4)
        self.assertIsNone(report["cost"]["estimated_usd"])
        self.assertEqual(report["summary"]["semantic"]["paired_new_rejections"], 1)
        self.assertEqual(report["summary"]["combined"]["paired_new_rejections"], 1)

    def test_offline_does_not_fabricate_semantic_accuracy_and_reproduces_development_counts(self):
        with patch("finbot.semantic_verification.runtime_client", side_effect=AssertionError("no API")):
            report = evaluate_cases(development_cases())
        self.assertEqual(report["cost"]["apply_guardrail_calls"], 0)
        self.assertEqual(report["summary"]["deterministic"]["incorrect_detected"], 12)
        self.assertEqual(report["summary"]["deterministic"]["correct_rejected"], 0)
        self.assertIsNone(report["summary"]["semantic"]["incorrect_detection_rate_assessed"])
        self.assertIsNone(report["summary"]["combined"]["incorrect_detection_rate_assessed"])
        self.assertEqual(report["summary"]["combined"]["unsupported_drafts"]["pending"], 32)

    def test_generation_keeps_failure_and_requires_separate_matching_labels(self):
        class Writer:
            def create(self, system, messages, tools):
                assert "supported" not in messages[0]["content"]
                raise TimeoutError()
        case = {"id": "new", "family": "refund", "question": "How much?", "evidence": EVIDENCE}
        drafts = generate({"config": CONFIG}, [case], Writer(), model_metadata={"model": "stub"})
        self.assertEqual(len(drafts["rows"]), 1)
        self.assertEqual(drafts["rows"][0]["stop_reason"], "provider_error")
        self.assertNotIn("supported", drafts["rows"][0])
        labels = {"drafts_sha256": digest(drafts), "annotator": "author", "basis": "source_based_author_review",
                  "rows": [{"id": "new", "supported": True, "complete": False, "rationale": "No answer; no false claim."}]}
        self.assertFalse(labelled_cases(drafts, labels)[0]["complete"])
        labels["drafts_sha256"] = "different"
        with self.assertRaises(ValueError):
            labelled_cases(drafts, labels)


if __name__ == "__main__":
    unittest.main()
