"""Paired gate study: one shared model draft per case, checked by three gate configurations.

    before        the runtime as frozen for fresh-llm-v1 behaviour: no policy-passage fallback
    after         the current runtime: a failed policy-only answer falls back to the quoted passage
    after_review  the current runtime plus the optional LLM evidence review

Pairing: every HTTP call to the writer or the checker goes through a response cache keyed by
the exact request body. The first configuration to make a request pays for it; any later
configuration making the identical request (the same first draft request, or a repair with
identical feedback) replays that response. So all three configurations judge the same first
draft, and share a repair whenever their feedback is the same. Calls are saved in
responses.json, so the whole study replays offline.

    python scripts/naacl2027/paired_gate_study.py freeze
    python scripts/naacl2027/paired_gate_study.py run          # live writer + checker calls
    python scripts/naacl2027/paired_gate_study.py replay       # offline, from responses.json
    python scripts/naacl2027/paired_gate_study.py labels       # blank form for every distinct answer
    python scripts/naacl2027/paired_gate_study.py score        # needs labels*.json
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fresh_llm_study import CHECKER, WRITER, environment, sha, write_new  # noqa: E402

DATA = ROOT / "data/naacl2027/fresh-llm-v2"
OUT = ROOT / "results/naacl2027/fresh-llm-v2"
CONFIGS = ("before", "after", "after_review")
NONCE = re.compile(r'nonce=\\"[0-9a-f]+\\"|nonce=\"[0-9a-f]+\"')


def read(path: Path):
    return json.loads(path.read_text())


def cases() -> list[dict]:
    return read(DATA / "cases.json")["cases"]


def sources() -> dict:
    paths = sorted(ROOT.glob("finbot/**/*.py")) + [Path(__file__), Path(__file__).parent / "fresh_llm_study.py"]
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}


def freeze(_args) -> None:
    from finbot.semantic_verification import LLM_PROMPT_VERSION, LLM_SYSTEM
    write_new(DATA / "protocol.json", {
        "version": "fresh-llm-v2", "frozen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases_sha256": sha((DATA / "cases.json").read_bytes()), "sources": sources(),
        "writer": WRITER, "checker": {**CHECKER, "prompt_version": LLM_PROMPT_VERSION,
                                       "prompt_sha256": sha(LLM_SYSTEM.encode())},
        "configs": {"before": "deterministic gate without the policy-passage fallback",
                    "after": "deterministic gate with the policy-passage fallback",
                    "after_review": "after, plus the LLM evidence review"},
        "pairing": "request-level response cache shared by all configurations",
        "faults": "none", "path": "finbot.demo.run_demo (post-confirmation path)",
        "success": "a released answer that is supported AND complete; labels never come from a gate verdict"})
    print("frozen", DATA / "protocol.json")


def verify_freeze() -> None:
    protocol = read(DATA / "protocol.json")
    now = sources()
    if protocol["sources"] != now:
        changed = sorted(k for k in set(protocol["sources"]) | set(now) if protocol["sources"].get(k) != now.get(k))
        raise SystemExit("Runtime or study code changed since the freeze: " + ", ".join(changed))
    if protocol["cases_sha256"] != sha((DATA / "cases.json").read_bytes()):
        raise SystemExit("cases.json changed since the freeze.")


class Cache:
    """Request-body-keyed response cache around OpenAICompatLLM._post (writer and checker)."""

    def __init__(self, saved: dict | None = None, offline: bool = False):
        self.responses: dict[str, dict] = dict(saved or {})
        self.offline, self.live_calls, self.replayed = offline, 0, 0

    @staticmethod
    def key(url: str, body: dict) -> str:
        # Tool results are wrapped with a random per-call nonce (an injection defence). It is
        # masked in the key only; the request actually sent keeps it.
        text = json.dumps([url.rsplit("/v1", 1)[-1], body], sort_keys=True, ensure_ascii=False)
        return sha(NONCE.sub("nonce", text).encode())

    @contextlib.contextmanager
    def installed(self):
        from finbot import llm
        original = llm.OpenAICompatLLM._post
        cache = self

        def post(client, url, body, headers):
            k = cache.key(url, body)
            if k in cache.responses:
                cache.replayed += 1
                return json.loads(json.dumps(cache.responses[k]))
            if cache.offline:
                raise OSError(f"offline replay: no saved response for request {k[:12]}")
            response = original(client, url, body, headers)
            cache.responses[k] = response
            cache.live_calls += 1
            return response

        llm.OpenAICompatLLM._post = post
        try:
            yield
        finally:
            llm.OpenAICompatLLM._post = original


@contextlib.contextmanager
def configured(config: str):
    from finbot import demo, orchestrator
    env = environment(config == "after_review")
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    original = orchestrator.policy_passage_answer
    if config == "before":
        orchestrator.policy_passage_answer = lambda _log, _question="": None
    demo.LIVE_CACHE.clear()      # no whole-run replay; pairing is per request (see Cache)
    demo.LIVE_BUDGET.__init__()
    try:
        yield
    finally:
        orchestrator.policy_passage_answer = original
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _one(case: dict, config: str) -> dict:
    from finbot import demo
    with configured(config):
        started = time.perf_counter()
        result = demo.run_demo(case["question"], "none", records=case["records"], live=True,
                               client=f"study-{case['id']}")
    return {"writer_source": result.get("writer_source"), "outcome": result["outcome"],
            "steps": [{k: s[k] for k in ("stage", "attempt", "answer", "action", "reasons", "checks", "evidence")}
                      for s in result["steps"]],
            "final": result["final"], "model_calls": result["metrics"]["model_calls"],
            "wall_ms": round((time.perf_counter() - started) * 1000, 1)}


def _run(offline: bool) -> None:
    verify_freeze()
    saved = read(OUT / "responses.json")["responses"] if offline else None
    cache = Cache(saved, offline=offline)
    rows = []
    with cache.installed():
        for case in cases():
            row = {"id": case["id"]}
            for config in CONFIGS:
                before = (cache.live_calls, cache.replayed)
                row[config] = _one(case, config)
                row[config]["new_calls"] = cache.live_calls - before[0]
                row[config]["replayed_calls"] = cache.replayed - before[1]
                print(case["id"], config, row[config]["writer_source"], row[config]["outcome"],
                      row[config]["new_calls"], row[config]["replayed_calls"], flush=True)
            rows.append(row)
    name = "replay.json" if offline else "runs.json"
    write_new(OUT / name, {"protocol_sha256": sha((DATA / "protocol.json").read_bytes()),
                           "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "note": "Saved before any labelling. Faults off.", "rows": rows})
    if not offline:
        write_new(OUT / "responses.json", {"note": "Raw provider responses keyed by request; enables offline replay.",
                                           "responses": cache.responses})


def run(_args) -> None:
    _run(offline=False)


def replay(_args) -> None:
    _run(offline=True)


def answers() -> dict[str, dict]:
    items: dict[str, dict] = {}
    by_id = {c["id"]: c for c in cases()}
    for row in read(OUT / "runs.json")["rows"]:
        for config in CONFIGS:
            r = row[config]
            texts = [s["answer"] for s in r["steps"] if s["stage"] == "draft"][:1]
            if not r["final"]["blocked_by"]:
                texts.append(r["final"]["answer"])
            for text in texts:
                key = f"{row['id']}:{sha(text.encode())[:12]}"
                items.setdefault(key, {"key": key, "case": row["id"], "question": by_id[row["id"]]["question"],
                                       "answer": text})
    return items


def labels(_args) -> None:
    write_new(OUT / "label-form.json", {"items": sorted(answers().values(), key=lambda x: x["key"])})
    print(len(answers()), "answers to label")


def score(_args) -> None:
    runs = read(OUT / "runs.json")["rows"]
    sets = {p.stem.removeprefix("labels-") or "labels": {i["key"]: bool(i["supported"]) and bool(i["complete"])
                                                       for i in read(p)["items"] if i["supported"] is not None}
            for p in sorted(OUT.glob("labels*.json"))}
    out = {"cases": len(runs), "by_labeller": {}}
    kinds = {c["id"]: c["kind"] for c in cases()}
    for name, lab in sets.items():
        table = {}
        for config in CONFIGS:
            t = {"released_good": 0, "released_bad": 0, "withheld": 0, "withheld_policy": 0,
                 "draft_good": 0, "draft_good_blocked": 0, "draft_bad": 0, "draft_bad_blocked": 0, "unlabelled": 0}
            for row in runs:
                r = row[config]
                draft = next((s for s in r["steps"] if s["stage"] == "draft"), None)
                if draft:
                    g = lab.get(f"{row['id']}:{sha(draft['answer'].encode())[:12]}")
                    if g is not None:
                        t["draft_good" if g else "draft_bad"] += 1
                        t["draft_good_blocked" if g else "draft_bad_blocked"] += draft["action"] == "block"
                if r["final"]["blocked_by"]:
                    t["withheld"] += 1
                    t["withheld_policy"] += kinds[row["id"]] == "policy"
                    continue
                g = lab.get(f"{row['id']}:{sha(r['final']['answer'].encode())[:12]}")
                t["unlabelled" if g is None else "released_good" if g else "released_bad"] += 1
            table[config] = t
        out["by_labeller"][name] = table
    out["outcomes"] = {c: {} for c in CONFIGS}
    for row in runs:
        for c in CONFIGS:
            o = row[c]["outcome"]
            out["outcomes"][c][o] = out["outcomes"][c].get(o, 0) + 1
    out["same_first_draft_all_configs"] = sum(
        len({next((s["answer"] for s in row[c]["steps"] if s["stage"] == "draft"), None) for c in CONFIGS}) == 1
        for row in runs)
    (OUT / "summary.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("freeze", "run", "replay", "labels", "score"))
    args = parser.parse_args()
    {"freeze": freeze, "run": run, "replay": replay, "labels": labels, "score": score}[args.command](args)
