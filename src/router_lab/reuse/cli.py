from __future__ import annotations

from pathlib import Path

from .contracts import ReuseSettings
from .dataset import FAMILIES


def add_parser(commands):
    parser = commands.add_parser(
        "reuse", help="Verified workflow reuse study; live calls are sequential and budgeted"
    )
    parser.add_argument("--dir", type=Path, default=Path("results/reuse"))
    sub = parser.add_subparsers(dest="reuse_command", required=True)
    sub.add_parser(
        "prepare", help="Archive sources, construct separated inputs/references and eight family contracts"
    )
    review = sub.add_parser("review-family", help="Record an explicit human family-contract review")
    review.add_argument("--family", choices=FAMILIES, required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", required=True)
    review.add_argument("--approve", action="store_true")
    sub.add_parser(
        "seed", help="Attempt sixteen real history executions; admit successful parameterizable plans"
    )
    sub.add_parser("pilot", help="Run eight development clusters across six conditions (paid)")
    run = sub.add_parser("run", help="Resume an exact-configuration matrix (paid)")
    run.add_argument("--split", choices=["dev", "test"], required=True)
    sub.add_parser(
        "freeze", help="Require reviews, complete development, calibration and affordable projection"
    )
    analyze = sub.add_parser("analyze", help="Offline analysis, confidence intervals, graphics, and report")
    analyze.add_argument("--split", choices=["dev", "test"], default="test")
    analyze.add_argument("--calibrate", action="store_true")
    sub.add_parser("publish", help="Publish measured results as Phoenix traces and evaluations")
    return parser


def run(args, settings):
    from . import study

    root = args.dir
    # Alternate study directories still share the canonical global budget ledger.
    if root.parent.resolve() != Path("results").resolve():
        raise ValueError(
            "reuse --dir must be an immediate child of results/ to share its global budget ledger"
        )
    command = args.reuse_command
    if command == "prepare":
        return study.prepare(root)
    if command == "review-family":
        return study.review_family(root, args.family, args.reviewer, args.note, args.approve)
    ReuseSettings.model_validate_json((root / "settings.json").read_text())
    if command in ("seed", "pilot", "run"):
        import os

        if not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "your-key":
            raise ValueError("OPENAI_API_KEY is required; use uv run --env-file .env router-lab reuse ...")
        if command == "seed":
            return study.locked(study.seed, root, settings)
        return study.locked(
            study.run_matrix,
            root,
            settings,
            split="dev" if command == "pilot" else args.split,
            pilot=command == "pilot",
        )
    if command == "freeze":
        return study.locked(study.freeze, root, settings)
    if command == "analyze":
        from .analysis import analyze

        return analyze(root, settings, split=args.split, calibrate=args.calibrate)
    if command == "publish":
        from .phoenix import publish

        return publish(root, settings)
    raise ValueError("unknown reuse command")
