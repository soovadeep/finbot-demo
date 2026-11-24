"""Three follow-up studies of clarification, on the eight-record benchmark with mixed personas.

Run from the repository root (after simulate_customers.py, whose reply cache they reuse):
  python scripts/naacl2027/review_studies.py sensitivity --simulator llama
  python scripts/naacl2027/review_studies.py llm_question --simulator llama
  python scripts/naacl2027/review_studies.py free_text --simulator llama
  python scripts/naacl2027/review_studies.py report

sensitivity   decision value with a budget of two, rerun with other assumed reply reliabilities
              (one value for every attribute, from 0.6 to 0.99; and 20 random draws with each
              attribute's reliability between 0.6 and 0.99) and other question costs.
llm_question  a language model (Claude Sonnet 5.5) chooses which question to ask, or to stop, from
              the same questions the selectors choose from; the belief update and the short list
              are unchanged, so only the choice of question differs.
free_text     the simulated customer answers each question in its own words, without options;
              the demo's free-text rules (finbot/clarification_conversation.py) read the reply, and a
              hedged detail counts as weaker evidence (reliability 0.65), as in the demo.

Every study meets the same simulated customers as the main study (same personas, cached replies),
so the customer's replies to a question already asked there are not drawn again.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("sim", ROOT / "scripts/naacl2027/simulate_customers.py")
sim_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim_mod)

from finbot.clarification import UNKNOWN, Candidate, ClarificationSession, ResponseModel  # noqa: E402
from finbot.clarification_conversation import extract_details  # noqa: E402

BENCH = ROOT / "data/naacl2027/ambiguity-8.jsonl"
OUT = ROOT / "results/naacl2027/review-studies"
CHOOSER = "claude-sonnet-5-5"
LEVELS = (0.6, 0.7, 0.8, 0.9, 0.99)
COSTS = (0.0, 0.01, 0.02, 0.05, 0.1)
DRAWS = 20


def candidates_of(episode: dict) -> tuple[Candidate, ...]:
    keys = ("kind", "merchant", "date", "amount")
    return tuple(Candidate(c["record_id"], episode["tenant_id"], {k: c[k] for k in keys})
                 for c in episode["candidates"])


def finish(sim, cache, episode, name, memory, session, extra: dict) -> dict:
    """Short list of the two most likely records, as in the main study."""
    belief = list(session.belief)
    order = sorted(range(len(belief)), key=lambda i: (-belief[i], i))
    target = episode["target_id"]
    shortlist = [episode["candidates"][i] for i in order[:sim_mod.MAX_PROPOSALS]]
    selected = sim_mod.pick_from_list(sim, cache, episode, name, memory, shortlist)
    return {"episode": episode["id"], "persona": name, "questions": len(session.asked),
            "asked": list(session.asked), "map_correct": episode["candidates"][order[0]]["record_id"] == target,
            "selected": selected, "correct": selected == target, "wrong": selected not in (None, target),
            "unresolved": selected is None, **extra}


def run_bayes(sim, cache, episode, models, cost, extra) -> dict:
    name, memory = sim_mod.persona_for(episode, "mixed")
    session = ClarificationSession(candidates_of(episode), episode["tenant_id"], strategy="decision_value",
                                   models=models, max_questions=2, question_cost=cost)
    while (q := session.next_question()) is not None:
        session.reply(q.template, sim_mod.answer_question(sim, cache, episode, name, memory, q))
    return finish(sim, cache, episode, name, memory, session, extra)


# ---------------------------------------------------------------- language model chooses the question

class Chooser:
    def __init__(self):
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("TG_ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=key, base_url="https://api.anthropic.com")
        self.lock = threading.Lock()
        self.calls = self.input_tokens = self.output_tokens = 0

    def choose(self, prompt: str) -> str:
        r = self.client.messages.create(model=CHOOSER, max_tokens=300, thinking={"type": "between_tools"},
                                        messages=[{"role": "user", "content": prompt}])
        with self.lock:
            self.calls += 1
            self.input_tokens += r.usage.input_tokens
            self.output_tokens += r.usage.output_tokens
        return "".join(b.text for b in r.content if b.type == "text")


def chooser_prompt(episode, available, history) -> str:
    rows = "\n".join(f"- {c['kind']} to {c['merchant']} on {c['date']} for {c['amount']} {c['currency']}"
                     for c in episode["candidates"])
    asked = "\n".join(f"- You asked \"{q}\"; the customer answered \"{a}\"." for q, a in history) or "- none yet"
    menu = "\n".join(f"- {q.template}: \"{q.text}\" (options: {', '.join(q.options)})" for q in available)
    return ("You are a bank's support assistant. A customer wrote: \"" + episode["opening"] + "\"\n"
            "Their account holds these payments, and you must find out which one they mean:\n" + rows + "\n\n"
            "Questions so far:\n" + asked + "\n\n"
            "You may ask at most one more question from this list, or stop and show the customer the two "
            "payments you think most likely:\n" + menu + "\n\n"
            "Reply with JSON only, no explanation: {\"ask\": \"<question key>\"} or {\"ask\": \"stop\"}.")


def run_llm_question(sim, cache, chooser_cache, chooser, episode) -> dict:
    name, memory = sim_mod.persona_for(episode, "mixed")
    session = ClarificationSession(candidates_of(episode), episode["tenant_id"], strategy="fixed",
                                   models=sim_mod.ASSUMED, max_questions=2)
    history: list[tuple[str, str]] = []
    from finbot.clarification import questions
    invalid = 0
    while len(session.asked) < 2:
        available = [q for q in questions(session.candidates) if q.template not in session.asked]
        if not available:
            break
        key = (f"choose|{episode['id']}{episode.get('slice', '')}|{name}|{memory.get('slip', '')}|"
               f"{json.dumps(history)}")
        prompt = chooser_prompt(episode, available, history)
        raw = chooser_cache.get_or(key, lambda p=prompt: {"raw": chooser.choose(p)})["raw"]
        pick = str(sim_mod.parse_json(raw).get("ask", "")).strip()
        q = next((x for x in available if x.template == pick), None)
        if q is None:
            invalid += pick != "stop"
            break
        session.pending = q            # the language model's choice replaces the selector's
        session.asked.append(q.template)
        choice = sim_mod.answer_question(sim, cache, episode, name, memory, q)
        session.reply(q.template, choice)
        history.append((q.text, choice))
    return finish(sim, cache, episode, name, memory, session, {"invalid_choice": invalid})


# ---------------------------------------------------------------- free-text replies

def free_reply(sim, cache, episode, name, memory, question) -> str:
    key = f"f|{episode['id']}|{name}|{memory.get('slip', '')}|{question.template}"

    def compute():
        prompt = (f"Your earlier message to the bank: \"{episode['opening']}\"\n"
                  f"Your memory note: {sim_mod.memory_note(name, memory)}\n\n"
                  f"The bank's assistant asks: \"{question.text}\"\n"
                  "Answer in your own words, in one short sentence, as a customer would type it in a chat. "
                  "Reply as {\"reply\": \"<your message>\"}.")
        raw = sim.ask(prompt)
        return {"reply": str(sim_mod.parse_json(raw).get("reply", "")).strip()[:200], "raw": raw[:300]}

    return cache.get_or(key, compute)["reply"]


def run_free_text(sim, cache, episode) -> dict:
    name, memory = sim_mod.persona_for(episode, "mixed")
    cands = candidates_of(episode)
    session = ClarificationSession(cands, episode["tenant_id"], strategy="decision_value",
                                   models=dict(sim_mod.ASSUMED), max_questions=2)
    readings = []
    while (q := session.next_question()) is not None:
        text = free_reply(sim, cache, episode, name, memory, q)
        fields, unknown, _ = extract_details(text, q, cands)
        detail = fields.get(q.template)
        value = detail["value"] if detail and detail["value"] in q.options else UNKNOWN
        base = sim_mod.ASSUMED[q.template]
        if detail and detail["certainty"] == "tentative":
            session.models[q.template] = ResponseModel(.65, base.unknown)
        session.reply(q.template, value)
        session.models[q.template] = base
        # what multiple choice got from the same customer, for comparison
        option = sim_mod.answer_question(sim, cache, episode, name, memory, q)
        readings.append({"template": q.template, "text": text, "read": value,
                         "certainty": detail["certainty"] if detail else None,
                         "parsed_other": bool(detail) and value == UNKNOWN, "option_choice": option})
    return finish(sim, cache, episode, name, memory, session, {"readings": readings})


# ---------------------------------------------------------------- driver

def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    pct = lambda k: round(100 * sum(bool(r[k]) for r in rows) / n, 1)  # noqa: E731
    return {"n": n, "questions": round(sum(r["questions"] for r in rows) / n, 2), "top1": pct("map_correct"),
            "correct": pct("correct"), "wrong": pct("wrong"), "unresolved": pct("unresolved"),
            "correct_ci": [round(100 * x, 1) for x in sim_mod.wilson(sum(r["correct"] for r in rows), n)]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("study", choices=["sensitivity", "llm_question", "free_text", "report"])
    ap.add_argument("--simulator", choices=sorted(sim_mod.SIMULATORS), default="llama")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--bench", default="ambiguity-8", help="benchmark file stem in data/naacl2027/")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.study == "report":
        report = {}
        for path in sorted(OUT.glob("rows-*.jsonl")):
            rows = [json.loads(x) for x in path.read_text().splitlines()]
            groups: dict[str, list] = {}
            for r in rows:
                groups.setdefault(r["setting"], []).append(r)
            report[path.stem.removeprefix("rows-")] = {k: summarize(v) for k, v in groups.items()}
        (OUT / "summary.json").write_text(json.dumps(report, indent=1) + "\n")
        for study, groups in report.items():
            for setting, s in groups.items():
                print(f"{study:24} {setting:22} q={s['questions']:.2f} top1={s['top1']:5} correct={s['correct']:5} "
                      f"wrong={s['wrong']:4} unres={s['unresolved']:5}")
        return
    episodes = [json.loads(x) for x in BENCH.with_name(f"{args.bench}.jsonl").read_text().splitlines()]
    sim = sim_mod.Simulator(args.simulator)
    cache = sim_mod.Cache(sim_mod.OUT / f"cache-{args.simulator}.jsonl")
    jobs = []
    if args.study == "sensitivity":
        for level in LEVELS:
            models = {k: ResponseModel(level, v.unknown) for k, v in sim_mod.ASSUMED.items()}
            jobs += [(e, lambda e, m=models, lv=level: run_bayes(sim, cache, e, m, 0.02,
                                                                 {"setting": f"reliability={lv}"})) for e in episodes]
        # Unequal reliabilities: 20 draws, each attribute's from 0.6 to 0.99, so the order of the
        # attributes' reliabilities changes too (a uniform level only rescales the belief).
        import random
        rng = random.Random(2027)
        for _ in range(DRAWS):
            models = {k: ResponseModel(round(rng.uniform(0.6, 0.99), 2), v.unknown) for k, v in sim_mod.ASSUMED.items()}
            label = "draw=" + ",".join(f"{k}:{m.accuracy}" for k, m in models.items())
            jobs += [(e, lambda e, m=models, lb=label: run_bayes(sim, cache, e, m, 0.02, {"setting": lb}))
                     for e in episodes]
        for cost in COSTS:
            jobs += [(e, lambda e, c=cost: run_bayes(sim, cache, e, sim_mod.ASSUMED, c,
                                                     {"setting": f"cost={c}"})) for e in episodes]
    elif args.study == "llm_question":
        chooser, chooser_cache = Chooser(), sim_mod.Cache(OUT / "cache-chooser.jsonl")
        jobs = [(e, lambda e: {"setting": f"chooser={CHOOSER}",
                               **run_llm_question(sim, cache, chooser_cache, chooser, e)}) for e in episodes]
    else:
        jobs = [(e, lambda e: {"setting": "free_text", **run_free_text(sim, cache, e)}) for e in episodes]
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(lambda j: {"simulator": args.simulator, **j[1](j[0])}, jobs))
    tag = "" if args.bench == "ambiguity-8" else f"-{args.bench}"
    (OUT / f"rows-{args.study}-{args.simulator}{tag}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    usage = {"simulator_calls": sim.calls, "simulator_tokens": [sim.input_tokens, sim.output_tokens]}
    if args.study == "llm_question":
        usage.update(chooser=CHOOSER, chooser_calls=chooser.calls,
                     chooser_tokens=[chooser.input_tokens, chooser.output_tokens])
    usage_path = OUT / "usage.json"
    all_usage = json.loads(usage_path.read_text()) if usage_path.exists() else {}
    all_usage.setdefault(f"{args.study}-{args.simulator}", []).append(usage)
    usage_path.write_text(json.dumps(all_usage, indent=1) + "\n")
    print(f"{len(rows)} runs; usage {usage}")


if __name__ == "__main__":
    main()
