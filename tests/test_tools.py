import pytest
from pydantic import ValidationError

from router_lab.tools import CATALOG, CalculateArgs, execute, load_fixtures


def test_deterministic_tools_and_not_found():
    f = load_fixtures()
    assert len(CATALOG) == 8
    assert execute("lookup_issue", {"issue_id": "ENG-101"}, f)["record"]["status"] == "open"
    assert (
        execute("lookup_deployment", {"service": "payments", "environment": "staging"}, f)["record"][
            "version"
        ]
        == "2.4.0"
    )
    assert execute("lookup_test_results", {"test_run_id": "TR-101"}, f)["record"]["failed"] == 2
    assert execute("lookup_issue", {"issue_id": "ENG-999"}, f) == {
        "found": False,
        "record": None,
        "error": "not found",
    }
    assert execute("search_docs", {"query": "max_retries"}, f)["found"]
    assert execute("search_code", {"query": "retry_delay"}, f)["found"]
    assert execute("search_docs", {"query": "zzzzzzzzzz"}, f)["error"] == "not found"
    assert execute("calculate", {"operation": "add", "left": 12, "right": 30}, f)["value"] == 42
    assert (
        execute("calculate", {"operation": "divide", "left": 12, "right": 0}, f)["error"]
        == "division by zero"
    )


@pytest.mark.parametrize(
    "action,args",
    [
        ("lookup_issue", {"issue_id": "101"}),
        ("lookup_deployment", {"service": "payments"}),
        ("lookup_test_results", {"test_run_id": "TR-101", "extra": 1}),
        ("calculate", {"operation": "eval", "left": 1, "right": 2}),
    ],
)
def test_argument_validation(action, args):
    with pytest.raises(ValidationError):
        execute(action, args, load_fixtures())


def test_no_eval_and_no_nonfinite():
    with pytest.raises(ValidationError):
        CalculateArgs(operation="add", left=float("inf"), right=1)
    with pytest.raises(ValueError):
        execute("answer_directly", {}, load_fixtures())
