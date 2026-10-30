"""Add a concise findings report to the frozen study's mechanical analysis.

Offline only: does not import runtime, mutate the study, or invoke a model.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from router_lab.util import digest, read_jsonl, write_json


def write_findings(root=Path("results/reuse")):
    summary = json.loads((root / "analysis/test/summary.json").read_text())
    if not summary["complete"]:
        raise ValueError("complete held-out matrix required")
    frozen = json.loads((root / "frozen.json").read_text())
    configuration = digest(frozen["fingerprint"])
    if configuration != summary["configuration"]:
        raise ValueError("summary does not match freeze")
    all_rows = read_jsonl(root / "runs.jsonl")
    rows = [r for r in all_rows if r["split"] == "test" and r["configuration"] == configuration]
    if len({r["run_id"] for r in rows}) != 768:
        raise ValueError("expected 768 distinct held-out measurements")
    calls = {r["reservation"]: r for r in read_jsonl(root / "model-calls.jsonl")}
    global_ledger = {r["id"]: r for r in read_jsonl(root.parent / "budget.jsonl")}
    summaries = summary["summaries"]
    # Offline presentation refinement: nearby exact/verified points need
    # staggered labels. The frozen runtime and measurements stay unchanged.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 4.5), dpi=150)
    colors = {"fused": "#1f77b4", "verified": "#ff7f0e", "exact": "#2ca02c", "ordinary": "#d62728"}
    for name in ("fused", "verified", "exact", "ordinary"):
        values = summaries[name + ":warm"]
        point = (values["cost_per_success_usd"], values["success_rate"])
        ax.scatter(*point, s=65, color=colors[name])
        ax.annotate(
            name,
            point,
            xytext={"exact": (-30, 20), "verified": (7, 4), "ordinary": (7, -20), "fused": (7, 8)}[name],
            textcoords="offset points",
        )
    ax.set(
        xlabel="Measured USD per successful resolution",
        ylabel="Mechanical task success",
        ylim=(0, 1.08),
        title="Observed quality and cost",
    )
    ax.margins(x=0.15)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(root / "analysis/test/quality-cost.png")
    plt.close(fig)
    base = summaries["fused:warm"]
    verified = summaries["verified:warm"]
    exact = summaries["exact:warm"]
    empty_tail_change = (
        summaries["verified:empty"]["latency_ms"]["p95"] / summaries["fused:empty"]["latency_ms"]["p95"] - 1
    )
    comparison = summary["paired"]["verified"]
    exact_comparison = summary["paired"]["exact"]
    cost_reduction, latency_reduction = comparison["point"][1:3]
    exact_targets = (
        exact_comparison["point"][0] >= 0
        and exact_comparison["point"][1] >= 0.2
        and exact_comparison["point"][2] >= 0.15
        and exact_comparison["harmful_clusters"] == 0
        and exact["authorization_violations"] == 0
    )
    recommendation = (
        "Prefer exact-skeleton reuse for v1: it meets the engineering cost/median-latency targets with no observed harmful clusters. "
        "Semantic compatibility remains useful evidence, but this workload does not require its added complexity to meet those targets."
        if exact_targets
        else "Verified semantic reuse offers the larger observed efficiency gain on this workload. Exact reuse remains the simpler control; "
        "the paired intervals below limit claims about the size and generality of the difference."
    )
    # Exploratory p95 interval uses the same predeclared paired cluster unit.
    clusters = sorted({r["cluster"] for r in rows})
    latencies = {
        (p, c): [
            r["record"]["timings_ms"]["end_to_end"]
            for r in rows
            if r["policy"] == p and r["bank_state"] == "warm" and r["cluster"] == c
        ]
        for p in ("fused", "exact", "verified")
        for c in clusters
    }
    rng = np.random.default_rng(1729)
    tail = {p: [] for p in ("exact", "verified")}
    for _ in range(2000):
        selected = rng.choice(clusters, len(clusters), replace=True)
        baseline = np.percentile([v for c in selected for v in latencies["fused", c]], 95)
        for policy in tail:
            value = np.percentile([v for c in selected for v in latencies[policy, c]], 95)
            tail[policy].append(1 - value / baseline)
    tail_intervals = {p: np.percentile(values, [2.5, 97.5]).tolist() for p, values in tail.items()}
    failures = [r for r in rows if r["evaluation"]["incorrect_accepted_reuse"]]
    # Shared family wording can correlate nominal base-request clusters. This
    # sensitivity bound avoids presenting 64 synthetic instances as broad traffic.
    families = {r["family"] for r in rows}
    family_zero_event_upper = 1 - 0.05 ** (1 / len(families)) if comparison["harmful_clusters"] == 0 else None
    audit = {
        "configuration": configuration,
        "endpoints_all_phases": len(all_rows),
        "held_out_endpoints": len(rows),
        "earlier_configuration_endpoints": sum(
            r["split"] == "dev" and r["configuration"] != configuration for r in all_rows
        ),
        "model_calls": len(calls),
        "usage_unknown_calls": sum(r.get("cost_estimated", True) for r in calls.values()),
        "reuse_committed_usd": sum(r["cost_usd"] for r in calls.values()),
        "global_committed_usd": sum(r["amount"] for r in global_ledger.values()),
        "held_out_incorrect_reuse_by_family": dict(Counter(r["family"] for r in failures)),
        "held_out_incorrect_reuse_runs": [r["run_id"] for r in failures],
        "p95_reduction_paired_cluster_bootstrap_95pct_exploratory": tail_intervals,
        "family_dependence_zero_harm_95pct_upper_sensitivity": family_zero_event_upper,
        "exact_meets_core_targets_without_observed_harmful_clusters": exact_targets,
        "recommendation": recommendation,
        "empty_bank_verified_p95_change_vs_fused": empty_tail_change,
        "report_script_hash": digest(Path(__file__)),
    }
    write_json(root / "execution-verification.json", audit)
    lines = [
        "# Verified plan reuse: findings",
        "",
        f"The frozen held-out study completed **768 endpoint runs over 64 clusters**, with two repetitions of six conditions. "
        f"Verified reuse reduced cost per successful resolution by **{cost_reduction:.1%}** and warm median latency by **{latency_reduction:.1%}** against fused planning.",
        "",
        f"Verified reuse resolved {verified['successes']}/{verified['n']} endpoints versus {base['successes']}/{base['n']} for fused planning. "
        f"It had {verified['false_hits']} incorrect accepted reuse hits, {comparison['harmful_clusters']} observed harmful clusters, and {verified['authorization_violations']} executed authorization violations. "
        "These are mechanical path/required-fact judgments, not semantic or human answer-quality certification.",
        "",
        recommendation,
        "",
        "|Condition|Resolved|Appropriate abstentions|USD/resolution|p50 ms|p95 ms|Reuse hits|Incorrect hits|",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in sorted(summaries.items()):
        lines.append(
            f"|{name}|{s['successes']}/{s['n']}|{s['appropriate_abstentions']}|{s['cost_per_success_usd']:.6f}|{s['latency_ms']['p50']:.0f}|{s['latency_ms']['p95']:.0f}|{s['hits']}|{s['false_hits']}|"
        )
    lines += [
        "",
        "## Paired uncertainty and tails",
        "",
        f"Verified paired 95% cluster-bootstrap intervals: success-rate difference {comparison['paired_cluster_bootstrap_95pct'][0]}; "
        f"cost reduction {comparison['paired_cluster_bootstrap_95pct'][1]}; median-latency reduction {comparison['paired_cluster_bootstrap_95pct'][2]}.",
        "",
        f"The conservative 95% upper bound on harmful-cluster rate is {comparison['conservative_harmful_cluster_rate_upper_95pct']:.1%}. "
        "This does not establish a 1% production-risk guarantee. "
        f"Because instances share family wording, the exploratory eight-family zero-event bound is {family_zero_event_upper}; independence assumptions matter.",
        "",
        f"Verified p95 latency is {verified['latency_ms']['p95']:.0f} ms versus {base['latency_ms']['p95']:.0f} ms for fused planning. "
        f"The exploratory paired p95-reduction interval is {tail_intervals['verified']}. Tail results remain visible regardless of the median.",
        "",
        "## Cost, construction, and provenance",
        "",
        f"All phases used {audit['model_calls']} real model calls, with {audit['usage_unknown_calls']} usage-unknown calls. "
        f"Reuse-study committed cost was ${audit['reuse_committed_usd']:.4f}; the shared global ledger total was ${audit['global_committed_usd']:.4f}. "
        f"The study retains {audit['earlier_configuration_endpoints']} earlier pilot endpoints, charged to budget and excluded from final comparisons.",
        "",
        "The frozen bank contains 14 admitted plans from 16 attempted history executions. It stores slots and dependencies rather than arguments, results, or answers. "
        "Eight family contracts were approved; generated substitutions remain derived references. The frozen source/configuration archive and all journals remain available.",
        "",
        f"Construction and break-even details: `{json.dumps(summary['break_even'], sort_keys=True)}`.",
        "",
        "Repeat-rate scenarios are estimates that scale measured warm-workload savings linearly; they assume no additional miss cost. "
        "They are not measured production traffic. Costs use actual API usage with frozen pricing assumptions, and exclude engineering/review labor.",
        "",
        "## Observed semantic reuse errors",
        "",
        f"Incorrect accepted reuse endpoints by family: {audit['held_out_incorrect_reuse_by_family']}. "
        "The diagnostic retained all authorization/schema/returned-binding guards. Those guards do not prove semantic intent. "
        "See runs.jsonl for exact paths and responses. The bad-result flag conservatively marks answer generation after an incorrect path; it does not prove an incorrect resource was mentioned to the user.",
        "",
    ]
    for name in ("quality-cost", "latency-components", "hit-miss", "reuse-errors", "break-even"):
        lines += [f"![{name}](analysis/test/{name}.png)", ""]
    lines += [
        "## Limits",
        "",
        "This is a small, deliberately recurring, read-only local fixture workload with real model calls. "
        "Unresolved and appropriately abstained requests are not completed resolutions. Mechanical scoring, selected wording, provider caching, "
        "and only 64 independent clusters constrain generalization. There is no production deployment, concurrency SLO, result cache, or formal privacy claim.",
    ]
    lines[6:6] = [
        f"**Empty-bank tail:** verified p95 was {empty_tail_change:.1%} higher than fused empty-bank p95. "
        "The warm median gains do not establish a miss-path tail-latency improvement.",
        "",
    ]
    for index, line in enumerate(lines):
        if line.startswith("Construction and break-even details:"):
            lines[index] = (
                f"API construction cost was ${summary['break_even']['exact']['construction_cost_usd']:.4f}. "
                f"Estimated warm requests to amortize construction: exact {summary['break_even']['exact']['requests_to_amortize']}, "
                f"verified {summary['break_even']['verified']['requests_to_amortize']}. Full scenarios are in analysis/test/summary.json."
            )
    markdown = "\n".join(lines) + "\n"
    for interval in [*comparison["paired_cluster_bootstrap_95pct"], tail_intervals["verified"]]:
        markdown = markdown.replace(str(interval), f"{interval[0]:.1%} to {interval[1]:.1%}")
    if family_zero_event_upper is not None:
        markdown = markdown.replace(str(family_zero_event_upper), f"{family_zero_event_upper:.1%}")
    (root / "findings.md").write_text(markdown)
    return audit


if __name__ == "__main__":
    print(json.dumps(write_findings(), indent=2))
