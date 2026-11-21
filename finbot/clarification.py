"""Bounded template elicitation over an already authorized candidate catalogue.

This module does not discover records, grant access, or assert financial facts.
Probabilities describe a configurable response channel, not measured human accuracy.
Only explicit record confirmation resolves the runtime workflow. A high posterior
is useful for selecting a question but never authorizes a financial answer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

UNKNOWN = "I'm not sure"
STRATEGIES = ("none", "fixed", "information_gain", "decision_value")
TEMPLATES = (
    ("kind", "Which type of payment do you mean?"),
    ("merchant", "Which merchant or recipient do you mean?"),
    ("date", "On which date was the payment?"),
    ("amount", "How much was the payment?"),
)


@dataclass(frozen=True)
class Candidate:
    record_id: str
    tenant_id: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class Question:
    template: str
    text: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class ResponseModel:
    """Symmetric errors among known options, plus an uninformative unknown reply.

    accuracy is conditional on giving a definite reply. Conditional independence
    between successive replies is an assumption, not a property of real users.
    """

    accuracy: float = 0.9
    unknown: float = 0.1

    def __post_init__(self) -> None:
        if any(not math.isfinite(v) or not 0 <= v <= 1 for v in (self.accuracy, self.unknown)):
            raise ValueError("Response probabilities must be finite and between zero and one.")

    def likelihood(self, candidate: Candidate, question: Question, reply: str) -> float:
        if len(question.options) < 2:
            raise ValueError("A clarification must distinguish at least two options.")
        if reply == UNKNOWN:
            return self.unknown
        if reply not in question.options:
            return 0.0
        if reply == candidate.attributes[question.template]:
            return (1 - self.unknown) * self.accuracy
        return (1 - self.unknown) * (1 - self.accuracy) / (len(question.options) - 1)


def normalize(values: list[float]) -> list[float]:
    if not values or any(not math.isfinite(p) or p < 0 for p in values):
        raise ValueError("Beliefs must be finite and nonnegative.")
    total = sum(values)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Beliefs must have positive finite mass.")
    return [p / total for p in values]


def entropy(belief: list[float]) -> float:
    return -sum(p * math.log2(p) for p in normalize(belief) if p)


def questions(candidates: tuple[Candidate, ...]) -> list[Question]:
    """Missing attributes and nondiscriminating templates are never asked."""
    result = []
    for key, text in TEMPLATES:
        values = [c.attributes.get(key, "") for c in candidates]
        options = tuple(dict.fromkeys(values))
        if all(values) and len(options) > 1 and UNKNOWN not in options:
            result.append(Question(key, text, options))
    return result


def posterior(candidates: tuple[Candidate, ...], belief: list[float], question: Question,
              reply: str, model: ResponseModel) -> tuple[float, list[float]]:
    if len(candidates) != len(belief):
        raise ValueError("One belief per candidate is required.")
    prior = normalize(belief)
    joint = [p * model.likelihood(c, question, reply) for c, p in zip(candidates, prior, strict=True)]
    mass = sum(joint)
    # Impossible observations are a model mismatch, never grounds for certainty.
    return mass, normalize(joint) if mass > 0 else prior


@dataclass(frozen=True)
class QuestionScore:
    question: Question
    information_gain_bits: float
    expected_error_after: float
    error_reduction: float
    decision_value: float


def score_question(candidates: tuple[Candidate, ...], belief: list[float], question: Question,
                   model: ResponseModel, question_cost: float = 0.02) -> QuestionScore:
    """One-step, zero-one wrong-record loss; cost uses the same loss units.

    Error predictions use a MAP record choice, NOT the runtime release rule.
    """
    if not math.isfinite(question_cost) or question_cost < 0:
        raise ValueError("Question cost must be finite and nonnegative.")
    belief = normalize(belief)
    expected_entropy = expected_error = total = 0.0
    for reply in (*question.options, UNKNOWN):
        mass, updated = posterior(candidates, belief, question, reply, model)
        total += mass
        expected_entropy += mass * entropy(updated)
        expected_error += mass * (1 - max(updated))
    if not math.isclose(total, 1.0, abs_tol=1e-9):
        raise ValueError("The response channel must sum to one.")
    reduction = max(0.0, 1 - max(belief) - expected_error)
    return QuestionScore(question, max(0.0, entropy(belief) - expected_entropy),
                         expected_error, reduction, reduction - question_cost)


@dataclass
class ClarificationSession:
    """Finite candidate selection with explicit confirmation and versioned corrections."""

    candidates: tuple[Candidate, ...]
    tenant_id: str
    belief: list[float] = field(default_factory=list)
    strategy: str = "information_gain"
    models: dict[str, ResponseModel] = field(default_factory=dict)
    max_questions: int = 2
    question_cost: float = 0.02
    threshold: float = 0.95
    asked: list[str] = field(default_factory=list, init=False)
    pending: Question | None = field(default=None, init=False)
    selected_id: str | None = field(default=None, init=False)
    revision: int = field(default=0, init=False)
    stopped: bool = field(default=False, init=False)
    trace: list[dict] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if not self.tenant_id or not 1 <= len(self.candidates) <= 8:
            raise ValueError("Supply 1–8 already authorized candidate records.")
        if any(c.tenant_id != self.tenant_id for c in self.candidates):
            raise ValueError("Candidate scope does not match the session tenant.")
        if len({c.record_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("Candidate record IDs must be unique.")
        if any(not c.record_id or any(not isinstance(v, str) or len(v) > 120 for v in c.attributes.values())
               for c in self.candidates):
            raise ValueError("Invalid candidate identifier or attribute.")
        if self.strategy not in STRATEGIES or type(self.max_questions) is not int or not 0 <= self.max_questions <= 3:
            raise ValueError("Unknown strategy or question budget.")
        if not math.isfinite(self.threshold) or not 0.5 < self.threshold <= 1:
            raise ValueError("Confidence threshold must be above 0.5 and at most one.")
        if not math.isfinite(self.question_cost) or self.question_cost < 0:
            raise ValueError("Question cost must be finite and nonnegative.")
        if self.belief and len(self.belief) != len(self.candidates):
            raise ValueError("One belief per candidate is required.")
        self.belief = normalize(self.belief or [1.0] * len(self.candidates))

    def model(self, question: Question) -> ResponseModel:
        return self.models.get(question.template, ResponseModel())

    def rank(self) -> list[QuestionScore]:
        scored = [score_question(self.candidates, self.belief, q, self.model(q), self.question_cost)
                  for q in questions(self.candidates) if q.template not in self.asked]
        if self.strategy in {"information_gain", "decision_value"}:
            scored.sort(key=lambda s: s.information_gain_bits if self.strategy == "information_gain"
                        else s.decision_value, reverse=True)
        return scored

    def next_question(self) -> Question | None:
        if self.selected_id or self.stopped:
            return None
        if self.pending:
            return self.pending
        if self.strategy == "none" or len(self.asked) >= self.max_questions or max(self.belief) >= self.threshold:
            return None
        ranked = self.rank()
        if not ranked:
            return None
        selected = ranked[0]
        if (self.strategy == "information_gain" and selected.information_gain_bits <= 1e-12) or (
                self.strategy == "decision_value" and selected.decision_value <= 1e-12):
            return None
        self.pending = selected.question
        self.asked.append(self.pending.template)
        self.trace.append({"event": "question", "revision": self.revision,
                           "belief": list(self.belief), "selected": self.pending.template,
                           "candidates": [score_dict(s) for s in ranked]})
        return self.pending

    def reply(self, template: str, text: str) -> None:
        if not self.pending or template != self.pending.template:
            raise ValueError("Reply does not match the pending question.")
        if not isinstance(text, str) or len(text) > 200:
            raise ValueError("Reply must have at most 200 characters.")
        q = self.pending
        # Exact option matching only. Unrecognized free text conveys no measured information.
        reply = next((v for v in (*q.options, UNKNOWN) if v.casefold() == text.strip().casefold()), UNKNOWN)
        before = list(self.belief)
        mass, updated = posterior(self.candidates, self.belief, q, reply, self.model(q))
        self.belief = updated
        self.pending = None
        self.trace.append({"event": "reply", "revision": self.revision, "template": template,
                           "reply_category": reply, "before": before, "after": list(updated),
                           "model_mismatch": mass == 0})

    def confirm(self, record_id: str) -> None:
        """An explicit user's selection, never called by posterior threshold logic."""
        if record_id not in {c.record_id for c in self.candidates}:
            raise ValueError("Selected record is outside the authorized catalogue.")
        previous = self.selected_id
        self.selected_id = record_id
        self.revision += 1
        self.belief = [float(c.record_id == record_id) for c in self.candidates]
        self.pending = None
        self.stopped = False
        self.trace.append({"event": "confirm" if previous is None else "correct",
                           "revision": self.revision, "selected_id": record_id,
                           "invalidated_record": previous})

    def reject_candidates(self) -> None:
        previous = self.selected_id
        self.selected_id = None
        self.pending = None
        self.stopped = True
        self.revision += 1
        self.trace.append({"event": "unresolved", "revision": self.revision,
                           "invalidated_record": previous})


def score_dict(score: QuestionScore) -> dict:
    return {"template": score.question.template, "text": score.question.text,
            "options": list(score.question.options), "information_gain_bits": score.information_gain_bits,
            "expected_error_after": score.expected_error_after, "error_reduction": score.error_reduction,
            "decision_value": score.decision_value}
