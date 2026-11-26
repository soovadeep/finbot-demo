"""Local, structured-response pilot. No recruitment, persistent storage or live LLM.

The server owns tasks and replays events; browser probabilities/outcome labels are
never accepted. Consent/provenance are researcher attestations, not identity proof.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from .clarification import UNKNOWN, Candidate, ClarificationSession, ResponseModel
from .clarification_demo import TENANT

PROTOCOL = "finbot-structured-pilot-v1"
KEYS = ("kind", "merchant", "date")
ARMS = ("none", "fixed", "information_gain", "decision_value")
SELECTOR_CONFIG: dict = {"evaluation_question_budget": 2, "development_question_budget": 1,
                   "prior": "uniform", "threshold": .95, "question_cost": .02, "arms": list(ARMS)}
ASSUMED = {"kind": ResponseModel(.9, .1), "merchant": ResponseModel(.8, .2),
           "date": ResponseModel(.85, .15)}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Task:
    task_id: str
    family: str
    prompt: str
    candidates: tuple[Candidate, ...]
    target: str | None
    expected: str


def catalogue() -> dict[str, list[Task]]:
    def candidates(prefix: str, rows: list[tuple[str, ...]]) -> tuple[Candidate, ...]:
        return tuple(Candidate(f"txn_{prefix}{i:04d}", TENANT, dict(zip(KEYS, row, strict=True)))
                     for i, row in enumerate(rows))

    dev = []
    for key in KEYS:
        first = ["Card payment", "Atlas Market", "2026-11-12"]
        second = list(first)
        second[KEYS.index(key)] = {"kind": "Bank transfer", "merchant": "Greenway", "date": "2026-11-13"}[key]
        rows = candidates(f"D{key.upper()}", [tuple(first), tuple(second)])
        for target in range(2):
            attrs = rows[target].attributes
            dev.append(Task(f"dev-{key}-{target}", f"dev-single-{key}",
                            f"Find the $200 {attrs['kind'].lower()} to {attrs['merchant']} on {attrs['date']}.",
                            rows, rows[target].record_id,
                            "Answer the distinguishing question, then confirm the matching record."))
    mixed = candidates("EMIX", [("Card payment", "Harbor Books", "2026-11-15"),
                               ("Bank transfer", "Willow Repairs", "2026-11-15"),
                               ("Card payment", "Willow Repairs", "2026-11-16"),
                               ("Bank transfer", "Harbor Books", "2026-11-16")])
    repeated = candidates("EREP", [("Card payment", "North Cafe", f"2026-11-{d}") for d in (16, 17, 18)])
    missing = candidates("EMISS", [("Card payment", "Elm Store", "2026-11-16"),
                                  ("Bank transfer", "Elm Store", "2026-11-17")])
    identical = candidates("ESAME", [("Card payment", "River Shop", "2026-11-18")] * 2)
    evaluation = [
        Task("eval-mixed", "eval-crossed-attributes", "Find your $200 bank transfer to Willow Repairs on 2026-11-15.",
             mixed, mixed[1].record_id, "Use the replies to narrow four records, then confirm the exact transfer."),
        Task("eval-repeat", "eval-three-dates", "Find your $200 card payment to North Cafe on 2026-11-17.",
             repeated, repeated[1].record_id, "The date distinguishes three otherwise similar payments."),
        Task("eval-missing", "eval-outside-catalogue", "Find your $200 card payment to Pine Pharmacy on 2026-11-18. "
             "You do not have a reference number.", missing, None,
             "The target is absent. Leave unresolved; do not answer about a substitute record."),
        Task("eval-identical", "eval-indistinguishable", "Find your $200 card payment to River Shop on 2026-11-18. "
             "You do not know the reference number or which of two identical entries it is.", identical, None,
             "The available details cannot distinguish the entries. Leave unresolved."),
    ]
    return {"development": dev, "evaluation": evaluation}


def validate_model(model: dict) -> dict[str, ResponseModel]:
    if not isinstance(model, dict) or model.get("protocol") != PROTOCOL or model.get("schema_version") != 1:
        raise ValueError("Wrong model protocol.")
    if model.get("model_id") != digest({k: v for k, v in model.items() if k != "model_id"}):
        raise ValueError("Frozen model content does not match its hash.")
    if model.get("provenance") not in {"participant", "rehearsal"}:
        raise ValueError("Invalid model provenance.")
    if model.get("selector_config") != SELECTOR_CONFIG:
        raise ValueError("Frozen selector configuration does not match this protocol.")
    codes = model.get("training_participants")
    families = model.get("training_families")
    if not isinstance(codes, list) or not codes or any(not valid_code(c) for c in codes):
        raise ValueError("Invalid development participant codes.")
    if not isinstance(families, list) or set(families) != {t.family for t in catalogue()["development"]}:
        raise ValueError("Wrong development families.")
    probabilities = model.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(KEYS):
        raise ValueError("One response model per template is required.")
    try:
        return {k: ResponseModel(**probabilities[k]) for k in KEYS}
    except (TypeError, KeyError) as exc:
        raise ValueError("Invalid response probabilities.") from exc


def valid_code(code: object) -> bool:
    # Opaque assigned code, not a name/email. Identity uniqueness is a study procedure.
    return isinstance(code, str) and re.fullmatch(r"P[0-9]{3,8}", code) is not None


def study_info(model: dict | None = None) -> dict:
    if model:
        validate_model(model)
    return {"protocol": PROTOCOL, "human_evaluation_ready": bool(model and model["provenance"] == "participant"),
            "model_id": model["model_id"] if model else None,
            "rehearsal_model_id": model["model_id"] if model and model["provenance"] == "rehearsal" else None,
            "tasks": {phase: len(tasks) for phase, tasks in catalogue().items()}}


def session_setup(request: dict, model: dict | None) -> tuple[list[Task], str, dict[str, ResponseModel], str]:
    allowed = {"protocol", "participant_code", "mode", "phase", "consent", "completed", "events"}
    if not isinstance(request, dict) or set(request) != allowed or request["protocol"] != PROTOCOL:
        raise ValueError("Invalid study request or protocol.")
    code, mode, phase = request["participant_code"], request["mode"], request["phase"]
    if not valid_code(code) or mode not in ("rehearsal", "participant") or phase not in catalogue():
        raise ValueError("Choose a mode, phase and assigned participant code (for example P001).")
    if type(request["consent"]) is not bool or (mode == "participant" and not request["consent"]):
        raise ValueError("Participant mode requires consent.")
    # Public rehearsals never load participant-derived parameters or IDs.
    if mode == "rehearsal" and model and model.get("provenance") == "participant":
        model = None
    models, model_id = ASSUMED, "assumed-v1"
    if phase == "evaluation" and model:
        models = validate_model(model)
        if mode != model["provenance"]:
            raise ValueError("Participant and rehearsal model provenance cannot be mixed.")
        if code in model["training_participants"]:
            raise ValueError("Evaluation requires new participant codes.")
        model_id = model["model_id"]
    elif phase == "evaluation" and mode == "participant":
        raise ValueError("Start the server with a frozen participant development model before evaluation.")
    tasks = list(catalogue()[phase])
    if model and phase == "evaluation" and set(model["training_families"]) & {t.family for t in tasks}:
        raise ValueError("Development and evaluation families overlap.")
    # Stable arm allocation avoids participant self-selection. It is not guaranteed balance.
    arm = ARMS[int(digest([PROTOCOL, code, "arm"]), 16) % len(ARMS)]
    if mode == "rehearsal":
        arm = "information_gain"
    if phase == "development":
        arm = "fixed"
    if mode == "participant":
        tasks.sort(key=lambda t: digest([PROTOCOL, code, t.task_id]))
    return tasks, arm, models, model_id


def replay_task(task: Task, events: list, arm: str, models: dict[str, ResponseModel], phase: str,
                *, finish: bool, financial: bool) -> tuple[dict, dict]:
    if not isinstance(events, list) or len(events) > 8:
        raise ValueError("At most eight events per task.")
    state = ClarificationSession(task.candidates, TENANT, strategy=arm, models=models,
                                 max_questions=int(SELECTOR_CONFIG[f"{phase}_question_budget"]),
                                 threshold=float(SELECTOR_CONFIG["threshold"]),
                                 question_cost=float(SELECTOR_CONFIG["question_cost"]))
    dialogue = []
    state.next_question()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Malformed event.")
        if event.get("type") == "reply" and set(event) == {"type", "template", "text"}:
            q = state.pending
            if not q or event["template"] != q.template or event["text"] not in (*q.options, UNKNOWN):
                raise ValueError("Only exact structured replies to the current question are collected.")
            dialogue.append({"question": q.text, "reply": event["text"]})
            state.reply(event["template"], event["text"])
        elif event.get("type") == "confirm" and set(event) == {"type", "record_id"}:
            if state.pending:
                raise ValueError("Answer the displayed question before confirming.")
            state.confirm(event["record_id"])
        elif event == {"type": "unresolved"}:
            if state.pending:
                raise ValueError("Answer the displayed question before leaving unresolved.")
            state.reject_candidates()
        else:
            raise ValueError("Invalid study event.")
        state.next_question()
    resolved = bool(state.selected_id or state.stopped)
    if finish and not resolved:
        raise ValueError("Each completed task requires confirmation or an explicit unresolved choice.")
    candidates = [{"record_id": c.record_id, **c.attributes} for c in task.candidates]
    public = {"task_id": task.task_id, "prompt": task.prompt, "candidates": candidates,
              "pending": asdict(state.pending) if state.pending else None, "dialogue": dialogue,
              "selected_id": state.selected_id, "unresolved": state.stopped, "can_finish": resolved}
    # Do not release labels, posteriors or verifier trace to the participant before the session ends.
    outcome = "correct_selection" if state.selected_id and state.selected_id == task.target else (
        "wrong_selection" if state.selected_id else "appropriate_unresolved" if task.target is None else "unresolved")
    answer = None
    if finish and financial and state.selected_id:
        from .demo import run_demo
        rows = [{"txn_id": c.record_id, "tenant_id": TENANT, "amount": "200.00", "currency": "USD",
                 "status": "pending" if c.attributes["kind"] == "Bank transfer" else "declined",
                 "created_at": c.attributes["date"] + "T12:00:00Z",
                 "payment_type": c.attributes["kind"], "merchant": c.attributes["merchant"],
                 **({"decline_code": "05", "processor_response": "Do not honor"}
                    if c.attributes["kind"] == "Card payment" else {})}
                for c in task.candidates]
        answer = run_demo(f"What are the recorded status and details of {state.selected_id}?", records=rows)
    report = {"task_id": task.task_id, "family": task.family, "target_id": task.target,
              "expected": task.expected, "selected_id": state.selected_id, "outcome": outcome,
              "question_count": len(state.asked), "corrections": sum(e["event"] == "correct" for e in state.trace),
              "candidates": candidates, "trace": state.trace, "financial": answer}
    return public, report


def run_study(request: dict, model: dict | None = None, *, financial: bool = True) -> dict:
    tasks, arm, models, model_id = session_setup(request, model)
    completed, events = request["completed"], request["events"]
    if not isinstance(completed, list) or len(completed) > len(tasks) or not isinstance(events, list):
        raise ValueError("Invalid task list.")
    reports = []
    done = len(completed) == len(tasks)
    for task, entry in zip(tasks, completed, strict=False):
        if not isinstance(entry, dict) or set(entry) != {"task_id", "events"} or entry["task_id"] != task.task_id:
            raise ValueError("Complete each assigned task exactly once and in order.")
        _, report = replay_task(task, entry["events"], arm, models, request["phase"],
                                finish=True, financial=financial and done)
        reports.append(report)
    if done and events:
        raise ValueError("No events after session completion.")
    current = None
    if not done:
        current, _ = replay_task(tasks[len(completed)], events, arm, models, request["phase"],
                                 finish=False, financial=False)
    result = {"protocol": PROTOCOL, "done": done, "mode": request["mode"], "phase": request["phase"],
              "completed_count": len(completed), "total": len(tasks), "current": current}
    if done:
        result["export"] = {"schema_version": 1, "protocol": PROTOCOL, "request": request,
                            "model_id": model_id, "selector_config": SELECTOR_CONFIG,
                            "strategy": arm, "results": reports,
                            "limitations": "Structured fictional tasks, scripted writer. Task targets are assigned, "
                            "not measurements of latent customer intent. "
                            "Verifier success is not independent factuality."}
    return result


def validated_exports(exports: list[dict], phase: str, *, allow_rehearsal: bool = False,
                      model: dict | None = None) -> list[dict]:
    if not exports:
        raise ValueError("Supply completed study exports.")
    seen, validated = set(), []
    for entry in exports:
        if not isinstance(entry, dict) or entry.get("schema_version") != 1 or entry.get("protocol") != PROTOCOL:
            raise ValueError("Wrong export schema.")
        if entry.get("selector_config") != SELECTOR_CONFIG:
            raise ValueError("Export selector configuration does not match this protocol.")
        request = entry.get("request", {})
        if not isinstance(request, dict):
            raise ValueError("Malformed exported request.")
        if request.get("phase") != phase:
            raise ValueError("Do not mix development and evaluation exports.")
        if request.get("mode") != "participant" and not allow_rehearsal:
            raise ValueError("Rehearsal data rejected. Use --allow-rehearsal only for infrastructure checks.")
        result = run_study(request, model, financial=False)
        if not result["done"] or entry.get("model_id") != result["export"]["model_id"]:
            raise ValueError("Incomplete session or mismatched frozen model.")
        code = request["participant_code"]
        if code in seen:
            raise ValueError("Duplicate participant: keep exactly one complete session export per participant.")
        seen.add(code)
        validated.append(result["export"])
    if len({e["request"]["mode"] for e in validated}) != 1:
        raise ValueError("Do not combine rehearsal and participant data.")
    return validated


def fit_model(exports: list[dict], *, allow_rehearsal: bool = False) -> dict:
    entries = validated_exports(exports, "development", allow_rehearsal=allow_rehearsal)
    counts = {k: {"correct": 0, "incorrect": 0, "unknown": 0} for k in KEYS}
    for entry in entries:
        for report in entry["results"]:
            target = next(c for c in report["candidates"] if c["record_id"] == report["target_id"])
            for event in report["trace"]:
                if event["event"] == "reply":
                    key, reply = event["template"], event["reply_category"]
                    category = "unknown" if reply == UNKNOWN else "correct" if reply == target[key] else "incorrect"
                    counts[key][category] += 1
    probabilities, estimates = {}, {}
    for key, count in counts.items():
        correct, incorrect, unknown = (count[k] for k in ("correct", "incorrect", "unknown"))
        definite, total = correct + incorrect, sum(count.values())
        if not total:
            raise ValueError(f"No observations for {key}.")
        probabilities[key] = {"accuracy": (correct + 1) / (definite + 2), "unknown": (unknown + 1) / (total + 2)}
        estimates[key] = {**count, "total": total, "raw_accuracy": correct / definite if definite else None,
                          "raw_unknown": unknown / total}
    artifact = {"schema_version": 1, "protocol": PROTOCOL, "provenance": entries[0]["request"]["mode"],
                "training_participants": sorted(e["request"]["participant_code"] for e in entries),
                "training_families": sorted({r["family"] for e in entries for r in e["results"]}),
                "selector_config": SELECTOR_CONFIG,
                "probabilities": probabilities, "counts": estimates,
                "estimator": "Beta(1,1) posterior means; accuracy conditional on definite replies",
                "assumptions": "Symmetric wrong options; uninformative unknown; independent replies. "
                "Binary development responses are extrapolated to multiclass evaluation. "
                "No minimum sample here establishes statistical sufficiency.",
                "source_digest": digest([e["request"] for e in entries])}
    artifact["model_id"] = digest(artifact)
    return artifact


def summarize(exports: list[dict], model: dict, *, allow_rehearsal: bool = False) -> dict:
    validate_model(model)
    entries = validated_exports(exports, "evaluation", model=model, allow_rehearsal=allow_rehearsal)
    arms: dict[str, dict] = {}
    for entry in entries:
        arm = arms.setdefault(entry["strategy"], {"participants": 0, "tasks": 0, "correct_selection": 0,
                             "wrong_selection": 0, "unresolved": 0, "appropriate_unresolved": 0,
                             "questions": 0, "corrections": 0, "identified_target_tasks": 0})
        arm["participants"] += 1
        for report in entry["results"]:
            arm["tasks"] += 1
            arm[report["outcome"]] += 1
            arm["questions"] += report["question_count"]
            arm["corrections"] += report["corrections"]
            arm["identified_target_tasks"] += report["target_id"] is not None
    return {"protocol": PROTOCOL, "model_id": model["model_id"], "provenance": entries[0]["request"]["mode"],
            "arms": arms, "limitations": "Descriptive counts only. Tasks from one participant are dependent. "
            "No significance, causal improvement, human reliability generalization or final-answer factuality claim."}
