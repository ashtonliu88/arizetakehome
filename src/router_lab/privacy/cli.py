from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from . import study


def add_parser(commands):
    privacy = commands.add_parser("privacy", help="Privacy-preserving trace-evaluation research")
    actions = privacy.add_subparsers(dest="privacy_command", required=True)
    actions.add_parser("prepare", help="Create/check 72 synthetic episodes and four offline views")
    inspect = actions.add_parser("inspect", help="Local canonical episode, oracle, and judge-input views")
    inspect.add_argument("--episode", required=True)
    for command in ("generate", "replay"):
        action = actions.add_parser(
            command,
            help="Explicit paid calls"
            if command == "generate"
            else "Blinded judgments; model judge makes paid calls",
        )
        action.add_argument("--split", choices=["dev", "test"], required=True)
        action.add_argument("--max-bases", type=int)
        if command == "generate":
            action.add_argument(
                "--retry-failed",
                action="store_true",
                help="Explicitly retry an interrupted answer after reviewing retained charges",
            )
        if command == "replay":
            action.add_argument("--judge", choices=["evidence", "exact", "model"], default="evidence")
            action.add_argument("--frozen", action="store_true")
    audit = actions.add_parser(
        "review", help="Record a real human audit of one canonical episode and all views"
    )
    audit.add_argument("--episode", required=True)
    audit.add_argument("--reviewer", required=True)
    audit.add_argument("--note", required=True)
    audit.add_argument(
        "--answerable", required=True, help="Comma-separated answerable representations, or empty"
    )
    audit.add_argument("--approve", action="store_true")
    resolve = actions.add_parser(
        "resolve-interruption", help="Record uncertain paid work without replaying it"
    )
    resolve.add_argument("--reviewer", required=True)
    resolve.add_argument("--note", required=True)
    actions.add_parser(
        "freeze", help="Require captured answers, human audits, and complete model development work"
    )
    actions.add_parser("status", help="Progress, reviews, and remaining scheduled calls; no model calls")
    for command in ("analyze", "publish"):
        action = actions.add_parser(
            command,
            help="Offline metrics"
            if command == "analyze"
            else "Publish saved results to local/configured Phoenix; no model calls",
        )
        action.add_argument("--split", choices=["dev", "test"], required=True)
        action.add_argument("--judge", choices=["evidence", "exact", "model"], default="evidence")
    return privacy


@contextmanager
def paid_provider(settings, directory, purpose):
    from opentelemetry.sdk.trace import TracerProvider

    from ..budget import Budget
    from ..providers import OpenAIProvider
    from ..tracing import Tracing

    # Deliberately no automatic instrumentation or live exporter. Canonical raw
    # synthetic material stays in local controls. Publish replays saved views later.
    tracing = Tracing(TracerProvider())
    try:
        provider = OpenAIProvider(
            settings,
            tracing,
            Budget(Path("results/budget.jsonl"), settings.budget_usd, settings.reserve_usd),
            call_log=directory / "calls" / f"{purpose}.jsonl",
        )
        yield provider
    finally:
        tracing.close()


def run(args, settings):
    from .contracts import REPRESENTATIONS
    from .views import make_view

    directory = args.results_dir / "privacy"
    command = args.privacy_command
    if command == "prepare":
        return study.prepare(directory, settings.seed)
    if command == "inspect":
        episode = next((e for e in study.load_episodes(directory) if e.episode_id == args.episode), None)
        if episode is None:
            raise ValueError("unknown episode ID")
        return {
            "canonical": episode.model_dump(),
            "judge_inputs": {r: make_view(episode, r) for r in REPRESENTATIONS},
        }
    if command == "status":
        episodes = study.load_episodes(directory)
        config = study.context(settings)
        progress = {}
        for split in ("dev", "test"):
            for judge in ("model", "evidence", "exact"):
                tasks = study.schedule(episodes, split, config, judge, seed=settings.seed)
                saved = study.existing_results(study.result_path(directory, split, judge))
                progress[f"{split}-{judge}"] = {
                    "scheduled": len(tasks),
                    "current_completed": sum(t["key"] in saved for t in tasks),
                }
        return {
            "episodes": len(episodes),
            "model_answers": sum(e.answer_origin == "model" for e in episodes),
            "current_human_reviews": len(study.audited_reviews(directory, episodes)),
            "frozen": (directory / "frozen.json").exists(),
            "judgments": progress,
        }
    if command == "review":
        return study.review(directory, args.episode, args.reviewer, args.note, args.answerable, args.approve)
    if command == "resolve-interruption":
        return study.resolve_interruption(directory, args.reviewer, args.note)
    if command == "freeze":
        return study.freeze(directory, settings)
    if command == "analyze":
        from .analysis import analyze

        return analyze(directory, settings, args.split, args.judge)
    if command == "publish":
        from .phoenix import publish

        return publish(directory, settings, args.split, args.judge)
    # Validate held-out freeze BEFORE model client construction, including no-work resumes.
    if command == "replay" and args.split == "test":
        if not args.frozen:
            raise ValueError("held-out work requires --frozen")
        study.verify_frozen(directory, settings)
    if command == "generate":
        if (directory / "frozen.json").exists():
            raise ValueError("answers are frozen")
        with paid_provider(settings, directory, "answers") as provider:
            return study.generate(
                directory,
                settings,
                args.split,
                provider,
                max_bases=args.max_bases,
                retry_failed=args.retry_failed,
            )
    if command == "replay":
        if args.judge == "model":
            with paid_provider(settings, directory, "judges") as provider:
                return study.replay(
                    directory,
                    settings,
                    args.split,
                    args.judge,
                    provider=provider,
                    max_bases=args.max_bases,
                    frozen=args.frozen,
                )
        return study.replay(
            directory, settings, args.split, args.judge, max_bases=args.max_bases, frozen=args.frozen
        )
    raise ValueError(f"unknown privacy command: {json.dumps(command)}")
