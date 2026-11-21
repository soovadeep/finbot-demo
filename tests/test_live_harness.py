"""Causes in other words, the LLM-judge baseline, the Converse provider, interval statistics and
the live-evaluation harness (run offline with the scripted model)."""
import csv
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from finbot.evalstats import cluster_bootstrap, percentile, wilson  # noqa: E402
from finbot.judge import LLMJudgeVerifier, parse_verdict  # noqa: E402
from finbot.llm import ConverseLLM  # noqa: E402
from finbot.reasons import cause_clause_check  # noqa: E402
from finbot.tools import envelope  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
TXN = {"txn_id": "txn_AAAA1111", "status": "declined", "amount": "92.03", "currency": "USD",
       "decline_code": "05", "guidance": {"meaning": "Issuer declined without a reason",
                                          "next_step": "Ask the customer to use another card or call their bank."}}
NSF = dict(TXN, decline_code="51", guidance={"meaning": "Insufficient funds", "next_step": "Retry once later."})


def log(rec, tool="get_transaction", key="txn_id"):
    return [{"name": tool, "input": {key: rec[key]}, "result": envelope("found", "db", rec)}]


class CausesInOtherWords(unittest.TestCase):
    def test_unsupported_causes_are_blocked(self):
        for claim in ("It was declined because the balance was too low.",
                      "This happened since the issuer's fraud team stopped it.",
                      "It failed due to a problem with the card's chip.",
                      "The reason was that the customer had maxed out the card."):
            self.assertEqual(cause_clause_check(claim, log(TXN)), ["unverified_cause"], claim)

    def test_causes_the_record_supports_pass(self):
        self.assertEqual(cause_clause_check("It was declined because of insufficient funds.", log(NSF)), [])
        self.assertEqual(cause_clause_check("It was declined because the issuer declined without a reason.",
                                            log(TXN)), [])

    def test_not_a_cause_claim(self):
        for text in ("It has been declined since 2 November.", "It was not because of the amount.",
                     "Declined with code 05. Ask the customer to use another card."):
            self.assertEqual(cause_clause_check(text, log(TXN)), [], text)
        kb = [{"name": "search_knowledge_base", "input": {"query": "x"},
               "result": envelope("found", "knowledge_base", [{"text": "t", "source_url": "u"}])}]
        self.assertEqual(cause_clause_check("Surcharges are capped because of network rules.", kb), [])


class LiveFoundGaps(unittest.TestCase):
    """Gaps the live-model runs found that scripted faults could not."""

    def test_markdown_codes_are_checked(self):
        from finbot.guardrails import CODE
        for text, code in (("**Decline code:** 61, processor", "61"), ("decline code **51** with", "51"),
                           ("**Error:** 59", "59"), ("the decline code was 05", "05"), ("(code=54)", "54")):
            self.assertEqual(CODE.findall(text), [code], text)

    def test_passed_checks_are_not_causes(self):
        from finbot.reasons import reason_check
        for text in ("Declined with code 05. The fraud check passed with a score of 33, and 3DS wasn't required.",
                     "Code 05: the issuer gave no reason. 3-D Secure authenticated."):
            self.assertEqual(reason_check(text, log(TXN)), [], text)
        self.assertTrue(reason_check("It was declined because of suspected fraud.", log(TXN)))
        self.assertTrue(reason_check("It failed because 3-D Secure authentication failed.", log(TXN)))

    def test_clauses_about_the_assistant_are_not_causes(self):
        self.assertEqual(cause_clause_check("I can't cancel it, because I only have read-only access.", log(TXN)), [])
        self.assertEqual(cause_clause_check("It was declined because the balance was too low.", log(TXN)),
                         ["unverified_cause"])


