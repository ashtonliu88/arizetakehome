from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .evaluation import (
    brier_score,
    grouped_paired_interval,
    outcome,
    overlap,
    reliability,
)
from .gate import pair_baselines, random_control, replay
from .models import RouteResult
from .util import read_jsonl, write_json


def quantile_interval(groups, quantile, seed=1729, samples=2000):
    values = [np.array(v) for _, v in sorted(groups.items())]
    rng = np.random.default_rng(seed)
    draws = [
        float(
            np.quantile(
                np.concatenate([values[i] for i in rng.integers(0, len(values), len(values))]), quantile
            )
        )
        for _ in range(samples)
    ]
    return [float(x) for x in np.quantile(draws, [0.025, 0.975])]


def analyze(
    path: Path, output_dir: Path, *, synthetic=False, frozen_path=Path("results/frozen.json"), seed=1729
):
    rows = read_jsonl(path)
    if not rows:
        raise ValueError(
            "no saved results; run the benchmark or use the documented synthetic offline example"
        )
    if not synthetic:
        if not frozen_path.exists():
            raise ValueError("held-out analysis requires its frozen manifest")
        from .manifest import RunManifest

        frozen = RunManifest.model_validate_json(frozen_path.read_text())
        if any(r["configuration_hash"] != frozen.configuration_hash for r in rows):
            raise ValueError("saved results do not match frozen manifest")
        if {r["split"] for r in rows} != {"test"} or len({r["example_id"] for r in rows}) != 80:
            raise ValueError("held-out analysis requires exactly 80 independent test questions")
        selected = {"threshold": frozen.threshold, "always_fallback": frozen.always_fallback}
    else:
        if not all(r.get("synthetic") is True for r in rows):
            raise ValueError("--synthetic requires explicitly marked synthetic fixture rows")
        selected = {"threshold": 0.7, "always_fallback": False}
    keys = [(r["policy"], r["example_id"], r["repetition"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate result rows")
    by_policy = defaultdict(set)
    for r in rows:
        by_policy[r["policy"]].add((r["example_id"], r["repetition"]))
    if (
        set(by_policy) != {"llm", "decisions", "hybrid"}
        or len({frozenset(v) for v in by_policy.values()}) != 1
    ):
        raise ValueError("all three policies must have complete paired coverage")
    expected_reps = set(range(1, (3 if synthetic else frozen.configuration["repetitions"]) + 1))
    for example_id in {r["example_id"] for r in rows}:
        reps = {r["repetition"] for r in rows if r["example_id"] == example_id}
        if reps != expected_reps:
            raise ValueError("incomplete repetition coverage")
    output_dir.mkdir(parents=True, exist_ok=True)
    label = "SYNTHETIC FIXTURE — no model calls" if synthetic else "LIVE held-out measurements"
    records = []
    for row in rows:
        result = RouteResult.model_validate(row["result"])
        records.append(
            {
                "policy": row["policy"],
                "example_id": row["example_id"],
                "repetition": row["repetition"],
                "expected_action": row["expected_action"],
                "tags": row["tags"],
                "fallback": result.fallback,
                "fallback_reason": result.fallback_reason,
                "cost_usd": result.cost_usd,
                "cost_estimated": any(c.cost_estimated for c in result.calls),
                "latency_ms": result.latency_ms,
                "calls": len(result.calls),
                **outcome(result, row["expected_action"]),
            }
        )
    df = pd.DataFrame(records)
    summaries = []
    for policy, group in df.groupby("policy", sort=False):

        def grouped(column, group=group):
            return {e: list(g[column]) for e, g in group.groupby("example_id")}

        summaries.append(
            {
                "policy": policy,
                "requests": len(group),
                "independent_questions": group.example_id.nunique(),
                "accuracy": float(group.correct.mean()),
                "accuracy_ci": grouped_paired_interval(grouped("correct"), seed=seed),
                "cost_per_request": float(group.cost_usd.mean()),
                "cost_ci": grouped_paired_interval(grouped("cost_usd"), seed=seed),
                "p50_latency_ms": float(group.latency_ms.quantile(0.5)),
                "p95_latency_ms": float(group.latency_ms.quantile(0.95)),
                "p50_latency_ci": quantile_interval(grouped("latency_ms"), 0.5, seed),
                "p95_latency_ci": quantile_interval(grouped("latency_ms"), 0.95, seed),
                "fallback_rate": float(group.fallback.mean()),
                "calls_per_request": float(group.calls.mean()),
                "rescues": int(group.rescue.sum()),
                "regressions": int(group.regression.sum()),
                "operational_failure_rate": float(group.operational_failure.mean()),
                "operational_error_rate": float(group.operational_error.mean()),
                "usage_unknown_cost_rows": int(group.cost_estimated.sum()),
            }
        )
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(output_dir / "policy-summary.csv", index=False)
    df.to_json(output_dir / "normalized-results.jsonl", orient="records", lines=True)
    aggregate = {
        "requests": ("correct", "size"),
        "accuracy": ("correct", "mean"),
        "errors": ("correct", lambda x: int((~x).sum())),
    }
    df.groupby(["policy", "expected_action"]).agg(**aggregate).to_csv(output_dir / "per-action.csv")
    df.explode("tags").groupby(["policy", "tags"]).agg(**aggregate).to_csv(output_dir / "per-category.csv")
    df[df.policy == "hybrid"][
        [
            "example_id",
            "repetition",
            "initial_correct",
            "correct",
            "fallback",
            "fallback_reason",
            "rescue",
            "regression",
        ]
    ].to_csv(output_dir / "rescue-regression.csv", index=False)
    pairs = pair_baselines(rows, rows[0]["split"])
    overlap_counts = overlap(
        [d["result"]["final_action"] == d["expected_action"] for _, d, _ in pairs],
        [llm["result"]["final_action"] == llm["expected_action"] for _, _, llm in pairs],
    )
    pd.DataFrame([{"outcome": k, "count": v} for k, v in overlap_counts.items()]).to_csv(
        output_dir / "overlap.csv", index=False
    )
    hybrid = df[df.policy == "hybrid"].set_index(["example_id", "repetition"])
    comparisons = {}
    for baseline in ("llm", "decisions"):
        other = df[df.policy == baseline].set_index(["example_id", "repetition"])
        for metric in ("correct", "cost_usd", "latency_ms"):
            delta = hybrid[metric].astype(float) - other[metric].astype(float)
            clusters = {e: list(g) for e, g in delta.groupby(level=0)}
            comparisons[f"hybrid_minus_{baseline}_{metric}"] = {
                "difference": float(delta.mean()),
                "paired_cluster_bootstrap_ci": grouped_paired_interval(clusters, seed=seed),
            }
    confidence, probability, margin, briers, secondary = [], [], [], [], []
    for _, d, _ in pairs:
        result = RouteResult.model_validate(d["result"])
        correct = result.initial_action == d["expected_action"]
        if result.decision_confidence is not None:
            confidence.append((result.decision_confidence, correct))
        if result.option_probabilities:
            briers.append(brier_score(result.option_probabilities, d["expected_action"]))
            probability.append((result.maximum_probability, correct))
            margin.append((result.probability_margin, correct))
        secondary.append(
            {
                "example_id": d["example_id"],
                "repetition": d["repetition"],
                "confidence": result.decision_confidence,
                "max_probability": result.maximum_probability,
                "probability_margin": result.probability_margin,
                "initial_correct": correct,
            }
        )
    bins, ece = reliability(confidence)
    prob_bins, prob_ece = reliability(probability)
    margin_bins, _ = reliability(margin)
    pd.DataFrame(secondary).to_csv(output_dir / "decision-signals.csv", index=False)
    pd.DataFrame(bins).to_csv(output_dir / "confidence-bins.csv", index=False)
    calibration = {
        "multiclass_brier_sum_over_classes": float(np.mean(briers)) if briers else None,
        "brier_valid_rows": len(briers),
        "confidence_valid_rows": len(confidence),
        "excluded_confidence_rows": len(pairs) - len(confidence),
        "exploratory_confidence_calibration_error": ece,
        "secondary_max_probability_ece": prob_ece,
        "note": "Descriptive diagnostics on balanced authored traffic; no test threshold retuning.",
    }
    replay_selected = replay(pairs, selected["threshold"], selected["always_fallback"])
    control = random_control(pairs, replay_selected, seed=seed)
    plt.rcParams.update({"figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for s in summaries:
        ax.errorbar(
            s["cost_per_request"],
            s["accuracy"],
            yerr=[[s["accuracy"] - s["accuracy_ci"][0]], [s["accuracy_ci"][1] - s["accuracy"]]],
            fmt="o",
            capsize=4,
        )
        ax.annotate(
            s["policy"], (s["cost_per_request"], s["accuracy"]), xytext=(6, 5), textcoords="offset points"
        )
    ax.set(
        xlabel="Combined routing USD / request",
        ylabel="Final routing accuracy",
        ylim=(-0.03, 1.08),
        title=label,
    )
    fig.tight_layout()
    fig.savefig(output_dir / "accuracy-cost.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = np.arange(len(summaries))
    ax.bar(x - 0.18, [s["p50_latency_ms"] for s in summaries], 0.36, label="p50")
    ax.bar(x + 0.18, [s["p95_latency_ms"] for s in summaries], 0.36, label="p95")
    ax.set(
        xticks=x,
        xticklabels=[s["policy"] for s in summaries],
        ylabel="Measured routing latency (ms)",
        title=label,
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "latency.png")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, signal_bins, name in (
        (axes[0], bins, "Decision confidence"),
        (axes[1], prob_bins, "Maximum option probability (secondary)"),
    ):
        valid = [b for b in signal_bins if b["count"]]
        ax.plot([0, 1], [0, 1], "--", color="gray")
        ax.plot([b["confidence"] for b in valid], [b["accuracy"] for b in valid], "o-")
        for b in valid:
            ax.annotate(
                f"n={b['count']}", (b["confidence"], b["accuracy"]), xytext=(3, 7), textcoords="offset points"
            )
        ax.set(xlabel=name, ylabel="Observed initial-choice accuracy", xlim=(-0.03, 1.03), ylim=(-0.03, 1.1))
    fig.suptitle(label)
    fig.tight_layout()
    fig.savefig(output_dir / "reliability.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 4))
    valid = [b for b in margin_bins if b["count"]]
    ax.plot([b["confidence"] for b in valid], [b["accuracy"] for b in valid], "o-")
    for b in valid:
        ax.annotate(
            f"n={b['count']}", (b["confidence"], b["accuracy"]), xytext=(3, 7), textcoords="offset points"
        )
    ax.set(
        xlabel="Probability margin (secondary; no retuning)",
        ylabel="Initial-choice accuracy",
        ylim=(-0.03, 1.1),
        title=label,
    )
    fig.tight_layout()
    fig.savefig(output_dir / "margin.png")
    plt.close(fig)
    summary = {
        "measurement": label,
        "policies": summaries,
        "paired_comparisons": comparisons,
        "overlap": overlap_counts,
        "calibration": calibration,
        "random_fallback_control": control,
        "selected_gate_replay": replay_selected,
        "bootstrap": {
            "unit": "example",
            "independent_questions": df.example_id.nunique(),
            "samples": 2000,
            "seed": seed,
        },
        "limitations": "Balanced authored requests, model pair and fixed catalog only. Repetitions are clustered, not independent questions. Latency includes provider retry backoff, excludes grading/export. Calls with unavailable usage retain conservative estimated charges.",
    }
    write_json(output_dir / "summary.json", summary)
    return summary
