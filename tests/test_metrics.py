import pytest

from router_lab.evaluation import (
    brier_score,
    confidence_bin,
    grouped_paired_interval,
    outcome,
    overlap,
    reliability,
)
from router_lab.models import ACTIONS, RouteResult, Usage


def test_rescue_regression_hand_calculated():
    rescue = RouteResult(
        initial_action="search_code", final_action="search_docs", fallback=True, fallback_reason="confidence"
    )
    regression = RouteResult(
        initial_action="search_docs", final_action="calculate", fallback=True, fallback_reason="confidence"
    )
    unchanged = RouteResult(initial_action="search_docs", final_action="search_docs")
    results = [outcome(r, "search_docs") for r in (rescue, regression, unchanged)]
    assert sum(r["rescue"] for r in results) == 1
    assert sum(r["regression"] for r in results) == 1
    assert sum(r["correct"] for r in results) == 2
    assert overlap([False, True, True, False], [True, False, True, False]) == {
        "both_correct": 1,
        "decision_only_correct": 1,
        "llm_only_correct": 1,
        "both_wrong": 1,
    }


def test_cache_accounting(settings):
    u = Usage(input_tokens=1000, cache_read_tokens=200, cache_write_tokens=100, output_tokens=50)
    d = settings.pricing["decisions"].cost(u)
    llm = settings.pricing["llm"].cost(u)
    assert d == pytest.approx((700 * 0.1 + 200 * 0.01 + 100 * 0.125) / 1e6)
    assert llm == pytest.approx((700 * 2 + 200 * 0.1 + 100 * 2.5 + 50 * 10) / 1e6)
    assert d + llm == pytest.approx(0.0022545)
    with pytest.raises(ValueError):
        Usage(input_tokens=1, cache_read_tokens=2)


def test_multiclass_brier_sum_convention():
    p = {a: 0.0 for a in ACTIONS}
    p["calculate"] = 1
    assert brier_score(p, "calculate") == 0
    assert brier_score(p, "search_docs") == 2
    p = {a: 1 / 8 for a in ACTIONS}
    assert brier_score(p, "calculate") == pytest.approx(0.875)


@pytest.mark.parametrize(
    "confidence,bin_index", [(0, 0), (0.1999, 0), (0.2, 1), (0.4, 2), (0.6, 3), (0.8, 4), (1, 4)]
)
def test_five_bin_boundaries(confidence, bin_index):
    assert confidence_bin(confidence) == bin_index


def test_exploratory_ece_and_cluster_bootstrap():
    bins, ece = reliability([(0.5, True), (0.5, False), (1, True)])
    assert sum(b["count"] for b in bins) == 3
    assert ece == 0
    clustered = {"question-a": [1, 1, 1], "question-b": [0, 0, 0]}
    interval = grouped_paired_interval(clustered, seed=0)
    assert interval == [0, 1]  # two independent questions, not six independent trials
