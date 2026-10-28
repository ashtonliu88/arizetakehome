from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from .models import RouteResult
from .phoenix_io import attach_scores, phoenix_client
from .routing import Router
from .tracing import span_id, trace_id
from .util import digest, now, write_json

SMOKE_PATH = Path("results/smoke.json")


def run_smoke(tracing, provider=None):
    """Real Phoenix writes, deterministic grades; provider calls only when requested."""
    client = phoenix_client()
    name = "router-lab-smoke"
    try:
        dataset = client.datasets.get_dataset(dataset=name)
    except Exception as exc:
        if (
            not (isinstance(exc, ValueError) and str(exc).startswith("Dataset not found:"))
            and getattr(getattr(exc, "response", None), "status_code", None) != 404
        ):
            raise
        dataset = client.datasets.create_dataset(
            name=name,
            dataframe=pd.DataFrame(
                [
                    {"request": "Add 1 and 1", "expected_action": "calculate"},
                    {"request": "Explain a unit test", "expected_action": "answer_directly"},
                ]
            ),
            input_keys=["request"],
            output_keys=["expected_action"],
        )
    recorded = []

    def task(input):
        with tracing.span("smoke mock policy", "CHAIN", **{"input.value": input["request"]}) as root:
            with tracing.span("smoke mocked decision", "DECISION") as decision:
                initial_id = span_id(decision)
            with tracing.span("smoke mocked response", "LLM") as llm:
                final_id = span_id(llm)
            result = RouteResult(
                initial_action="calculate",
                final_action="calculate",
                trace_id=trace_id(root),
                policy_span_id=span_id(root),
                initial_span_id=initial_id,
                final_span_id=final_id,
            )
            recorded.append(result)
            return result.model_dump(mode="json")

    def accuracy(output, expected):
        result = RouteResult.model_validate(output)
        attach_scores(client, tracing, result, expected["expected_action"])
        return output["final_action"] == expected["expected_action"]

    experiment = client.experiments.run_experiment(
        dataset=dataset,
        task=task,
        evaluators={"route_accuracy": accuracy},
        experiment_name=f"smoke-mocked-{now()}",
        repetitions=1,
        retries=0,
        timeout=None,
        experiment_metadata={"synthetic": True, "purpose": "setup acceptance; not research"},
    )
    scores = []
    for evaluation in experiment["evaluation_runs"]:
        result = evaluation.result
        if result is None:
            raise ValueError("smoke evaluator failed; inspect Phoenix and command logs")
        scores.append(result["score"] if isinstance(result, dict) else result.score)
    if sorted(scores) != [0.0, 1.0]:
        raise ValueError(f"smoke grades must contain zero and one, got {scores}")
    live = []
    if provider:
        for policy in ("decisions", "llm"):
            result = Router(policy, provider, tracing).route("Calculate 1 plus 1.")
            if result.final_action is None or result.errors:
                raise RuntimeError(f"live {policy} smoke failed: {result.errors}")
            live.append(result.model_dump(mode="json"))
        tracing.provider.force_flush()
    spans = all_spans(client, [experiment["project_name"]])
    ids = set(spans["context.span_id"].astype(str))
    for result in recorded:
        if result.policy_span_id not in ids:
            raise RuntimeError("manual smoke trace not visible in Phoenix")
    if live:
        kinds = dict(zip(spans["context.span_id"].astype(str), spans["span_kind"], strict=False))
        for row, required in zip(live, ("DECISION", "LLM"), strict=True):
            if str(kinds.get(row["final_span_id"])) != required:
                raise RuntimeError(f"automatic {required} span missing; check instrumentor version")
    result = {
        "timestamp": now(),
        "dataset_id": dataset.id,
        "experiment_id": experiment["experiment_id"],
        "mock_scores": scores,
        "policy_span_ids": [r.policy_span_id for r in recorded],
        "live": live,
        "live_verified": bool(live),
        "persistence_verified": False,
        "endpoint_hash": digest(os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")),
        "status": "local Phoenix passed; live calls pending"
        if not live
        else "live passed; restart check pending",
    }
    write_json(SMOKE_PATH, result)
    return result


def check_persistence():
    import json

    result = json.loads(SMOKE_PATH.read_text())
    client = phoenix_client()
    experiment = client.experiments.get_experiment(experiment_id=result["experiment_id"])
    if len(experiment["task_runs"]) != 2:
        raise ValueError("persisted smoke experiment missing")
    spans = all_spans(client, [experiment.get("project_name")])
    if not set(result["policy_span_ids"]) <= set(spans["context.span_id"].astype(str)):
        raise ValueError("persisted smoke traces missing")
    result["persistence_verified"] = True
    result["persistence_checked_at"] = now()
    result["status"] = "persistent local Phoenix passed" + (
        "; live passed" if result["live_verified"] else "; live pending"
    )
    write_json(SMOKE_PATH, result)
    return result


def all_spans(client, experiment_projects=()):
    # Experiment capture may assign its own project resource to application spans.
    names = {p["name"] for p in client.projects.list()} | {p for p in experiment_projects if p}
    frames = [client.spans.get_spans_dataframe(project_name=name, limit=10000) for name in names]
    frames = [f for f in frames if not f.empty]
    return (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["context.span_id", "span_kind"])
    )
