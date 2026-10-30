from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from ..models import Contract

TOOLS = (
    "lookup_issue",
    "lookup_deployment",
    "lookup_test_results",
    "search_docs",
    "search_code",
    "calculate",
)
POLICIES = ("fused", "exact", "ordinary", "verified")


class ApplicationContext(Contract):
    tenant: str = "acme"
    capabilities: list[str] = Field(default_factory=lambda: list(TOOLS))
    # Empty grants mean no resource-level restriction within the tenant.
    grants: list[str] = Field(default_factory=list)
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    service: str | None = None
    environment: str | None = None


class RequestInput(Contract):
    request: str
    context: ApplicationContext = Field(default_factory=ApplicationContext)


class RequestBindings(Contract):
    slots: dict[str, str | float]
    slot_types: dict[str, str]
    skeleton: str
    namespace: str
    unresolved: list[str] = Field(default_factory=list)
    semantics: list[str] = Field(default_factory=list)


class Step(Contract):
    tool: Literal[
        "lookup_issue", "lookup_deployment", "lookup_test_results", "search_docs", "search_code", "calculate"
    ]
    arguments: dict[str, Any]


class PlannedResponse(Contract):
    kind: Literal["tools", "direct", "clarify", "abstain"]
    steps: list[Step] = Field(default_factory=list, max_length=3)
    response: str = ""

    @model_validator(mode="after")
    def consistent(self):
        if (self.kind == "tools") != bool(self.steps):
            raise ValueError("tools require steps; direct/clarify require no steps")
        if self.kind != "tools" and not self.response.strip():
            raise ValueError("direct/clarify requires response")
        return self


class PlanTemplate(Contract):
    template_id: str
    skeleton: str
    namespace: str
    slot_types: dict[str, str]
    semantics: list[str]
    steps: list[Step] = Field(min_length=1, max_length=3)
    contracts: dict[str, str]
    provenance: dict[str, str]


class ExecutionRecord(Contract):
    run_id: str
    policy: str
    bank_state: str
    status: Literal[
        "completed",
        "clarified",
        "abstained",
        "safe_failure",
        "transport_failure",
        "semantic_failure",
        "pending",
    ] = "pending"
    bindings: RequestBindings
    answer: str = ""
    calls: list[dict] = Field(default_factory=list)
    executions: list[dict] = Field(default_factory=list)
    cache_hit: bool = False
    candidate: str | None = None
    retrieval_score: float = 0
    retrieval_margin: float = 0
    rejection: str | None = None
    replans: int = 0
    error: str | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
    cost_usd: float = 0
    trace_id: str | None = None


class ReuseSettings(Contract):
    threshold: float = Field(default=0.55, ge=0, le=1)
    margin: float = Field(default=0.05, ge=0, le=1)
    pilot_cap: float = Field(default=3, gt=0, le=3)
    core_cap: float = Field(default=20, gt=0, le=20)
    ordinary_subset: bool = False
    seed: int = 1729
    planner_tokens: int = 1536
    answer_tokens: int = 512
