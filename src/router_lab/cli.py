from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .dataset import load_data, validate_data
from .util import append_jsonl, digest, now, read_jsonl, write_json


def parser():
    p = argparse.ArgumentParser(
        description="Decision Router Lab — paid runs are explicit; analysis works offline"
    )
    p.add_argument("--config", type=Path, default=Path("config/settings.json"))
    p.add_argument("--results-dir", type=Path, default=Path("results"))
    commands = p.add_subparsers(dest="command", required=True)
    s = commands.add_parser("smoke", help="Phoenix setup check; --live adds two paid routing calls")
    s.add_argument("--live", action="store_true")
    s.add_argument(
        "--check-persistence", action="store_true", help="verify previous smoke after restarting Phoenix"
    )
    commands.add_parser("validate-data")
    commands.add_parser("upload-data")
    b = commands.add_parser("benchmark")
    b.add_argument("--split", choices=["dev", "test"], required=True)
    b.add_argument("--frozen", action="store_true")
    commands.add_parser("select-gate")
    a = commands.add_parser("analyze")
    a.add_argument("--input", type=Path)
    a.add_argument("--output", type=Path)
    a.add_argument("--synthetic", action="store_true")
    d = commands.add_parser("demo")
    d.add_argument(
        "--skip-semantic-evals",
        action="store_true",
        help="diagnostic only; final demo includes the prebuilt evaluators",
    )
    r = commands.add_parser("review-label", help="Record one human label audit; never calls a model")
    r.add_argument("--id", required=True)
    r.add_argument("--reviewer", required=True)
    r.add_argument("--note", required=True)
    r.add_argument("--approve", action="store_true")
    n = commands.add_parser("annotate", help="Human development failure review in Phoenix")
    n.add_argument("--id", required=True)
    n.add_argument("--policy", choices=["llm", "decisions", "hybrid"], required=True)
    n.add_argument("--repetition", type=int, required=True)
    n.add_argument("--label", required=True)
    n.add_argument("--note", required=True)
    n.add_argument("--reviewer", required=True)
    v = commands.add_parser("review-demo")
    v.add_argument("--id", required=True)
    v.add_argument("--policy", choices=["llm", "decisions", "hybrid"], required=True)
    v.add_argument("--answer-success", choices=["yes", "no"], required=True)
    v.add_argument("--unsupported-claims", choices=["yes", "no"], required=True)
    v.add_argument("--reviewer", required=True)
    v.add_argument("--note", required=True)
    return p


def select_and_freeze(settings, results_dir):
    from .gate import pair_baselines, random_control, select_gate
    from .manifest import current_manifest, require_label_review, save_manifest

    held_out = results_dir / "test.jsonl"
    if held_out.exists() and held_out.stat().st_size:
        raise ValueError("held-out results already exist; do not retune this study")
    examples = load_data()
    validate_data(examples)
    manifest = current_manifest(settings)
    review_hash = require_label_review(examples)
    dev_path = results_dir / "dev.jsonl"
    rows = read_jsonl(dev_path)
    if any(r["configuration_hash"] != manifest.configuration_hash for r in rows):
        raise ValueError("development outputs do not match current configuration")
    pairs = pair_baselines(
        rows, "dev", settings.repetitions, [e.example_id for e in examples if e.split == "dev"]
    )
    selection = select_gate(pairs)
    selection["random_control"] = random_control(pairs, selection["selected"], settings.seed)
    write_json(results_dir / "gate-selection.json", selection)
    manifest.threshold = selection["selected"]["threshold"]
    manifest.always_fallback = selection["selected"]["always_fallback"]
    manifest.development_results_hash = digest(dev_path)
    manifest.review_hash = review_hash
    save_manifest(results_dir / "frozen.json", manifest)
    return selection


