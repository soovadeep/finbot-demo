"""Local evidence inspector: python -m finbot.demo. Synthetic data; no model API calls.

This separate development server deliberately exposes rejected drafts. It is not a
production API, accepts no credentials, and binds only to the loopback interface.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from socketserver import ThreadingMixIn
from types import SimpleNamespace as NS
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from . import replies
from .config import Settings
from .domains import find_ids
from .faults import HallucinatingLLM
from .guardrails import LocalGuardrail
from .knowledge import Index
from .llm import FakeLLM
from .orchestrator import Chatbot
from .pii import mask_value
from .tools import DEMO_DOCS, DEMO_LOGS, DEMO_TXNS, InMemoryLogs, InMemoryTxns, ToolBox
from .untrusted import unwrap
from .verification import VerificationStep

ASSETS = Path(__file__).with_name("demo_assets")
MAX_BODY = 8192
FAULTS = {
    "none": "No injected fault",
    "status_once": "Wrong status in first draft",
    "amount_once": "Invented fee in first draft",
    "amount_always": "Invented fee in draft and repair",
    "swap_once": "Swap two transaction amounts in first draft",
    "policy_once": "Reverse a policy rule while keeping its citation",
    "settlement_once": "Present an expected settlement date as an actual date",
    "refund_once": "Present the payment amount as the refund amount",
}
PAIR = "Compare txn_A1B2C3D4 and txn_E5F6G7H8: what are their amounts and statuses?"
SCENARIOS = [
    {"id": "settlement_role", "title": "Expected is not actual", "fault": "settlement_once",
     "question": "What are the settlement details for txn_ROLE0001?",
     "description": "The date exists on the right record, but only as an expectation. Inspect the field that rejects an actual-date claim."},
    {"id": "refund_role", "title": "Payment is not refund", "fault": "refund_once",
     "question": "What are the payment and refund details for txn_ROLE0001?",
     "description": "A $200 payment has a $50 refund. Reusing the payment amount as the refund fails the role check."},
    {"id": "correct", "title": "A supported answer", "fault": "none",
     "question": "Why was txn_A1B2C3D4 declined?",
     "description": "The scripted draft passes the implemented checks."},
    {"id": "repair", "title": "Catch a wrong status", "fault": "status_once",
     "question": "Why was txn_A1B2C3D4 declined?",
     "description": "An injected approval claim is rejected; one repair uses the retrieved facts."},
    {"id": "fallback", "title": "Recover after failed repair", "fault": "amount_always",
     "question": "Why was txn_A1B2C3D4 declined?",
     "description": "Both drafts contain an injected fee. Code builds and verifies a record summary."},
    {"id": "timeout", "title": "An unknown outcome", "fault": "none",
     "question": "What is the status of txn_TIMEOUT01?",
     "description": "A timeout does not establish approval or decline. Policy requires checking the status."},
    {"id": "pair", "title": "Keep two records separate", "fault": "none", "question": PAIR,
     "description": "Each amount and status stays associated with its own transaction."},
    {"id": "binding", "title": "Catch swapped amounts", "fault": "swap_once", "question": PAIR,
     "description": "Both amounts exist, but belong to different records. Claim binding catches the swap."},
    {"id": "policy_quote", "title": "Quote the policy instead", "fault": "amount_always",
     "question": "What are the surcharge rules?",
     "description": "Both policy drafts add a fee. Code quotes the retrieved policy passage, with its source, instead."},
    {"id": "refusal", "title": "When recovery is unavailable", "fault": "amount_always",
     "question": "What is the interest rate on my savings account?",
     "description": "Repair fails and there is neither a record nor a matching policy passage to quote, so the turn is refused."},
    {"id": "policy", "title": "A citation is not enough", "fault": "policy_once",
     "question": "What are the surcharge rules?",
     "description": "An injected claim reverses the debit-card rule but keeps the real citation. "
                    "Source-sentence checks reject it; repair restores the source wording."},
]
TIMEOUT = {"txn_id": "txn_TIMEOUT01", "tenant_id": "m_100", "status": "unknown", "amount": "80.00",
           "currency": "USD", "error": "PROCESSOR_TIMEOUT", "created_at": "2026-11-12T16:15:00Z"}
ROLE_RECORD = {"txn_id": "txn_ROLE0001", "tenant_id": "m_100", "status": "approved", "amount": "200.00",
               "currency": "USD", "settlement": {"status": "settled", "expected_date": "2026-11-20"},
               "refund": {"status": "succeeded", "amount": "50.00"}}


class ScriptedPayments(FakeLLM):
    """Extend the offline fixture model to fetch every payment explicitly named by the user."""

    def create(self, system, messages, tools):
        # Let FakeLLM compose from tool results. Otherwise fetch all requested records,
        # including on repair. The ordinary tool gateway still enforces provenance/tenant.
        if not isinstance(messages[-1]["content"], list):
            question = next(m["content"] for m in reversed(messages) if m["role"] == "user"
                            and isinstance(m["content"], str) and not m["content"].startswith("<verifier>"))
            ids = list(dict.fromkeys(t for t in find_ids(question) if t.startswith("txn_")))
            if len(ids) > 1:
                self.calls += 1
                return NS(stop_reason="tool_use", content=[
                    NS(type="tool_use", id=f"demo_{self.calls}_{i}", name="get_transaction", input={"txn_id": tid})
                    for i, tid in enumerate(ids)])
        return super().create(system, messages, tools)


def writer() -> dict:
    """Who drafts the answers: the scripted writer (default, no key, reproducible) or, with
    FINBOT_DEMO_WRITER=live, the model that FINBOT_LLM_PROVIDER and FINBOT_MODEL select, as in
    the command-line assistant. Clarification and the checks are the same either way."""
    if os.environ.get("FINBOT_DEMO_WRITER", "scripted") != "live":
        return {"mode": "offline_scripted", "label": "Scripted writer"}
    provider = os.environ.get("FINBOT_LLM_PROVIDER", "openai")
    model = os.environ.get("FINBOT_MODEL", "qwen2.5:7b")
    name = os.environ.get("FINBOT_DEMO_LIVE_NAME") or model.split("/")[-1]
    return {"mode": "live_model", "label": f"Live model ({name})", "provider": provider, "model": model}


class LiveBudget:
    """Caps live-model answers so a public page cannot run up the owner's bill.

    FINBOT_DEMO_LIVE_DAILY      live answers per UTC day, per server instance (default 100)
    FINBOT_DEMO_LIVE_PER_CLIENT live answers per visitor per hour (default 5)
    Replays of the same answer come from a cache and cost nothing. When a cap is reached the
    scripted writer answers instead and the page says so. The hard ceiling belongs on the
    provider key itself (a credit limit), which no code path can exceed."""

    def __init__(self):
        self.lock = threading.Lock()
        self.day, self.used = "", 0
        self.clients: dict[str, list[float]] = {}

    def allow(self, client: str) -> bool:
        daily = int(os.environ.get("FINBOT_DEMO_LIVE_DAILY", "100"))
        hourly = int(os.environ.get("FINBOT_DEMO_LIVE_PER_CLIENT", "5"))
        now = time.time()
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        with self.lock:
            if today != self.day:
                self.day, self.used, self.clients = today, 0, {}
            recent = [t for t in self.clients.get(client, []) if now - t < 3600]
            if self.used >= daily or len(recent) >= hourly:
                self.clients[client] = recent
                return False
            self.used += 1
            self.clients[client] = [*recent, now]
            return True


LIVE_BUDGET = LiveBudget()


def PILOT_ENABLED() -> bool:  # noqa: N802 - read per request so tests can toggle it
    """The usability-pilot page is optional future work: off unless FINBOT_DEMO_PILOT=1, so a
    hosted copy does not show a consent form for a study that is not running."""
    return os.environ.get("FINBOT_DEMO_PILOT", "0") == "1"
LIVE_CACHE: OrderedDict[str, dict] = OrderedDict()
LIVE_MAX_TOKENS = 400


class DemoModel:
    """Fault injection happens after the writer's answer, before the actual verifier chain."""

    def __init__(self, fault: str, live: bool = False):
        w = writer()
        if live and w["mode"] == "live_model":
            from .llm import make_client
            self.base = make_client(w["provider"], w["model"])
            if hasattr(self.base, "max_tokens"):
                self.base.max_tokens = LIVE_MAX_TOKENS
        else:
            self.base = ScriptedPayments()
        self.fault = fault
        self.injections: list[dict] = []

    def create(self, system, messages, tools):
        response = self.base.create(system, messages, tools)
        repair = HallucinatingLLM._is_retry(messages)
        if response.stop_reason != "end_turn" or self.fault == "none" or (
                repair and self.fault != "amount_always"):
            return response
        before = "".join(b.text for b in response.content if b.type == "text")
        after, marker = before, None
        if self.fault == "settlement_once":
            after = before.replace("Expected settlement date:", "Actual settlement date:")
            if after != before:
                after = after.replace(" An actual settlement date is not recorded.", "")
                marker = "expected date relabelled as actual; date value unchanged"
        elif self.fault == "refund_once":
            blocks = messages[-1]["content"]
            for block in blocks if isinstance(blocks, list) else []:
                if block.get("type") != "tool_result":
                    continue
                result = unwrap(block["content"])
                if result["status"] != "found" or result["source"] != "txn_db":
                    continue
                data = result["data"]
                refund = (data.get("refund") or {}).get("amount")
                if refund and refund != data.get("amount"):
                    after = after.replace(f"Refund amount: {refund}.", f"Refund amount: {data['amount']}.")
            if after != before:
                marker = "payment amount reused as refund amount on the same record"
        elif self.fault == "policy_once":
            after = before.replace("Debit and prepaid cards cannot be surcharged.",
                                   "Debit and prepaid cards can be surcharged.")
            if after != before:
                marker = "policy condition reversed; original citation retained"
        elif self.fault == "swap_once":
            blocks = messages[-1]["content"]
            records = [unwrap(b["content"]) for b in blocks if b.get("type") == "tool_result"]
            amounts = [r["data"]["amount"] for r in records if r["status"] == "found"
                       and r["source"] == "txn_db"]
            if len(amounts) == 2 and amounts[0] != amounts[1]:
                after = before.replace(amounts[0], "__DEMO_SWAP__").replace(amounts[1], amounts[0])
                after = after.replace("__DEMO_SWAP__", amounts[1])
                marker = "amounts exchanged between records"
        else:
            mode = "status_flip" if self.fault == "status_once" else "invented_amount"
            after, marker = HallucinatingLLM(self.base, mode)._corrupt(before)
        if marker and after != before:
            self.injections.append({"stage": "repair" if repair else "draft", "fault": self.fault,
                                    "marker": marker})
        return NS(stop_reason="end_turn", content=[NS(type="text", text=after)])


