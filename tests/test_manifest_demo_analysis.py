from pathlib import Path

import pytest

from router_lab.dataset import load_data
from router_lab.demo import check_answer
from router_lab.manifest import require_label_review
from router_lab.models import CallRecord, RouteResult
from router_lab.phoenix_io import annotations_for


def test_human_review_is_never_fabricated(tmp_path):
    with pytest.raises(ValueError, match="labels need human review"):
        require_label_review(load_data(), tmp_path / "review.jsonl")


def test_initial_and_final_annotations_have_different_responsibility():
    r = RouteResult(
        initial_action="calculate",
        final_action="search_docs",
        fallback=True,
        initial_span_id="0000000000000001",
        final_span_id="0000000000000002",
        policy_span_id="0000000000000003",
    )
    rows = annotations_for(r, "search_docs")
    assert [(r["span_id"], r["result"]["score"]) for r in rows] == [
        ("0000000000000001", 0),
        ("0000000000000002", 1),
        ("0000000000000003", 1),
    ]


def test_demo_expected_facts_and_unsupported_claim_flags():
    good = check_answer(
        "lookup_issue", "ENG-101 is open. Use version 2.3.1.", {"found": True, "record": {"version": "2.3.1"}}
    )
    assert good["answer_success_candidate"]
    bad = check_answer("lookup_issue", "I deployed version 9.9.9.", {"found": False, "error": "not found"})
    assert not bad["answer_success_candidate"]
    assert bad["unsupported_version_claims"] == ["9.9.9"]
    assert bad["unperformed_action_claim"]
    assert not bad["tool_failure_handled"]
    assert "pending" in good["human_review_status"]


def test_prebuilt_phoenix_evaluators_use_metered_client():
    from router_lab.demo import semantic_evaluations

    class FakeProvider:
        class settings:
            llm_model = "mock-judge"

        calls = []

        def generate(self, kind, request, **kwargs):
            self.calls.append((kind, request, kwargs))
            return [
                CallRecord(
                    kind="judge",
                    raw={
                        "status": "completed",
                        "output": [
                            {
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": '{"label":"correct","explanation":"fixture"}',
                                    }
                                ]
                            }
                        ],
                    },
                )
            ]

    p = FakeProvider()
    results, calls = semantic_evaluations(
        p, "Add 1 and 1", "calculate", {"operation": "add", "left": 1, "right": 1}
    )
    assert len(p.calls) == 2 and len(calls) == 2
    assert results["tool_selection"][0]["score"] == 1
    assert results["tool_invocation"][0]["score"] == 1
    assert all(c[0] == "judge" for c in p.calls)


def test_offline_analysis_artifact_and_synthetic_guard(tmp_path):
    from router_lab.analysis import analyze

    source = Path("results/offline-example/runs.jsonl")
    summary = analyze(source, tmp_path, synthetic=True)
    assert summary["bootstrap"]["independent_questions"] == 8
    assert summary["measurement"].startswith("SYNTHETIC")
    assert len(summary["policies"]) == 3
    for figure in ["accuracy-cost.png", "latency.png", "reliability.png", "margin.png"]:
        assert (tmp_path / figure).stat().st_size > 1000
    with pytest.raises(ValueError, match="frozen manifest"):
        analyze(source, tmp_path / "invalid", synthetic=False, frozen_path=tmp_path / "missing.json")


def test_full_demo_executes_tools_and_separates_route_and_answer(telemetry, tmp_path, monkeypatch, settings):
    import json
    from types import SimpleNamespace

    from router_lab.demo import run_demo
    from router_lab.models import ACTIONS
    from router_lab.tracing import span_id
    from router_lab.util import read_jsonl

    tracing, exporter = telemetry
    examples = {e.request: e.expected_action for e in load_data(split="dev") if e.example_id.endswith("-01")}
    arguments = {
        "search_docs": {"query": "disable SDK retries"},
        "search_code": {"query": "retry_delay"},
        "lookup_issue": {"issue_id": "ENG-101"},
        "lookup_deployment": {"service": "payments", "environment": "staging"},
        "lookup_test_results": {"test_run_id": "TR-101"},
        "calculate": {"operation": "add", "left": 12, "right": 30},
    }
    answers = {
        "search_docs": "Set max_retries to 0.",
        "search_code": "return min(2 ** attempt, 8)",
        "lookup_issue": "It is open; use version 2.3.1.",
        "lookup_deployment": "Staging uses version 2.4.0.",
        "lookup_test_results": "48 passed and 2 failed.",
        "calculate": "42",
        "answer_directly": "Repeated calls have the same effect.",
        "ask_for_clarification": "Which environment?",
    }

    class FakeClient:
        def __init__(self):
            self.spans = self
            self.annotations = []

        def log_span_annotations(self, span_annotations, sync=False):
            self.annotations.extend(span_annotations)

    client = FakeClient()
    monkeypatch.setattr("router_lab.phoenix_io.phoenix_client", lambda: client)

    class FakeProvider:
        def __init__(self):
            self.settings = settings

        def call(self, kind, request, catalog):
            action = examples[request]
            with tracing.span("fake route", "DECISION" if kind == "decisions" else "LLM") as s:
                return [
                    CallRecord(
                        kind=kind,
                        action=action,
                        confidence=0.5 if kind == "decisions" else None,
                        probabilities={a: float(a == action) for a in ACTIONS} if kind == "decisions" else {},
                        span_id=span_id(s),
                    )
                ]

        def generate(self, kind, request, **kwargs):
            if kind == "judge":
                text = '{"label":"correct","explanation":"explicit test fixture"}'
            elif kind == "arguments":
                text = json.dumps(arguments[examples[request]])
            else:
                text = answers[json.loads(request)["selected_action"]]
            with tracing.span("fake generation", "LLM") as s:
                return [
                    CallRecord(
                        kind=kind,
                        raw={
                            "status": "completed",
                            "output": [{"content": [{"type": "output_text", "text": text}]}],
                        },
                        span_id=span_id(s),
                    )
                ]

    manifest = SimpleNamespace(configuration_hash="test-only", threshold=0.7, always_fallback=False)
    output = run_demo(settings, tracing, FakeProvider(), manifest, results_dir=tmp_path)
    rows = read_jsonl(tmp_path / "demo.jsonl")
    assert output["rows"] == len(rows) == 24
    assert sum(r["argument_valid"] is True for r in rows) == 18
    assert sum(r["lookup_success"] is True for r in rows) == 18
    assert all(r["answer_success_candidate"] for r in rows)
    assert all(r["route"]["fallback"] for r in rows if r["policy"] == "hybrid")
    assert (
        sum(s.attributes.get("openinference.span.kind") == "AGENT" for s in exporter.get_finished_spans())
        == 24
    )
    assert (
        sum(s.attributes.get("openinference.span.kind") == "TOOL" for s in exporter.get_finished_spans())
        == 18
    )
    assert all(r["human_review_status"].startswith("pending") for r in rows)
    # Completed demos are resumable without invoking a fake or paid provider again.
    assert run_demo(settings, tracing, None, manifest, results_dir=tmp_path)["rows"] == 24
