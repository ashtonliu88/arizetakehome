from __future__ import annotations

import json
import re
from pathlib import Path

from .dataset import load_data
from .evaluation import outcome
from .models import ACTIONS
from .prompts import ANSWER_PROMPT, ARGUMENT_PROMPT
from .providers import response_text
from .routing import Router
from .tools import CATALOG, execute, load_fixtures
from .tracing import span_id, trace_id
from .util import append_jsonl, digest, now, read_jsonl

FACTS = {
    "search_docs": [["max_retries"], ["0", "zero"]],
    "search_code": [["2 **", "2**", "exponential", "power"], ["8", "eight"]],
    "lookup_issue": [["open"], ["2.3.1"]],
    "lookup_deployment": [["2.4.0"], ["staging"]],
    "lookup_test_results": [["48"], ["2"], ["fail"]],
    "calculate": [["42"]],
    "answer_directly": [["same", "repeat"], ["effect", "result", "outcome"]],
    "ask_for_clarification": [["environment", "staging", "production"]],
}


def check_answer(expected_action, answer, tool_result):
    text = answer.lower()
    facts = FACTS[expected_action]
    facts_present = all(any(value in text for value in alternatives) for alternatives in facts)
    evidence = json.dumps(tool_result)
    unsupported_versions = [v for v in re.findall(r"\b\d+\.\d+\.\d+\b", answer) if v not in evidence]
    unperformed = bool(re.search(r"\bi (?:ran|executed the tests|deployed|created a ticket)\b", text))
    missing_handled = (
        not tool_result
        or tool_result.get("found", True)
        or any(
            s in text
            for s in ["not found", "could not find", "couldn't find", "no record", "failed", "error"]
        )
    )
    return {
        "expected_facts_present": facts_present,
        "unsupported_version_claims": unsupported_versions,
        "unperformed_action_claim": unperformed,
        "tool_failure_handled": bool(missing_handled),
        "answer_success_candidate": facts_present
        and not unsupported_versions
        and not unperformed
        and bool(missing_handled),
        "human_review_status": "pending; heuristic checks do not establish absence of unsupported claims",
    }


class BudgetedJudge:
    """Phoenix prebuilt evaluator prompts, through the same metered Responses client."""

    def __init__(self, provider):
        self.provider = provider
        self.model = provider.settings.llm_model
        self.calls = []

    def generate_classification(self, prompt, labels, include_explanation=True, **kwargs):
        allowed = list(labels)
        schema = {
            "type": "object",
            "properties": {"label": {"type": "string", "enum": allowed}, "explanation": {"type": "string"}},
            "required": ["label", "explanation"],
            "additionalProperties": False,
        }
        records = self.provider.generate(
            "judge",
            json.dumps(prompt, default=str),
            schema=schema,
            instructions="Evaluate the supplied evidence using the supplied rubric. Return a label and explanation.",
        )
        self.calls.extend(records)
        if records[-1].error:
            raise RuntimeError(records[-1].error)
        return json.loads(response_text(records[-1].raw))


def semantic_evaluations(provider, request, action, arguments):
    from phoenix.evals.metrics.tool_invocation import ToolInvocationEvaluator
    from phoenix.evals.metrics.tool_selection import ToolSelectionEvaluator

    judge = BudgetedJudge(provider)
    available = json.dumps(
        [
            dict(
                t.catalog_entry(),
                parameters=t.argument_schema.model_json_schema() if t.argument_schema else None,
            )
            for t in CATALOG
        ]
    )
    evidence = {
        "input": request,
        "available_tools": available,
        "tool_selection": json.dumps({"name": action, "arguments": arguments}),
    }
    results = {}
    for name, cls in (
        ("tool_selection", ToolSelectionEvaluator),
        ("tool_invocation", ToolInvocationEvaluator),
    ):
        if name == "tool_invocation" and arguments is None:
            results[name] = {"status": "not applicable: no executable invocation"}
            continue
        try:
            scores = cls(llm=judge).evaluate(evidence)
            results[name] = [
                s.model_dump(mode="json") if hasattr(s, "model_dump") else vars(s) for s in scores
            ]
        except Exception as exc:
            from .budget import BudgetExceeded

            if isinstance(exc, BudgetExceeded):
                raise
            results[name] = {"error": str(exc)}
    return results, judge.calls


