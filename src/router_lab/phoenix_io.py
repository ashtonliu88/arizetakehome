from __future__ import annotations

import os
import time
from pathlib import Path

from phoenix.client import Client

from .dataset import load_data, validate_data
from .models import RouteResult
from .util import digest, write_json

DATASET_NAME = "router-benchmark-v1"


def phoenix_client():
    return Client(base_url=os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006"))


def upload_data(client=None, path=Path("data/benchmark.jsonl")):
    client = client or phoenix_client()
    examples = load_data(path)
    validate_data(examples)
    try:
        dataset = client.datasets.get_dataset(dataset=DATASET_NAME)
    except Exception as exc:
        if (
            not (isinstance(exc, ValueError) and str(exc).startswith("Dataset not found:"))
            and getattr(getattr(exc, "response", None), "status_code", None) != 404
        ):
            raise
        dataset = client.datasets.create_dataset(
            name=DATASET_NAME,
            # The tabular uploader serializes list-valued tags into Python strings.
            # Native JSON examples preserve metadata types and explicit splits.
            examples=[
                {
                    "input": e.model_input(),
                    "output": {"expected_action": e.expected_action},
                    "metadata": {
                        k: getattr(e, k) for k in ("example_id", "tags", "rationale", "paraphrase_group")
                    },
                    "splits": [e.split],
                }
                for e in examples
            ],
            dataset_description=f"120 balanced authored next-action examples; sha256={digest(path)}",
        )
    expected = {e.example_id: e for e in examples}
    if len(dataset.examples) != 120:
        raise ValueError("existing Phoenix dataset has a different size; version it explicitly")
    for row in dataset.examples:
        example = expected.get(row["metadata"]["example_id"])
        if (
            example is None
            or row["input"] != example.model_input()
            or row["output"] != {"expected_action": example.expected_action}
        ):
            raise ValueError("Phoenix dataset differs from local benchmark; do not overwrite silently")
        for key in ("tags", "rationale", "paraphrase_group"):
            if row["metadata"].get(key) != getattr(example, key):
                raise ValueError(f"Phoenix metadata differs: {key}")
    for split, count in (("dev", 40), ("test", 80)):
        subset = client.datasets.get_dataset(dataset=DATASET_NAME, splits=[split])
        actual_ids = {r["metadata"]["example_id"] for r in subset.examples}
        if len(subset.examples) != count or actual_ids != {
            e.example_id for e in examples if e.split == split
        }:
            raise ValueError("Phoenix dataset split mismatch")
    write_json(
        Path("results/dataset.json"),
        {
            "dataset_id": dataset.id,
            "version_id": dataset.version_id,
            "dataset_hash": digest(path),
            "dev": 40,
            "test": 80,
        },
    )
    return dataset


def annotations_for(result: RouteResult, expected: str) -> list[dict]:
    entries = []
    for target, name, correct in (
        (result.initial_span_id, "initial_route_accuracy", result.initial_action == expected),
        (result.final_span_id, "selected_route_accuracy", result.final_action == expected),
        (result.policy_span_id, "final_route_accuracy", result.final_action == expected),
    ):
        if target:
            entries.append(
                {
                    "span_id": target,
                    "name": name,
                    "annotator_kind": "CODE",
                    "result": {"score": float(correct), "label": "correct" if correct else "incorrect"},
                }
            )
    return entries


def attach_scores(client, tracing, result: RouteResult, expected: str):
    tracing.provider.force_flush()
    entries = annotations_for(result, expected)
    if entries:
        log_annotations(client, entries)


def log_annotations(client, entries):
    # OTLP collection acknowledges before asynchronous database ingestion finishes.
    for delay in (0.1, 0.25, 0.5, 1, 2, 4, None):
        try:
            return client.spans.log_span_annotations(span_annotations=entries, sync=True)
        except Exception as exc:
            if delay is None or getattr(getattr(exc, "response", None), "status_code", None) != 404:
                raise
            time.sleep(delay)
