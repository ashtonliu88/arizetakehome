from __future__ import annotations

import json
from pathlib import Path

from .budget import BudgetExceeded
from .dataset import load_data, validate_data
from .evaluation import outcome
from .manifest import (
    current_manifest,
    require_label_review,
    save_manifest,
    verify_frozen,
)
from .models import RouteResult
from .phoenix_io import DATASET_NAME, attach_scores, phoenix_client, upload_data
from .routing import Router
from .tools import catalog_payload
from .util import append_jsonl, digest, now, read_jsonl, write_json


class Checkpoints:
    def __init__(self, path: Path, configuration_hash: str):
        self.path, self.configuration_hash = path, configuration_hash
        self.completed = {}
        for row in read_jsonl(path):
            if row["configuration_hash"] != configuration_hash:
                raise ValueError("checkpoint configuration differs; use a separate results directory")
            key = (row["policy"], row["example_id"], row["repetition"])
            if key in self.completed:
                raise ValueError(f"duplicate checkpoint: {key}")
            self.completed[key] = row

    def get(self, policy, example_id, repetition):
        return self.completed.get((policy, example_id, repetition))

    def add(self, row):
        key = (row["policy"], row["example_id"], row["repetition"])
        if key in self.completed:
            raise ValueError("refusing duplicate completed experiment row")
        if row["configuration_hash"] != self.configuration_hash:
            raise ValueError("configuration mismatch")
        append_jsonl(self.path, row)
        self.completed[key] = row