def run(args):
    from .manifest import load_settings

    settings = load_settings(args.config)
    if args.command == "validate-data":
        return validate_data(load_data())
    if args.command == "review-label":
        example = next((e for e in load_data() if e.example_id == args.id), None)
        if example is None:
            raise ValueError("unknown example ID")
        record = {
            "example_id": args.id,
            "label_hash": digest(example.model_dump()),
            "reviewer": args.reviewer,
            "approved": args.approve,
            "note": args.note,
            "timestamp": now(),
        }
        append_jsonl(Path("data/review.jsonl"), record)
        return record
    if args.command == "analyze":
        from .analysis import analyze

        return analyze(
            args.input or args.results_dir / "test.jsonl",
            args.output or args.results_dir / "analysis",
            synthetic=args.synthetic,
            frozen_path=args.results_dir / "frozen.json",
            seed=settings.seed,
        )
    if args.command == "select-gate":
        return select_and_freeze(settings, args.results_dir)
    if args.command == "upload-data":
        from .phoenix_io import upload_data

        dataset = upload_data()
        return {"dataset_id": dataset.id, "examples": len(dataset.examples)}
    if args.command == "annotate":
        from .phoenix_io import log_annotations, phoenix_client

        row = next(
            (
                r
                for r in read_jsonl(args.results_dir / "dev.jsonl")
                if r["example_id"] == args.id
                and r["policy"] == args.policy
                and r["repetition"] == args.repetition
            ),
            None,
        )
        if row is None:
            raise ValueError("development row not found")
        record = {
            "span_id": row["result"]["initial_span_id"],
            "name": "human_failure_taxonomy",
            "annotator_kind": "HUMAN",
            "result": {"label": args.label, "explanation": args.note},
            "metadata": {"reviewer": args.reviewer},
        }
        log_annotations(phoenix_client(), [record])
        append_jsonl(
            args.results_dir / "human-annotations.jsonl", dict(record, timestamp=now(), example_id=args.id)
        )
        return record
    if args.command == "review-demo":
        from .phoenix_io import log_annotations, phoenix_client

        row = next(
            (
                r
                for r in read_jsonl(args.results_dir / "demo.jsonl")
                if r["example_id"] == args.id and r["policy"] == args.policy
            ),
            None,
        )
        if row is None:
            raise ValueError("demo row not found")
        annotations = [
            {
                "span_id": row["agent_span_id"],
                "name": name,
                "annotator_kind": "HUMAN",
                "result": {"score": float(value == "yes"), "explanation": args.note},
                "metadata": {"reviewer": args.reviewer},
            }
            for name, value in (
                ("answer_success", args.answer_success),
                ("unsupported_claims", args.unsupported_claims),
            )
        ]
        log_annotations(phoenix_client(), annotations)
        append_jsonl(
            args.results_dir / "demo-human-review.jsonl",
            {"example_id": args.id, "policy": args.policy, "annotations": annotations, "timestamp": now()},
        )
        return {"reviewed": args.id, "policy": args.policy}
    if args.command == "smoke" and args.check_persistence:
        from .smoke import check_persistence

        return check_persistence()
    # Validate test freeze before initializing tracing or model clients.
    if args.command == "benchmark" and args.split == "test":
        if not args.frozen:
            raise ValueError("test command requires --frozen")
        from .manifest import verify_frozen

        verify_frozen(settings, args.results_dir / "frozen.json")
    if args.command == "demo":
        from .manifest import verify_frozen

        manifest = verify_frozen(settings, args.results_dir / "frozen.json")
    paid = args.command in ("benchmark", "demo") or (args.command == "smoke" and args.live)
    if paid and (not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "your-key"):
        raise ValueError("OPENAI_API_KEY is not configured; add it to .env and use uv run --env-file .env")
    from .budget import Budget, run_lock
    from .providers import OpenAIProvider
    from .tracing import Tracing

    with run_lock():
        tracing = Tracing()  # Must precede model client initialization.
        try:
            # A single ledger covers smoke, reruns, routing, demo and semantic judges,
            # even when checkpoint directories differ.
            provider = (
                OpenAIProvider(
                    settings,
                    tracing,
                    Budget(Path("results/budget.jsonl"), settings.budget_usd, settings.reserve_usd),
                    headroom=args.command != "demo",
                )
                if paid
                else None
            )
            if args.command == "smoke":
                from .smoke import run_smoke

                return run_smoke(tracing, provider)
            if args.command == "benchmark":
                from .experiments import run_benchmark

                return run_benchmark(
                    settings, tracing, provider, args.split, frozen=args.frozen, results_dir=args.results_dir
                )
            if args.command == "demo":
                from .demo import run_demo

                return run_demo(
                    settings,
                    tracing,
                    provider,
                    manifest,
                    results_dir=args.results_dir,
                    judges=not args.skip_semantic_evals,
                )
        finally:
            tracing.close()


def main():
    import sys

    try:
        result = run(parser().parse_args())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"router-lab: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps(result, indent=2, default=str, allow_nan=False))


if __name__ == "__main__":
    main()
