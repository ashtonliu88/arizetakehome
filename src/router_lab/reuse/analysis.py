"""Offline, cluster-paired analysis. No model calls or cache admission."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict

import numpy as np

from ..util import digest, read_jsonl, write_json
from .bank import compatible, resolve, retrieve
from .bindings import bind
from .contracts import RequestInput
from .service import dispatch
from .study import conditions, config_hash, inputs_and_references, load_bank, load_config, verify_freeze

GRID = [(threshold, margin) for threshold in (0.35, 0.55, 0.75, 0.9, 1.0) for margin in (0.0, 0.05, 0.15)]


def calibrate_development(root):
    if (root / "frozen.json").exists() or any(r["split"] == "test" for r in read_jsonl(root / "runs.jsonl")):
        raise ValueError("cannot calibrate after freeze or held-out execution")
    cases, refs = inputs_and_references(root, "dev")
    bank = load_bank(root)
    grid = []
    for threshold, margin in GRID:
        accepted, wrong = 0, 0
        for case in (c for c in cases if c["split"] == "dev"):
            inp = RequestInput.model_validate(case["input"])
            bindings = bind(inp)
            if not bindings.slots or bindings.unresolved or "requires_planning" in bindings.semantics:
                continue
            plan, score, gap = retrieve(bindings, bank)
            if not plan or score < threshold or gap < margin or compatible(plan, bindings):
                continue
            accepted += 1
            try:
                outputs, path = [], []
                for index in range(len(plan.steps)):
                    step = resolve(plan.steps, bindings, outputs, index)
                    path.append(step.model_dump())
                    outputs.append(dispatch(step, inp.context, case["state"]))
                wrong += path not in refs[case["id"]]["acceptable_paths"]
            except (ValueError, KeyError):
                wrong += 1
        grid.append({"threshold": threshold, "margin": margin, "accepted": accepted, "incorrect": wrong})
    candidates = [r for r in grid if not r["incorrect"]]
    selected = max(candidates, key=lambda row: (row["accepted"], row["threshold"], row["margin"]))
    result = {
        "grid": grid,
        "selected": {k: selected[k] for k in ("threshold", "margin")},
        "accepted_development_clusters": selected["accepted"],
        "selection_basis": "offline development plan/resource validity; maximize eliminated planning calls with zero incorrect hits, strict tie break",
        "bank_hash": digest(root / "bank.json"),
        "inputs_hash": digest(root / "inputs.jsonl"),
        "references_hash": digest(root / "references-dev.jsonl"),
    }
    write_json(root / "calibration.json", result)
    return result


def summary(rows):
    if not rows:
        return {}
    records = [r["record"] for r in rows]
    latencies = [r["timings_ms"]["end_to_end"] for r in records]
    successes = sum(r["evaluation"]["success"] for r in rows)
    cost = sum(r["cost_usd"] for r in records)
    calls = [c for r in records for c in r["calls"]]
    hits = [r for r in records if r["cache_hit"]]

    def quantiles(values):
        return (
            {"p50": float(np.percentile(values, 50)), "p95": float(np.percentile(values, 95))}
            if values
            else None
        )

    return {
        "n": len(rows),
        "successes": successes,
        "success_rate": successes / len(rows),
        "resource_correct": sum(r["evaluation"]["resource_correct"] for r in rows),
        "cost_usd": cost,
        "cost_per_success_usd": cost / successes if successes else None,
        "latency_ms": quantiles(latencies),
        "hits": len(hits),
        "hit_rate": len(hits) / len(rows),
        "false_hits": sum(r["evaluation"]["incorrect_accepted_reuse"] for r in rows),
        "incorrect_hit_rate": sum(r["evaluation"]["incorrect_accepted_reuse"] for r in rows) / len(hits)
        if hits
        else None,
        "hit_latency_ms": quantiles([r["timings_ms"]["end_to_end"] for r in hits]),
        "miss_latency_ms": quantiles([r["timings_ms"]["end_to_end"] for r in records if not r["cache_hit"]]),
        "model_calls": len(calls),
        "planning_calls": sum(c["kind"] == "planning" for c in calls),
        "answer_calls": sum(c["kind"] == "answer" for c in calls),
        "tool_calls": sum(len(r["executions"]) for r in records),
        "replans": sum(r["replans"] for r in records),
        "tokens": {
            key: sum(c.get("usage", {}).get(key, 0) for c in calls)
            for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
        },
        "unknown_usage_calls": sum(c.get("cost_estimated", False) for c in calls),
        "status": dict(Counter(r["status"] for r in records)),
        "rejections": dict(Counter(r["rejection"] for r in records if r["rejection"])),
        "authorization_violations": sum(r["evaluation"]["authorization_violations"] for r in rows),
        "wrong_returned_bindings": sum(r["evaluation"]["wrong_returned_bindings"] for r in rows),
        "bad_result_reached_answer": sum(r["evaluation"]["bad_result_reached_answer"] for r in rows),
        "unnecessary_clarifications": sum(r["evaluation"]["unnecessary_clarification"] for r in rows),
        "unnecessary_refusals": sum(r["evaluation"].get("unnecessary_refusal", False) for r in rows),
        "appropriate_abstentions": sum(r["evaluation"].get("appropriate_abstention", False) for r in rows),
        "unresolved": sum(r["evaluation"].get("unresolved", not r["evaluation"]["success"]) for r in rows),
        "mean_decomposition_ms": {
            key: float(np.mean([r["timings_ms"].get(key, 0) for r in records]))
            for key in ("binding", "retrieval_validation", "planning", "answer", "tools", "persistence")
        },
    }


def paired_uncertainty(rows, policy, seed=1729, samples=2000):
    groups = defaultdict(list)
    for row in rows:
        if row["bank_state"] == "warm" and row["policy"] in ("fused", policy):
            groups[row["cluster"]].append(row)
    groups = {
        key: values for key, values in groups.items() if {r["policy"] for r in values} == {"fused", policy}
    }
    if not groups:
        return {}
    clusters = list(groups)
    rng = np.random.default_rng(seed)

    def statistics(selected):
        base = [r for key in selected for r in groups[key] if r["policy"] == "fused"]
        candidate = [r for key in selected for r in groups[key] if r["policy"] == policy]

        def metrics(rs):
            success = sum(r["evaluation"]["success"] for r in rs)
            return (
                success / len(rs),
                sum(r["record"]["cost_usd"] for r in rs) / max(success, 1),
                float(np.median([r["record"]["timings_ms"]["end_to_end"] for r in rs])),
            )

        b, c = metrics(base), metrics(candidate)
        return [c[0] - b[0], 1 - c[1] / b[1] if b[1] else 0, 1 - c[2] / b[2] if b[2] else 0]

    draws = np.array([statistics(rng.choice(clusters, len(clusters), replace=True)) for _ in range(samples)])
    # One-sided exact zero-event bound at the cluster level is still several percent
    # at n=64; the bootstrap must not be sold as a 1% safety guarantee.
    harmful = sum(
        any(r["evaluation"]["success"] for r in values if r["policy"] == "fused")
        and any(not r["evaluation"]["success"] for r in values if r["policy"] == policy)
        for values in groups.values()
    )
    upper = (
        1 - 0.05 ** (1 / len(clusters))
        if harmful == 0
        else min(1.0, harmful / len(clusters) + math.sqrt(math.log(20) / (2 * len(clusters))))
    )
    return {
        "clusters": len(clusters),
        "point": statistics(clusters),
        "metric_order": ["success_rate_difference", "cost_per_success_reduction", "median_latency_reduction"],
        "paired_cluster_bootstrap_95pct": np.percentile(draws, [2.5, 97.5], axis=0).T.tolist(),
        "harmful_clusters": harmful,
        "conservative_harmful_cluster_rate_upper_95pct": upper,
        "method": "resample base-request clusters, retaining all conditions and repetitions; zero-event exact bound or Hoeffding upper bound",
    }


def make_graphics(out, summaries, break_even):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {"figure.dpi": 150, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False}
    )
    warm = {name.split(":")[0]: value for name, value in summaries.items() if name.endswith(":warm")}
    labels = list(warm)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for name, value in warm.items():
        if value["cost_per_success_usd"] is not None:
            ax.scatter(value["cost_per_success_usd"], value["success_rate"], s=65)
            ax.annotate(
                name,
                (value["cost_per_success_usd"], value["success_rate"]),
                xytext=(5, 5),
                textcoords="offset points",
            )
    ax.set(
        xlabel="Measured USD per successful resolution",
        ylabel="Mechanical task success",
        ylim=(0, 1.08),
        title="Observed quality and cost",
    )
    fig.tight_layout()
    fig.savefig(out / "quality-cost.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bottom = np.zeros(len(labels))
    for stage in ("binding", "retrieval_validation", "planning", "tools", "answer", "persistence"):
        values = np.array([warm[label]["mean_decomposition_ms"][stage] for label in labels])
        ax.bar(labels, values, bottom=bottom, label=stage)
        bottom += values
    ax.set(ylabel="Mean elapsed milliseconds", title="Request latency components")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "latency-components.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for idx, kind in enumerate(("hit_latency_ms", "miss_latency_ms")):
        values = [warm[label][kind]["p50"] if warm[label][kind] else np.nan for label in labels]
        ax.bar(np.arange(len(labels)) + idx * 0.35, values, width=0.35, label=kind.replace("_latency_ms", ""))
    ax.set(
        xticks=np.arange(len(labels)) + 0.175,
        xticklabels=labels,
        ylabel="Median milliseconds",
        title="Warm hits and miss paths",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "hit-miss.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.bar(labels, [warm[label]["false_hits"] for label in labels], label="Incorrect accepted reuse")
    ax.set(ylabel="Observed endpoint count", title="Semantic reuse execution errors")
    ax.yaxis.get_major_locator().set_params(integer=True)
    fig.tight_layout()
    fig.savefig(out / "reuse-errors.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for name, value in break_even.items():
        saving = value["saving_per_warm_request_usd"]
        counts = np.linspace(0, max(1000, (value["requests_to_amortize"] or 0) * 1.5), 100)
        ax.plot(counts, counts * saving - value["construction_cost_usd"], label=name)
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set(
        xlabel="Repeated requests (scenario estimate)",
        ylabel="Estimated net USD saved",
        title="Construction-cost break-even: estimated repeat traffic",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "break-even.png")
    plt.close(fig)


def analyze(root, settings, *, split="test", calibrate=False):
    if calibrate:
        return calibrate_development(root)
    if split == "test":
        verify_freeze(root, settings)
    configuration = config_hash(root, settings)
    rows = [
        r
        for r in read_jsonl(root / "runs.jsonl")
        if r["split"] == split and r["configuration"] == configuration
    ]
    if not rows:
        raise ValueError("no measured rows with the current configuration")
    groups = defaultdict(list)
    for row in rows:
        groups[f"{row['policy']}:{row['bank_state']}"].append(row)
    summaries = {key: summary(value) for key, value in groups.items()}
    cfg = load_config(root)
    cases, _ = inputs_and_references(root)
    expected = sum(
        len(conditions(c, cfg.ordinary_subset)) * (2 if split == "test" else 1)
        for c in cases
        if c["split"] == split
    )
    construction = json.loads((root / "seed.json").read_text())["construction_cost_usd"]
    base = summaries.get("fused:warm", {})
    break_even = {}
    for policy in ("exact", "verified"):
        candidate = summaries.get(f"{policy}:warm")
        if candidate and base:
            saving = base["cost_usd"] / base["n"] - candidate["cost_usd"] / candidate["n"]
            break_even[policy] = {
                "construction_cost_usd": construction,
                "saving_per_warm_request_usd": saving,
                "requests_to_amortize": math.ceil(construction / saving) if saving > 0 else None,
                "repeat_rate_scenarios_estimates": {
                    str(rate): math.ceil(construction / (saving * rate)) if saving > 0 else None
                    for rate in (0.25, 0.5, 0.75, 1.0)
                },
            }
    paired = {policy: paired_uncertainty(rows, policy) for policy in ("exact", "ordinary", "verified")}
    verified = paired.get("verified", {})
    targets = bool(
        verified
        and verified["point"][0] >= 0
        and verified["point"][1] >= 0.2
        and verified["point"][2] >= 0.15
        and summaries["verified:warm"]["authorization_violations"] == 0
    )
    result = {
        "split": split,
        "configuration": configuration,
        "measured_endpoints": len(rows),
        "expected_endpoints": expected,
        "complete": len(rows) == expected,
        "summaries": summaries,
        "paired": paired,
        "break_even": break_even,
        "engineering_targets_observed": targets,
        "limits": [
            "mechanical path and required-fact checks do not prove semantic task success",
            "64 held-out clusters cannot establish a 1% production-risk guarantee",
            "read-only local fixture service with real model calls; no production traffic or concurrency claim",
        ],
    }
    out = root / "analysis" / split
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "summary.json", result)
    make_graphics(out, summaries, break_even)
    lines = [
        "# Verified plan reuse: measured local experiment",
        "",
        f"Split: {split}. Measured {len(rows)}/{expected} endpoints.",
        "",
        "All reported model costs and latencies come from real calls; tools use the local HTTP fixture service.",
        "",
        "|Condition|Success|USD/success|p50 ms|p95 ms|Planning calls|Reuse hits|Incorrect hits|",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, value in sorted(summaries.items()):
        cost = value["cost_per_success_usd"]
        lines.append(
            f"|{name}|{value['successes']}/{value['n']}|{cost if cost is not None else 'undefined'}|{value['latency_ms']['p50']:.1f}|{value['latency_ms']['p95']:.1f}|{value['planning_calls']}|{value['hits']}|{value['false_hits']}|"
        )
    lines += [
        "",
        f"Observed engineering targets met: {targets}. This is an observation, not a production guarantee.",
        "",
        "Paired intervals resample base-request clusters, keeping repetitions and conditions together. See summary.json for intervals, harmful-regression bounds, token accounting, statuses, and rejection reasons.",
        "",
        "Construction cost includes history attempts. Break-even and reweighted repeat-rate scenarios are estimates, not measured production traffic.",
        "",
        "Scoring checks execution paths, resource roles, and required facts in answers. It is not a semantic or human answer-quality judgment. Blocked unsafe actions count as safe failures, not completed tasks.",
        "",
    ]
    for filename in ("quality-cost", "latency-components", "hit-miss", "reuse-errors", "break-even"):
        lines += [f"![{filename}]({filename}.png)", ""]
    lines += ["## Limits", "", *[f"- {line}" for line in result["limits"]]]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    return {
        "report": str(out / "report.md"),
        "summary": str(out / "summary.json"),
        "complete": result["complete"],
    }