WRITER_SOURCES = {
    "scripted": "Scripted writer",
    "live_generated": "Live model, generated for this request",
    "live_cached": "Live model, replayed from an earlier identical request",
    "scripted_after_limit": "Scripted writer (live-model limit reached)",
    "scripted_after_provider_error": "Scripted writer (live model unavailable)",
}


def _labelled(result: dict, source: str) -> dict:
    """Every answer says who wrote it, so a reader never mistakes a script or a replay for a
    newly generated model answer, or a fallback for the model."""
    result["writer_source"] = source
    result["writer_label"] = WRITER_SOURCES[source] + (
        f": {writer()['label'].removeprefix('Live model (').rstrip(')')}" if source.startswith("live") else "")
    return result


def run_demo(question: str, fault: str = "none", *, records: list[dict] | None = None,
             live: bool = False, client: str = "") -> dict:
    """live=True asks for the live writer; it is used only when the server enables it
    (FINBOT_DEMO_WRITER=live) and the caps allow, otherwise the scripted writer answers.
    The result's writer_source says which happened (see WRITER_SOURCES)."""
    note, source = None, "scripted"
    semantic = os.environ.get("FINBOT_DEMO_SEMANTIC", "off")
    if live and writer()["mode"] == "live_model":
        key = json.dumps([question, fault, records], sort_keys=True, default=str)
        if semantic == "off" and key in LIVE_CACHE:
            LIVE_CACHE.move_to_end(key)
            return _labelled(copy.deepcopy(LIVE_CACHE[key]), "live_cached")
        if LIVE_BUDGET.allow(client):
            try:
                result = _run_demo(question, fault, records=records, live=True)
            except Exception:  # noqa: BLE001 - a provider outage must not break the page
                note = "The live model did not answer; the scripted writer answered instead."
                source = "scripted_after_provider_error"
            else:
                if semantic == "off":
                    LIVE_CACHE[key] = copy.deepcopy(result)
                while len(LIVE_CACHE) > 256:
                    LIVE_CACHE.popitem(last=False)
                return _labelled(result, "live_generated")
        else:
            note = "The live-model limit for now is reached; the scripted writer answered instead."
            source = "scripted_after_limit"
    result = _run_demo(question, fault, records=records, live=False)
    if note:
        result["writer_note"] = note
    return _labelled(result, source)


