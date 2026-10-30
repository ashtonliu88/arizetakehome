"""Publish saved measurements after execution; never a part of response latency."""

from __future__ import annotations

import json
import os
from datetime import datetime

from opentelemetry.trace import set_span_in_context
from phoenix.otel import register

from ..phoenix_io import log_annotations, phoenix_client
from ..util import digest, read_jsonl, write_json
from .study import config_hash, inputs_and_references, verify_freeze


def publish(root, settings):
    verify_freeze(root, settings)
    rows = [
        r
        for r in read_jsonl(root / "runs.jsonl")
        if r["split"] == "test" and r["configuration"] == config_hash(root, settings)
    ]
    if not rows:
        raise ValueError("no held-out measurements to publish")
    result_hash = digest(rows)
    receipt = root / "published.json"
    if receipt.exists() and json.loads(receipt.read_text())["result_hash"] == result_hash:
        return json.loads(receipt.read_text())
    client = phoenix_client()
    # Confirm the collector exists before creating an OTLP exporter.
    client.projects.list()
    provider = register(
        project_name="verified-plan-reuse",
        endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"),
        protocol="http/protobuf",
        auto_instrument=False,
        set_global_tracer_provider=False,
    )
    tracer = provider.get_tracer("router_lab.reuse.saved_measurements")
    cases, _ = inputs_and_references(root)
    by_id = {c["id"]: c for c in cases}
    starts = {
        r["run_id"]: r["timestamp"] for r in read_jsonl(root / "endpoints.jsonl") if r["state"] == "started"
    }
    annotations, links = [], []
    try:
        for row in rows:
            record = row["record"]
            start = int(datetime.fromisoformat(starts[row["run_id"]]).timestamp() * 1e9)
            duration = int(record["timings_ms"]["end_to_end"] * 1e6)
            parent = tracer.start_span(f"{row['policy']} / {row['bank_state']}", start_time=start)
            parent.set_attributes(
                {
                    "openinference.span.kind": "AGENT",
                    "input.value": by_id[row["case_id"]]["input"]["request"],
                    "output.value": record["answer"],
                    "reuse.run_id": row["run_id"],
                    "reuse.cache_hit": record["cache_hit"],
                    "reuse.policy": row["policy"],
                    "reuse.bank_state": row["bank_state"],
                    "reuse.status": record["status"],
                    "reuse.cost_usd": record["cost_usd"],
                    "reuse.case_id": row["case_id"],
                    "reuse.measurement": "saved real endpoint measurement",
                }
            )
            for call in record["calls"]:
                at = int(datetime.fromisoformat(call["timestamp"]).timestamp() * 1e9)
                child = tracer.start_span(call["kind"], context=set_span_in_context(parent), start_time=at)
                child.set_attributes(
                    {
                        "openinference.span.kind": "LLM",
                        "llm.model_name": settings.llm_model,
                        "llm.token_count.prompt": call["usage"]["input_tokens"],
                        "llm.token_count.completion": call["usage"]["output_tokens"],
                        "llm.token_count.prompt_details.cache_read": call["usage"]["cache_read_tokens"],
                        "llm.cost.total": call["cost_usd"],
                        "output.value": call.get("output", ""),
                        "reuse.provider_response_id": call.get("response_id") or "unknown",
                    }
                )
                child.end(end_time=min(start + duration, at + int(call["latency_ms"] * 1e6)))
            for execution in record["executions"]:
                at = int(datetime.fromisoformat(execution["started_at"]).timestamp() * 1e9)
                child = tracer.start_span(
                    execution["tool"], context=set_span_in_context(parent), start_time=at
                )
                child.set_attributes(
                    {
                        "openinference.span.kind": "TOOL",
                        "tool.name": execution["tool"],
                        "input.value": json.dumps(execution["arguments"]),
                        "output.value": json.dumps(execution["result"]),
                        "reuse.bindings": json.dumps(execution["bindings"]),
                        "reuse.tenant": execution["tenant"],
                        "reuse.fixture_state_version": execution["state_version"],
                    }
                )
                child.end(end_time=at + int(execution["latency_ms"] * 1e6))
            sid = f"{parent.get_span_context().span_id:016x}"
            tid = f"{parent.get_span_context().trace_id:032x}"
            parent.end(end_time=start + duration)
            for name in (
                "success",
                "resource_correct",
                "incorrect_accepted_reuse",
                "authorization_violations",
            ):
                annotations.append(
                    {
                        "span_id": sid,
                        "name": "reuse_" + name,
                        "annotator_kind": "CODE",
                        "result": {"score": float(row["evaluation"][name])},
                    }
                )
            links.append({"run_id": row["run_id"], "trace_id": tid, "span_id": sid})
        provider.force_flush()
        for index in range(0, len(annotations), 100):
            log_annotations(client, annotations[index : index + 100])
    finally:
        provider.shutdown()
    result = {
        "result_hash": result_hash,
        "project": "verified-plan-reuse",
        "endpoint": os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006"),
        "published_endpoints": len(rows),
        "traces": links,
    }
    write_json(receipt, result)
    return {k: v for k, v in result.items() if k != "traces"}
