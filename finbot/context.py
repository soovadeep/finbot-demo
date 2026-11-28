"""Local prompt admission, not a provider tokenizer or semantic summarizer.

One UTF-8 byte per estimated token deliberately overestimates ordinary English BPE
text. Serialization and per-message overhead include system/state text and tool schemas.
Provider framing/tokenizers vary: configure the smallest deployed context window and
retain a margin. Output capacity is reserved separately and never counted as input.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .resilience import ServiceUnavailable


class ContextBudgetExceeded(ServiceUnavailable):
    """The complete request cannot be admitted; do not send a truncated request."""


def _serialize(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return vars(value)
    raise TypeError(f"unsupported prompt block: {type(value).__name__}")


def estimate_tokens(system: str, messages: list, tools: list[dict]) -> int:
    payload = json.dumps({"system": system, "messages": messages, "tools": tools},
                         ensure_ascii=False, default=_serialize, separators=(",", ":"))
    return len(payload.encode("utf-8")) + 64 * (len(messages) + len(tools) + 1)


@dataclass(frozen=True)
class ContextBudget:
    window_tokens: int
    output_tokens: int
    margin_tokens: int

    def __post_init__(self):
        if (any(type(v) is not int or v < 0 for v in
                (self.window_tokens, self.output_tokens, self.margin_tokens))
                or self.window_tokens <= self.output_tokens + self.margin_tokens):
            raise ValueError("context window must exceed the output reserve plus safety margin")

    @property
    def input_limit(self) -> int:
        return self.window_tokens - self.output_tokens - self.margin_tokens

    def fits(self, system: str, messages: list, tools: list[dict]) -> bool:
        return estimate_tokens(system, messages, tools) <= self.input_limit

    def require_fit(self, system: str, messages: list, tools: list[dict]) -> int:
        size = estimate_tokens(system, messages, tools)
        if size > self.input_limit:
            raise ContextBudgetExceeded(f"context_budget_exceeded:estimated={size}:limit={self.input_limit}")
        return size
