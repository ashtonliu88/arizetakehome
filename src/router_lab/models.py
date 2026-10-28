from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Action = Literal[
    "search_docs",
    "search_code",
    "lookup_issue",
    "lookup_deployment",
    "lookup_test_results",
    "calculate",
    "answer_directly",
    "ask_for_clarification",
]
ACTIONS: tuple[str, ...] = (
    "search_docs",
    "search_code",
    "lookup_issue",
    "lookup_deployment",
    "lookup_test_results",
    "calculate",
    "answer_directly",
    "ask_for_clarification",
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class BenchmarkExample(Contract):
    example_id: str
    request: str = Field(min_length=1)
    expected_action: Action
    rationale: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    paraphrase_group: str
    split: Literal["dev", "test"]

    def model_input(self) -> dict[str, str]:
        return {"request": self.request}


class RouteChoice(Contract):
    action: Action


class Usage(Contract):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def cache_is_subset(self):
        if self.cache_read_tokens + self.cache_write_tokens > self.input_tokens:
            raise ValueError("cache read/write tokens must be subsets of input tokens")
        return self

    @classmethod
    def from_provider(cls, raw: dict[str, Any]) -> Usage:
        details = raw.get("input_tokens_details") or {}
        return cls(
            input_tokens=raw.get("input_tokens", 0),
            output_tokens=raw.get("output_tokens", 0),
            cache_read_tokens=details.get("cached_tokens", 0) or 0,
            cache_write_tokens=details.get("cache_write_tokens", 0) or 0,
        )


class Rates(Contract):
    input: float = Field(ge=0)
    cache_read: float = Field(ge=0)
    cache_write: float = Field(ge=0)
    output: float = Field(ge=0)

    def cost(self, usage: Usage) -> float:
        uncached = usage.input_tokens - usage.cache_read_tokens - usage.cache_write_tokens
        return (
            uncached * self.input
            + usage.cache_read_tokens * self.cache_read
            + usage.cache_write_tokens * self.cache_write
            + usage.output_tokens * self.output
        ) / 1_000_000


class Settings(Contract):
    decision_model: str = "gpt-6-luna"
    llm_model: str = "gpt-6.1-sol"
    reasoning_effort: Literal["low"] = "low"
    max_output_tokens: int = Field(default=512, ge=128, le=4096)
    answer_max_output_tokens: int = Field(default=2048, ge=128, le=4096)
    timeout_seconds: float = Field(default=30, gt=0, le=30)
    max_retries: int = Field(default=2, ge=0, le=2)
    repetitions: int = Field(default=3, ge=1)
    budget_usd: float = Field(default=50, gt=0, le=50)
    reserve_usd: float = Field(default=5, ge=0)
    seed: int = 1729
    pricing: dict[str, Rates]
    pricing_note: str


class CallRecord(Contract):
    kind: Literal["decisions", "llm", "arguments", "answer", "judge"]
    attempt: int = 0
    action: Action | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    probabilities: dict[str, float] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    usage: Usage = Field(default_factory=Usage)
    cost_usd: float = Field(default=0, ge=0)
    cost_estimated: bool = False
    latency_ms: float = Field(default=0, ge=0)
    error: str | None = None
    span_id: str | None = None
    timestamp: str = ""


class RouteResult(Contract):
    initial_action: Action | None = None
    final_action: Action | None = None
    decision_confidence: float | None = Field(default=None, ge=0, le=1)
    option_probabilities: dict[str, float] = Field(default_factory=dict)
    fallback: bool = False
    fallback_reason: Literal["confidence", "operational", "always"] | None = None
    latency_ms: float = Field(default=0, ge=0)
    usage: Usage = Field(default_factory=Usage)
    cost_usd: float = Field(default=0, ge=0)
    calls: list[CallRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    policy_span_id: str | None = None
    initial_span_id: str | None = None
    final_span_id: str | None = None

    @property
    def maximum_probability(self) -> float | None:
        return max(self.option_probabilities.values(), default=None)

    @property
    def probability_margin(self) -> float | None:
        p = sorted(self.option_probabilities.values(), reverse=True)
        return p[0] - p[1] if len(p) > 1 else None


def validate_probabilities(probabilities: dict[str, float]) -> None:
    if set(probabilities) != set(ACTIONS):
        raise ValueError("probabilities must cover the exact action catalog")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values()):
        raise ValueError("invalid option probability")
    if not math.isclose(sum(probabilities.values()), 1, abs_tol=1e-4):
        raise ValueError("option probabilities must sum to one")
