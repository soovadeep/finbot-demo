"""Freeze and rehearse paired short/long conversations through Chatbot.ask.

Rehearsal NEVER calls a provider. Live runs require a separately frozen, named
writer and the explicit `live` command. No mode infers semantic labels from gate
verdicts. The supplied cases are development fixtures, not independent test data.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DEFAULT = ROOT / "data/naacl2027/conversation-study-v1"
SETTINGS = dict(llm_provider="fake", semantic_verification="off", policy_verification="extractive",
                record_fallback=True, repair_attempts=1, llm_retry_attempts=1, routing="single",
                model_chain="", domains="payments", cache="none", kb_max_age_days=540,
                context_window_tokens=131072, context_output_reserve_tokens=600,
                context_margin_tokens=1024, max_history_chars=120000, max_turns_per_thread=30,
                max_tool_rounds=6, turn_deadline_s=90)


def plain(obj):
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [plain(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return plain(vars(obj))
    return obj


def digest(obj):
    return hashlib.sha256(json.dumps(plain(obj), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write_new(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(plain(obj), f, indent=2, ensure_ascii=False)
        f.write("\n")


def sources():
    paths = sorted((ROOT / "finbot").rglob("*.py")) + [Path(__file__)]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def normalized(text):
    text = re.sub(r"\btxn_\w+\b", " record ", text.lower())
    text = re.sub(r"\d+(?:\.\d+)?", " number ", text)
    return " ".join(re.findall(r"[a-z]+", text))


def questions(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "question" and isinstance(value, str):
                yield value
            elif key in {"turns", "prefix", "filler"} and isinstance(value, list):
                yield from (v for v in value if isinstance(v, str))
            else:
                yield from questions(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from questions(value)


def prior_questions(exclude):
    exclude = exclude.resolve()
    seen = set()
    for folder in (ROOT / "data/test", ROOT / "data/naacl2027"):
        for path in folder.rglob("*.json*"):
            if path.is_relative_to(exclude):
                continue
            try:
                data = ([json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                        if path.suffix == ".jsonl" else read(path))
                seen.update(normalized(q) for q in questions(data))
            except (ValueError, UnicodeError):
                continue
    return seen


def build_cases():
    a = {"txn_id": "txn_LONG0001", "tenant_id": "m_100", "status": "approved", "amount": "184.60",
         "currency": "USD", "refund": {"status": "succeeded", "amount": "24.60"},
         "settlement": {"status": "pending", "expected_date": "2026-11-26"}}
    b = {**copy.deepcopy(a), "txn_id": "txn_LONG0002", "amount": "97.30",
         "refund": {"status": "succeeded", "amount": "17.30"}}
    prefix = ["Please check the payment txn_LONG0001.", "Please check txn_LONG0002 as well.",
              "Correction: this conversation is about txn_LONG0001. Please check that payment."]
    filler = ["For this payment, could you repeat its current status?",
              "For this payment, which currency does it use?",
              "For this payment, please remind me of its original amount.",
              "For this payment, is its settlement pending or complete?"] * 8
    updates = [
        ("refund_updated", {**copy.deepcopy(a), "refund": {"status": "succeeded", "amount": "39.20"}},
         "How much was refunded on that payment now?", ["39.20"], ["24.60"],
         "State the latest refund, USD 39.20, for txn_LONG0001; do not reuse USD 24.60 or the other record's refund."),
        ("refund_removed", {k: v for k, v in a.items() if k != "refund"},
         "How much was refunded on that payment now?", ["does not show a refund amount"], ["24.60", "17.30"],
         "State that the current record has no refund amount. Absence is not a zero refund."),
        ("settlement_updated", {**copy.deepcopy(a), "settlement": {"status": "settled", "expected_date": "2026-11-26",
                                                                 "actual_date": "2026-11-27"}},
         "When did that payment actually settle?", ["2026-11-27"], [],
         "Give 2026-11-27 as the actual settlement date, distinguishing the earlier expected date."),
        ("corrected_focus", copy.deepcopy(a),
         "How much was refunded on that payment?", ["24.60"], ["17.30"],
         "Use the explicitly corrected focus txn_LONG0001 and its refund USD 24.60, not txn_LONG0002."),
    ]
    cases = []
    for name, updated, question, required, forbidden, rubric in updates:
        cases.append({"id": name, "records": [copy.deepcopy(a), copy.deepcopy(b)], "pages": [],
                      "prefix": prefix, "filler": filler,
                      "probe": {"question": question, "replace_records": [updated],
                                "expected_focus": a["txn_id"], "required_lookups": [a["txn_id"]],
                                "required_strings": required, "forbidden_strings": forbidden, "rubric": rubric}})
    return {"version": "conversation-study-v1", "provenance": {
                "author_role": "developer", "source": "AI-assisted development fixtures in this repository",
                "independent": False},
            "scope": "Paired short/long post-identification conversations; synthetic records. "
                     "Not the ambiguous-record selection UI, independent wording or live-model evidence.",
            "cases": cases}


def validate_cases(bundle, seen=frozenset()):
    provenance = bundle.get("provenance", {})
    if not isinstance(provenance.get("source"), str) or not provenance["source"].strip():
        raise ValueError("Case provenance/source is required")
    external = provenance.get("independent") is True
    if external and provenance.get("author_role") != "external":
        raise ValueError("Developer-authored cases cannot be marked independent")
    if not bundle.get("cases"):
        raise ValueError("No cases supplied")
    ids, probes = set(), set()
    for case in bundle["cases"]:
        if not isinstance(case["id"], str) or case["id"] in ids:
            raise ValueError("Case IDs must be unique strings")
        ids.add(case["id"])
        if not case["prefix"] or not case["filler"] or not all(
                isinstance(t, str) and t.strip() for t in case["prefix"] + case["filler"]):
            raise ValueError("Prefix and filler must contain actual user turns")
        for record in case["records"] + case["probe"]["replace_records"]:
            if record.get("tenant_id") != "m_100" or not re.fullmatch(r"txn_[A-Za-z0-9]{6,}", record.get("txn_id", "")):
                raise ValueError("Study fixtures need synthetic m_100 transaction records")
        probe = case["probe"]
        if not isinstance(probe["question"], str) or not probe["question"].strip() or not probe["rubric"]:
            raise ValueError("A probe question and preregistered answer rubric are required")
        for key in ("required_lookups", "required_strings", "forbidden_strings"):
            if not isinstance(probe[key], list) or not all(isinstance(v, str) for v in probe[key]):
                raise ValueError(f"{key} must be a list of strings")
        q = normalized(probe["question"])
        if external and (q in seen or q in probes):
            raise ValueError("Claimed independent wording overlaps a prior/duplicate normalized probe")
        probes.add(q)


def freeze(folder, writer):
    bundle = read(folder / "cases.json")
    validate_cases(bundle, prior_questions(folder))
    write_new(folder / "protocol.json", {
        "cases_sha256": digest(bundle), "sources": sources(), "settings": SETTINGS,
        "base_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "as_of": "2026-11-24", "writer": writer, "arms": ["short", "long"],
        "design": "Same prefix, final query and final backend snapshot; long adds real intervening turns. "
                  "Fresh session per arm. Alternate arm order by case. No injected model errors.",
        "labels": "Blind judgments of correct record, support and completeness for drafts and final answers. "
                  "Gate acceptance and literal string checks never provide gold labels.",
        "limitations": "Fixtures are development data unless independently supplied with provenance. "
                       "Deduplication is lexical, not proof of independence. This comparison does not "
                       "isolate a causal benefit of rollover versus other context mechanisms."})


def verify(folder):
    protocol, bundle = read(folder / "protocol.json"), read(folder / "cases.json")
    if protocol["sources"] != sources() or protocol["cases_sha256"] != digest(bundle):
        raise ValueError("Runtime or cases changed after freeze; create a new study version")
    return protocol, bundle


class Recorder:
    def __init__(self, client, budget):
        self.client, self.budget = client, budget
        self.max_tokens = getattr(client, "max_tokens", 600)
        self.calls = []

    def create(self, system, messages, tools):
        from finbot.context import estimate_tokens
        from finbot.orchestrator import current_turn
        from finbot.resilience import ServiceUnavailable
        if self.budget["remaining"] <= 0:
            self.budget["exhausted"] = True
            raise ServiceUnavailable("study_model_call_limit")
        self.budget["remaining"] -= 1
        row = {"request_sha256": digest([system, messages, tools]),
               "estimated_input_tokens": estimate_tokens(system, messages, tools),
               "evidence": copy.deepcopy(current_turn().calls if current_turn() else [])}
        self.calls.append(row)
        try:
            response = self.client.create(system, messages, tools)
        except Exception as exc:
            row["error_type"] = type(exc).__name__  # do not persist credentials or provider error bodies
            raise
        row["response"] = plain(response)
        return response


def probe_checks(probe, turn, rows):
    """Mechanical diagnostics only; independent semantic labels remain mandatory."""
    snapshots = {c["input"]["txn_id"]: c["result"].get("data") for c in turn["tools_called"]
                 if c["name"] == "get_transaction" and c["result"].get("status") == "found"}
    text = turn["answer"].lower()
    return {"focused_record_matches": turn["focus"] == probe["expected_focus"],
            "refetched_current_records": all(rid in snapshots and snapshots[rid] ==
                                             {k: v for k, v in rows.get(rid, {}).items() if k != "tenant_id"}
                                             for rid in probe["required_lookups"]),
            "literal_required_strings": all(s.lower() in text for s in probe["required_strings"]),
            "literal_forbidden_strings_absent": all(s.lower() not in text for s in probe["forbidden_strings"]),
            "released": turn["blocked_by"] is None}


def run_arm(case, arm, client, settings, budget, as_of):
    from finbot.config import Settings
    from finbot.guardrails import LocalGuardrail
    from finbot.knowledge import Index
    from finbot.orchestrator import Chatbot
    from finbot.tools import InMemoryLogs, InMemoryTxns, ToolBox
    records = InMemoryTxns(copy.deepcopy(case["records"]))
    kb = Index()
    for page in case.get("pages", []):
        kb.upsert_page(copy.deepcopy(page))
    recorder = Recorder(client, budget)
    bot = Chatbot(recorder, LocalGuardrail(), ToolBox(records, InMemoryLogs([]), kb, domains=["payments"]),
                  Settings(**settings))
    bot.today = lambda: date.fromisoformat(as_of)
    session = bot.new_session("m_100", ["support"], "support")
    prompts = case["prefix"] + (case["filler"] if arm == "long" else []) + [case["probe"]["question"]]
    trace = []
    for i, question in enumerate(prompts):
        if budget["exhausted"]:
            break
        probe = i == len(prompts) - 1
        if probe:
            for record in case["probe"]["replace_records"]:
                records.rows[record["txn_id"]] = copy.deepcopy(record)  # replace, not patch: missing fields matter
        before = session.memory.turns_in_thread
        start = len(recorder.calls)
        turn = plain(bot.ask(session, question))
        after = session.memory.turns_in_thread
        trace.append({"index": i, "probe": probe, "question": question, "turn": turn,
                      "calls": recorder.calls[start:], "thread_turns_before": before, "thread_turns_after": after,
                      "rolled_over": bool(before and after == 1 and turn["blocked_by"] not in {"unavailable", "context_budget"}),
                      "focus": session.memory.focus, "recap": list(session.memory.recap)})
    finished = bool(trace and trace[-1]["probe"] and not budget["exhausted"])
    return {"case": case["id"], "arm": arm, "planned_turns": len(prompts), "completed": finished,
            "trace": trace, "rollovers": sum(t["rolled_over"] for t in trace),
            "probe_rubric": case["probe"]["rubric"], "final_backend": records.rows,
            "diagnostics": probe_checks(case["probe"], trace[-1]["turn"], records.rows) if finished else None}


def review_form(runs):
    items = {}
    for run in runs:
        if not run["completed"]:
            continue
        last = run["trace"][-1]
        candidates = []
        for call in last["calls"]:
            response = call.get("response", {})
            if response.get("stop_reason") == "end_turn":
                answer = "".join(b.get("text", "") for b in response.get("content", []) if b["type"] == "text")
                if answer:
                    candidates.append((answer, call["evidence"]))
        candidates.append((last["turn"]["answer"], last["turn"]["tools_called"]))
        for answer, evidence in candidates:
            item = {"user_turns": [t["question"] for t in run["trace"]],
                    "question": last["question"], "evidence": evidence,
                    "current_backend": run["final_backend"], "rubric": run["probe_rubric"], "answer": answer}
            key = digest(item)
            items[key] = {"key": key, **item, "correct_record": None, "supported": None, "complete": None,
                          "rationale": ""}
    return {"reviewer": "", "reviewer_relationship": "", "items": [items[k] for k in sorted(items)],
            "instructions": "Judge record identity, support and completeness from the user turns and evidence. "
                            "Do not read gate verdicts or report diagnostics. Label honest missing-data answers "
                            "against the rubric; do not count a refusal as a complete answer when facts are available."}


def run_study(folder, output, live=False, max_calls=2000):
    from finbot.llm import FakeLLM, OpenAICompatLLM
    protocol, bundle = verify(folder)
    if output.exists():
        raise ValueError("Output directory already exists; use a new path")
    writer = protocol["writer"]
    if live and (not writer["model"] or not writer["base_url"]):
        raise ValueError("Freeze a named model and endpoint in a new study before live calls")
    if max_calls <= 0:
        raise ValueError("max-calls must be positive")
    output.mkdir(parents=True)
    budget = {"remaining": max_calls, "exhausted": False}
    runs = []
    for i, case in enumerate(bundle["cases"]):
        for arm in (["short", "long"] if i % 2 == 0 else ["long", "short"]):
            if budget["exhausted"]:
                break
            client = (OpenAICompatLLM(writer["model"], writer["base_url"],
                                     api_key=os.environ.get("FINBOT_OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY", ""),
                                     temperature=0, max_tokens=writer["max_tokens"], timeout_s=60)
                      if live else FakeLLM())
            runs.append(run_arm(case, arm, client, protocol["settings"], budget, protocol["as_of"]))
            write_new(output / f"run-{len(runs):03d}.json", runs[-1])  # persist progress after each arm
    calls = [c for r in runs for t in r["trace"] for c in t["calls"]]
    report = {"mode": "live" if live else "offline scripted rehearsal", "protocol_sha256": digest(protocol),
              "provenance": bundle["provenance"], "planned_arms": len(bundle["cases"]) * 2,
              "completed_arms": sum(r["completed"] for r in runs), "model_requests": len(calls),
              "provider_call_attempts": len(calls) if live else 0, "call_limit_exhausted": budget["exhausted"],
              "provider_usage": {key: sum(c.get("response", {}).get("usage", {}).get(key, 0) for c in calls)
                                 for key in ("input_tokens", "output_tokens")},
              "semantic_success_rate": None, "labels": "pending",
              "summary": [{k: r[k] for k in ("case", "arm", "planned_turns", "completed", "rollovers", "diagnostics")}
                          for r in runs]}
    write_new(output / "report.json", report)
    write_new(output / "review-form.json", review_form(runs))
    return report


def score(output, labels):
    expected = read(output / "review-form.json")
    if not labels.get("reviewer", "").strip() or not labels.get("reviewer_relationship", "").strip():
        raise ValueError("Reviewer identity and relationship are required")
    by_key = {i["key"]: i for i in labels["items"]}
    if len(by_key) != len(labels["items"]) or set(by_key) != {i["key"] for i in expected["items"]}:
        raise ValueError("Labels do not match the blind form")
    fields = {"correct_record", "supported", "complete", "rationale"}
    for item in expected["items"]:
        label = by_key[item["key"]]
        if {k: v for k, v in item.items() if k not in fields} != {k: v for k, v in label.items() if k not in fields}:
            raise ValueError("Answer, question or evidence changed during labeling")
        if not all(type(label[k]) is bool for k in fields - {"rationale"}):
            raise ValueError("Blank labels are not accuracy measurements")
    report = read(output / "report.json")
    results = []
    for path in sorted(output.glob("run-*.json")):
        run = read(path)
        if not run["completed"]:
            continue
        last = run["trace"][-1]
        item = {"user_turns": [t["question"] for t in run["trace"]], "question": last["question"],
                "evidence": last["turn"]["tools_called"], "current_backend": run["final_backend"],
                "rubric": run["probe_rubric"], "answer": last["turn"]["answer"]}
        label = by_key[digest(item)]
        success = last["turn"]["blocked_by"] is None and all(label[k] for k in fields - {"rationale"})
        results.append({"case": run["case"], "arm": run["arm"], "success": success})
    return {"mode": report["mode"], "reviewer": labels["reviewer"],
            "reviewer_relationship": labels["reviewer_relationship"], "labels_sha256": digest(labels),
            "results": results, "planned_arms": report["planned_arms"], "scored_arms": len(results),
            "paired_comparison_ready": len(results) == report["planned_arms"],
            "note": "Report all arms, including unfinished ones. Scripted rehearsal is never live LLM accuracy."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("prepare", "freeze", "rehearse", "live", "score"))
    p.add_argument("--study", type=Path, default=DEFAULT)
    p.add_argument("--input", type=Path, help="Independently authored bundle or completed label form")
    p.add_argument("--output", type=Path)
    p.add_argument("--writer-model", default="")
    p.add_argument("--writer-base-url", default="")
    p.add_argument("--max-calls", type=int, default=2000)
    args = p.parse_args()
    if args.command == "prepare":
        bundle = read(args.input) if args.input else build_cases()
        validate_cases(bundle, prior_questions(args.study))
        write_new(args.study / "cases.json", bundle)
    elif args.command == "freeze":
        freeze(args.study, {"model": args.writer_model, "base_url": args.writer_base_url,
                            "max_tokens": 600, "temperature": 0})
    else:
        if not args.output:
            p.error("--output is required")
        if args.command == "score":
            if not args.input:
                p.error("--input is required for completed labels")
            print(json.dumps(score(args.output, read(args.input)), indent=2))
        else:
            print(json.dumps(run_study(args.study, args.output, args.command == "live", args.max_calls), indent=2))


if __name__ == "__main__":
    main()
