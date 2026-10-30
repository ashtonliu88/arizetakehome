"""Runtime imports no dataset, labels, scoring references, or evaluation modules."""

from __future__ import annotations

import time

from ..util import now
from .bank import compatible, resolve, retrieve
from .bindings import bind
from .contracts import ExecutionRecord, PlannedResponse
from .service import GuardError


def execute_request(inp, policy, bank, settings, model, adapter, run_id, *, bank_state="warm"):
    start = time.perf_counter()
    bindings = bind(inp)
    record = ExecutionRecord(run_id=run_id, policy=policy, bank_state=bank_state, bindings=bindings)
    record.timings_ms["binding"] = (time.perf_counter() - start) * 1000
    plan = None
    retrieval_start = time.perf_counter()
    # Direct/clarification cases have no admissible templates, so no extra answer call.
    if (
        policy != "fused"
        and bindings.slots
        and not bindings.unresolved
        and "requires_planning" not in bindings.semantics
    ):
        candidate, score, margin = retrieve(bindings, bank, exact=policy == "exact")
        record.retrieval_score, record.retrieval_margin = score, margin
        if candidate:
            record.candidate = candidate.template_id
            if score < settings.threshold or margin < settings.margin:
                record.rejection = "retrieval_threshold_or_margin"
            elif policy != "ordinary":
                record.rejection = compatible(candidate, bindings, semantic=policy == "verified")
            # Ordinary is deliberately an isolated read-only ablation; all execution
            # guards below remain mandatory, even when cache compatibility is skipped.
            if not record.rejection:
                plan = PlannedResponse(kind="tools", steps=candidate.steps)
                record.cache_hit = True
        else:
            record.rejection = "empty_bank" if not bank else "no_candidate"
    record.timings_ms["retrieval_validation"] = (time.perf_counter() - retrieval_start) * 1000
    feedback = None
    successful_outputs = []
    for attempt in range(2):
        if plan is None:
            plan, call = model.plan(inp, bindings, feedback)
            record.calls.append(call)
            if plan is None:
                record.status, record.error = "transport_failure", call.get("error") or "invalid_plan"
                break
        if plan.kind != "tools":
            record.answer = plan.response
            record.status = {"clarify": "clarified", "abstain": "abstained", "direct": "completed"}[plan.kind]
            break
        try:
            outputs = []
            for index in range(len(plan.steps)):
                if len(record.executions) >= 3:
                    raise GuardError("three-step endpoint limit")
                step = resolve(plan.steps, bindings, outputs, index)
                tool_start = time.perf_counter()
                tool_timestamp = now()
                output = adapter.execute(step, inp.context)
                record.executions.append(
                    dict(
                        output,
                        latency_ms=(time.perf_counter() - tool_start) * 1000,
                        started_at=tool_timestamp,
                    )
                )
                if not output["result"].get("found"):
                    raise LookupError("resource not found or invalid arithmetic")
                outputs.append(output)
            successful_outputs = outputs
            record.answer, call = model.answer(inp, successful_outputs)
            record.calls.append(call)
            record.status = "completed" if not call.get("error") else "transport_failure"
            break
        except GuardError as exc:
            record.status, record.error = "safe_failure", str(exc)
            break
        except (KeyError, ValueError, LookupError, OSError) as exc:
            if attempt == 0 and len(record.executions) < 3:
                record.replans += 1
                feedback, plan = type(exc).__name__, None
            else:
                record.status, record.error = (
                    "semantic_failure"
                    if isinstance(exc, (LookupError, KeyError, ValueError))
                    else "transport_failure",
                    type(exc).__name__,
                )
    record.cost_usd = sum(c["cost_usd"] for c in record.calls)
    record.timings_ms.update(
        planning=sum(c["latency_ms"] for c in record.calls if c["kind"] == "planning"),
        answer=sum(c["latency_ms"] for c in record.calls if c["kind"] == "answer"),
        tools=sum(e["latency_ms"] for e in record.executions),
        runtime=(time.perf_counter() - start) * 1000,
    )
    return record, plan
