from __future__ import annotations

import importlib.metadata
import os
import subprocess
from pathlib import Path

from . import prompts
from .models import Contract, Settings
from .tools import catalog_payload
from .util import digest, now, read_jsonl, write_json

PACKAGES = [
    "openai",
    "arize-phoenix",
    "arize-phoenix-client",
    "arize-phoenix-otel",
    "arize-phoenix-evals",
    "openinference-instrumentation-openai",
    "pydantic",
    "pandas",
    "numpy",
]


class RunManifest(Contract):
    schema_version: int = 1
    dataset_hash: str
    catalog_hash: str
    prompt_hash: str
    evaluator_hash: str
    source_hash: str
    lock_hash: str
    configuration: dict
    endpoint_hash: str
    package_versions: dict[str, str]
    timestamp: str
    git_commit: str
    git_dirty: bool
    threshold: float | None = None
    always_fallback: bool = False
    development_results_hash: str | None = None
    review_hash: str | None = None

    @property
    def configuration_hash(self):
        # Runtime timestamp and Git bookkeeping must not prevent safe resume.
        return digest(self.model_dump(exclude={"timestamp", "git_commit", "git_dirty"}))


def load_settings(path=Path("config/settings.json")) -> Settings:
    return Settings.model_validate_json(path.read_text())


def current_manifest(settings: Settings, dataset=Path("data/benchmark.jsonl")) -> RunManifest:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except subprocess.CalledProcessError:
        commit = "uncommitted"
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
    sources = {str(p): digest(p) for p in sorted(Path("src/router_lab").glob("*.py"))}
    return RunManifest(
        dataset_hash=digest(dataset),
        catalog_hash=digest(catalog_payload()),
        prompt_hash=digest(
            {
                "routing": prompts.ROUTING_PROMPT,
                "arguments": prompts.ARGUMENT_PROMPT,
                "answer": prompts.ANSWER_PROMPT,
            }
        ),
        evaluator_hash=digest(prompts.EVALUATOR_VERSION),
        source_hash=digest(sources),
        lock_hash=digest(Path("uv.lock")),
        configuration=settings.model_dump(mode="json"),
        endpoint_hash=digest(os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")),
        package_versions={p: importlib.metadata.version(p) for p in PACKAGES},
        timestamp=now(),
        git_commit=commit,
        git_dirty=dirty,
    )


def verify_frozen(settings: Settings, path=Path("results/frozen.json")) -> RunManifest:
    if not path.exists():
        raise ValueError("test evaluation requires select-gate and a frozen manifest")
    frozen = RunManifest.model_validate_json(path.read_text())
    current = current_manifest(settings)
    for field in (
        "dataset_hash",
        "catalog_hash",
        "prompt_hash",
        "evaluator_hash",
        "source_hash",
        "configuration",
        "lock_hash",
        "package_versions",
        "endpoint_hash",
    ):
        if getattr(frozen, field) != getattr(current, field):
            raise ValueError(f"frozen configuration changed: {field}; rerun development and freeze again")
    if frozen.threshold is None:
        raise ValueError("manifest contains no selected gate")
    review_path = Path("data/review.jsonl")
    if not review_path.exists() or digest(review_path) != frozen.review_hash:
        raise ValueError("human label review changed after freeze")
    dev_path = path.parent / "dev.jsonl"
    if not dev_path.exists() or digest(dev_path) != frozen.development_results_hash:
        raise ValueError("development evidence changed or missing after freeze")
    return frozen


def require_label_review(examples, path=Path("data/review.jsonl")):
    reviews = {r["example_id"]: r for r in read_jsonl(path)}
    missing = [
        e.example_id
        for e in examples
        if e.example_id not in reviews
        or reviews[e.example_id].get("label_hash") != digest(e.model_dump())
        or not reviews[e.example_id].get("reviewer")
        or not reviews[e.example_id].get("approved")
    ]
    if missing:
        raise ValueError(f"{len(missing)} labels need human review; use router-lab review-label")
    return digest(path)


def save_manifest(path: Path, manifest: RunManifest):
    write_json(path, manifest.model_dump(mode="json"))
