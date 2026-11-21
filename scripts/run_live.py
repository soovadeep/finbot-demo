"""Live-model evaluation and baselines. Costs model usage; nothing here runs in CI.

Every condition runs the same labelled cases, tools and data, with a real model writing the
answers, for several trials:

  full             the system as shipped (deterministic gate, one repair, record-built fallback)
  no_gate          the model's answer is shown as written (prompting alone)
  grounding_only   no deterministic gate; Bedrock Guardrails contextual grounding on the output
                   (needs FINBOT_GUARDRAIL_ID / FINBOT_GUARDRAIL_VERSION)
  llm_judge        no deterministic gate; a second model lists unsupported claims (finbot/judge.py)
  gate_plus_judge  the deterministic gate and the judge together
  template_only    no model text: answers built by code from the record, else refused

Per turn it records the model's first draft, whether the deterministic checks would have flagged
it (always computed, in every condition, as a "shadow" verdict), what the user saw, latency,
model calls and tokens. --inject adds the randomized record-derived faults (finbot/faultgen.py)
on top of the live text, with repairs repeating the mistake half the time.

Outputs, in --out:
  turns.jsonl        one row per turn (no PII: the data is synthetic)
  summary.json/.txt  per model x condition: eval pass rate, outcomes, shadow flag rate,
                     leak rate under injection, p50/p95 latency, calls and tokens per turn,
                     each rate with a 95% interval (cluster bootstrap over cases)
  annotation.csv     a blinded sample of shown answers, shuffled across conditions, with the
  annotation_key.csv records each answer rests on; the key maps items back to conditions.
                     Score it with scripts/score_annotations.py.

  # Claude on Bedrock, two models, three trials, test split, with a judge baseline
  FINBOT_LLM_PROVIDER=bedrock python3 scripts/run_live.py --data data/test \\
      --models anthropic.claude-sonnet-5-5 anthropic.claude-haiku-5-5 --trials 3 \\
      --judge-model anthropic.claude-opus-5-5 --out results/live

  # a non-Claude model through the Bedrock Converse API
  FINBOT_LLM_PROVIDER=converse python3 scripts/run_live.py --models amazon.nova-pro-v1:0 ...

  # free: open-weight models in Ollama on this machine, Banking77 wording on the test records
  ollama pull qwen2.5:7b && ollama pull llama3.1:8b
  FINBOT_LLM_PROVIDER=openai FINBOT_TEMPERATURE=0.7 python3 scripts/run_live.py --data data/test \
      --cases data/test/banking77.jsonl --models qwen2.5:7b llama3.1:8b --judge-model qwen2.5:7b \
      --trials 3 --conditions full no_gate llm_judge template_only --out results/live-ollama

  # offline smoke test of the harness itself (scripted model)
  python3 scripts/run_live.py --models fake --trials 1 --conditions full no_gate --out /tmp/live
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import os
import random
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from run_ablation import TemplateGate  # noqa: E402

from finbot.app import build  # noqa: E402
from finbot.config import Settings  # noqa: E402
from finbot.evalkit import load_cases, score  # noqa: E402
from finbot.evalstats import cluster_bootstrap, percentile  # noqa: E402
from finbot.faultgen import RecordFaultLLM  # noqa: E402
from finbot.judge import LLMJudgeVerifier  # noqa: E402
from finbot.llm import make_client  # noqa: E402
from finbot.provenance import trusted_view  # noqa: E402
from finbot.verification import VerifierChain  # noqa: E402

CONDITIONS = ("full", "no_gate", "grounding_only", "llm_judge", "gate_plus_judge", "template_only")


class Recorder:
    """Wraps the model: keeps every final draft of the turn and counts calls and tokens."""

    def __init__(self, base):
        self.base, self.drafts, self.calls, self.tokens = base, [], 0, 0

    def create(self, system, messages, tools):
        resp = self.base.create(system, messages, tools)
        self.calls += 1
        u = getattr(resp, "usage", None)
        self.tokens += int(getattr(u, "input_tokens", 0) or 0) + int(getattr(u, "output_tokens", 0) or 0)
        if resp.stop_reason == "end_turn":
            self.drafts.append("".join(b.text for b in resp.content if getattr(b, "type", "") == "text"))
        return resp


def configure(bot, condition: str, judge) -> None:
    det = bot.gate.chain
    if condition in ("no_gate", "grounding_only"):
        bot.gate.chain = VerifierChain([])
    elif condition == "llm_judge":
        bot.gate.chain = VerifierChain([LLMJudgeVerifier(judge)])
    elif condition == "gate_plus_judge":
        bot.gate.chain = VerifierChain([*det.verifiers, LLMJudgeVerifier(judge)])
    elif condition == "template_only":
        bot.gate = TemplateGate(det)
    bot.shadow_chain = det         # the deterministic checks, run on every draft for the shadow verdict


def outcome(t) -> str:
    if t.blocked_by:
        return "refused"
    if any(str(r).startswith("records_only:") for r in t.reasons):
        return "records_only"
    if t.repaired:
        return "repaired"
    return "answered"


def run(a) -> list[dict]:
    rows = []
    cases = load_cases(a.cases or os.path.join(a.data, "eval.jsonl"))
    if a.limit:
        cases = random.Random(0).sample(cases, min(a.limit, len(cases)))
    for model in a.models:
        base = Settings(data_dir=a.data, kb_path=os.environ.get("FINBOT_KB_PATH", "/nonexistent"),
                        **({"model": model} if model != "fake" else {"llm_provider": "fake"}))
        judge = make_client(base.llm_provider, a.judge_model, base.aws_region) if a.judge_model else None
        for condition in a.conditions:
            if condition in ("llm_judge", "gate_plus_judge") and judge is None:
                print(f"skip {condition}: no --judge-model")
                continue
            s = dataclasses.replace(base, guardrail_provider="bedrock") if condition == "grounding_only" else base
            for trial in range(a.trials):
                for n, case in enumerate(cases):
                    bot = build(s)
                    configure(bot, condition, judge)
                    inner = bot.llm
                    fault = None
                    if a.inject:
                        inner = fault = RecordFaultLLM(inner, seed=trial * 100_003 + n, persist=a.persist)
                    bot.llm = rec = Recorder(inner)
                    cs = bot.new_session(case["tenant_id"], case["groups"], case.get("role", "support"))
                    turns = []
                    for q in case["turns"]:
                        rec.drafts, calls0, tok0 = [], rec.calls, rec.tokens
                        k = len(fault.injections) if fault else 0
                        t0 = time.perf_counter()
                        t = bot.ask(cs, q)
                        ms = (time.perf_counter() - t0) * 1000
                        turns.append(t)
                        draft = rec.drafts[0] if rec.drafts else ""
                        log = [{"name": c["name"], "input": c["input"], "result": c["result"]}
                               for c in t.tools_called] if t.tools_called and "result" in t.tools_called[0] else []
                        shadow = bot.shadow_chain.check(draft, log, cs.memory.focus) if draft and log else None
                        inj = fault.injections[k:] if fault else []
                        rows.append({
                            "model": model, "condition": condition, "trial": trial, "case": case["id"],
                            "category": case.get("category"), "question": q, "draft": draft,
                            "shadow_flagged": bool(shadow and shadow.action == "block"),
                            "shadow_reasons": shadow.reasons if shadow else [],
                            "answer": t.answer, "outcome": outcome(t), "reasons": t.reasons,
                            "injected": [i.marker for i in inj],
                            "leaked": any(i.marker.lower() in t.answer.lower() for i in inj),
                            "latency_ms": round(ms), "model_calls": rec.calls - calls0,
                            "tokens": rec.tokens - tok0,
                            "tool_log": log,           # lets scripts/rescore_live.py re-check drafts offline
                            "records": [trusted_view(c["result"].get("data")) for c in log
                                        if c["result"].get("status") == "found"],
                        })
                    rows[-1]["case_passed"] = not score(case, turns, cs)
                    print(f"{model} {condition} t{trial} {case['id']}: {rows[-1]['outcome']}", flush=True)
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    out = []
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["condition"])].append(r)
    for (model, cond), rs in sorted(groups.items()):
        by_case: dict[str, list[dict]] = defaultdict(list)
        for r in rs:
            by_case[f"{r['case']}#{r['trial']}"].append(r)

        def rate(pred, pool=rs):
            per_case = defaultdict(list)
            for r in pool:
                per_case[r["case"]].append(1.0 if pred(r) else 0.0)
            k = sum(sum(v) for v in per_case.values())
            n = sum(len(v) for v in per_case.values())
            lo, hi = cluster_bootstrap(list(per_case.values()))
            return {"k": int(k), "n": n, "rate": k / n if n else 0.0, "ci95": [lo, hi]}
        last = [v[-1] for v in by_case.values()]
        injected = [r for r in rs if r["injected"]]
        lat = [r["latency_ms"] for r in rs]
        out.append({
            "model": model, "condition": cond, "turns": len(rs),
            "eval_pass": rate(lambda r: r.get("case_passed"), last),
            "answered": rate(lambda r: r["outcome"] in ("answered", "repaired")),
            "records_only": rate(lambda r: r["outcome"] == "records_only"),
            "refused": rate(lambda r: r["outcome"] == "refused"),
            "shadow_flagged_drafts": rate(lambda r: r["shadow_flagged"]),
            "leaked_under_injection": rate(lambda r: r["leaked"], injected) if injected else None,
            "latency_ms_p50": percentile(lat, 50), "latency_ms_p95": percentile(lat, 95),
            "model_calls_per_turn": sum(r["model_calls"] for r in rs) / len(rs),
            "tokens_per_turn": sum(r["tokens"] for r in rs) / len(rs),
        })
    return out


def annotation_pack(rows: list[dict], per_condition: int, out: str, seed: int = 0) -> None:
    """A blinded sample: annotators see the question, the records and one shown answer, never
    which condition produced it. Columns to fill: unsupported_claims (count), helpful (1-5)."""
    rng = random.Random(seed)
    by_cond: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_cond[(r["model"], r["condition"])].append(r)
    items = []
    for key, rs in by_cond.items():
        for r in rng.sample(rs, min(per_condition, len(rs))):
            items.append((key, r))
    rng.shuffle(items)
    with open(os.path.join(out, "annotation.csv"), "w", newline="") as f, \
            open(os.path.join(out, "annotation_key.csv"), "w", newline="") as k:
        w, wk = csv.writer(f), csv.writer(k)
        w.writerow(["item", "question", "records", "answer", "unsupported_claims", "helpful", "notes"])
        wk.writerow(["item", "model", "condition", "trial", "case", "outcome"])
        for i, ((model, cond), r) in enumerate(items):
            w.writerow([i, r["question"], json.dumps(r["records"], default=str), r["answer"], "", "", ""])
            wk.writerow([i, model, cond, r["trial"], r["case"], r["outcome"]])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/test")
    ap.add_argument("--cases", default="", help="case file (default: <data>/eval.jsonl); e.g. "
                    "data/test/banking77.jsonl for real customer wording")
    ap.add_argument("--models", nargs="+", required=True, help="model ids (or 'fake' for a smoke test)")
    ap.add_argument("--conditions", nargs="+", default=list(CONDITIONS), choices=CONDITIONS)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="random sample of N cases (budget)")
    ap.add_argument("--judge-model", default="")
    ap.add_argument("--inject", action="store_true", help="add randomized record-derived faults")
    ap.add_argument("--persist", type=float, default=0.5)
    ap.add_argument("--annotate", type=int, default=50, help="answers per model x condition in the pack")
    ap.add_argument("--out", default="results/live")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = run(a)
    with open(os.path.join(a.out, "turns.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    summary = summarize(rows)
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    lines = [f"{'model':<34} {'condition':<16} {'eval pass':>18} {'answered':>9} {'records':>8} {'refused':>8} "
             f"{'flagged':>8} {'leaked':>8} {'p50 ms':>7} {'p95 ms':>7} {'calls':>6}"]
    for x in summary:
        leak = f"{x['leaked_under_injection']['rate']:.1%}" if x["leaked_under_injection"] else "-"
        ep = x["eval_pass"]
        lines.append(f"{x['model']:<34} {x['condition']:<16} "
                     f"{ep['rate']:>6.1%} [{ep['ci95'][0]:.0%},{ep['ci95'][1]:.0%}] "
                     f"{x['answered']['rate']:>9.1%} {x['records_only']['rate']:>8.1%} {x['refused']['rate']:>8.1%} "
                     f"{x['shadow_flagged_drafts']['rate']:>8.1%} {leak:>8} {x['latency_ms_p50']:>7.0f} "
                     f"{x['latency_ms_p95']:>7.0f} {x['model_calls_per_turn']:>6.2f}")
    text = "\n".join(lines)
    print("\n" + text)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(text + "\n")
    annotation_pack(rows, a.annotate, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