def _run_demo(question: str, fault: str = "none", *, records: list[dict] | None = None,
              live: bool = False) -> dict:
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError("Enter a question of 1–2000 characters.")
    if not isinstance(fault, str) or fault not in FAULTS:
        raise ValueError("Choose a listed fault mode.")
    # Direct wiring isolates this demo from production data, model and storage environment
    # settings. Every request receives new in-memory state and a fixed synthetic identity.
    kb = Index()
    for page in DEMO_DOCS:
        kb.upsert_page(copy.deepcopy(page))
    rows: list[dict] = copy.deepcopy(records if records is not None else [*DEMO_TXNS, TIMEOUT, ROLE_RECORD])
    toolbox = ToolBox(InMemoryTxns(rows), InMemoryLogs(copy.deepcopy(DEMO_LOGS)), kb, domains=["payments"])
    model = DemoModel(fault, live)
    settings = Settings(llm_provider="fake", guardrail_provider="local", store_provider="sqlite",
                        semantic_verification=os.environ.get("FINBOT_DEMO_SEMANTIC", "off"),
                        semantic_model=os.environ.get("FINBOT_SEMANTIC_MODEL", ""),
                        auth_mode="hmac", repair_attempts=1, record_fallback=True, routing="single",
                        policy_verification="extractive",
                        llm_retry_attempts=1, support_contact="the demo support desk", tool_policy_path="")
    bot = Chatbot(model, LocalGuardrail(), toolbox, settings)
    steps: list[VerificationStep] = []
    bot.gate.observer = steps.append
    turn = bot.ask(bot.new_session("m_100", ["support"], role="support"), question.strip())
    if turn.blocked_by:
        outcome = "blocked"
    elif any(reason.startswith("records_only:") for reason in turn.reasons):
        outcome = "policy_fallback" if turn.answer.startswith(replies.POLICY_ONLY) else "record_fallback"
    elif turn.repaired:
        outcome = "repaired"
    elif steps:
        outcome = "passed"
    else:
        outcome = "handled_by_code"
    return mask_value({
        "schema_version": 2, "mode": "live_model" if live else "offline_scripted",
        "writer": writer()["label"] if live else "Scripted writer", "synthetic_data": True,
        "question": turn.question,
        "policy_verification": "extractive",
        **({"semantic_verification": settings.semantic_verification}
           if settings.semantic_verification != "off" else {}),
        "fault": fault, "injections": model.injections, "outcome": outcome,
        "steps": [asdict(step) for step in steps], "evidence": turn.tools_called,
        "final": {"answer": turn.answer, "blocked_by": turn.blocked_by, "reasons": turn.reasons,
                  "repaired": turn.repaired, "escalated": turn.escalated},
        "metrics": {"latency_ms": turn.latency_ms, "model_calls": len(turn.models_used),
                    "tool_calls": len(turn.tools_called)},
        "limits": ("Live model" if live else "Scripted model") +
                  " and synthetic fixtures. Passing these checks is not a proof of factuality. "
                  "No live-model accuracy, latency or cost has been measured here.",
    })


