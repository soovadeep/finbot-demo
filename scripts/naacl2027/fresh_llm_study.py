"""Fresh LLM answers checked three ways: deterministic, LLM evidence review, and both.

    freeze    pin the runtime, this script, the cases, the writer and the checker (before any
              answer exists); refuses to overwrite an existing protocol
    generate  run the deployed post-confirmation path (finbot.demo.run_demo) with the live
              writer and injected faults off. Saves every draft, repair, fallback and final
              answer BEFORE anything is scored. Two end-to-end runs per case: deterministic
              checks only, and deterministic plus the LLM review.
    check     replay the three checker configurations on the identical first drafts
    labels    write a blank label form for every distinct released or first-draft answer
    score     combine checker verdicts with the labels; the checker never supplies a label

Labels come from the authors (author adjudication, not independent review). Unfilled
labels stay null and are reported as unlabelled, never inferred from a gate verdict.

    python scripts/naacl2027/fresh_llm_study.py freeze
    python scripts/naacl2027/fresh_llm_study.py generate     # live writer + checker calls
    python scripts/naacl2027/fresh_llm_study.py check        # checker calls only
    python scripts/naacl2027/fresh_llm_study.py labels
    python scripts/naacl2027/fresh_llm_study.py score
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data/naacl2027/fresh-llm-v1"
OUT = ROOT / "results/naacl2027/fresh-llm-v1"
WRITER = {"provider": "openai", "model": "meta-llama/llama-3.3-70b-instruct", "temperature": 0,
          "max_tokens": 400, "endpoint": "https://openrouter.ai/api/v1"}
CHECKER = {"model": "google/gemini-2.5-flash-lite", "temperature": 0, "max_tokens": 500,
           "endpoint": "https://openrouter.ai/api/v1"}
CONFIGS = ("deterministic", "semantic", "combined")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value) -> str:
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def sources() -> dict:
    paths = sorted(ROOT.glob("finbot/**/*.py")) + [Path(__file__)]
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}


def write_new(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        f.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def read(path: Path):
    return json.loads(path.read_text())


def cases() -> list[dict]:
    return read(DATA / "cases.json")["cases"]


def verify_freeze() -> dict:
    protocol = read(DATA / "protocol.json")
    if protocol["sources"] != sources():
        changed = sorted(k for k in set(protocol["sources"]) | set(sources())
                         if protocol["sources"].get(k) != sources().get(k))
        raise SystemExit("Runtime or study code changed since the freeze: " + ", ".join(changed))
    if protocol["cases_sha256"] != sha((DATA / "cases.json").read_bytes()):
        raise SystemExit("cases.json changed since the freeze.")
    return protocol


def environment(semantic: bool) -> dict:
    env = {"FINBOT_DEMO_WRITER": "live", "FINBOT_LLM_PROVIDER": WRITER["provider"], "FINBOT_MODEL": WRITER["model"],
           "FINBOT_OPENAI_BASE_URL": WRITER["endpoint"], "FINBOT_TEMPERATURE": str(WRITER["temperature"]),
           "FINBOT_DEMO_LIVE_NAME": "Llama 3.3 70B", "FINBOT_DEMO_LIVE_DAILY": "100000",
           "FINBOT_DEMO_LIVE_PER_CLIENT": "100000", "FINBOT_DEMO_SEMANTIC": "llm" if semantic else "off",
           "FINBOT_SEMANTIC_MODEL": CHECKER["model"], "FINBOT_SEMANTIC_BASE_URL": CHECKER["endpoint"]}
    env.setdefault("FINBOT_OPENAI_API_KEY", os.environ.get("FINBOT_OPENAI_API_KEY", "sk-or-proxy"))
    env.setdefault("FINBOT_SEMANTIC_API_KEY", os.environ.get("FINBOT_SEMANTIC_API_KEY", "sk-or-proxy"))
    return env


def freeze(_args) -> None:
    from finbot.semantic_verification import LLM_PROMPT_VERSION, LLM_SYSTEM
    write_new(DATA / "protocol.json", {
        "version": "fresh-llm-v1", "frozen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases_sha256": sha((DATA / "cases.json").read_bytes()), "sources": sources(),
        "writer": WRITER, "checker": {**CHECKER, "prompt_version": LLM_PROMPT_VERSION,
                                       "prompt_sha256": sha(LLM_SYSTEM.encode())},
        "configs": {"deterministic": "production verifier chain incl. question coverage checks",
                    "semantic": "LLM evidence review alone (unavailable counts as a block, reported apart)",
                    "combined": "both; a block from either blocks"},
        "faults": "none", "path": "finbot.demo.run_demo (the conversation's post-confirmation path)",
        "labels": "author adjudication of support and completeness, recorded separately with a rationale; "
                  "never taken from a checker verdict",
        "success": "a released answer that is supported AND complete; an explicit refusal or 'not found' "
                   "counts as complete only when the evidence really lacks the answer"})
    print("frozen", DATA / "protocol.json")


def _run(case: dict, semantic: bool) -> dict:
    from finbot import demo
    old = {k: os.environ.get(k) for k in environment(semantic)}
    os.environ.update(environment(semantic))
    try:
        demo.LIVE_CACHE.clear()   # every run is a new generation, never a replay
        demo.LIVE_BUDGET.__init__()
        started = time.perf_counter()
        result = demo.run_demo(case["question"], "none", records=case["records"], live=True,
                               client=f"study-{case['id']}")
        result["wall_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return result
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def generate(_args) -> None:
    verify_freeze()
    rows = []
    for case in cases():
        row = {"id": case["id"]}
        for name, semantic in (("deterministic", False), ("combined", True)):
            result = _run(case, semantic)
            row[name] = {"writer_source": result.get("writer_source"), "outcome": result["outcome"],
                         "steps": [{k: s[k] for k in ("stage", "attempt", "answer", "action", "reasons", "checks",
                                                      "evidence")} for s in result["steps"]],
                         "final": result["final"], "evidence": result["evidence"],
                         "model_calls": result["metrics"]["model_calls"], "wall_ms": result["wall_ms"]}
            print(case["id"], name, result.get("writer_source"), result["outcome"], flush=True)
        rows.append(row)
    write_new(OUT / "generations.json", {"protocol_sha256": sha((DATA / "protocol.json").read_bytes()),
                                         "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                         "note": "Saved before any scoring. Faults off.", "rows": rows})


def chain_for(config: str, question: str):
    from finbot.comparison import ComparisonCoverageVerifier
    from finbot.policy_documents import PolicyDocumentVerifier
    from finbot.requested_fields import RequestedInformationVerifier
    from finbot.semantic_verification import LLMEvidenceVerifier
    from finbot.verification import VerifierChain
    from scripts.naacl2027.evaluate_support import component_chain
    deterministic = [*component_chain().verifiers[:-1], ComparisonCoverageVerifier(question),
                     RequestedInformationVerifier(question), PolicyDocumentVerifier("extractive", question=question)]
    semantic = [LLMEvidenceVerifier(CHECKER["model"], question, base_url=CHECKER["endpoint"],
                                    api_key=os.environ.get("FINBOT_SEMANTIC_API_KEY", "sk-or-proxy"))]
    return VerifierChain({"deterministic": deterministic, "semantic": semantic,
                          "combined": deterministic + semantic}[config])


def check(_args) -> None:
    verify_freeze()
    generations = read(OUT / "generations.json")
    by_id = {c["id"]: c for c in cases()}
    rows = []
    for row in generations["rows"]:
        draft = next(s for s in row["deterministic"]["steps"] if s["stage"] == "draft") \
            if row["deterministic"]["steps"] else None
        entry = {"id": row["id"], "draft": draft["answer"] if draft else None}
        if draft:
            for config in CONFIGS:
                started = time.perf_counter()
                verdict = chain_for(config, by_id[row["id"]]["question"]).check(draft["answer"], draft["evidence"], None)
                semantic = [c for c in verdict.checks if c.get("kind") == "semantic_review"]
                entry[config] = {"action": verdict.action, "reasons": verdict.reasons,
                                 "semantic": semantic[0] if semantic else None,
                                 "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
        rows.append(entry)
        print(row["id"], *(entry.get(c, {}).get("action") for c in CONFIGS), flush=True)
    write_new(OUT / "component-checks.json", {"generations_sha256": sha((OUT / "generations.json").read_bytes()),
                                              "rows": rows})


def answers_to_label() -> dict[str, dict]:
    """Every distinct first draft and released final answer, keyed by case and text hash."""
    generations = read(OUT / "generations.json")
    items: dict[str, dict] = {}
    for row in generations["rows"]:
        texts = []
        for run in ("deterministic", "combined"):
            steps = row[run]["steps"]
            if steps:
                texts.append(("draft", next(s for s in steps if s["stage"] == "draft")["answer"]))
            if not row[run]["final"]["blocked_by"]:
                texts.append(("released", row[run]["final"]["answer"]))
        for _, text in texts:
            key = f"{row['id']}:{sha(text.encode())[:12]}"
            items.setdefault(key, {"case": row["id"], "answer": text})
    return items


def labels(_args) -> None:
    by_id = {c["id"]: c for c in cases()}
    form = [{"key": key, "case": item["case"], "question": by_id[item["case"]]["question"],
             "records": by_id[item["case"]]["records"], "answer": item["answer"],
             "supported": None, "complete": None, "rationale": "", "labeller": ""}
            for key, item in sorted(answers_to_label().items())]
    write_new(OUT / "label-form.json", {"instructions": "Judge each answer against its records and the policy pages "
                                        "only. supported: every claim agrees with the evidence, in the right role. "
                                        "complete: it gives what was asked that the evidence contains, or says it is "
                                        "not there. Do not look at checker verdicts while labelling.", "items": form})
    print(len(form), "answers to label")


def score(_args) -> None:
    labelled = {i["key"]: i for i in read(OUT / "labels.json")["items"]}
    checks = {r["id"]: r for r in read(OUT / "component-checks.json")["rows"]}
    generations = read(OUT / "generations.json")

    def label(case, text):
        item = labelled.get(f"{case}:{sha(text.encode())[:12]}")
        if not item or item["supported"] is None or item["complete"] is None:
            return None
        return bool(item["supported"]) and bool(item["complete"])

    component = {c: {"bad_drafts": 0, "bad_blocked": 0, "good_drafts": 0, "good_blocked": 0,
                     "unavailable": 0, "unlabelled": 0} for c in CONFIGS}
    for row in checks.values():
        if row["draft"] is None:
            continue
        good = label(row["id"], row["draft"])
        for c in CONFIGS:
            entry = row[c]
            unavailable = any(r.startswith("semantic_unavailable") for r in entry["reasons"])
            component[c]["unavailable"] += unavailable
            if good is None:
                component[c]["unlabelled"] += 1
                continue
            blocked = entry["action"] == "block"
            component[c]["good_drafts" if good else "bad_drafts"] += 1
            component[c]["good_blocked" if good else "bad_blocked"] += blocked
    end_to_end = {}
    for run in ("deterministic", "combined"):
        tally = {"cases": 0, "released_good": 0, "released_bad": 0, "withheld": 0, "unlabelled": 0,
                 "outcomes": {}, "model_calls": 0, "wall_ms": []}
        for row in generations["rows"]:
            r = row[run]
            tally["cases"] += 1
            tally["outcomes"][r["outcome"]] = tally["outcomes"].get(r["outcome"], 0) + 1
            tally["model_calls"] += r["model_calls"]
            tally["wall_ms"].append(r["wall_ms"])
            if r["final"]["blocked_by"]:
                tally["withheld"] += 1
                continue
            good = label(row["id"], r["final"]["answer"])
            tally["unlabelled" if good is None else "released_good" if good else "released_bad"] += 1
        walls = sorted(tally.pop("wall_ms"))
        tally["median_wall_ms"] = walls[len(walls) // 2]
        end_to_end[run] = tally
    usage = [row[c]["semantic"]["usage"] for row in checks.values() if row["draft"] for c in ("semantic",)
             if row[c]["semantic"] and row[c]["semantic"]["usage"]]
    semantic_latency = sorted(row["semantic"]["semantic"]["latency_ms"] for row in checks.values()
                              if row["draft"] and row["semantic"]["semantic"])
    summary = {"component": component, "end_to_end": end_to_end,
               "checker_tokens": {"input": sum(u["input_tokens"] or 0 for u in usage),
                                  "output": sum(u["output_tokens"] or 0 for u in usage), "calls": len(usage)},
               "checker_median_latency_ms": semantic_latency[len(semantic_latency) // 2] if semantic_latency else None,
               "labels": read(OUT / "labels.json").get("provenance")}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("freeze", "generate", "check", "labels", "score"))
    args = parser.parse_args()
    {"freeze": freeze, "generate": generate, "check": check, "labels": labels, "score": score}[args.command](args)
