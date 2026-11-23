"""Three-way draft verification study. No network calls without --live / generate.

development: reuse the 32 inspected pairs, explicitly as development data.
freeze: pin runtime, study code, writer and guardrail configuration before new data.
generate: generate fresh drafts, saving all outputs BEFORE any checker verdict.
evaluate: score independently supplied author labels; never use a verifier as gold.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finbot.comparison import ComparisonCoverageVerifier
from finbot.policy_documents import PolicyDocumentVerifier
from finbot.semantic_verification import BedrockGroundingVerifier, grounding_source, runtime_client
from finbot.verification import VerifierChain
from scripts.naacl2027.evaluate_support import component_chain


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open("x") as f:
        f.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def sources():
    paths = sorted(ROOT.glob("finbot/**/*.py")) + [Path(__file__), ROOT / "scripts/naacl2027/evaluate_support.py"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def verify_plan(plan):
    if plan["sources"] != sources():
        raise ValueError("Runtime/study code changed since freeze. Make a new development plan; do not relabel a tuned run as held out.")


def validate_config(config):
    BedrockGroundingVerifier(config["guardrail_id"], config["version"], config["region"], "")
    if config["tier"] not in ("STANDARD", "CLASSIC"):
        raise ValueError("Specify the actual contextual grounding tier.")
    for key in ("grounding_threshold", "relevance_threshold"):
        if type(config[key]) not in (int, float) or not math.isfinite(config[key]) or not 0 <= config[key] < 1:
            raise ValueError("Thresholds must be finite numbers between 0 and 0.99.")
    if config.get("usd_per_unit") is not None:
        price = config["usd_per_unit"]
        if type(price) not in (int, float) or not math.isfinite(price) or price < 0 or not config.get("pricing_source"):
            raise ValueError("An estimated price needs a nonnegative rate and a pricing source/date.")


def check_remote_config(config):
    """Read-only configuration check before paid ApplyGuardrail calls."""
    validate_config(config)
    import boto3
    response = boto3.client("bedrock", region_name=config["region"]).get_guardrail(
        guardrailIdentifier=config["guardrail_id"], guardrailVersion=config["version"])
    policy = response["contextualGroundingPolicy"]
    thresholds = {f["type"]: f["threshold"] for f in policy["filters"] if f.get("enabled", True)}
    if thresholds != {"GROUNDING": config["grounding_threshold"], "RELEVANCE": config["relevance_threshold"]}:
        raise ValueError("Published guardrail thresholds differ from the frozen plan.")
    if policy.get("tier", {}).get("tierName", "CLASSIC") != config["tier"]:
        raise ValueError("Published guardrail tier differs from the frozen plan.")
    if any(k.endswith("Policy") and k != "contextualGroundingPolicy" and v for k, v in response.items()):
        raise ValueError("Use a dedicated contextual-grounding-only guardrail for an interpretable ablation.")
    return {k: response.get(k) for k in ("guardrailId", "version", "contextualGroundingPolicy", "crossRegionDetails")}


def development_cases():
    rows = []
    for pair in read(ROOT / "data/naacl2027/fresh-wording-v1/cases.json")["draft_pairs"]:
        record = pair["record"]
        evidence = [{"name": "get_transaction", "input": {"txn_id": record["txn_id"]},
                     "result": {"status": "found", "source": "txn_db", "data": record}}]
        questions = {"payment_amount": "What was the payment amount?", "refund_amount": "How much was refunded?",
                     "actual_settlement_date": "When did the payment actually settle?",
                     "expected_settlement_date": "What was the expected settlement date?"}
        for side in ("clean", "corrupted"):
            rows.append({"id": f"{pair['id']}/{side}", "pair_id": pair["id"], "side": side,
                         "family": pair["role"], "question": questions[pair["role"]], "focus": record["txn_id"],
                         "evidence": evidence, "answer": pair[side], "supported": side == "clean",
                         "complete": None, "label_basis": pair["label_basis"]})
    return rows


def outcome(action, reasons, **extra):
    return {"verdict": "reject" if action == "block" else "accept", "reasons": reasons, **extra}


def combined(deterministic, semantic):
    # An unavailable API is not a semantic detection. A deterministic rejection
    # remains a real rejection even when that API is down.
    if semantic["verdict"] == "pending":
        return "pending"
    if deterministic["verdict"] == "reject" or semantic["verdict"] == "reject":
        return "reject"
    return "accept" if semantic["verdict"] == "accept" else semantic["verdict"]


def metrics(rows, method):
    def group(supported):
        items = [r for r in rows if r["supported"] is supported]
        return {"total": len(items), **{v: sum(r["methods"][method]["verdict"] == v for r in items)
                                       for v in ("accept", "reject", "unavailable", "pending")}}
    good, bad = group(True), group(False)
    assessed_bad, assessed_good = bad["accept"] + bad["reject"], good["accept"] + good["reject"]
    pairs = {}
    for row in rows:
        if row.get("pair_id"):
            pairs.setdefault(row["pair_id"], {})[row["side"]] = row["methods"][method]["verdict"]
    eligible = [p for p in pairs.values() if p.get("clean") == "accept" and p.get("corrupted") in ("accept", "reject")]
    return {"supported_drafts": good, "unsupported_drafts": bad,
            "incorrect_detected": bad["reject"], "incorrect_assessed": assessed_bad,
            "incorrect_detection_rate_assessed": bad["reject"] / assessed_bad if assessed_bad else None,
            "correct_rejected": good["reject"], "correct_assessed": assessed_good,
            "false_rejection_rate_assessed": good["reject"] / assessed_good if assessed_good else None,
            "eligible_clean_accepted_pairs": len(eligible),
            "paired_new_rejections": sum(p["corrupted"] == "reject" for p in eligible),
            "remaining_unsupported_ids": [r["id"] for r in rows if r["supported"] is False
                                           and r["methods"][method]["verdict"] == "accept"],
            "accepted_incomplete_ids": [r["id"] for r in rows if r.get("complete") is False
                                        and r["methods"][method]["verdict"] == "accept"]}


def evaluate_cases(cases, *, config=None, client=None):
    base = component_chain()
    rows = []
    for case in cases:
        chain = VerifierChain([*[v for v in base.verifiers if v.name != "policy_documents"],
                               PolicyDocumentVerifier("extractive", question=case["question"]),
                               ComparisonCoverageVerifier(case["question"])])
        started = time.perf_counter()
        deterministic = chain.check(case["answer"], case["evidence"], case.get("focus"))
        elapsed = (time.perf_counter() - started) * 1000
        d = outcome(deterministic.action, deterministic.reasons, latency_ms=elapsed)
        s = {"verdict": "pending", "reasons": [], "latency_ms": None}
        if config is not None:
            checker = BedrockGroundingVerifier(config["guardrail_id"], config["version"], config["region"],
                                               case["question"], client=client)
            result = checker.check(case["answer"], case["evidence"], case.get("focus"))
            detail = result.checks[0]
            s = outcome(result.action, result.reasons, latency_ms=detail["latency_ms"], check=detail)
            if detail["verdict"] == "unavailable":
                s["verdict"] = "unavailable"
            if any(f["threshold"] != config[f"{f['type'].lower()}_threshold"] for f in detail["filters"]):
                s.update(verdict="unavailable", reasons=["semantic_unavailable:threshold_drift"])
        # One identical API assessment reused in both arms: no extra paid call.
        hybrid = {"verdict": combined(d, s), "reasons": d["reasons"] + s["reasons"],
                  "latency_ms": elapsed + s["latency_ms"] if s["latency_ms"] is not None else None}
        rows.append({**case, "methods": {"deterministic": d, "semantic": s, "combined": hybrid}})
    checks = [r["methods"]["semantic"].get("check") for r in rows]
    checks = [c for c in checks if c is not None]
    units = [(c.get("usage") or {}).get("contextualGroundingPolicyUnits") for c in checks]
    known = [u for u in units if type(u) in (int, float) and math.isfinite(u) and u >= 0]
    all_usage_known = bool(checks) and len(known) == len(checks)
    price = (config or {}).get("usd_per_unit")
    latency = {}
    for method in ("deterministic", "semantic", "combined"):
        values = sorted(r["methods"][method]["latency_ms"] for r in rows
                        if r["methods"][method]["latency_ms"] is not None)
        latency[method] = {"samples": len(values), "median_ms": statistics.median(values) if values else None,
                           "p95_ms": values[math.ceil(.95 * len(values)) - 1] if values else None}
    try:
        sdk_version = importlib.metadata.version("boto3")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = None
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "sources": sources(),
            "environment": {"python": sys.version.split()[0], "boto3": sdk_version},
            "summary": {m: metrics(rows, m) for m in ("deterministic", "semantic", "combined")},
            "latency": latency, "latency_basis": "uncached wall time; combined is the sequential sum, not end-to-end chat latency",
            "cost": {"apply_guardrail_calls": sum(c["provider_called"] for c in checks),
                     "known_contextual_grounding_units": sum(known), "all_usage_known": all_usage_known,
                     "estimated_usd": sum(known) * price if all_usage_known and price is not None else None,
                     "pricing_source": (config or {}).get("pricing_source"),
                     "scope": "one shared semantic assessment per draft; excludes writer generation and hosting"},
            "rows": rows}


WRITER_SYSTEM = ("Answer the payment-support question using only the supplied synthetic evidence. "
                 "Keep payment and refund amounts, and expected and actual settlement dates distinct. "
                 "Preserve policy exceptions, cite supplied policy URLs, and cover requested records. "
                 "State when evidence is missing. Write an ordinary customer-facing answer; do not use tools.")


def generate(plan, prompts, client, *, model_metadata):
    rows = []
    for case in prompts:
        # No old clean/corrupted answers, labels, checker output or feedback enters
        # the writer prompt. Retain refusals/truncations for adjudication too.
        payload = {"question": case["question"], "evidence": json.loads(grounding_source(case["evidence"]))}
        started = time.perf_counter()
        error = None
        try:
            response = client.create(WRITER_SYSTEM, [{"role": "user", "content": json.dumps(payload)}], [])
            answer = "".join(b.text for b in response.content if b.type == "text")
            usage = vars(response.usage) if hasattr(response, "usage") else None
            stop = response.stop_reason
        except Exception as exc:
            answer, usage, stop, error = "", None, "provider_error", type(exc).__name__
        rows.append({**{k: case[k] for k in ("id", "family", "question", "evidence")},
                     "focus": case.get("focus"), "answer": answer, "usage": usage, "stop_reason": stop,
                     "error_type": error, "generation_ms": (time.perf_counter() - started) * 1000})
    return {"plan_sha256": digest(plan), "prompts_sha256": digest(prompts), "writer": model_metadata,
            "writer_prompt_sha256": digest(WRITER_SYSTEM), "status": "awaiting_source_based_author_labels",
            "generated_at": datetime.now(timezone.utc).isoformat(), "rows": rows}


def labelled_cases(generated, labels):
    if labels["drafts_sha256"] != digest(generated):
        raise ValueError("Labels do not match these exact generated drafts.")
    if not labels.get("annotator") or labels.get("basis") != "source_based_author_review":
        raise ValueError("Supply source-based author review; verifier verdicts are not gold labels.")
    index = {r["id"]: r for r in labels["rows"]}
    if len(index) != len(labels["rows"]) or set(index) != {r["id"] for r in generated["rows"]}:
        raise ValueError("Label every generated output, including failures; IDs must match uniquely.")
    rows = []
    for row in generated["rows"]:
        label = index[row["id"]]
        if type(label.get("supported")) is not bool or type(label.get("complete")) is not bool or not label.get("rationale"):
            raise ValueError("Each draft needs supported/complete booleans and a source-based rationale.")
        rows.append({**row, "supported": label["supported"], "complete": label["complete"],
                     "label_basis": label["rationale"]})
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    dev = sub.add_parser("development")
    dev.add_argument("--config", type=Path)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--config", type=Path, required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--plan", type=Path, required=True)
    gen.add_argument("--prompts", type=Path, required=True)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--plan", type=Path, required=True)
    ev.add_argument("--drafts", type=Path, required=True)
    ev.add_argument("--labels", type=Path, required=True)
    for cmd in (dev, freeze, gen, ev):
        cmd.add_argument("--out", type=Path, required=True)
    for cmd in (dev, gen, ev):
        cmd.add_argument("--live", action="store_true", help="Enable real potentially paid provider calls")
        cmd.add_argument("--max-calls", type=int, default=0)
    args = p.parse_args()
    if args.out.exists():
        p.error("Output exists; reports/drafts/plans are immutable. Choose a new path.")
    if args.command == "freeze":
        config = read(args.config)
        validate_config(config)
        writer = config["writer"]
        if writer["provider"] not in ("openai", "converse") or not writer.get("model"):
            p.error("Freeze a real writer provider/model; scripted writers cannot generate fresh LLM data.")
        write_new(args.out, {"created_at": datetime.now(timezone.utc).isoformat(), "config": config,
                            "sources": sources(), "development_data": "fresh-wording-v1 (32 inspected pairs)",
                            "protocol": "finbot-semantic-v1", "writer_system": WRITER_SYSTEM})
        return
    plan = read(args.plan) if hasattr(args, "plan") else None
    if plan:
        verify_plan(plan)
    config = plan["config"] if plan else read(args.config) if args.config else None
    if args.command == "generate":
        prompts = read(args.prompts)
        if not prompts or len({r["id"] for r in prompts}) != len(prompts):
            p.error("Prompts must be nonempty with unique IDs.")
        if not args.live or not 0 < len(prompts) <= args.max_calls:
            p.error("Generation requires --live and --max-calls at least the number of prompts.")
        from finbot.llm import ConverseLLM, OpenAICompatLLM
        writer = config["writer"]
        if writer["provider"] == "openai":
            if not writer.get("base_url"):
                p.error("Freeze the explicit OpenAI-compatible base_url in config.writer.")
            client = OpenAICompatLLM(writer["model"], base_url=writer["base_url"], temperature=0,
                                     timeout_s=60, max_tokens=1024)
        else:
            client = ConverseLLM(writer["model"], client=runtime_client(config["region"]), max_tokens=1024)
        write_new(args.out, generate(plan, prompts, client, model_metadata=writer))
        return
    cases = development_cases() if args.command == "development" else labelled_cases(read(args.drafts), read(args.labels))
    if plan and read(args.drafts)["plan_sha256"] != digest(plan):
        p.error("Generated drafts belong to a different frozen plan.")
    snapshot, client = None, None
    if args.live:
        if config is None or not 0 < len(cases) <= args.max_calls:
            p.error("Live checks need config and --max-calls at least the number of drafts.")
        snapshot = check_remote_config(config)
        client = runtime_client(config["region"])
    report = evaluate_cases(cases, config=config if args.live else None, client=client)
    report.update(evaluation_type="inspected_development_pairs" if args.command == "development" else "author_adjudicated_fresh_llm_drafts",
                  semantic_status="live_calls_attempted" if args.live else "pending_not_run", remote_config=snapshot,
                  dataset_sha256=digest(cases), plan_sha256=digest(plan) if plan else None,
                  limitations=["Semantic-only is a component ablation, never a deployment without access controls.",
                               "Unavailable assessments are not detections; inspect coverage and all denominators.",
                               "New paired rejections do not prove the particular injected error was identified.",
                               "Draft support does not establish completeness or end-to-end customer success.",
                               "Author labels and synthetic data are not independent customer validation."])
    write_new(args.out, report)
    print(json.dumps({"summary": report["summary"], "cost": report["cost"]}, indent=2))


if __name__ == "__main__":
    main()
