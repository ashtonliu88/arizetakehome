import pytest

from router_lab.budget import Budget, BudgetExceeded
from router_lab.cli import parser, run
from router_lab.experiments import Checkpoints
from router_lab.gate import pair_baselines, random_control, replay, select_gate
from router_lab.models import CallRecord, RouteResult
from router_lab.util import append_jsonl


def paired_rows():
    rows = []
    # A is recoverable; B regresses if escalated. Different confidence signals.
    for i, (decision, llm, confidence) in enumerate(
        [("search_code", "search_docs", 0.2), ("search_docs", "calculate", 0.9)]
    ):
        for policy, action, cost in [("decisions", decision, 0.001), ("llm", llm, 0.01)]:
            r = RouteResult(
                initial_action=action,
                final_action=action,
                decision_confidence=confidence if policy == "decisions" else None,
                cost_usd=cost,
                calls=[CallRecord(kind=policy, action=action, cost_usd=cost)],
            )
            rows.append(
                {
                    "example_id": f"q{i}",
                    "repetition": 1,
                    "split": "dev",
                    "policy": policy,
                    "expected_action": "search_docs",
                    "configuration_hash": "same",
                    "result": r.model_dump(),
                }
            )
    return rows


def test_gate_and_random_control_hand_fixture():
    pairs = pair_baselines(paired_rows(), "dev", 1, ["q0", "q1"])
    selected = select_gate(pairs)
    # Threshold .0 matches the 50% LLM baseline and costs least, as specified.
    assert selected["selected"]["threshold"] == 0
    assert selected["selected"]["accuracy"] == 0.5
    useful = replay(pairs, 0.25)
    assert useful["accuracy"] == 1 and useful["rescues"] == 1 and useful["regressions"] == 0
    assert replay(pairs, 1, always=True)["accuracy"] == 0.5
    random = random_control(pairs, useful, seed=1729, samples=1000)
    assert 0.45 < random["accuracy_mean"] < 0.55
    assert random == random_control(pairs, useful, seed=1729, samples=1000)


def test_no_useful_saving_preserves_llm_recommendation():
    rows = paired_rows()
    # Both decision routes wrong; LLM perfect; always fallback is feasible but costs extra.
    for row in rows:
        row["result"]["final_action"] = "calculate" if row["policy"] == "decisions" else "search_docs"
    selected = select_gate(pair_baselines(rows, "dev"))
    assert selected["selected"]["accuracy"] == 1
    assert not selected["saves_cost"]
    assert "LLM-only" in selected["recommendation"]


def test_pairs_reject_missing_and_duplicates():
    rows = paired_rows()
    with pytest.raises(ValueError):
        pair_baselines(rows[:-1], "dev")
    with pytest.raises(ValueError):
        pair_baselines(rows + [rows[0]], "dev")
    with pytest.raises(ValueError):
        pair_baselines(rows, "dev", 3, ["q0", "q1"])


def test_resume_does_not_duplicate_completed_rows(tmp_path):
    path = tmp_path / "dev.jsonl"
    rows = paired_rows()
    c = Checkpoints(path, "same")
    c.add(rows[0])
    resumed = Checkpoints(path, "same")
    assert resumed.get("decisions", "q0", 1) == rows[0]
    with pytest.raises(ValueError):
        resumed.add(rows[0])
    assert len(Checkpoints(path, "same").completed) == 1
    with pytest.raises(ValueError):
        Checkpoints(path, "changed")
    path.write_text(path.read_text() + '{"partial":')
    with pytest.raises(ValueError, match="corrupt checkpoint"):
        Checkpoints(path, "same")


def test_durable_budget_reservation_includes_interrupted_calls(tmp_path):
    path = tmp_path / "budget.jsonl"
    budget = Budget(path, limit=1, reserve=0.2)
    first = budget.reserve_call(0.3, "llm")
    assert Budget(path, 1, 0.2).spent == pytest.approx(0.3)
    budget.settle(first, 0.1)
    assert budget.spent == pytest.approx(0.1)
    budget.reserve_call(0.4, "llm")
    with pytest.raises(BudgetExceeded):
        budget.check(0.31)
    budget.check(0.49, headroom=False)


def test_test_cli_refuses_unfrozen_before_clients(monkeypatch, tmp_path):
    args = parser().parse_args(["--results-dir", str(tmp_path), "benchmark", "--split", "test"])
    with pytest.raises(ValueError, match="--frozen"):
        run(args)
    args.frozen = True
    with pytest.raises(ValueError, match="frozen manifest"):
        run(args)


def test_test_results_cannot_trigger_development_retuning(tmp_path, settings):
    from router_lab.cli import select_and_freeze

    append_jsonl(tmp_path / "test.jsonl", {"anything": "already evaluated"})
    with pytest.raises(ValueError, match="do not retune"):
        select_and_freeze(settings, tmp_path)
