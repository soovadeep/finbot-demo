"""Mocked ApplyGuardrail contracts; no AWS access or cloud configuration."""
import unittest
from unittest.mock import Mock

from finbot.guardrails import BLOCKED_OUTPUT_MSG, BedrockGuardrail


def guard(assessments=None, action="GUARDRAIL_INTERVENED", outputs=None):
    result = BedrockGuardrail.__new__(BedrockGuardrail)
    result.gid, result.version = "test-guard", "1"
    result.client = Mock()
    result.client.apply_guardrail.return_value = {"action": action, "assessments": assessments or [],
                                                 "outputs": outputs or []}
    return result


class BedrockContracts(unittest.TestCase):
    def test_unknown_intervention_is_not_misclassified_as_anonymization(self):
        result = guard(outputs=[{"text": "unsafe replacement"}]).check_output("candidate", "", "query")
        self.assertEqual((result.action, result.text), ("block", BLOCKED_OUTPUT_MSG))
        self.assertIn("bedrock_unhandled_intervention", result.reasons)

    def test_blocked_words_and_regexes_fail_closed_without_logging_match(self):
        for assessment in ({"wordPolicy": {"customWords": [{"match": "private", "action": "BLOCKED"}]}},
                           {"wordPolicy": {"managedWordLists": [{"action": "BLOCKED"}]}},
                           {"sensitiveInformationPolicy": {"regexes": [{"match": "private", "action": "BLOCKED"}]}}):
            with self.subTest(assessment=assessment):
                result = guard([assessment], outputs=[{"text": "replacement"}]).check_output("candidate", "", "q")
                self.assertEqual(result.action, "block")
                self.assertNotIn("private", str(result))

    def test_anonymization_requires_nonempty_replacement_and_no_block(self):
        assessment = {"sensitiveInformationPolicy": {"piiEntities": [{"type": "EMAIL", "action": "ANONYMIZED"}]}}
        self.assertEqual(guard([assessment]).check_output("candidate", "", "q").action, "block")
        result = guard([assessment], outputs=[{"text": "[EMAIL]"}]).check_output("candidate", "", "q")
        self.assertEqual((result.action, result.text), ("masked", "[EMAIL]"))
        blocked = {**assessment, "contentPolicy": {"filters": [{"type": "MISCONDUCT", "action": "BLOCKED"}]}}
        self.assertEqual(guard([blocked], outputs=[{"text": "[EMAIL]"}]).check_output("candidate", "", "q").action,
                         "block")

    def test_nonblocking_detection_does_not_turn_anonymization_into_a_block(self):
        assessment = {"topicPolicy": {"topics": [{"name": "example", "action": "NONE"}]},
                      "sensitiveInformationPolicy": {"piiEntities": [{"type": "EMAIL", "action": "ANONYMIZED"}]}}
        self.assertEqual(guard([assessment], outputs=[{"text": "[EMAIL]"}]).check_output("candidate", "", "q").action,
                         "masked")

    def test_unknown_policy_is_not_hidden_by_an_anonymization(self):
        assessment = {"futurePolicy": {"action": "BLOCKED"}, "sensitiveInformationPolicy": {
            "piiEntities": [{"type": "EMAIL", "action": "ANONYMIZED"}]}}
        result = guard([assessment], outputs=[{"text": "[EMAIL]"}]).check_output("candidate", "", "q")
        self.assertEqual(result.action, "block")
        self.assertIn("bedrock_unknown_policy", result.reasons)

    def test_local_topic_rules_apply_even_if_aws_would_allow(self):
        g = guard(action="NONE")
        self.assertEqual(g.check_input("Which stock should I buy?").action, "block")
        g.client.apply_guardrail.assert_not_called()

    def test_output_qualifiers_and_local_pii_masking_are_preserved(self):
        g = guard(action="NONE")
        result = g.check_output("Card 4111 1111 1111 1111", "trusted source", "question")
        self.assertEqual(result.action, "masked")
        request = g.client.apply_guardrail.call_args.kwargs
        self.assertEqual(request["source"], "OUTPUT")
        self.assertEqual([b["text"]["qualifiers"] for b in request["content"]],
                         [["grounding_source"], ["query"], ["guard_content"]])
        self.assertNotIn("4111 1111 1111 1111", str(request))

    def test_unhandled_automated_reasoning_and_invalid_actions_block(self):
        g = guard([{"automatedReasoningPolicy": {"findings": [{"invalid": {}}]}}], action="NONE")
        self.assertEqual(g.check_output("candidate", "", "q").reasons, ["bedrock_automated_reasoning_not_supported"])
        self.assertEqual(guard(action="unexpected").check_input("hello").action, "block")


if __name__ == "__main__":
    unittest.main()
