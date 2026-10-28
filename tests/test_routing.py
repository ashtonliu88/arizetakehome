import pytest
from pydantic import ValidationError

from router_lab.models import CallRecord, RouteChoice
from router_lab.routing import Router


class QueueProvider:
    def __init__(self, calls):
        self.queue, self.inputs = list(calls), []

    def call(self, kind, request, catalog):
        self.inputs.append((kind, request, catalog))
        return [self.queue.pop(0)]


def decision(confidence=0.7, error=None):
    return CallRecord(
        kind="decisions",
        action="search_docs",
        confidence=confidence,
        error=error,
        cost_usd=0.001,
        span_id="0000000000000001",
    )


def llm(action="search_code", error=None):
    return CallRecord(kind="llm", action=action, error=error, cost_usd=0.01, span_id="0000000000000002")


@pytest.mark.parametrize(
    "confidence,expected_fallback", [(0.7, False), (0.70001, False), (0.69999, True), (0, True), (1, False)]
)
def test_threshold_equality_accepts(telemetry, confidence, expected_fallback):
    tracing, _ = telemetry
    p = QueueProvider([decision(confidence), llm()])
    r = Router("hybrid", p, tracing, threshold=0.7).route("Find implementation")
    assert r.fallback is expected_fallback
    assert r.fallback_reason == ("confidence" if expected_fallback else None)
    assert r.final_action == ("search_code" if expected_fallback else "search_docs")
    assert r.cost_usd == pytest.approx(0.011 if expected_fallback else 0.001)


def test_operational_fallback_and_failed_fallback(telemetry):
    tracing, _ = telemetry
    r = Router(
        "hybrid",
        QueueProvider([decision(None, "unusable confidence"), llm(error="refusal")]),
        tracing,
        threshold=0,
    ).route("hello")
    assert r.fallback_reason == "operational"
    assert r.final_action is None
    assert r.initial_action == "search_docs"
    assert len(r.errors) == 2
    assert r.cost_usd == pytest.approx(0.011)


def test_always_fallback_includes_confidence_one(telemetry):
    tracing, _ = telemetry
    r = Router(
        "hybrid", QueueProvider([decision(1), llm()]), tracing, threshold=1, always_fallback=True
    ).route("request")
    assert r.fallback_reason == "always"


def test_only_request_and_identical_catalog_sent(telemetry):
    tracing, _ = telemetry
    p = QueueProvider([decision(0.1), llm()])
    Router("hybrid", p, tracing, threshold=0.7).route("literal request")
    assert p.inputs[0][1] == p.inputs[1][1] == "literal request"
    assert p.inputs[0][2] == p.inputs[1][2]
    assert all(set(c) == {"value", "description"} for c in p.inputs[0][2])


def test_invalid_output_and_gate(telemetry):
    with pytest.raises(ValidationError):
        RouteChoice(action="invent_tool")
    with pytest.raises(ValidationError):
        RouteChoice(action="calculate", rationale="not allowed")
    with pytest.raises(ValueError):
        Router("hybrid", None, telemetry[0], threshold=float("nan"))
