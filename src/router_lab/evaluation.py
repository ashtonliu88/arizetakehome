from __future__ import annotations

import numpy as np

from .models import ACTIONS, RouteResult, validate_probabilities


def route_accuracy(output, expected):
    return output["final_action"] == expected["expected_action"]


def outcome(result: RouteResult, expected: str) -> dict:
    initial_correct = result.initial_action == expected
    final_correct = result.final_action == expected
    return {
        "initial_correct": initial_correct,
        "correct": final_correct,
        "rescue": bool(result.fallback and not initial_correct and final_correct),
        "regression": bool(result.fallback and initial_correct and not final_correct),
        "operational_failure": result.final_action is None,
        "operational_error": bool(result.errors),
        "failure_taxonomy": (
            "operational_failure"
            if result.final_action is None
            else "fallback_regression"
            if result.fallback and initial_correct and not final_correct
            else "unrecovered_route_error"
            if not final_correct
            else "rescued"
            if result.fallback and not initial_correct
            else "correct"
        ),
    }


def brier_score(probabilities: dict[str, float], expected: str) -> float:
    validate_probabilities(probabilities)
    if expected not in ACTIONS:
        raise ValueError("invalid expected action")
    # Multiclass convention: sum across classes (range 0..2), not mean over classes.
    return sum((probabilities[a] - int(a == expected)) ** 2 for a in ACTIONS)


def confidence_bin(value: float) -> int:
    if not np.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("confidence outside [0,1]")
    return min(4, int(value * 5))


def reliability(pairs: list[tuple[float, bool]]) -> tuple[list[dict], float | None]:
    bins = []
    total = len(pairs)
    ece = 0.0
    for i in range(5):
        group = [(c, correct) for c, correct in pairs if confidence_bin(c) == i]
        mean_confidence = float(np.mean([c for c, _ in group])) if group else None
        accuracy = float(np.mean([correct for _, correct in group])) if group else None
        if group:
            ece += len(group) / total * abs(mean_confidence - accuracy)
        bins.append(
            {
                "bin": i,
                "lower": i / 5,
                "upper": (i + 1) / 5,
                "count": len(group),
                "confidence": mean_confidence,
                "accuracy": accuracy,
            }
        )
    return bins, ece if total else None


def overlap(decisions: list[bool], llm: list[bool]) -> dict:
    if len(decisions) != len(llm):
        raise ValueError("unpaired overlap inputs")
    return {
        "both_correct": sum(d and llm for d, llm in zip(decisions, llm, strict=True)),
        "decision_only_correct": sum(d and not llm for d, llm in zip(decisions, llm, strict=True)),
        "llm_only_correct": sum(not d and llm for d, llm in zip(decisions, llm, strict=True)),
        "both_wrong": sum(not d and not llm for d, llm in zip(decisions, llm, strict=True)),
    }


def grouped_paired_interval(values: dict[str, list[float]], *, seed=1729, samples=2000) -> list[float]:
    """Resample questions; all paired repetitions travel together as one cluster."""
    if not values:
        raise ValueError("no examples to bootstrap")
    per_question = np.array([np.mean(v) for _, v in sorted(values.items())])
    rng = np.random.default_rng(seed)
    draws = rng.choice(per_question, size=(samples, len(per_question)), replace=True).mean(axis=1)
    return [float(x) for x in np.quantile(draws, [0.025, 0.975])]
