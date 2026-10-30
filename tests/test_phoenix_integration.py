"""Start, stop and restart an isolated real Phoenix server. No paid requests."""

import json
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest


@pytest.mark.integration
def test_phoenix_persistence_splits_annotations_and_resume(tmp_path, monkeypatch, settings):
    from phoenix.client import Client

    from router_lab.manifest import current_manifest
    from router_lab.phoenix_io import upload_data
    from router_lab.privacy import study as privacy_study
    from router_lab.privacy.phoenix import publish
    from router_lab.smoke import check_persistence, run_smoke
    from router_lab.tracing import Tracing

    workspace = Path.cwd()
    settings.repetitions = 1  # Smaller protocol fixture; research configuration remains three.
    fixture_manifest = current_manifest(settings)
    privacy_context = privacy_study.context(settings)
    shutil.copytree(workspace / "data", tmp_path / "data")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    endpoint = f"http://127.0.0.1:{port}"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        grpc_port = s.getsockname()[1]
    storage = tmp_path / "phoenix-storage"
    env = dict(
        os.environ,
        PHOENIX_PORT=str(port),
        PHOENIX_GRPC_PORT=str(grpc_port),
        PHOENIX_HOST="127.0.0.1",
        PHOENIX_WORKING_DIR=str(storage),
    )
    monkeypatch.setenv("PHOENIX_ENDPOINT", endpoint)
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", endpoint)
    monkeypatch.setenv("PHOENIX_PROJECT_NAME", "router-integration")
    monkeypatch.chdir(tmp_path)
    log = (tmp_path / "server.log").open("a")

    def start():
        process = subprocess.Popen(
            [str(workspace / ".venv/bin/phoenix"), "serve"],
            env=env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError((tmp_path / "server.log").read_text())
            try:
                if httpx.get(endpoint + "/healthz", timeout=0.5).status_code == 200:
                    return process
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        os.killpg(process.pid, signal.SIGTERM)
        raise RuntimeError("Phoenix failed to start: " + (tmp_path / "server.log").read_text())

    def stop(process):
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)

    process = start()
    tracing = None
    try:
        tracing = Tracing()
        evidence = run_smoke(tracing)
        c = Client(base_url=endpoint)
        dataset = upload_data(c)
        assert len(dataset.examples) == 120
        assert len(c.datasets.get_dataset(dataset=dataset.id, splits=["dev"]).examples) == 40
        assert len(c.datasets.get_dataset(dataset=dataset.id, splits=["test"]).examples) == 80
        experiment = c.experiments.get_experiment(experiment_id=evidence["experiment_id"])
        project = experiment["project_name"]
        outputs = [r["output"] for r in experiment["task_runs"]]
        span_ids = [o[k] for o in outputs for k in ["initial_span_id", "final_span_id", "policy_span_id"]]
        annotations = c.spans.get_span_annotations(span_ids=span_ids, project_identifier=project)
        assert len(annotations) == 6
        names = {a["name"] for a in annotations}
        assert names == {"initial_route_accuracy", "selected_route_accuracy", "final_route_accuracy"}
        expected_spans = {("initial_route_accuracy", o["initial_span_id"]) for o in outputs}
        expected_spans |= {("selected_route_accuracy", o["final_span_id"]) for o in outputs}
        expected_spans |= {("final_route_accuracy", o["policy_span_id"]) for o in outputs}
        assert {(a["name"], a["span_id"]) for a in annotations} == expected_spans
        # Exercise the actual measured-run orchestration with an explicitly fake
        # provider. Only these test-local external prerequisites are bypassed.
        from router_lab.budget import Budget
        from router_lab.dataset import load_data
        from router_lab.experiments import run_benchmark
        from router_lab.models import ACTIONS, CallRecord
        from router_lab.tracing import span_id
        from router_lab.util import read_jsonl

        monkeypatch.setattr("router_lab.experiments.current_manifest", lambda config: fixture_manifest)
        monkeypatch.setattr("router_lab.experiments.require_setup", lambda: None)
        monkeypatch.setattr("router_lab.experiments.require_label_review", lambda examples: None)

        class FakeProvider:
            budget = Budget(tmp_path / "fake-budget.jsonl")
            requests = []
            labels = {e.request: e.expected_action for e in load_data()}

            def estimate_call(self, *args):
                return 0.001

            def call(self, kind, request, catalog):
                self.requests.append((kind, request, catalog))
                action = self.labels[request]
                with tracing.span(
                    "explicitly fake provider", "DECISION" if kind == "decisions" else "LLM"
                ) as span:
                    return [
                        CallRecord(
                            kind=kind,
                            action=action,
                            confidence=0.9 if kind == "decisions" else None,
                            probabilities={a: float(a == action) for a in ACTIONS}
                            if kind == "decisions"
                            else {},
                            span_id=span_id(span),
                        )
                    ]

        provider = FakeProvider()
        checkpoint_dir = tmp_path / "fixture-runs"
        assert run_benchmark(settings, tracing, provider, "dev", results_dir=checkpoint_dir)["rows"] == 80
        assert len(provider.requests) == 80
        assert run_benchmark(settings, tracing, provider, "dev", results_dir=checkpoint_dir)["rows"] == 80
        assert len(provider.requests) == 80
        assert len(read_jsonl(checkpoint_dir / "dev.jsonl")) == 80
        assert len(c.experiments.list(dataset_id=dataset.id)) == 2
        # Publish saved privacy judgments through the real Phoenix API. Dataset
        # inputs are the exact blinded views; no model client is initialized.
        monkeypatch.setattr(privacy_study, "context", lambda config: privacy_context)
        monkeypatch.setattr("router_lab.privacy.phoenix.context", lambda config: privacy_context)
        privacy_dir = tmp_path / "privacy-fixture"
        privacy_study.prepare(privacy_dir, settings.seed)
        privacy_study.replay(privacy_dir, settings, "dev", "evidence")
        published = publish(privacy_dir, settings, "dev", "evidence", client=c)
        assert published["new_model_calls"] == 0
        assert len(published["published"]) == 4
        for item in published["published"]:
            saved_dataset = c.datasets.get_dataset(dataset=item["dataset_id"])
            assert len(saved_dataset.examples) == 48
            assert all("oracle" not in row["input"] for row in saved_dataset.examples)
            saved_experiment = c.experiments.get_experiment(experiment_id=item["experiment_id"])
            assert len(saved_experiment["task_runs"]) == 48
            assert len(saved_experiment["evaluation_runs"]) == 96
        resumed = publish(privacy_dir, settings, "dev", "evidence", client=c)
        assert resumed == published
        tracing.provider.force_flush()
        assert (storage / "phoenix.db").exists()
        stop(process)
        process = start()
        persisted = check_persistence()
        assert persisted["persistence_verified"]
        assert not persisted["live_verified"]
        assert len(c.datasets.get_dataset(dataset=dataset.id, splits=["test"]).examples) == 80

        # A completed experiment must not invoke its task when resumed.
        def forbidden(input):
            raise AssertionError("completed row was invoked twice")

        before = len(c.experiments.get_experiment(experiment_id=evidence["experiment_id"])["task_runs"])
        c.experiments.resume_experiment(
            experiment_id=evidence["experiment_id"], task=forbidden, retries=0, timeout=None
        )
        after = len(c.experiments.get_experiment(experiment_id=evidence["experiment_id"])["task_runs"])
        assert before == after == 2
        (tmp_path / "acceptance.json").write_text(json.dumps(persisted))
    finally:
        if tracing:
            tracing.close()
        stop(process)
        log.close()
