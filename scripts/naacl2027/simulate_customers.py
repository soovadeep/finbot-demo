"""Simulated-customer study of Bayesian clarification on the ambiguity benchmark.

Run from the repository root (build the benchmark first with build_ambiguity_set.py):
  python scripts/naacl2027/simulate_customers.py --simulator haiku
  python scripts/naacl2027/simulate_customers.py --simulator llama
  python scripts/naacl2027/simulate_customers.py --report

A language model plays the customer. It knows its own payment only through a persona note
(exact receipt, vague memory, or one detail misremembered) and answers Finbot's multiple-choice
questions and then picks its payment from a short list of the most likely records (or says
none), as in the demo. Finbot never sees the target or the persona. `--confirm sequential`
instead proposes records one at a time for a yes or no.

Every selector meets the same simulated customer: replies are cached per (episode, persona,
question) and per (episode, persona, proposed record), so differences between selectors come
from which questions they ask, not from sampling noise. Cached replies are stored on disk, so an
interrupted run resumes without new calls.

Simulated customers are not people. These results measure the selectors against two model
families' role-play, not human effort or satisfaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finbot.clarification import UNKNOWN, Candidate, ClarificationSession, ResponseModel  # noqa: E402

BENCH = ROOT / "data/naacl2027/ambiguity.jsonl"
OUT = ROOT / "results/naacl2027/clarification-sim"
SIMULATORS = {"haiku": ("anthropic", "claude-haiku-5-5"),
              "llama": ("openrouter", "meta-llama/llama-3.3-70b-instruct")}
SELECTORS = ("none", "fixed", "information_gain", "decision_value")
PERSONAS = (("receipt", 0.40), ("vague", 0.35), ("misremembers", 0.25))
ASSUMED = {"kind": ResponseModel(0.9, 0.1), "merchant": ResponseModel(0.8, 0.2),
           "date": ResponseModel(0.85, 0.15), "amount": ResponseModel(0.8, 0.2)}
# Safety test: the system believes replies are almost always right, which they are not.
OVERCONFIDENT = {k: ResponseModel(0.99, 0.01) for k in ASSUMED}
CONDITIONS = ("mixed", "all_misremember", "overconfident")
MAX_PROPOSALS = 2
SYSTEM = ("You are role-playing a bank customer in a support chat, for a software test. Stay in character. "
          "Use only what your memory note says. If the note does not tell you the answer, say you are not sure. "
          "Never invent certainty you do not have. Reply with JSON only, no other text.")


# ---------------------------------------------------------------- personas


def persona_for(episode: dict, condition: str) -> tuple[str, dict]:
    """Deterministic per episode, so every selector and simulator meets the same customer."""
    rng = random.Random(f"{episode['id']}|persona")
    if condition == "all_misremember":
        name = "misremembers"
    else:
        draw, name = rng.random(), PERSONAS[-1][0]
        for persona, share in PERSONAS:
            if draw < share:
                name = persona
                break
            draw -= share
    target = next(c for c in episode["candidates"] if c["record_id"] == episode["target_id"])
    memory = {k: target[k] for k in ("kind", "merchant", "date", "amount", "currency")}
    if name == "misremembers":
        others = [c for c in episode["candidates"] if c["record_id"] != target["record_id"]]
        keys = [k for k in ("kind", "merchant", "date", "amount") if any(c[k] != target[k] for c in others)]
        if keys:
            key = random.Random(f"{episode['id']}|slip").choice(keys)
            memory[key] = next(c[key] for c in others if c[key] != target[key])
            memory["slip"] = key
    return name, memory


def memory_note(name: str, memory: dict) -> str:
    amount = f"{memory['amount']} {memory['currency']}"
    if name == "vague":
        rough = float(memory["amount"])
        rough = f"roughly {round(rough, -1) if rough >= 20 else round(rough)} {memory['currency']}"
        return (f"You remember it was a {memory['kind'].lower()} to {memory['merchant']}, some time in "
                f"{memory['date'][:7]}, for {rough}. You do not remember the exact day or the exact amount.")
    # A misremembering customer is confident in the wrong detail; that is the point of the persona.
    return (f"You have the details in front of you: a {memory['kind'].lower()} to {memory['merchant']} "
            f"on {memory['date']} for {amount}.")


# ---------------------------------------------------------------- model calls


class Simulator:
    def __init__(self, name: str):
        self.name = name
        self.provider, self.model = SIMULATORS[name]
        self.lock = threading.Lock()
        self.calls = self.input_tokens = self.output_tokens = 0
        if self.provider == "anthropic":
            import anthropic
            key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("TG_ANTHROPIC_API_KEY")
            # The container's ANTHROPIC_BASE_URL points at a session gateway; go to the public API.
            self.client = anthropic.Anthropic(api_key=key, base_url="https://api.anthropic.com")

    def ask(self, prompt: str) -> str:
        for attempt in range(5):
            try:
                if self.provider == "anthropic":
                    r = self.client.messages.create(model=self.model, max_tokens=200, system=SYSTEM,
                                                    thinking={"type": "disabled"},
                                                    messages=[{"role": "user", "content": prompt}])
                    text = "".join(b.text for b in r.content if b.type == "text")
                    used = (r.usage.input_tokens, r.usage.output_tokens)
                else:
                    body = json.dumps({"model": self.model, "temperature": 0, "max_tokens": 80,
                                       "messages": [{"role": "system", "content": SYSTEM},
                                                    {"role": "user", "content": prompt}]}).encode()
                    request = urllib.request.Request(
                        "https://openrouter.ai/api/v1/chat/completions", data=body, method="POST",
                        headers={"Content-Type": "application/json",
                                 "Authorization": "Bearer " + os.environ.get("OPENROUTER_API_KEY", "sk-or-proxy")})
                    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https URL
                        data = json.load(response)
                    text = data["choices"][0]["message"]["content"]
                    usage = data.get("usage") or {}
                    used = (usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
                with self.lock:
                    self.calls += 1
                    self.input_tokens += used[0]
                    self.output_tokens += used[1]
                return text
            except Exception:  # noqa: BLE001 - transient provider errors; retried with backoff
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt + random.random())
        raise RuntimeError("unreachable")


def parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}


class Cache:
    """Append-only JSONL cache of customer replies, keyed by prompt identity."""

    def __init__(self, path: Path):
        self.path, self.lock, self.data, self.inflight = path, threading.Lock(), {}, {}
        if path.exists():
            for line in path.read_text().splitlines():
                row = json.loads(line)
                self.data[row["key"]] = row["value"]

    def get_or(self, key: str, compute):
        """One model call per key, even when several selectors ask the same thing at once."""
        with self.lock:
            if key in self.data:
                return self.data[key]
            key_lock = self.inflight.setdefault(key, threading.Lock())
        with key_lock:
            if key in self.data:
                return self.data[key]
            value = compute()
            with self.lock:
                self.data[key] = value
                with self.path.open("a") as f:
                    f.write(json.dumps({"key": key, "value": value}) + "\n")
        return value


def answer_question(sim, cache, episode, name, memory, question) -> str:
    options = [*question.options, UNKNOWN]
    key = f"q|{episode['id']}|{name}|{memory.get('slip', '')}|{question.template}|{'||'.join(options)}"

    def compute():
        prompt = (f"Your earlier message to the bank: \"{episode['opening']}\"\n"
                  f"Your memory note: {memory_note(name, memory)}\n\n"
                  f"The bank's assistant asks: \"{question.text}\"\n"
                  f"Choose exactly one of these options: {json.dumps(options)}\n"
                  "Reply as {\"choice\": \"<one option, copied exactly>\"}.")
        raw = sim.ask(prompt)
        choice = str(parse_json(raw).get("choice", "")).strip()
        matched = next((o for o in options if o.casefold() == choice.casefold()), UNKNOWN)
        return {"choice": matched, "raw": raw[:200]}

    return cache.get_or(key, compute)["choice"]


def answer_confirmation(sim, cache, episode, name, memory, record: dict) -> str:
    key = f"c|{episode['id']}|{name}|{memory.get('slip', '')}|{record['record_id']}"

    def compute():
        shown = (f"{record['kind']} to {record['merchant']} on {record['date']} for "
                 f"{record['amount']} {record['currency']} ({record['status']})")
        prompt = (f"Your earlier message to the bank: \"{episode['opening']}\"\n"
                  f"Your memory note: {memory_note(name, memory)}\n\n"
                  f"The bank's assistant asks: \"Is this the payment you mean? {shown}\"\n"
                  "Reply as {\"answer\": \"yes\"}, {\"answer\": \"no\"} or {\"answer\": \"not sure\"}.")
        raw = sim.ask(prompt)
        answer = str(parse_json(raw).get("answer", "")).strip().lower()
        return {"answer": answer if answer in {"yes", "no", "not sure"} else "not sure", "raw": raw[:200]}

    return cache.get_or(key, compute)["answer"]


def pick_from_list(sim, cache, episode, name, memory, records: list[dict] | None = None) -> str | None:
    """Show records at once and let the customer choose one or none.

    With every candidate this is the show-the-list baseline; with the top records after the
    questions it is the shortlist confirmation that the demo shows."""
    records = records or episode["candidates"]
    key = f"l|{episode['id']}|{name}|{memory.get('slip', '')}|{'|'.join(r['record_id'] for r in records)}"

    def compute():
        lines = "\n".join(f"{i + 1}. {r['kind']} to {r['merchant']} on {r['date']} for {r['amount']} "
                          f"{r['currency']} ({r['status']})" for i, r in enumerate(records))
        prompt = (f"Your earlier message to the bank: \"{episode['opening']}\"\n"
                  f"Your memory note: {memory_note(name, memory)}\n\n"
                  f"The bank's assistant shows your recent payments and asks which one you mean:\n{lines}\n"
                  "Reply as {\"number\": <the number>} or {\"number\": 0} if none of them or you are not sure.")
        raw = sim.ask(prompt)
        try:
            number = int(parse_json(raw).get("number", 0))
        except (TypeError, ValueError):
            number = 0
        return {"record_id": records[number - 1]["record_id"] if 1 <= number <= len(records) else None,
                "raw": raw[:200]}

    return cache.get_or(key, compute)["record_id"]


# ---------------------------------------------------------------- one episode


def run_episode(sim, cache, episode: dict, selector: str, budget: int, condition: str,
                confirm: str = "shortlist", bench: str = "ambiguity") -> dict:
    name, memory = persona_for(episode, condition)
    target = episode["target_id"]
    if selector == "show_list":
        chosen = pick_from_list(sim, cache, episode, name, memory)
        return {"episode": episode["id"], "selector": selector, "budget": budget, "condition": condition,
                "confirm": confirm, "bench": bench, "persona": name, "candidates": len(episode["candidates"]),
                "questions": 0, "proposals": 0,
                "records_shown": len(episode["candidates"]), "map_correct": None,
                "selected": chosen, "correct": chosen == target, "wrong": chosen not in (None, target),
                "unresolved": chosen is None}
    candidates = tuple(Candidate(c["record_id"], episode["tenant_id"],
                                 {k: c[k] for k in ("kind", "merchant", "date", "amount")})
                       for c in episode["candidates"])
    models = OVERCONFIDENT if condition == "overconfident" else ASSUMED
    session = ClarificationSession(candidates, episode["tenant_id"], strategy=selector, models=models,
                                   max_questions=budget)
    replies = []
    while (question := session.next_question()) is not None:
        choice = answer_question(sim, cache, episode, name, memory, question)
        replies.append({"template": question.template, "choice": choice})
        session.reply(question.template, choice)
    belief = list(session.belief)
    order = sorted(range(len(candidates)), key=lambda i: (-belief[i], i))
    map_correct = candidates[order[0]].record_id == target
    selected, proposals = None, 0
    if confirm == "shortlist":
        # One turn: the most likely records, most likely first, and the customer picks one or none.
        shortlist = [episode["candidates"][i] for i in order[:MAX_PROPOSALS]]
        proposals, selected = len(shortlist), pick_from_list(sim, cache, episode, name, memory, shortlist)
        if selected:
            session.confirm(selected)
    else:
        for index in order[:MAX_PROPOSALS]:
            record = episode["candidates"][index]
            proposals += 1
            if answer_confirmation(sim, cache, episode, name, memory, record) == "yes":
                selected = record["record_id"]
                session.confirm(selected)
                break
    turns = len(session.asked) + (1 if confirm == "shortlist" else proposals)
    return {"episode": episode["id"], "selector": selector, "budget": budget, "condition": condition,
            "confirm": confirm, "bench": bench, "turns": turns, "persona": name, "candidates": len(candidates),
            "questions": len(session.asked),
            "proposals": proposals, "records_shown": proposals, "replies": replies,
            "final_belief_max": max(belief), "map_correct": map_correct, "selected": selected,
            "correct": selected == target, "wrong": selected not in (None, target), "unresolved": selected is None}


# ---------------------------------------------------------------- report


def wilson(k: int, n: int) -> list[float]:
    if not n:
        return [0.0, 0.0]
    z, p = 1.96, k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def summarize(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for r in rows:
        groups[(r.get("bench", "ambiguity"), r.get("confirm", "sequential"), r["simulator"], r["condition"],
                r["budget"], r["selector"])].append(r)
    out = []
    for (bench, confirm, sim, condition, budget, selector), group in sorted(groups.items()):
        n = len(group)
        k = {m: sum(bool(r[m]) for r in group) for m in ("correct", "wrong", "unresolved")}
        maps = [r["map_correct"] for r in group if r["map_correct"] is not None]
        out.append({"bench": bench, "confirm": confirm, "simulator": sim, "condition": condition, "budget": budget,
                    "selector": selector, "episodes": n,
                    "correct_rate": round(k["correct"] / n, 4), "correct_ci95": wilson(k["correct"], n),
                    "wrong_record_rate": round(k["wrong"] / n, 4), "wrong_record_ci95": wilson(k["wrong"], n),
                    "unresolved_rate": round(k["unresolved"] / n, 4),
                    "mean_questions": round(sum(r["questions"] for r in group) / n, 3),
                    "mean_records_shown": round(sum(r["records_shown"] for r in group) / n, 3),
                    "mean_turns": round(sum(1 if r["selector"] == "show_list" else
                                            r.get("turns", r["questions"] + r["proposals"]) for r in group) / n, 3),
                    "top_guess_correct_rate": round(sum(maps) / len(maps), 4) if maps else None,
                    "wrong_if_no_confirmation": round(1 - sum(maps) / len(maps), 4) if maps else None})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator", choices=sorted(SIMULATORS))
    parser.add_argument("--conditions", nargs="+", default=["mixed", "all_misremember"], choices=CONDITIONS)
    parser.add_argument("--bench", default="ambiguity", help="benchmark file stem in data/naacl2027/")
    parser.add_argument("--budgets", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--limit", type=int, help="first N episodes only (smoke test)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--confirm", choices=["shortlist", "sequential"], default="shortlist",
                        help="shortlist: one turn showing the top records (as the demo does); "
                             "sequential: propose records one at a time for a yes or no")
    parser.add_argument("--report", action="store_true", help="summarize every rows-*.jsonl in the output folder")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.report:
        rows = [json.loads(line) for path in sorted(OUT.glob("rows-*.jsonl")) for line in path.read_text().splitlines()]
        sources = ("finbot/clarification.py", "scripts/naacl2027/simulate_customers.py",
                   "scripts/naacl2027/build_ambiguity_set.py", "data/naacl2027/ambiguity.jsonl",
                   "data/naacl2027/ambiguity-8.jsonl")
        usage = {p.stem.removeprefix("usage-"): json.loads(p.read_text()) for p in sorted(OUT.glob("usage-*.json"))}
        report = {"schema_version": 1, "scope": "simulated customers (language models), not human participants",
                  "max_proposals": MAX_PROPOSALS, "assumed_reply_models": {k: vars(v) for k, v in ASSUMED.items()},
                  "overconfident_reply_models": {k: vars(v) for k, v in OVERCONFIDENT.items()},
                  "personas": dict(PERSONAS), "simulators": {k: v[1] for k, v in SIMULATORS.items()},
                  "usage": usage,
                  "source_sha256": {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in sources},
                  "summary": summarize(rows)}
        (OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        for row in report["summary"]:
            print(f"{row['bench'][-12:]:12} {row['confirm'][:5]} {row['simulator']:5} {row['condition']:15} "
                  f"b={row['budget']} {row['selector']:16} "
                  f"correct={row['correct_rate']:.3f} wrong={row['wrong_record_rate']:.3f} "
                  f"unresolved={row['unresolved_rate']:.3f} q={row['mean_questions']:.2f} "
                  f"turns={row['mean_turns']:.2f} top={row['top_guess_correct_rate']}")
        return
    if not args.simulator:
        parser.error("choose --simulator or --report")
    bench_path = BENCH.with_name(f"{args.bench}.jsonl")
    episodes = [json.loads(line) for line in bench_path.read_text().splitlines()][: args.limit]
    sim = Simulator(args.simulator)
    cache = Cache(OUT / f"cache-{args.simulator}.jsonl")
    jobs = [(e, s, b, c) for c in args.conditions for e in episodes for b in args.budgets for s in SELECTORS]
    if args.confirm == "shortlist":  # the baseline does not depend on the confirmation mode
        jobs += [(e, "show_list", 0, c) for c in args.conditions for e in episodes]

    def work(job):
        episode, selector, budget, condition = job
        return {"simulator": args.simulator,
                **run_episode(sim, cache, episode, selector, budget, condition, args.confirm, args.bench)}

    # Workers spread across episodes; the per-key lock in Cache prevents duplicate calls.
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(work, jobs))
    suffix = "" if not args.limit else f"-first{args.limit}"
    mode = ("" if args.bench == "ambiguity" else f"-{args.bench}") + \
        ("" if args.confirm == "shortlist" else "-sequential")
    if args.conditions != ["mixed", "all_misremember"]:
        mode += "-" + "-".join(args.conditions)
    (OUT / f"rows-{args.simulator}{mode}{suffix}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    usage_path = OUT / f"usage-{args.simulator}.json"  # one running total per simulator
    usage = json.loads(usage_path.read_text()) if usage_path.exists() else {
        "model": sim.model, "calls": 0, "input_tokens": 0, "output_tokens": 0}
    for key, value in (("calls", sim.calls), ("input_tokens", sim.input_tokens), ("output_tokens", sim.output_tokens)):
        usage[key] += value  # accumulated across resumed runs
    usage_path.write_text(json.dumps(usage, indent=2) + "\n")
    print(f"{len(rows)} episode runs, {sim.calls} new model calls, "
          f"{sim.input_tokens} input / {sim.output_tokens} output tokens")


if __name__ == "__main__":
    main()
