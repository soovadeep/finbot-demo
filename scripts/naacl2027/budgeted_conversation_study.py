"""OpenRouter-only live runner with a persisted dollar reservation before every call.

No credentials are embedded or copied from the hosted demo. `prepare` reads only
public pricing. `run` requires a local key and a frozen protocol. Existing offline
study code/results remain unchanged. No automatic retries or provider fallbacks.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finbot.llm import OpenAICompatLLM
from finbot.resilience import ServiceUnavailable
from scripts.naacl2027 import conversation_study as study

MODEL = "meta-llama/llama-3.3-70b-instruct"
BASE = "https://openrouter.ai/api/v1"
ENDPOINT = "deepinfra/turbo"
DEFAULT = ROOT / "data/naacl2027/conversation-live-v1"


def runner_sha():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def local_key(path):
    for name in ("FINBOT_OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        if value := os.environ.get(name, "").strip():
            return value
    if path.is_file():
        # Parse only literal key assignments; never source/execute a credential file.
        for line in path.read_text().splitlines():
            name, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and name.strip() in {"FINBOT_OPENAI_API_KEY", "OPENROUTER_API_KEY"}:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if value and not any(c.isspace() for c in value):
                    return value
    raise ValueError("No local OpenRouter key configured; the hosted demo's secret is not accessible here")


def price(value):
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Invalid numeric pricing or cost") from None
    if not number.is_finite() or number < 0:
        raise ValueError("Pricing and costs must be finite and nonnegative")
    return number


def public_endpoint():
    with urllib.request.urlopen(f"{BASE}/models/{MODEL}/endpoints", timeout=25) as response:
        data = json.load(response)
    matches = [e for e in data["data"]["endpoints"] if e["tag"] == ENDPOINT]
    if len(matches) != 1:
        raise ValueError("Pinned provider endpoint is unavailable")
    endpoint = matches[0]
    if endpoint["context_length"] != study.SETTINGS["context_window_tokens"] or not {
            "tools", "max_tokens", "temperature"} <= set(endpoint["supported_parameters"]):
        raise ValueError("Endpoint capacity/tool support no longer matches the protocol")
    for key, value in endpoint["pricing"].items():
        if key not in {"prompt", "completion", "discount"} and price(value) != 0:
            raise ValueError("Unbudgeted pricing dimension; review before paid calls")
    if price(endpoint["pricing"]["prompt"]) <= 0 or price(endpoint["pricing"]["completion"]) <= 0:
        raise ValueError("Expected paid text-token pricing")
    return endpoint


def prepare(folder):
    endpoint = public_endpoint()  # public metadata only: no model calls or key required
    bundle = study.read(study.DEFAULT / "cases.json")
    bundle["version"] = "conversation-live-v1"
    bundle["scope"] = ("Live follow-up using the existing developer-authored short/long conversations; "
                       "not independently authored or unseen wording. Synthetic records only.")
    study.write_new(folder / "cases.json", bundle)
    study.freeze(folder, {"model": MODEL, "base_url": BASE, "max_tokens": 600, "temperature": 0,
                          "budget_usd": "1.00", "endpoint": endpoint, "runner_sha256": runner_sha(),
                          "pricing_checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


class SpendBudget:
    """One sequential run; a missing/failed response keeps its full reservation.

    Reserve the provider's entire accepted context window, not an estimated prompt
    token count. Reconcile only against valid reported usage.cost. The model is
    text-only; max_price forbids higher rates and per-request charges. This relies
    on OpenRouter honoring its advertised capacity, routing and billing contract.
    A provider-key credit limit remains useful as an independent account control.
    """
    def __init__(self, writer, output, call_budget):
        self.writer, self.output, self.call_budget = writer, output, call_budget
        self.limit = price(writer["budget_usd"])
        if not 0 < self.limit <= Decimal("1.00"):
            raise ValueError("This authorised run must be capped at US$1 or less")
        self.held = Decimal("0")
        self.reported = Decimal("0")
        self.events = []
        self.journal = output / "spend.jsonl"
        self.journal.touch(exist_ok=False)
        self.stopped = None

    def log(self, event):
        self.events.append(event)
        with self.journal.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())  # reservation reaches disk before the paid request

    def stop(self, reason):
        self.stopped = reason
        self.call_budget["exhausted"] = True

    def report(self):
        return {"limit_usd": str(self.limit), "charged_or_reserved_usd": str(self.held),
                "provider_reported_usd": str(self.reported), "stopped": self.stopped,
                "request_attempts": sum(e["event"] == "reserve" for e in self.events),
                "unknown_cost_requests": sum(e["event"] == "unknown_cost" for e in self.events)}

    def send(self, send, url, body, headers):
        if self.stopped:
            raise ServiceUnavailable("study_spending_stopped")
        if url != BASE + "/chat/completions" or body.get("model") != MODEL:
            raise ValueError("The budget authorizes only the frozen OpenRouter model and endpoint")
        if body.get("max_tokens") != self.writer["max_tokens"] or set(body) - {
                "model", "messages", "max_tokens", "temperature", "tools"}:
            raise ValueError("Unbudgeted generation options")
        endpoint = self.writer["endpoint"]
        prompt, completion = (price(endpoint["pricing"][k]) for k in ("prompt", "completion"))
        reserve = endpoint["context_length"] * prompt + body["max_tokens"] * completion
        if self.held + reserve > self.limit:
            self.stop("insufficient_remaining_budget")
            self.log({"event": "stop", **self.report()})
            raise ServiceUnavailable("study_dollar_limit")
        request = copy.deepcopy(body)
        request["provider"] = {"only": [endpoint["tag"]], "order": [endpoint["tag"]],
                               "allow_fallbacks": False, "require_parameters": True,
                               "max_price": {"prompt": float(prompt * 1_000_000),
                                             "completion": float(completion * 1_000_000), "request": 0}}
        self.held += reserve
        index = self.report()["request_attempts"] + 1
        self.log({"event": "reserve", "index": index, "reserved_usd": str(reserve),
                  "held_usd": str(self.held), "request_sha256": study.digest(request)})
        try:
            response = send(url, request, headers)
        except Exception as exc:
            self.stop("provider_error_cost_unknown")
            self.log({"event": "unknown_cost", "index": index, "error_type": type(exc).__name__})
            raise ServiceUnavailable("study_provider_error_cost_reserved") from None
        # Store raw outputs/usage for crash recovery; never store authorization headers.
        study.write_new(self.output / f"response-{index:04d}.json", response)
        try:
            cost = price(response["usage"]["cost"])
            if type(response["usage"]["cost"]) is bool:
                raise ValueError("Invalid cost")
        except (KeyError, TypeError, ValueError):
            self.stop("provider_cost_missing_or_invalid")
            self.log({"event": "unknown_cost", "index": index, "error_type": "CostUnavailable"})
            raise ServiceUnavailable("study_cost_unavailable") from None
        self.reported += cost
        self.held += cost - reserve
        self.log({"event": "reconcile", "index": index, "cost_usd": str(cost),
                  "held_usd": str(self.held), "generation_id": response.get("id")})
        if cost > reserve:
            self.stop("provider_charge_exceeded_reservation")
            raise ServiceUnavailable("study_pricing_contract_changed")
        if response.get("error") or not response.get("choices"):
            self.stop("provider_response_error")
            raise ServiceUnavailable("study_provider_response_error")
        return response


def run(folder, output, key_file):
    protocol, bundle = study.verify(folder)
    writer = protocol["writer"]
    if writer.get("runner_sha256") != runner_sha():
        raise ValueError("Budget runner changed since freeze")
    key = local_key(key_file)  # fail before creating result artifacts or making model calls
    current = public_endpoint()
    if any(price(current["pricing"][k]) > price(writer["endpoint"]["pricing"][k])
           for k in ("prompt", "completion")):
        raise ValueError("Pinned prices increased; freeze a new protocol before paid calls")
    if output.exists():
        raise ValueError("Results exist; do not restart this budget or overwrite earlier expenditure")
    output.mkdir(parents=True)
    calls = {"remaining": 500, "exhausted": False}
    spend = SpendBudget(writer, output, calls)
    runs = []
    try:
        for i, case in enumerate(bundle["cases"]):
            for arm in (["short", "long"] if i % 2 == 0 else ["long", "short"]):
                if calls["exhausted"]:
                    break
                client = OpenAICompatLLM(MODEL, BASE, api_key=key, temperature=0,
                                         max_tokens=writer["max_tokens"], timeout_s=60)
                sender = client._post
                client.transport = lambda url, body, headers: spend.send(sender, url, body, headers)
                result = study.run_arm(case, arm, client, protocol["settings"], calls, protocol["as_of"])
                runs.append(result)
                study.write_new(output / f"run-{len(runs):03d}.json", result)
                print(json.dumps({"case": case["id"], "arm": arm, "completed": result["completed"],
                                  "spending": spend.report()}), flush=True)
    finally:
        report = {"mode": "live", "protocol_sha256": study.digest(protocol), "provenance": bundle["provenance"],
                  "planned_arms": len(bundle["cases"]) * 2, "completed_arms": sum(r["completed"] for r in runs),
                  "semantic_success_rate": None, "labels": "pending", "spending": spend.report(),
                  "summary": [{k: r[k] for k in ("case", "arm", "planned_turns", "completed", "rollovers", "diagnostics")}
                              for r in runs]}
        study.write_new(output / "report.json", report)
        study.write_new(output / "review-form.json", study.review_form(runs))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--study", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path, default=ROOT / "results/naacl2027/conversation-live-v1")
    parser.add_argument("--key-file", type=Path, default=ROOT / ".env.local")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.study)
        print("Prepared US$1 live protocol; no model calls made.")
    else:
        print(json.dumps(run(args.study, args.output, args.key_file), indent=2))


if __name__ == "__main__":
    main()
