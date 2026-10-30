from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from router_lab.budget import Budget, BudgetExceeded
from router_lab.cli import parser
from router_lab.manifest import load_settings
from router_lab.models import Usage
from router_lab.reuse.bank import admit_history, compatible, parameterize, resolve, retrieve
from router_lab.reuse.bindings import bind
from router_lab.reuse.contracts import ApplicationContext, PlannedResponse, RequestInput, ReuseSettings, Step
from router_lab.reuse.dataset import FAMILIES, build_case, build_dataset
from router_lab.reuse.provider import LiveModel, planning_schema
from router_lab.reuse.runtime import execute_request
from router_lab.reuse.service import GuardError, dispatch, tool_service
from router_lab.reuse.study import (
    assert_no_pending,
    execute_endpoint,
    prepare,
    require_reviews,
    review_family,
)
from router_lab.util import append_jsonl, read_jsonl, write_json


class FakeModel:
    """Explicit plan responses only. Runtime tests never read scoring references."""

    def __init__(self, plan):
        self.value, self.plans, self.answers = plan, 0, 0

    def call_record(self, kind):
        return {
            "kind": kind,
            "cost_usd": 0.001,
            "latency_ms": 1,
            "error": None,
            "usage": Usage().model_dump(),
            "cost_estimated": False,
        }

    def plan(self, inp, bindings, feedback=None):
        self.plans += 1
        return self.value, self.call_record("planning")

    def answer(self, inp, outputs):
        self.answers += 1
        return json.dumps(outputs), self.call_record("answer")


def issue_plan():
    return PlannedResponse(
        kind="tools", steps=[Step(tool="lookup_issue", arguments={"issue_id": "$slot.issue0"})]
    )


def template(request="Show issue ENG-101"):
    return parameterize(
        issue_plan().steps, bind(RequestInput(request=request)), {"history_run": "successful"}
    )


def test_dataset_counts_and_split_clusters():
    cases = build_dataset()
    assert len(cases) == 104
    assert [sum(c["split"] == s for c in cases) for s in ("history", "dev", "test")] == [16, 24, 64]
    assert len({c["cluster"] for c in cases}) == 104
    assert all(c["reference"]["provenance"].startswith("derived") for c in cases)
    for family in FAMILIES[:-1]:
        history = {
            bind(RequestInput.model_validate(c["input"])).skeleton
            for c in cases
            if c["family"] == family and c["split"] == "history"
        }
        novel = build_case("dev", family, 1)
        assert bind(RequestInput.model_validate(novel["input"])).skeleton not in history


def test_skeleton_preserves_wording_roles_order_negation_and_numbers():
    a = bind(RequestInput(request="Compare ENG-1 with ENG-2, not ENG-3"))
    b = bind(RequestInput(request="Compare ENG-90 with ENG-80, not ENG-70"))
    assert a.skeleton == b.skeleton
    assert list(a.slots.values()) == ["ENG-1", "ENG-2", "ENG-3"]
    assert "not" in a.skeleton and "constraint" in a.semantics
    c = bind(RequestInput(request="Subtract 2 from 8"))
    assert c.slots == {"number0": 2.0, "number1": 8.0}
    assert "subtract_from" in c.semantics


def test_binding_context_and_alias_ambiguity():
    inp = RequestInput(
        request="Show deployment for service gateway", context=ApplicationContext(environment="staging")
    )
    assert bind(inp).slots["environment0"] == "staging"
    alias = RequestInput(
        request="Show issue incident", context=ApplicationContext(aliases={"incident": ["ENG-1", "ENG-2"]})
    )
    assert bind(alias).unresolved
    alias.context.aliases = {"incident": ["ENG-99"]}
    assert bind(alias).slots["issue0"] == "ENG-99"


def test_plan_is_resource_free_and_no_previous_payloads():
    plan = template()
    text = plan.model_dump_json()
    assert "ENG-101" not in text and "open" not in text
    assert plan.steps[0].arguments == {"issue_id": "$slot.issue0"}
    with pytest.raises(ValueError, match="parameterized"):
        parameterize(
            [Step(tool="lookup_issue", arguments={"issue_id": "ENG-999"})],
            bind(RequestInput(request="Show ENG-1")),
            {},
        )