class DemoApp:
    """The demo's only state is per request: every call replays at most twelve events.

    By default it answers only on the loopback origin. `public_host` adds one HTTPS hostname
    for a hosted copy (behind a TLS-terminating proxy); `max_concurrent` turns excess load
    into 503s instead of an unbounded thread pile-up."""

    def __init__(self, port: int = 8765, study_model: dict | None = None, public_host: str | None = None,
                 max_concurrent: int = 32):
        self.origins = {f"127.0.0.1:{port}": "http", f"localhost:{port}": "http"}
        # A comma-separated list lets a host's several URLs (e.g. both Cloud Run addresses) work.
        for name in (public_host or "").split(","):
            if name.strip():
                self.origins[name.strip()] = "https"
        self.public = bool(public_host)
        self.study_model = study_model
        self.slots = threading.BoundedSemaphore(max_concurrent)

    def __call__(self, environ, start_response):
        if not self.slots.acquire(blocking=False):
            body = b'{"error": "The demo is busy. Please retry in a moment."}'
            start_response("503 Service Unavailable", [("Content-Type", "application/json; charset=utf-8"),
                                                       ("Content-Length", str(len(body))), ("Retry-After", "2")])
            return [body]
        try:
            return self._handle(environ, start_response)
        finally:
            self.slots.release()

    def _handle(self, environ, start_response):
        status, mime, body = "200 OK", "application/json; charset=utf-8", b""
        payload: dict | None
        try:
            host = environ.get("HTTP_HOST", "")
            scheme = self.origins.get(host)
            if scheme is None or environ.get("HTTP_ORIGIN", f"{scheme}://{host}") != f"{scheme}://{host}":
                status, payload = "403 Forbidden", {"error": "Use the demo's own origin."}
            elif environ["REQUEST_METHOD"] == "GET" and environ["PATH_INFO"] in {
                    "/", "/inspector", "/app.js", "/style.css", "/clarification", "/clarification.js",
                    "/study", "/study/probes", "/study.js", "/study.css",
                    "/conversation.js", "/conversation.css", "/pilot", "/pilot.js", "/pilot.css"} and (
                    not environ["PATH_INFO"].startswith("/pilot") or PILOT_ENABLED()):
                filename, mime = {"/": ("conversation.html", "text/html; charset=utf-8"),
                                  "/inspector": ("index.html", "text/html; charset=utf-8"),
                                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                                  "/style.css": ("style.css", "text/css; charset=utf-8"),
                                  "/clarification": ("clarification.html", "text/html; charset=utf-8"),
                                  "/clarification.js": ("clarification.js", "text/javascript; charset=utf-8"),
                                  "/study": ("conversation.html", "text/html; charset=utf-8"),
                                  "/study/probes": ("study.html", "text/html; charset=utf-8"),
                                  "/conversation.js": ("conversation.js", "text/javascript; charset=utf-8"),
                                  "/conversation.css": ("conversation.css", "text/css; charset=utf-8"),
                                  "/study.js": ("study.js", "text/javascript; charset=utf-8"),
                                  "/study.css": ("study.css", "text/css; charset=utf-8"),
                                  "/pilot": ("pilot.html", "text/html; charset=utf-8"),
                                  "/pilot.js": ("pilot.js", "text/javascript; charset=utf-8"),
                                  "/pilot.css": ("pilot.css", "text/css; charset=utf-8")
                                  }[environ["PATH_INFO"]]
                body = (ASSETS / filename).read_bytes()
                payload = None
            elif environ["REQUEST_METHOD"] == "GET" and environ["PATH_INFO"] == "/api/scenarios":
                w = writer()
                payload = {"scenarios": SCENARIOS, "faults": FAULTS, "mode": "offline_scripted",
                           "live_writer": w["label"] if w["mode"] == "live_model" else None}
            elif environ["REQUEST_METHOD"] == "GET" and environ["PATH_INFO"] == "/api/pilot/tasks" and PILOT_ENABLED():
                from .usability import public_tasks
                payload = public_tasks()
            elif environ["REQUEST_METHOD"] == "GET" and environ["PATH_INFO"] == "/api/clarification/cases":
                from .clarification_demo import case_catalogue
                payload = case_catalogue()
            elif environ["REQUEST_METHOD"] == "GET" and environ["PATH_INFO"] == "/api/study":
                from .clarification_study import study_info
                payload = study_info(self.study_model)
            elif environ["REQUEST_METHOD"] == "GET" and environ["PATH_INFO"] == "/api/conversation/scenarios":
                from .clarification_conversation import scenario_catalogue
                payload = scenario_catalogue()
            elif environ["REQUEST_METHOD"] == "POST" and environ["PATH_INFO"] in {
                    "/api/run", "/api/clarification", "/api/study", "/api/conversation"}:
                if environ.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json":
                    status, payload = "415 Unsupported Media Type", {"error": "Send application/json."}
                else:
                    size = int(environ.get("CONTENT_LENGTH") or "0")
                    if size < 1 or size > MAX_BODY:
                        status, payload = "413 Content Too Large", {"error": "Request size must be 1–8192 bytes."}
                    else:
                        request = json.loads(environ["wsgi.input"].read(size))
                        if environ["PATH_INFO"] == "/api/conversation":
                            from .clarification_conversation import run_conversation
                            # The host's front end appends the caller's address last; earlier
                            # entries come from the caller and could be forged to dodge the cap.
                            forwarded = environ.get("HTTP_X_FORWARDED_FOR", "").split(",")[-1].strip()
                            payload = run_conversation(request, client=forwarded or environ.get("REMOTE_ADDR", ""))
                        elif environ["PATH_INFO"] == "/api/study":
                            from .clarification_study import run_study
                            payload = run_study(request, self.study_model)
                        elif environ["PATH_INFO"] == "/api/clarification":
                            from .clarification_demo import run_clarification
                            payload = run_clarification(request)
                        else:
                            if not isinstance(request, dict) or set(request) - {"question", "fault", "live"}:
                                raise ValueError("Unexpected request fields.")
                            live = request.get("live", False)
                            if type(live) is not bool:
                                raise ValueError("live must be true or false.")
                            forwarded = environ.get("HTTP_X_FORWARDED_FOR", "").split(",")[-1].strip()
                            payload = run_demo(request.get("question", ""), request.get("fault", "none"), live=live,
                                               client=forwarded or environ.get("REMOTE_ADDR", ""))
            else:
                status, payload = "404 Not Found", {"error": "Route not found."}
        except (ValueError, TypeError, UnicodeError):
            status, payload = "400 Bad Request", {"error": "Invalid request, option, or stale clarification reply."}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = [("Content-Type", mime), ("Content-Length", str(len(body))), ("Cache-Control", "no-store"),
                   ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"),
                   ("Content-Security-Policy", "default-src 'self'; object-src 'none'; base-uri 'none'; "
                    "frame-ancestors 'none'; form-action 'self'")]
        if self.public:
            headers.append(("Strict-Transport-Security", "max-age=31536000"))
        start_response(status, headers)
        return [body]