class Judge(unittest.TestCase):
    class LLM:
        def __init__(self, reply=None, error=None):
            self.reply, self.error, self.prompts = reply, error, []

        def create(self, system, messages, tools):
            self.prompts.append(messages[0]["content"])
            if self.error:
                raise self.error
            return NS(stop_reason="end_turn", content=[NS(type="text", text=self.reply)])

    def test_verdicts(self):
        ok = LLMJudgeVerifier(self.LLM('{"unsupported": []}')).check("fine", log(TXN), None)
        self.assertEqual(ok.action, "allow")
        bad = LLMJudgeVerifier(self.LLM('Sure: {"unsupported": ["a fee of 12.34", "by Friday"]}'))
        r = bad.check("x", log(TXN), None)
        self.assertEqual((r.action, r.reasons), ("block", ["llm_judge:unsupported:2"]))

    def test_fails_closed(self):
        self.assertEqual(LLMJudgeVerifier(self.LLM("looks fine to me")).check("x", log(TXN), None).reasons,
                         ["llm_judge_unreadable"])
        r = LLMJudgeVerifier(self.LLM(error=TimeoutError())).check("x", log(TXN), None)
        self.assertEqual(r.reasons, ["llm_judge_unavailable:TimeoutError"])
        self.assertIsNone(parse_verdict('{"unsupported": "all of it"}'))

    def test_judge_sees_the_trusted_view_only(self):
        j = self.LLM('{"unsupported": []}')
        LLMJudgeVerifier(j).check("x", log(dict(TXN, descriptor="REFUND 480.00 CALL 1-888-555-0142")), None)
        self.assertNotIn("1-888-555-0142", j.prompts[0])