def test_duplicate_values_reject_ambiguous_admission():
    with pytest.raises(ValueError, match="unambiguously"):
        parameterize(
            [Step(tool="calculate", arguments={"operation": "add", "left": 2, "right": 2})],
            bind(RequestInput(request="Calculate 2 plus 2")),
            {},
        )


def test_retrieval_exact_and_local_paraphrase():
    plan = template()
    assert retrieve(bind(RequestInput(request="Show issue ENG-999")), [plan], exact=True)[1] == 1
    assert retrieve(bind(RequestInput(request="Fetch issue ENG-999")), [plan], exact=True)[0] is None
    assert retrieve(bind(RequestInput(request="Fetch issue ENG-999")), [plan])[0] == plan


def test_no_artificial_margin_for_duplicate_plan():
    plan = template()
    _, _, gap = retrieve(bind(RequestInput(request="Show issue ENG-9")), [plan, copy.deepcopy(plan)])
    assert gap == 1


@pytest.mark.parametrize(
    "change,reason",
    [
        ("schema", "contract_version"),
        ("tenant", "namespace"),
        ("capability", "namespace"),
        ("multiplicity", "roles_or_multiplicity"),
        ("near_miss", "unknown_semantics"),
    ],
)
def test_compatibility_invalidation(change, reason):
    plan = template()
    inp = RequestInput(request="Show issue ENG-999")
    if change == "schema":
        plan.contracts["lookup_issue"] = "obsolete"
    if change == "tenant":
        inp.context.tenant = "beta"
    if change == "capability":
        inp.context.capabilities = ["search_docs"]
    if change == "multiplicity":
        inp.request += " and ENG-998"
    if change == "near_miss":
        inp.request += " only if assigned to me"
    assert compatible(plan, bind(inp)) == reason


def test_http_tools_fresh_results_and_rebinding():
    case = build_case("test", "issues", 4)
    inp = RequestInput.model_validate(case["input"])
    model = FakeModel(issue_plan())
    plan = template("Get issue ENG-101")
    with tool_service(case["state"]) as adapter:
        record, _ = execute_request(inp, "verified", [plan], ReuseSettings(), model, adapter, "fresh")
    assert record.cache_hit and model.plans == 0 and model.answers == 1
    assert record.executions[0]["bindings"]["issue_id"] == "ENG-10012"
    assert record.executions[0]["result"]["record"]["status"] == "in_progress"


def test_current_issue_link_is_followed():
    case = build_case("test", "linked", 4)
    inp = RequestInput.model_validate(case["input"])
    steps = [
        Step(tool="lookup_issue", arguments={"issue_id": "$slot.issue0"}),
        Step(tool="lookup_test_results", arguments={"test_run_id": "$step.0.record.test_run_id"}),
    ]
    history = RequestInput(request="Get issue ENG-101 and its associated test results")
    plan = parameterize(steps, bind(history), {})
    model = FakeModel(PlannedResponse(kind="tools", steps=steps))
    with tool_service(case["state"]) as adapter:
        record, _ = execute_request(inp, "verified", [plan], ReuseSettings(), model, adapter, "link")
    assert record.cache_hit and model.plans == 0
    assert record.executions[1]["bindings"]["test_run_id"] == "TR-10613"
    assert record.executions[1]["result"]["record"]["outcome"] == "failed"


@pytest.mark.parametrize("policy", ["fused", "exact", "ordinary", "verified"])
def test_authorization_is_common_and_bad_results_cannot_reach_answer(policy):
    case = build_case("test", "issues", 0)
    inp = RequestInput.model_validate(case["input"])
    inp.context.capabilities = ["search_docs"]
    model = FakeModel(issue_plan())
    with tool_service(case["state"]) as adapter:
        record, _ = execute_request(
            inp, policy, [template()], ReuseSettings(threshold=0, margin=0), model, adapter, "deny"
        )
    assert record.status == "safe_failure" and not record.answer and model.answers == 0
    assert not record.executions