def require_setup():
    path = Path("results/smoke.json")
    if not path.exists():
        raise ValueError("run router-lab smoke --live before the benchmark")
    smoke = json.loads(path.read_text())
    if not smoke.get("live_verified") or not smoke.get("persistence_verified"):
        raise ValueError("setup milestone incomplete: live smoke and Phoenix restart check required")
    import os

    endpoint = digest(os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"))
    if smoke["endpoint_hash"] != endpoint:
        raise ValueError("OpenAI endpoint changed since live smoke; repeat setup acceptance")


def run_benchmark(settings, tracing, provider, split, *, frozen=False, results_dir=Path("results")):
    # Guard before reading held-out outputs, initializing clients, or scheduling calls.
    if split == "test" and not frozen:
        raise ValueError("test command requires --frozen")
    manifest = (
        verify_frozen(settings, results_dir / "frozen.json")
        if split == "test"
        else current_manifest(settings)
    )
    examples = load_data()
    validate_data(examples)
    require_label_review(examples)
    require_setup()
    examples = [e for e in examples if e.split == split]
    client = phoenix_client()
    upload_data(client)
    dataset = client.datasets.get_dataset(dataset=DATASET_NAME, splits=[split])
    checkpoints = Checkpoints(results_dir / f"{split}.jsonl", manifest.configuration_hash)
    save_manifest(results_dir / f"{split}-manifest.json", manifest)
    policies = ["llm", "decisions"] if split == "dev" else ["llm", "decisions", "hybrid"]
    lookup = {e.request: e for e in examples}
    experiment_log = results_dir / f"{split}-experiments.json"
    completed_experiments = json.loads(experiment_log.read_text()) if experiment_log.exists() else {}
    # Project the remaining full run using observed usage where possible. Per-attempt
    # reservations still stop scheduling if the projection underestimates usage.
    projected = 0.0
    for policy in policies:
        observed = [r["result"]["cost_usd"] for r in checkpoints.completed.values() if r["policy"] == policy]
        bound = provider.estimate_call(
            "decisions" if policy != "llm" else "llm", "x" * 1000, catalog_payload()
        )
        if policy == "hybrid":
            bound += provider.estimate_call("llm", "x" * 1000, catalog_payload())
        mean = sum(observed) / len(observed) * 1.5 if observed else bound
        pending = sum(
            checkpoints.get(policy, e.example_id, r) is None
            for e in examples
            for r in range(1, settings.repetitions + 1)
        )
        projected += pending * mean
    provider.budget.check(projected)
    print(
        f"Projected remaining run cost: ${projected:.4f}; ledger ${provider.budget.spent:.4f} (reserve ${settings.reserve_usd:.2f})."
    )
    for repetition in range(1, settings.repetitions + 1):
        order = policies[(repetition - 1) % len(policies) :] + policies[: (repetition - 1) % len(policies)]
        for policy in order:
            name = f"router-{split}-{policy}-r{repetition}-{manifest.configuration_hash[:12]}"
            if name in completed_experiments:
                persisted = client.experiments.get(experiment_id=completed_experiments[name])
                if persisted["name"] != name:
                    raise ValueError("saved Phoenix experiment identity differs; preserve the original database")
                continue
            router = Router(
                policy,
                provider,
                tracing,
                threshold=manifest.threshold or 0,
                always_fallback=manifest.always_fallback,
            )
            budget_errors = []

            def task(input, *, _policy=policy, _rep=repetition, _router=router, _errors=budget_errors):
                if set(input) != {"request"}:
                    raise ValueError("model input contains fields other than request")
                example = lookup[input["request"]]
                existing = checkpoints.get(_policy, example.example_id, _rep)
                if existing:
                    return existing["result"]
                with tracing.span(
                    "benchmark example",
                    "CHAIN",
                    **{
                        "router.example_id": example.example_id,
                        "router.repetition": _rep,
                        "router.policy": _policy,
                        "router.configuration_hash": manifest.configuration_hash,
                    },
                ):
                    try:
                        result = _router.route(input["request"])
                    except BudgetExceeded as exc:
                        _errors.append(str(exc))
                        raise
                row = {
                    "example_id": example.example_id,
                    "split": split,
                    "policy": _policy,
                    "repetition": _rep,
                    "timestamp": now(),
                    "expected_action": example.expected_action,
                    "tags": example.tags,
                    "configuration_hash": manifest.configuration_hash,
                    "result": result.model_dump(mode="json"),
                    **outcome(result, example.expected_action),
                }
                checkpoints.add(row)
                return row["result"]

            def accuracy(output, expected):
                result = RouteResult.model_validate(output)
                attach_scores(client, tracing, result, expected["expected_action"])
                return result.final_action == expected["expected_action"]

            # The installed client's synchronous runner processes one task at a time.
            # Disable task retries: only the provider owns transient retry handling.
            existing = [e for e in client.experiments.list(dataset_id=dataset.id) if e["name"] == name]
            if existing:
                experiment_id = existing[-1]["id"]
                client.experiments.resume_experiment(
                    experiment_id=experiment_id,
                    task=task,
                    evaluators={"route_accuracy": accuracy},
                    retries=0,
                    timeout=None,
                    print_summary=True,
                )
            else:
                experiment = client.experiments.run_experiment(
                    dataset=dataset,
                    task=task,
                    evaluators={"route_accuracy": accuracy},
                    experiment_name=name,
                    repetitions=1,
                    retries=0,
                    timeout=None,
                    experiment_metadata={
                        "policy": policy,
                        "split": split,
                        "repetition": repetition,
                        "configuration_hash": manifest.configuration_hash,
                        "concurrency": 1,
                        "measurement": "live",
                        "policy_order": order,
                    },
                )
                experiment_id = experiment["experiment_id"]
            if budget_errors:
                raise BudgetExceeded(budget_errors[0])
            if any(checkpoints.get(policy, e.example_id, repetition) is None for e in examples):
                raise RuntimeError(
                    "experiment incomplete; resume this same command after resolving the error"
                )
            recorded = client.experiments.get_experiment(experiment_id=experiment_id)
            evaluations = recorded["evaluation_runs"]
            if len(evaluations) != len(examples) or any(e.result is None for e in evaluations):
                client.experiments.resume_evaluation(
                    experiment_id=experiment_id,
                    evaluators={"route_accuracy": accuracy},
                    retries=0,
                    timeout=None,
                    print_summary=False,
                )
                evaluations = client.experiments.get_experiment(experiment_id=experiment_id)[
                    "evaluation_runs"
                ]
            if len(evaluations) != len(examples) or any(e.result is None for e in evaluations):
                raise RuntimeError("Phoenix evaluations incomplete; resume after resolving annotation errors")
            completed_experiments[name] = experiment_id
            write_json(experiment_log, completed_experiments)
    return {
        "split": split,
        "rows": len(checkpoints.completed),
        "configuration_hash": manifest.configuration_hash,
        "spent_usd": provider.budget.spent,
    }
