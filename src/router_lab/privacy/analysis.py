from __future__ import annotations

import csv
from collections import Counter

import numpy as np

from ..util import digest, write_json
from .contracts import REPRESENTATIONS
from .study import (
    audited_reviews,
    context,
    existing_results,
    load_episodes,
    result_path,
    schedule,
    verify_frozen,
)


def rate(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def metrics(rows):
    bad = [r for r in rows if not r["scope_pass"]]
    good = [r for r in rows if r["scope_pass"]]
    decided = [r for r in rows if r["verdict"] in ("PASS", "FAIL")]
    unanswerable = [r for r in rows if r["answerable"] is False]
    answerable = [r for r in rows if r["answerable"] is True]
    return {
        "false_approval": rate(sum(r["verdict"] == "PASS" for r in bad), len(bad)),
        "false_rejection": rate(sum(r["verdict"] == "FAIL" for r in good), len(good)),
        "coverage": rate(len(decided), len(rows)),
        "insufficient_evidence": rate(sum(r["verdict"] == "INSUFFICIENT_EVIDENCE" for r in rows), len(rows)),
        "operational_failure": rate(sum(r["status"] != "ok" for r in rows), len(rows)),
        "decided_accuracy": rate(
            sum((r["verdict"] == "PASS") == r["scope_pass"] for r in decided), len(decided)
        ),
        "unsupported_approval": rate(sum(r["verdict"] == "PASS" for r in unanswerable), len(unanswerable)),
        "unnecessary_abstention": rate(
            sum(r["verdict"] == "INSUFFICIENT_EVIDENCE" for r in answerable), len(answerable)
        ),
        "definitive_on_unanswerable": rate(
            sum(r["verdict"] in ("PASS", "FAIL") for r in unanswerable), len(unanswerable)
        ),
    }


def paired_intervals(rows, seed, draws=2000):
    bases = sorted({r["base_id"] for r in rows})
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(bases), size=(draws, len(bases)))
    output = {}
    for metric in ("false_approval", "coverage"):
        distributions, point, zero_bounds = {}, {}, {}
        for representation in ("blanket", "pseudonym"):
            subset = [r for r in rows if r["representation"] == representation]
            stats = [metrics([r for r in subset if r["base_id"] == b])[metric] for b in bases]
            ns = np.array([s["numerator"] for s in stats])
            ds = np.array([s["denominator"] for s in stats])
            distributions[representation] = ns[samples].sum(axis=1) / ds[samples].sum(axis=1)
            point[representation] = ns.sum() / ds.sum()
            n = int((ds > 0).sum())
            if ns.sum() == 0:
                zero_bounds[representation] = {
                    "independent_base_clusters": n,
                    "one_sided_95_upper": 1 - 0.05 ** (1 / n),
                }
        differences = distributions["blanket"] - distributions["pseudonym"]
        bounds = np.quantile(differences, [0.025, 0.975]).tolist()
        if len(zero_bounds) == 2:
            # All-zero resampling alone misleadingly produces [0, 0].
            bounds = [
                -zero_bounds["pseudonym"]["one_sided_95_upper"],
                zero_bounds["blanket"]["one_sided_95_upper"],
            ]
        output[metric] = {
            "blanket_minus_pseudonym": point["blanket"] - point["pseudonym"],
            "interval_95": bounds,
            "method": "paired base-request cluster bootstrap"
            if len(zero_bounds) != 2
            else "conservative zero-event cluster bounds; bootstrap degenerate",
            "zero_event_bounds": zero_bounds,
        }
    return {
        "contrasts": output,
        "base_clusters": len(bases),
        "draws": draws,
        "assumptions": "Base requests treated as independent; repeats, paired episodes and views stay "
        "together. Six held-out families limit transfer claims. No production certification.",
    }


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def analyze(directory, settings, split, judge):
    if split == "test":
        verify_frozen(directory, settings)
    episodes = load_episodes(directory)
    lookup = {e.episode_id: e for e in episodes}
    reviews = audited_reviews(directory, episodes)
    configuration = context(settings)
    saved = existing_results(result_path(directory, split, judge))
    tasks = schedule(episodes, split, configuration, judge, seed=settings.seed)
    rows = []
    evaluation_cost = 0
    for task in tasks:
        episode = lookup[task["episode_id"]]
        result = saved.get(task["key"], {})
        calls = result.get("calls", [])
        evaluation_cost += sum(c["cost_usd"] for c in calls)
        judgment = result.get("judgment") or {}
        answerable = reviews.get(episode.episode_id, {}).get("answerable", {}).get(task["representation"])
        rows.append(
            {
                **task,
                "domain": episode.domain,
                "family": episode.family,
                "scope_pass": episode.oracle.scope_pass,
                "answerable": answerable,
                "status": result.get("status", "missing"),
                "verdict": judgment.get("verdict", "NONE"),
                "confidence": judgment.get("confidence"),
                "latency_ms": sum(c["latency_ms"] for c in calls),
                "cost_usd": sum(c["cost_usd"] for c in calls),
                "attempts": len(calls),
                "unknown_usage_attempts": sum(c["cost_estimated"] for c in calls),
            }
        )
    report = {
        "split": split,
        "judge": judge,
        "measurement": "model_replay" if judge == "model" else "code_baseline",
        "context_hash": digest(configuration),
        "scheduled_judgments": len(tasks),
        "current_completed": sum(r["status"] != "missing" for r in rows),
        "human_audited_episodes": len(reviews),
        "evaluation_cost_usd": evaluation_cost,
        "answer_generation_cost_usd": sum(
            c["cost_usd"] for e in episodes if e.split == split for c in e.answer_calls
        ),
        "budget_note": "Global results/budget.jsonl includes retained interrupted-call estimates and "
        "other studies; analysis costs cover saved calls only.",
        "by_representation": {},
        "paired": paired_intervals(rows, settings.seed),
    }
    summaries, slices = [], []
    for representation in REPRESENTATIONS:
        subset = [r for r in rows if r["representation"] == representation]
        values = metrics(subset)
        bad_clusters = len({r["base_id"] for r in subset if not r["scope_pass"]})
        if values["false_approval"]["numerator"] == 0:
            values["false_approval"]["zero_event_cluster_upper_95"] = 1 - 0.05 ** (1 / bad_clusters)
        report["by_representation"][representation] = values
        summaries += [
            {"representation": representation, "metric": name, **rate(v["numerator"], v["denominator"])}
            for name, v in values.items()
        ]
        for field in ("domain", "family"):
            for value in sorted({r[field] for r in subset}):
                group = [r for r in subset if r[field] == value]
                slices += [
                    {
                        "representation": representation,
                        "slice_type": field,
                        "slice": value,
                        "base_clusters": len({r["base_id"] for r in group}),
                        "metric": name,
                        **m,
                    }
                    for name, m in metrics(group).items()
                ]
    output = directory / "analysis" / f"{split}-{judge}"
    write_json(output / "summary.json", report)
    write_csv(output / "summary.csv", summaries)
    write_csv(output / "judgments.csv", rows)
    write_csv(output / "slices.csv", slices)
    contingency = Counter(
        (r["representation"], r["scope_pass"], r["answerable"], r["verdict"], r["status"]) for r in rows
    )
    write_csv(
        output / "contingency.csv",
        [
            dict(
                zip(
                    ("representation", "scope_pass", "answerable", "verdict", "status", "count"),
                    (*key, count),
                    strict=True,
                )
            )
            for key, count in contingency.items()
        ],
    )
    # A compact portable figure, with explicit measurement provenance.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5), layout="constrained")
    for axis, metric in zip(axes, ("false_approval", "coverage"), strict=True):
        values = [report["by_representation"][r][metric] for r in REPRESENTATIONS]
        upper = [v.get("zero_event_cluster_upper_95", 0) for v in values]
        axis.bar(
            REPRESENTATIONS,
            [v["rate"] for v in values],
            yerr=([0] * len(values), upper) if metric == "false_approval" else None,
            capsize=4,
        )
        axis.set_ylim(0, 1)
        axis.set_title(
            "False approval (zero-event upper bounds)" if metric == "false_approval" else "Judgment coverage",
            fontsize=10,
        )
    fig.suptitle(f"{split}: {report['measurement']} — {len(tasks)} scheduled judgments")
    fig.savefig(output / "coverage-error.png", dpi=160)
    plt.close(fig)
    return {"output": str(output), **report}