def test_wrong_authoritative_binding_blocked_before_answer():
    case = build_case("test", "issues", 0)
    inp = RequestInput.model_validate(case["input"])
    iid = case["reference"]["acceptable_paths"][0][0]["arguments"]["issue_id"]
    case["state"]["acme"]["issues"][iid]["issue_id"] = "ENG-999999"
    model = FakeModel(issue_plan())
    with tool_service(case["state"]) as adapter:
        record, _ = execute_request(inp, "fused", [], ReuseSettings(), model, adapter, "wrong")
    assert record.status == "safe_failure" and "wrong returned binding" == record.error
    assert model.answers == 0


@pytest.mark.parametrize("kind", ["direct", "clarify", "abstain"])
def test_no_extra_answer_or_cache_for_direct_and_missing_fields(kind):
    inp = RequestInput(request="Explain recursion" if kind == "direct" else "Show issue status")
    model = FakeModel(
        PlannedResponse(
            kind=kind, response="It calls itself." if kind == "direct" else "Which issue identifier?"
        )
    )
    with tool_service(build_case("test", "direct", 0)["state"]) as adapter:
        record, _ = execute_request(
            inp, "ordinary", [template()], ReuseSettings(threshold=0, margin=0), model, adapter, "direct"
        )
    assert not record.candidate and not record.cache_hit
    assert model.plans == 1 and model.answers == 0


def test_abstention_is_safe_handling_but_not_a_completed_resolution():
    from router_lab.reuse.contracts import ExecutionRecord
    from router_lab.reuse.scoring import score

    record = ExecutionRecord(
        run_id="denied",
        policy="fused",
        bank_state="warm",
        status="abstained",
        bindings=bind(RequestInput(request="Show issue ENG-1")),
        answer="Permission denied.",
    )
    reference = {"kind": "abstain", "acceptable_paths": [[]], "facts": [], "any_facts": ["permission"]}
    result = score(record, reference)
    assert result["appropriate_abstention"] and not result["success"] and result["unresolved"]


def test_conceptual_question_with_identifier_still_bypasses_reuse():
    inp = RequestInput(request="Explain what an issue identifier such as ENG-1 means")
    model = FakeModel(PlannedResponse(kind="direct", response="It identifies an issue."))
    with tool_service(build_case("test", "direct", 0)["state"]) as adapter:
        record, _ = execute_request(
            inp, "ordinary", [template()], ReuseSettings(threshold=0, margin=0), model, adapter, "concept"
        )
    assert not record.candidate and not record.cache_hit and model.plans == 1 and model.answers == 0


def test_near_match_falls_back_once():
    case = build_case("test", "linked", 2)
    inp = RequestInput.model_validate(case["input"])
    model = FakeModel(issue_plan())
    with tool_service(case["state"]) as adapter:
        record, _ = execute_request(
            inp, "verified", [template()], ReuseSettings(threshold=0, margin=0), model, adapter, "miss"
        )
    assert not record.cache_hit and model.plans == 1


def test_recovery_bounded_to_one_replan_and_three_total_steps():
    inp = RequestInput(request="Show issue ENG-999")
    model = FakeModel(issue_plan())
    with tool_service(build_case("test", "issues", 0)["state"]) as adapter:
        record, _ = execute_request(inp, "fused", [], ReuseSettings(), model, adapter, "repair")
    assert record.replans == 1 and model.plans == 2 and len(record.executions) == 2
    assert record.status == "semantic_failure" and model.answers == 0


def test_forward_dependency_rejected():
    with pytest.raises(ValueError, match="precede"):
        resolve(
            [Step(tool="lookup_issue", arguments={"issue_id": "$step.1.record.test_run_id"})],
            bind(RequestInput(request="ENG-1")),
            [],
            0,
        )


def test_schema_argument_and_resource_grant_checks():
    context = ApplicationContext(grants=["ENG-1"])
    with pytest.raises(GuardError, match="resource denied"):
        dispatch(Step(tool="lookup_issue", arguments={"issue_id": "ENG-2"}), context, {})
    with pytest.raises(ValueError):
        dispatch(Step(tool="lookup_issue", arguments={"issue_id": "wrong"}), context, {})