def run_demo(settings, tracing, provider, manifest, *, results_dir=Path("results"), judges=True):
    from .phoenix_io import attach_scores, phoenix_client

    client = phoenix_client()
    fixtures = load_fixtures()
    examples = {a: next(e for e in load_data(split="dev") if e.expected_action == a) for a in ACTIONS}
    path = results_dir / "demo.jsonl"
    configuration_hash = digest(
        {
            "manifest": manifest.configuration_hash,
            "fixtures": digest(Path("fixtures/support.json")),
            "judges": judges,
        }
    )
    previous = read_jsonl(path)
    if any(r["configuration_hash"] != configuration_hash for r in previous):
        raise ValueError("demo configuration changed; use a separate results directory")
    completed = {(r["policy"], r["example_id"]) for r in previous}
    for policy in ("llm", "decisions", "hybrid"):
        router = Router(
            policy, provider, tracing, threshold=manifest.threshold, always_fallback=manifest.always_fallback
        )
        for expected, example in examples.items():
            if (policy, example.example_id) in completed:
                continue
            with tracing.span(
                "developer support demo",
                "AGENT",
                **{
                    "router.example_id": example.example_id,
                    "router.policy": policy,
                    "input.value": example.request,
                },
            ) as agent:
                result = router.route(example.request)
                action = result.final_action
                arguments, tool_result, tool_span_id = None, None, None
                argument_valid, lookup_success = None, None
                extra_calls = []
                tool = next((t for t in CATALOG if t.action_id == action), None)
                if tool and tool.argument_schema:
                    records = provider.generate(
                        "arguments",
                        example.request,
                        schema=tool.argument_schema.model_json_schema(),
                        instructions=ARGUMENT_PROMPT + "\nSelected tool: " + json.dumps(tool.catalog_entry()),
                    )
                    extra_calls.extend(records)
                    try:
                        if records[-1].error:
                            raise ValueError(records[-1].error)
                        arguments = json.loads(response_text(records[-1].raw))
                        validated = tool.argument_schema.model_validate(arguments)
                        argument_valid = True
                        with tracing.span(action, "TOOL", **{"input.value": arguments}) as tool_span:
                            tool_span_id = span_id(tool_span)
                            tool_result = execute(action, validated.model_dump(), fixtures)
                            tool_span.set_attribute("output.value", json.dumps(tool_result))
                        lookup_success = tool_result.get("found", False)
                    except (ValueError, KeyError, TypeError) as exc:
                        argument_valid = False
                        tool_result = {"found": False, "error": f"argument validation failed: {exc}"}
                if action:
                    records = provider.generate(
                        "answer",
                        json.dumps(
                            {
                                "request": example.request,
                                "selected_action": action,
                                "tool_result": tool_result,
                            }
                        ),
                        instructions=ANSWER_PROMPT,
                    )
                    extra_calls.extend(records)
                    answer = response_text(records[-1].raw) if not records[-1].error else ""
                else:
                    answer = ""
                agent.set_attribute("output.value", answer)
                agent_span_id, agent_trace_id = span_id(agent), trace_id(agent)
            # Evaluators see labels only after inference is complete.
            attach_scores(client, tracing, result, expected)
            evaluations, judge_calls = (
                semantic_evaluations(provider, example.request, action, arguments)
                if judges and action
                else ({}, [])
            )
            all_calls = result.calls + extra_calls + judge_calls
            checks = check_answer(expected, answer, tool_result)
            row = {
                "example_id": example.example_id,
                "policy": policy,
                "expected_action": expected,
                "timestamp": now(),
                "configuration_hash": configuration_hash,
                "request": example.request,
                "route": result.model_dump(mode="json"),
                "arguments": arguments,
                "tool_result": tool_result,
                "argument_valid": argument_valid,
                "lookup_success": lookup_success,
                "answer": answer,
                "tool_span_id": tool_span_id,
                "agent_span_id": agent_span_id,
                "trace_id": agent_trace_id,
                "semantic_second_opinions": evaluations,
                "extra_calls": [c.model_dump(mode="json") for c in extra_calls + judge_calls],
                "total_cost_usd": sum(c.cost_usd for c in all_calls),
                **outcome(result, expected),
                **checks,
            }
            append_jsonl(path, row)
            tracing.provider.force_flush()
            client.spans.log_span_annotations(
                span_annotations=[
                    {
                        "span_id": agent_span_id,
                        "name": "answer_success_candidate",
                        "annotator_kind": "CODE",
                        "result": {
                            "score": float(checks["answer_success_candidate"]),
                            "explanation": "Lexical expected-fact and limited unsupported-claim checks; human review pending.",
                        },
                    }
                ],
                sync=True,
            )
    return {"rows": len(read_jsonl(path)), "path": str(path), "human_review": "pending"}
