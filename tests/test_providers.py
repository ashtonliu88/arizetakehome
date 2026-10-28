import json

import httpx
import pytest
from openai import OpenAI
from openinference.instrumentation.openai import OpenAIInstrumentor

from router_lab.budget import Budget
from router_lab.models import ACTIONS
from router_lab.providers import OpenAIProvider
from router_lab.routing import Router
from router_lab.util import read_jsonl


def decision_body(confidence=0.8):
    return {
        "model": "gpt-6-luna",
        "answers": [
            {
                "type": "choice",
                "name": "next_action",
                "choice": "calculate",
                "confidence": confidence,
                "probabilities": [
                    {"value": a, "probability": 1.0 if a == "calculate" else 0.0} for a in ACTIONS
                ],
            }
        ],
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 0,
            "total_tokens": 1000,
            "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 100},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def llm_body(text='{"action":"calculate"}', status="completed", content_type="output_text"):
    return {
        "id": "resp_mock",
        "object": "response",
        "created_at": 1,
        "model": "gpt-6.1-sol",
        "status": status,
        "output": [
            {
                "id": "msg_mock",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": content_type,
                        "refusal" if content_type == "refusal" else "text": text,
                        "annotations": [],
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 50,
            "total_tokens": 1050,
            "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 100},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


@pytest.fixture
def instrumented(telemetry):
    tracing, exporter = telemetry
    instrumentor = OpenAIInstrumentor()
    # The real-Phoenix integration test uses auto instrumentation in this process.
    # Rebind the test-only instrumentation to this fixture's in-memory provider.
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()
    instrumentor.instrument(tracer_provider=tracing.provider)
    yield tracing, exporter
    instrumentor.uninstrument()


def make_provider(settings, tracing, tmp_path, handler):
    client = OpenAI(
        api_key="unit-test-only",
        base_url="https://mock.invalid/v1",
        max_retries=0,
        timeout=30,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return OpenAIProvider(
        settings, tracing, Budget(tmp_path / "ledger.jsonl"), tmp_path / "calls.jsonl", client=client
    )


def test_actual_sdk_shapes_and_automatic_span_kinds(settings, instrumented, tmp_path):
    tracing, exporter = instrumented
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json=decision_body() if request.url.path.endswith("decisions") else llm_body()
        )

    p = make_provider(settings, tracing, tmp_path, handler)
    decision = Router("decisions", p, tracing).route("Add 1 and 1")
    llm = Router("llm", p, tracing).route("Add 1 and 1")
    spans = {f"{s.context.span_id:016x}": s for s in exporter.get_finished_spans()}
    assert spans[decision.final_span_id].attributes["openinference.span.kind"] == "DECISION"
    assert spans[llm.final_span_id].attributes["openinference.span.kind"] == "LLM"
    assert decision.decision_confidence == 0.8
    assert decision.maximum_probability == 1
    assert decision.probability_margin == 1
    assert decision.usage.cache_write_tokens == 100
    assert p.client.max_retries == 0
    assert requests[0]["input"] == requests[1]["input"] == "Add 1 and 1"
    assert requests[1]["reasoning"]["effort"] == "low"
    assert requests[1]["max_output_tokens"] == 512
    assert all("expected_action" not in json.dumps(r) and "rationale" not in json.dumps(r) for r in requests)
    assert p.budget.spent == pytest.approx(decision.cost_usd + llm.cost_usd)


@pytest.mark.parametrize(
    "defect", ["refusal", "invalid_confidence", "missing_probability", "duplicate_probability", "bad_route"]
)
def test_decision_operational_fallback(settings, instrumented, tmp_path, defect):
    tracing, _ = instrumented
    body = decision_body()
    a = body["answers"][0]
    if defect == "refusal":
        body["answers"] = [{"name": "next_action", "type": "refusal"}]
    elif defect == "invalid_confidence":
        a["confidence"] = None
    elif defect == "missing_probability":
        a["probabilities"].pop()
    elif defect == "duplicate_probability":
        a["probabilities"].append(a["probabilities"][0])
    else:
        a["choice"] = "run_tests"

    def handler(request):
        return httpx.Response(200, json=body if request.url.path.endswith("decisions") else llm_body())

    p = make_provider(settings, tracing, tmp_path, handler)
    r = Router("hybrid", p, tracing, threshold=0).route("Add 1 and 1")
    assert r.fallback_reason == "operational"
    assert r.final_action == "calculate"
    assert len(r.calls) == 2
    assert r.calls[0].raw == body
    assert r.cost_usd > r.calls[1].cost_usd
    assert not r.calls[0].cost_estimated  # usage preserved even if normalization fails


@pytest.mark.parametrize(
    "body",
    [
        llm_body(status="incomplete"),
        llm_body("no", content_type="refusal"),
        llm_body("{broken"),
        llm_body('{"action":"invented"}'),
    ],
)
def test_invalid_llm_remains_visible(settings, instrumented, tmp_path, body):
    tracing, _ = instrumented
    p = make_provider(settings, tracing, tmp_path, lambda request: httpx.Response(200, json=body))
    r = Router("llm", p, tracing).route("request")
    assert r.final_action is None
    assert len(r.calls) == 1
    assert r.errors and r.cost_usd > 0
    assert read_jsonl(tmp_path / "calls.jsonl")[0]["raw"] == body


def test_timeout_retries_owned_by_application(settings, instrumented, tmp_path, monkeypatch):
    tracing, _ = instrumented
    requests, sleeps = [], []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path.endswith("decisions"):
            raise httpx.ReadTimeout("simulated", request=request)
        return httpx.Response(200, json=llm_body())

    monkeypatch.setattr("router_lab.providers.time.sleep", lambda value: sleeps.append(value))
    p = make_provider(settings, tracing, tmp_path, handler)
    r = Router("hybrid", p, tracing, threshold=0).route("Add 1 and 1")
    assert len(requests) == 4 and len(r.calls) == 4
    assert sleeps == [1, 2]
    assert r.fallback_reason == "operational"
    assert r.final_action == "calculate"
    assert all(c.cost_estimated for c in r.calls[:3])
    assert p.budget.spent == pytest.approx(r.cost_usd)


def test_nontransient_failure_has_no_retry(settings, instrumented, tmp_path):
    tracing, _ = instrumented
    count = []

    def handler(request):
        count.append(1)
        return httpx.Response(401, json={"error": {"message": "bad credentials", "type": "auth_error"}})

    p = make_provider(settings, tracing, tmp_path, handler)
    r = Router("llm", p, tracing).route("request")
    assert len(count) == 1 and r.final_action is None
    assert r.calls[0].cost_estimated
