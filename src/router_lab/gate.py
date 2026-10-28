from __future__ import annotations

from collections import defaultdict

import numpy as np

from .models import RouteResult


def pair_baselines(rows: list[dict], split: str, repetitions=3, expected_ids=None):
    selected = [r for r in rows if r["split"] == split and r["policy"] in ("llm", "decisions")]
    groups = defaultdict(dict)
    configurations = set()
    for row in selected:
        key = (row["example_id"], row["repetition"])
        if row["policy"] in groups[key]:
            raise ValueError("duplicate baseline checkpoint row")
        groups[key][row["policy"]] = row
        configurations.add(row["configuration_hash"])
    if len(configurations) != 1:
        raise ValueError("baseline configurations differ or no baseline data")
    if any(set(pair) != {"llm", "decisions"} for pair in groups.values()):
        raise ValueError("incomplete paired baseline outputs")
    if expected_ids is not None:
        expected_keys = {(i, r) for i in expected_ids for r in range(1, repetitions + 1)}
        if set(groups) != expected_keys:
            raise ValueError("baseline coverage differs from the required split/repetitions")
    for pair in groups.values():
        if pair["llm"]["expected_action"] != pair["decisions"]["expected_action"]:
            raise ValueError("paired expected labels differ")
    return [(key, pair["decisions"], pair["llm"]) for key, pair in sorted(groups.items())]


def needs_fallback(decision: RouteResult, threshold: float, always=False):
    if decision.final_action is None or decision.decision_confidence is None:
        return True
    return always or decision.decision_confidence < threshold


def replay(pairs, threshold: float, always=False, selection=None):
    n = len(pairs)
    correct, cost, fallbacks, rescues, regressions = 0, 0.0, 0, 0, 0
    for i, (_, drow, lrow) in enumerate(pairs):
        decision, llm = RouteResult.model_validate(drow["result"]), RouteResult.model_validate(lrow["result"])
        expected = drow["expected_action"]
        fallback = needs_fallback(decision, threshold, always) if selection is None else i in selection
        final = llm if fallback else decision
        correct += final.final_action == expected
        fallbacks += fallback
        cost += decision.cost_usd + (llm.cost_usd if fallback else 0)
        rescues += fallback and decision.initial_action != expected and llm.final_action == expected
        regressions += fallback and decision.initial_action == expected and llm.final_action != expected
    return {
        "threshold": threshold,
        "always_fallback": always,
        "accuracy": correct / n,
        "cost_per_request": cost / n,
        "fallback_rate": fallbacks / n,
        "fallbacks": fallbacks,
        "rescues": int(rescues),
        "regressions": int(regressions),
        "measurement": "offline replay estimate",
        "requests": n,
    }


def select_gate(pairs):
    llm_accuracy = sum(llm["result"]["final_action"] == llm["expected_action"] for _, _, llm in pairs) / len(
        pairs
    )
    llm_cost = sum(llm["result"]["cost_usd"] for _, _, llm in pairs) / len(pairs)
    candidates = [replay(pairs, i / 20) for i in range(21)] + [replay(pairs, 1.0, True)]
    feasible = [r for r in candidates if r["accuracy"] >= llm_accuracy]
    chosen = min(
        feasible, key=lambda r: (round(r["cost_per_request"], 12), -r["accuracy"], r["fallback_rate"])
    )
    return {
        "selected": chosen,
        "candidates": candidates,
        "llm_accuracy": llm_accuracy,
        "llm_cost_per_request": llm_cost,
        "saves_cost": chosen["cost_per_request"] < llm_cost,
        "recommendation": "hybrid candidate"
        if chosen["cost_per_request"] < llm_cost
        else "LLM-only; no cost-saving feasible hybrid",
    }


def random_control(pairs, selected, seed=1729, samples=1000):
    # Operational fallbacks are mandatory. Randomize only discretionary escalation,
    # matching the confidence gate's count within every repetition.
    by_rep = defaultdict(list)
    mandatory = set()
    target = defaultdict(int)
    for i, (key, d, _) in enumerate(pairs):
        result = RouteResult.model_validate(d["result"])
        rep = key[1]
        if result.final_action is None or result.decision_confidence is None:
            mandatory.add(i)
        else:
            by_rep[rep].append(i)
            if needs_fallback(result, selected["threshold"], selected["always_fallback"]):
                target[rep] += 1
    rng = np.random.default_rng(seed)
    results = []
    for _ in range(samples):
        selection = set(mandatory)
        for rep, indices in by_rep.items():
            selection.update(int(x) for x in rng.choice(indices, size=target[rep], replace=False))
        results.append(replay(pairs, 0, selection=selection))
    return {
        "measurement": "seeded matched-rate random replay, not live latency",
        "seed": seed,
        "samples": samples,
        "mandatory_operational_fallbacks": len(mandatory),
        "accuracy_mean": float(np.mean([r["accuracy"] for r in results])),
        "accuracy_randomization_interval": [
            float(x) for x in np.quantile([r["accuracy"] for r in results], [0.025, 0.975])
        ],
        "cost_per_request_mean": float(np.mean([r["cost_per_request"] for r in results])),
        "confidence_gate_accuracy": selected["accuracy"],
    }