class DemoServer(ThreadingMixIn, WSGIServer):
    """An idle browser preconnection must not block other local page requests."""

    daemon_threads = True


class DemoRequestHandler(WSGIRequestHandler):
    timeout = 10

    def handle(self):
        try:
            super().handle()
        except TimeoutError:
            # Browsers may open speculative sockets without ever sending a request.
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")),
                        help="listening port (default: $PORT, else 8765)")
    parser.add_argument("--host", default=os.environ.get("FINBOT_DEMO_BIND", "127.0.0.1"),
                        help="interface to listen on; use 0.0.0.0 only inside a container behind HTTPS")
    parser.add_argument("--public-host", default=os.environ.get("FINBOT_DEMO_PUBLIC_HOST") or None,
                        help="public HTTPS hostname(s) of a hosted copy, comma-separated")
    parser.add_argument("--study-model", type=Path, help="Frozen local development model JSON for study evaluation")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    study_model = None
    if args.study_model:
        from .clarification_study import validate_model
        try:
            study_model = json.loads(args.study_model.read_text())
            validate_model(study_model)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            parser.error(f"Invalid frozen study model: {exc}")
    if args.host != "127.0.0.1" and not args.public_host:
        # Not an error: a first container deploy may not know its URL yet. Requests are refused
        # (403) until FINBOT_DEMO_PUBLIC_HOST names it, so nothing is served on a guessed origin.
        print("No --public-host set: only loopback origins are accepted.", flush=True)
    app = DemoApp(args.port, study_model, public_host=args.public_host)
    with make_server(args.host, args.port, app,
                     server_class=DemoServer, handler_class=DemoRequestHandler) as server:
        where = f"https://{args.public_host.split(',')[0].strip()}" if args.public_host else f"http://127.0.0.1:{args.port}"
        print(f"Conversation demo: {where}/  Evidence inspector: {where}/inspector "
              "(offline; synthetic data only)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
