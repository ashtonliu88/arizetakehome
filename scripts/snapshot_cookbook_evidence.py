"""Copy saved, synthetic study evidence; never run or modify an experiment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "notebooks/evidence"


def main():
    sources = {
        "routing/runs.jsonl": "results/offline-example/runs.jsonl",
        "routing/manifest.json": "results/offline-example/manifest.json",
        "routing/benchmark.jsonl": "data/benchmark.jsonl",
        "protocol/settings.json": "config/settings.json",
    }
    for name in (
        "runs.jsonl",
        "inputs.jsonl",
        "model-calls.jsonl",
        "bank.json",
        "frozen.json",
        "frozen-source.tar.gz",
        "calibration.json",
        "settings.json",
        "seed.json",
        "references-history.jsonl",
        "references-dev.jsonl",
        "references-test.jsonl",
        "reviews.jsonl",
        "family-contracts.json",
        "execution-verification.json",
        "final-verification.json",
    ):
        sources[f"reuse/{name}"] = f"results/reuse/{name}"
    sources["reuse/summary.json"] = "results/reuse/analysis/test/summary.json"
    for name in (
        "episodes.jsonl",
        "reviews.jsonl",
        "checks.json",
        "information-limit-control.json",
    ):
        sources[f"privacy/{name}"] = f"results/privacy/{name}"
    for judge in ("model", "exact", "evidence"):
        for suffix in (".jsonl", "-schedule.json"):
            sources[f"privacy/dev-{judge}{suffix}"] = f"results/privacy/dev-{judge}{suffix}"
        sources[f"privacy/summary-{judge}.json"] = f"results/privacy/analysis/dev-{judge}/summary.json"
    for view in ("raw", "blanket", "pseudonym", "relation"):
        sources[f"privacy/views/{view}.json"] = f"results/privacy/views/{view}.json"
    # Read everything first: missing ignored evidence must not create a partial snapshot.
    blobs = {target: (ROOT / source).read_bytes() for target, source in sources.items()}
    manifest = {
        "schema": "trace-evidence-cookbook-v1",
        "captured_date": "2026-10-29",
        "scope": "Saved real-model measurements on synthetic fixtures; routing is synthetic-only.",
        "privacy_boundary": "Local analysis bundle contains synthetic raw controls and fixture oracles. "
        "It is not a sanitized Phoenix export. No credentials or environment files are copied.",
        "files": {},
    }
    for target, blob in blobs.items():
        path = DEST / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        manifest["files"][target] = {
            "source": sources[target],
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
        }
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Copied {len(blobs)} evidence files ({sum(map(len, blobs.values())):,} bytes)")


if __name__ == "__main__":
    main()
