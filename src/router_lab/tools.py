from __future__ import annotations

import math
import operator
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field

from .models import ACTIONS, Action, Contract


class SearchArgs(Contract):
    query: str = Field(min_length=1, max_length=500)


class IssueArgs(Contract):
    issue_id: str = Field(pattern=r"^ENG-\d+$")


class DeploymentArgs(Contract):
    service: str = Field(min_length=1)
    environment: Literal["production", "staging", "development"]


class TestArgs(Contract):
    test_run_id: str = Field(pattern=r"^TR-\d+$")


class CalculateArgs(Contract):
    operation: Literal["add", "subtract", "multiply", "divide"]
    left: float
    right: float


@dataclass(frozen=True)
class ToolDefinition:
    action_id: Action
    description: str
    argument_schema: type[Contract] | None
    handler: Callable[[Contract, dict], dict] | None

    def catalog_entry(self) -> dict:
        return {"value": self.action_id, "description": self.description}


def search(args: Contract, collection: list[dict]) -> dict:
    words = set(re.findall(r"[a-z0-9]+", args.query.lower()))
    scored = [(len(words & set(re.findall(r"[a-z0-9]+", str(item).lower()))), item) for item in collection]
    matches = [item for score, item in sorted(scored, key=lambda x: -x[0]) if score > 0][:3]
    return {"found": bool(matches), "records": matches, "error": None if matches else "not found"}


def lookup(key: str, records: dict) -> dict:
    record = records.get(key)
    return {
        "found": record is not None,
        "record": record,
        "error": None if record is not None else "not found",
    }


def calculate(args: CalculateArgs, _: dict) -> dict:
    functions = {
        "add": operator.add,
        "subtract": operator.sub,
        "multiply": operator.mul,
        "divide": operator.truediv,
    }
    if args.operation == "divide" and args.right == 0:
        return {"found": False, "error": "division by zero"}
    value = functions[args.operation](args.left, args.right)
    if not math.isfinite(value):
        return {"found": False, "error": "non-finite arithmetic result"}
    return {"found": True, "value": value}


CATALOG = (
    ToolDefinition(
        "search_docs",
        "Find project documentation, supported configuration, API usage, runbooks or documented behavior; not actual source implementation.",
        SearchArgs,
        lambda a, f: search(a, f["docs"]),
    ),
    ToolDefinition(
        "search_code",
        "Find actual implementation, source functions, code paths or repository snippets; not documentation or generic explanations.",
        SearchArgs,
        lambda a, f: search(a, f["code"]),
    ),
    ToolDefinition(
        "lookup_issue",
        "Look up the status, details or workaround of a specific issue with an issue ID. An issue ID is essential.",
        IssueArgs,
        lambda a, f: lookup(a.issue_id, f["issues"]),
    ),
    ToolDefinition(
        "lookup_deployment",
        "Look up a service's actual deployed version, status or rollout record in a specified environment. Both service and environment are essential.",
        DeploymentArgs,
        lambda a, f: lookup(f"{a.service}/{a.environment}", f["deployments"]),
    ),
    ToolDefinition(
        "lookup_test_results",
        "Retrieve a stored test-run outcome by test-run ID. Does not execute tests. A test-run ID is essential.",
        TestArgs,
        lambda a, f: lookup(a.test_run_id, f["test_runs"]),
    ),
    ToolDefinition(
        "calculate",
        "Compute numeric arithmetic from explicit operands using add, subtract, multiply or divide; not explanations of math concepts.",
        CalculateArgs,
        calculate,
    ),
    ToolDefinition(
        "answer_directly",
        "Explain general programming or mathematical concepts that need no project-specific facts, lookup, or arithmetic execution.",
        None,
        None,
    ),
    ToolDefinition(
        "ask_for_clarification",
        "Ask for essential missing identifiers, operands, environment, context or a first step needed to select or execute one action. Use for unresolved requests.",
        None,
        None,
    ),
)
assert tuple(t.action_id for t in CATALOG) == ACTIONS


def catalog_payload(catalog=CATALOG) -> list[dict]:
    return [tool.catalog_entry() for tool in catalog]


def load_fixtures(path: Path = Path("fixtures/support.json")) -> dict:
    import json

    return json.loads(path.read_text())


def execute(action: str, arguments: dict, fixtures: dict) -> dict:
    tool = next(t for t in CATALOG if t.action_id == action)
    if tool.argument_schema is None or tool.handler is None:
        raise ValueError(f"{action} has no executable tool")
    args = tool.argument_schema.model_validate(arguments)
    return tool.handler(args, fixtures)