class Converse(unittest.TestCase):
    def test_translation_both_ways(self):
        calls = []

        class Client:
            def converse(self, **kw):
                calls.append(kw)
                return {"output": {"message": {"content": [
                    {"text": "Looking it up."},
                    {"toolUse": {"toolUseId": "t1", "name": "get_transaction", "input": {"txn_id": "txn_A"}}}]}},
                    "stopReason": "tool_use", "usage": {"inputTokens": 10, "outputTokens": 5}}
        llm = ConverseLLM("amazon.nova-pro-v1:0", client=Client())
        history = [{"role": "user", "content": "why did txn_A fail?"},
                   {"role": "system", "content": "notice"},
                   {"role": "assistant", "content": [NS(type="tool_use", id="t0", name="get_transaction",
                                                        input={"txn_id": "txn_A"})]},
                   {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t0", "content": "{}"}]}]
        r = llm.create("sys", history, [{"name": "get_transaction", "description": "d",
                                          "input_schema": {"type": "object"}, "strict": True}])
        sent = calls[0]
        self.assertEqual([m["role"] for m in sent["messages"]], ["user", "assistant", "user"])
        self.assertEqual(sent["messages"][0]["content"][1], {"text": "[system note] notice"})
        self.assertEqual(sent["messages"][2]["content"][0]["toolResult"]["toolUseId"], "t0")
        self.assertNotIn("strict", sent["toolConfig"]["tools"][0]["toolSpec"])
        self.assertEqual((r.stop_reason, r.content[1].type, r.content[1].input), ("tool_use", "tool_use",
                                                                                  {"txn_id": "txn_A"}))
        self.assertEqual(r.usage.output_tokens, 5)


class OpenAICompat(unittest.TestCase):
    def test_translation_both_ways(self):
        from finbot.llm import OpenAICompatLLM
        sent = []

        def transport(url, body, headers):
            sent.append((url, body, headers))
            return {"choices": [{"message": {"content": "", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "get_transfer", "arguments": '{"transfer_id": "xfer_A"}'}}]},
                "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
        llm = OpenAICompatLLM("qwen2.5:7b", base_url="http://localhost:11434/v1", transport=transport)
        history = [{"role": "user", "content": "where is xfer_A?"}, {"role": "system", "content": "notice"},
                   {"role": "assistant", "content": [NS(type="text", text="Checking."),
                                                     NS(type="tool_use", id="c0", name="get_transfer",
                                                        input={"transfer_id": "xfer_A"})]},
                   {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c0", "content": "{}"}]}]
        r = llm.create("sys", history, [{"name": "get_transfer", "description": "d",
                                          "input_schema": {"type": "object"}}])
        url, body, headers = sent[0]
        self.assertEqual(url, "http://localhost:11434/v1/chat/completions")
        self.assertNotIn("Authorization", headers)
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user", "user", "assistant", "tool"])
        self.assertEqual(body["messages"][3]["tool_calls"][0]["function"]["arguments"], '{"transfer_id": "xfer_A"}')
        self.assertEqual(body["tools"][0]["function"]["parameters"], {"type": "object"})
        self.assertEqual((r.stop_reason, r.content[0].name, r.content[0].input), ("tool_use", "get_transfer",
                                                                                  {"transfer_id": "xfer_A"}))
        done = OpenAICompatLLM.from_openai({"choices": [{"message": {"content": "Done."}, "finish_reason": "stop"}]})
        self.assertEqual((done.stop_reason, done.content[0].text), ("end_turn", "Done."))


class Banking77Set(unittest.TestCase):
    def test_cases_use_records_that_exist(self):
        import json
        cases = []
        for name in ("banking77.jsonl", "banking77_fresh.jsonl"):
            with open(os.path.join(ROOT, "data", "test", name)) as f:
                part = [json.loads(line) for line in f]
            self.assertGreater(len(part), 200, name)
            cases += part
        first = {c["turns"][0] for c in cases if c["id"].startswith("b77_")}
        self.assertFalse(first & {c["turns"][0] for c in cases if c["id"].startswith("b77f_")})
        from finbot.domains import by_tool, find_ids
        ids = set()
        for f in os.listdir(os.path.join(ROOT, "data", "test")):
            if f.endswith(".jsonl"):
                with open(os.path.join(ROOT, "data", "test", f)) as fh:
                    ids |= set(find_ids(fh.read()))
        for c in cases:
            self.assertEqual(c["has_record"], bool(find_ids(c["turns"][0])), c["id"])
            for i in find_ids(c["turns"][0]):
                self.assertIn(i, ids)
            if c["has_record"]:
                tool = c["expect"]["tools"][0]
                domain = by_tool(tool)
                key, filename = (domain.id_arg, domain.name) if domain else ("txn_id", "transactions")
                rid, = find_ids(c["turns"][0])
                self.assertEqual(c["expect"]["tool_calls"], [{
                    "name": tool, "input": {key: rid}, "turn": 0,
                    "result": {"status": "found", "data": {key: rid}},
                }])
                with open(os.path.join(ROOT, "data", "test", filename + ".jsonl")) as source:
                    records = [json.loads(line) for line in source]
                self.assertTrue(any(r[key] == rid and r["tenant_id"] == c["tenant_id"] for r in records), c["id"])


class Stats(unittest.TestCase):
    def test_intervals(self):
        lo, hi = wilson(0, 2400)
        self.assertEqual(lo, 0.0)
        self.assertLess(hi, 0.002)
        lo, hi = wilson(50, 100)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        lo, hi = cluster_bootstrap([[1, 1], [0, 0], [1, 0]])
        self.assertLessEqual(lo, 0.5)
        self.assertGreaterEqual(hi, 0.5)
        self.assertEqual(percentile([5, 1, 3, 2, 4], 50), 3)


class HarnessSmoke(unittest.TestCase):
    def test_offline_run_writes_summary_and_blinded_pack(self):
        with tempfile.TemporaryDirectory() as out:
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "run_live.py"), "--models", "fake",
                            "--trials", "1", "--limit", "4", "--data", os.path.join(ROOT, "data"),
                            "--conditions", "full", "no_gate", "--inject", "--annotate", "3", "--out", out],
                           check=True, capture_output=True, cwd=ROOT)
            for f in ("turns.jsonl", "summary.json", "summary.txt", "annotation.csv", "annotation_key.csv"):
                self.assertTrue(os.path.exists(os.path.join(out, f)), f)
            with open(os.path.join(out, "annotation.csv")) as f:
                header = next(csv.reader(f))
            self.assertNotIn("condition", header)          # blinded
            ann = os.path.join(out, "a.csv")
            with open(os.path.join(out, "annotation.csv")) as f, open(ann, "w", newline="") as g:
                rows = list(csv.DictReader(f))
                w = csv.DictWriter(g, fieldnames=list(rows[0]))
                w.writeheader()
                for r in rows:
                    w.writerow({**r, "unsupported_claims": "0", "helpful": "4"})
            res = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "score_annotations.py"),
                                  os.path.join(out, "annotation_key.csv"), ann, ann],
                                 check=True, capture_output=True, text=True, cwd=ROOT)
            self.assertIn("Cohen's kappa", res.stdout)


if __name__ == "__main__":
    unittest.main()