def test_runtime_has_no_reference_imports_and_model_inputs_reject_labels():
    root = Path("src/router_lab/reuse")
    for module in ("runtime", "bindings", "bank", "service", "provider"):
        tree = ast.parse((root / f"{module}.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not any(
                    part in (node.module or "") for part in ("dataset", "scoring", "study", "evaluation")
                )
    with pytest.raises(ValueError):
        RequestInput(request="Show issue ENG-1", expected_action="lookup_issue")
    assert "reference" not in planning_schema()["properties"]


def test_budget_unknown_usage_retains_reserved_estimate(tmp_path):
    budget = Budget(tmp_path / "budget.jsonl", limit=1, reserve=0)
    reservation = budget.reserve_call(0.8, "reuse")
    budget.settle(reservation, 0.01, estimated=True)
    assert budget.spent == 0.8
    with pytest.raises(BudgetExceeded):
        budget.reserve_call(0.3, "reuse")


def test_live_model_interruption_retains_global_and_stage_reservations(tmp_path):
    class Responses:
        def create(self, **kwargs):
            raise KeyboardInterrupt

    class Client:
        responses = Responses()

    root = tmp_path / "reuse"
    root.mkdir()
    model = LiveModel(
        load_settings(Path("config/settings.json")), ReuseSettings(), root, stage="pilot", client=Client()
    )
    with pytest.raises(KeyboardInterrupt):
        model.plan(RequestInput(request="Show issue ENG-1"), bind(RequestInput(request="Show issue ENG-1")))
    assert model.budget.spent > 0 and model.stage_spent() == model.budget.spent
    assert read_jsonl(root / "model-calls.jsonl")[-1]["state"] == "estimated"


def test_pending_resume_never_replays(tmp_path):
    append_jsonl(tmp_path / "endpoints.jsonl", {"run_id": "paid", "state": "started"})
    with pytest.raises(ValueError, match="never automatically replay"):
        assert_no_pending(tmp_path)


def test_exact_configuration_resume_skips_completed_calls(tmp_path):
    root = tmp_path / "reuse"
    prepare(root)
    settings = load_settings(Path("config/settings.json"))
    case = build_case("dev", "issues", 0)
    model = FakeModel(issue_plan())
    arguments = (root, case, case["reference"], "fused", "warm", 0, settings, ReuseSettings(), model, [])
    first = execute_endpoint(*arguments)
    second = execute_endpoint(*arguments)
    assert first == second and model.plans == 1 and model.answers == 1
    assert len(read_jsonl(root / "runs.jsonl")) == 1
    assert first["record"]["timings_ms"]["end_to_end"] >= first["record"]["timings_ms"]["runtime"]


def test_family_review_hash_and_cli_commands(tmp_path):
    root = tmp_path / "reuse"
    prepare(root)
    with pytest.raises(ValueError, match="review required"):
        require_reviews(root)
    for family in FAMILIES:
        review_family(root, family, "test reviewer", "fixture only", True)
    require_reviews(root)
    write_json(root / "family-contracts.json", {family: {"changed": True} for family in FAMILIES})
    with pytest.raises(ValueError, match="review required"):
        require_reviews(root)
    for command in ("prepare", "seed", "pilot", "freeze", "publish"):
        assert parser().parse_args(["reuse", command]).reuse_command == command


def test_role_swaps_and_noncommutative_operands_cannot_share_signature():
    a = bind(RequestInput(request="Compare source ENG-1 with target ENG-2"))
    b = bind(RequestInput(request="Compare target ENG-1 with source ENG-2"))
    assert a.slot_types == b.slot_types and a.semantics != b.semantics
    steps = [
        Step(tool="lookup_issue", arguments={"issue_id": "$slot.issue0"}),
        Step(tool="lookup_issue", arguments={"issue_id": "$slot.issue1"}),
    ]
    plan = parameterize(steps, a, {})
    assert compatible(plan, b) == "semantic_signature"
    subtract = bind(RequestInput(request="Subtract 3 from 11"))
    minus = bind(RequestInput(request="Calculate 3 minus 11"))
    assert subtract.semantics != minus.semantics


def test_admission_requires_history_certificate_not_just_transport_success():
    from router_lab.reuse.contracts import ExecutionRecord

    record = ExecutionRecord(
        run_id="history",
        policy="fused",
        bank_state="empty",
        status="completed",
        bindings=bind(RequestInput(request="Show issue ENG-101")),
        executions=[{"result": {"found": True}}],
    )
    with pytest.raises(ValueError, match="certified"):
        admit_history(record, issue_plan(), {}, history_success=False)
    plan = admit_history(record, issue_plan(), {}, history_success=True)
    assert "ENG-101" not in plan.model_dump_json()


def test_history_reference_loading_does_not_open_held_out_labels(tmp_path, monkeypatch):
    from router_lab.reuse import study

    prepare(tmp_path / "reuse")
    original = study.read_jsonl

    def guarded(path):
        assert path.name not in ("references-dev.jsonl", "references-test.jsonl")
        return original(path)

    monkeypatch.setattr(study, "read_jsonl", guarded)
    _, references = study.inputs_and_references(tmp_path / "reuse", "history")
    assert len(references) == 16 and all(key.startswith("history-") for key in references)


def test_crash_after_completed_outcome_cannot_duplicate_paid_work(tmp_path):
    from router_lab.reuse.study import config_hash
    from router_lab.util import digest

    root = tmp_path / "reuse"
    prepare(root)
    settings = load_settings(Path("config/settings.json"))
    case = build_case("dev", "issues", 0)
    config = config_hash(root, settings)
    identity = f"{case['id']}:fused:warm:0:{config[:16]}"
    run_id = digest([identity, config])[:24]
    append_jsonl(root / "endpoints.jsonl", {"run_id": run_id, "state": "completed"})
    model = FakeModel(issue_plan())
    with pytest.raises(ValueError, match="never replay"):
        execute_endpoint(
            root, case, case["reference"], "fused", "warm", 0, settings, ReuseSettings(), model, []
        )
    assert model.plans == 0


def test_freeze_gates_and_post_freeze_invalidation(tmp_path):
    from router_lab.reuse.study import conditions, config_hash, freeze, verify_freeze
    from router_lab.util import digest

    root = tmp_path / "reuse"
    prepare(root)
    settings = load_settings(Path("config/settings.json"))
    for family in FAMILIES:
        review_family(root, family, "test reviewer", "fixture only", True)
    with pytest.raises(ValueError, match="complete development"):
        freeze(root, settings)
    cfg = ReuseSettings()
    configuration = config_hash(root, settings)
    for case in build_dataset():
        if case["split"] == "dev":
            for policy, state in conditions(case, False):
                append_jsonl(
                    root / "runs.jsonl",
                    {
                        "split": "dev",
                        "case_id": case["id"],
                        "policy": policy,
                        "bank_state": state,
                        "configuration": configuration,
                        "evaluation": {"incorrect_accepted_reuse": False},
                        "record": {"cost_usd": 0.001},
                    },
                )
    write_json(
        root / "calibration.json",
        {
            "selected": {"threshold": cfg.threshold, "margin": cfg.margin},
            "bank_hash": digest(root / "bank.json"),
            "references_hash": digest(root / "references-dev.jsonl"),
        },
    )
    write_json(root / "pilot.json", {"fits_full_matrix": True})
    frozen = freeze(root, settings)
    assert frozen["held_out_endpoints"] == 768
    assert verify_freeze(root, settings) == frozen
    write_json(root / "bank.json", [{"changed": True}])
    with pytest.raises(ValueError, match="changed"):
        verify_freeze(root, settings)


def test_paired_bootstrap_retains_clusters_and_reports_conservative_bound():
    from router_lab.reuse.analysis import paired_uncertainty

    rows = [
        {
            "cluster": f"c{cluster}",
            "policy": policy,
            "bank_state": "warm",
            "evaluation": {"success": True},
            "record": {
                "cost_usd": 0.01 if policy == "fused" else 0.005,
                "timings_ms": {"end_to_end": 100 if policy == "fused" else 70},
            },
        }
        for cluster in range(4)
        for policy in ("fused", "verified")
        for _ in range(2)
    ]
    result = paired_uncertainty(rows, "verified", samples=100)
    assert result["clusters"] == 4 and result["point"][:2] == [0, 0.5]
    assert result["conservative_harmful_cluster_rate_upper_95pct"] > 0.01
