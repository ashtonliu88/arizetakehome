"""Experiment construction only. Never imported by runtime, binder, bank, or models.

References are declared here from family contracts, not inferred by the runtime parser.
"""

from __future__ import annotations

from .contracts import ApplicationContext, RequestInput

FAMILIES = ("issues", "deployments", "tests", "sources", "calculations", "comparisons", "linked", "direct")

FAMILY_CONTRACTS = {
    "issues": {
        "rule": "Retrieve the requested issue only; negated distractors are excluded. Ambiguous aliases require clarification.",
        "positive": "Show issue ENG-101 → lookup_issue(ENG-101), current issue status.",
        "adverse": "Get ENG-102, not ENG-101 → only ENG-102. Alias incident → two issues requires clarification.",
    },
    "deployments": {
        "rule": "Service AND environment identify a deployment; environment comes from the request or independent context.",
        "positive": "Show service gateway in staging → gateway/staging, current version.",
        "adverse": "Missing environment requires clarification; production must never silently bind to staging.",
    },
    "tests": {
        "rule": "Retrieve stored results for the requested run; never claim to execute tests.",
        "positive": "Get stored results TR-101 → lookup_test_results(TR-101), current outcome.",
        "adverse": "Run tests for TR-101 cannot be fulfilled by a stored-result lookup; clarify unavailable execution.",
    },
    "sources": {
        "rule": "Use documentation for documented behavior and code for actual implementation; preserve query text.",
        "positive": "Search documentation for `retry policy` → search_docs. Search code → search_code.",
        "adverse": "Find code, not documentation → code only. Never substitute a documentation hit.",
    },
    "calculations": {
        "rule": "Compute explicit operands with correct order and operation; missing operands require clarification.",
        "positive": "Subtract 3 from 11 → subtract(left=11,right=3), 8.",
        "adverse": "11 minus 3 is 8; 3 minus 11 is -8. A missing right operand must not be invented.",
    },
    "comparisons": {
        "rule": "Retrieve both resources in the specified role order; one result is incomplete.",
        "positive": "Compare source ENG-101 with target ENG-102 → both issues, in that order.",
        "adverse": "Role-swapped request requires reversed argument order; permission denial must not execute a forbidden lookup.",
    },
    "linked": {
        "rule": "Retrieve the issue and follow its current authoritative test_run_id; never reuse a historical run ID.",
        "positive": "Get ENG-101 and its associated test results → issue then current linked run.",
        "adverse": "Get just ENG-101, without associated tests → issue only. Changed linkage must fetch the new run.",
    },
    "direct": {
        "rule": "Conceptual explanations need no tool; missing required fields need a specific clarification. No reuse templates.",
        "positive": "Explain recursion → direct explanation, no tools, no second answer-generation call.",
        "adverse": "Get issue status (no ID) → ask for issue identifier. Capability denial must not execute a tool.",
    },
}


def build_case(split, family, index):
    offset = {"history": 100, "dev": 1000, "test": 10000}[split] + FAMILIES.index(family) * 100 + index * 3
    issue, other, run = f"ENG-{offset}", f"ENG-{offset + 1}", f"TR-{offset}"
    states = {
        "acme": {"issues": {}, "deployments": {}, "test_runs": {}, "docs": [], "code": []},
        "beta": {"issues": {}, "deployments": {}, "test_runs": {}, "docs": [], "code": []},
    }
    for tenant, state in states.items():
        for n in range(2):
            iid, tid = f"ENG-{offset + n}", f"TR-{offset + n}"
            state["issues"][iid] = {
                "issue_id": iid,
                "status": "open" if n == 0 else "resolved",
                "test_run_id": tid,
            }
            state["test_runs"][tid] = {"test_run_id": tid, "outcome": "passed" if n == 0 else "failed"}
        for env, version in [("production", "v3.1"), ("staging", "v4.2"), ("development", "v5.0")]:
            state["deployments"][f"gateway/{env}"] = {
                "service": "gateway",
                "environment": env,
                "version": version,
                "status": "healthy",
            }
        state["docs"] = [{"id": "retry-guide", "text": "Retry policy: use exponential backoff."}]
        state["code"] = [{"id": "retry.py", "text": "def retry_policy(): return 3"}]
        if tenant == "beta":
            state["issues"][issue]["status"] = "triaged"
    context = ApplicationContext()
    expected = []
    facts = []
    any_facts = []
    kind = "tools"

    def step(tool, **args):
        return {"tool": tool, "arguments": args}

    variant = index if split == "test" else index % (2 if split == "history" else 3)
    if family == "issues":
        requests = [
            f"Show issue {issue}",
            f"Please retrieve current status for ticket {issue}",
            f"Get {other}, not {issue}",
            "Show issue incident",
            f"Get issue {issue}",
            f"Fetch issue {issue}",
            f"Get issue {issue}",
            f"Inspect issue {issue}",
        ]
        request = requests[variant]
        chosen = other if variant == 2 else issue
        if variant == 3:
            context.aliases = {"incident": [issue, other]}
            kind, any_facts = "clarify", ["which", "identifier", "ambiguous"]
        else:
            if variant == 6:
                context.tenant = "beta"
            if variant == 4:
                states["acme"]["issues"][issue]["status"] = "in_progress"
            expected = [step("lookup_issue", issue_id=chosen)]
            facts = [chosen, states[context.tenant]["issues"][chosen]["status"]]
    elif family == "deployments":
        env = "production" if variant in (0, 4, 6) else "staging"
        request = f"Show deployment for service gateway in {env}"
        if variant == 1:
            request = "Get deployed version for service gateway in staging"
        if variant == 2:
            request = "Show deployment for service gateway in staging, not production"
        if variant == 3:
            request, kind, any_facts = "Show deployment for service gateway", "clarify", ["environment"]
        else:
            if variant == 4:
                states["acme"]["deployments"]["gateway/production"]["version"] = "v9.8"
            if variant == 5:
                request, context.environment = "Get deployment for service gateway", "staging"
            if variant == 6:
                context.tenant = "beta"
            expected = [step("lookup_deployment", service="gateway", environment=env)]
            facts = ["gateway", env, states[context.tenant]["deployments"][f"gateway/{env}"]["version"]]
    elif family == "tests":
        request = f"Get stored test results {run}"
        if variant == 1:
            request = f"Retrieve outcome for test run {run}"
        if variant == 2:
            request = f"Get {run}, not TR-{offset + 1}"
        if variant in (3, 7):
            request = "Get stored test results" if variant == 3 else f"Run tests for {run}"
            kind, any_facts = (
                "clarify",
                ["identifier", "run id", "test run", "execute", "execution", "cannot", "can't"],
            )
        else:
            if variant == 4:
                states["acme"]["test_runs"][run]["outcome"] = "failed"
            expected, facts = (
                [step("lookup_test_results", test_run_id=run)],
                [run, states["acme"]["test_runs"][run]["outcome"]],
            )
    elif family == "sources":
        source = "code" if variant in (1, 3, 5, 7) else "documentation"
        request = f'Search {source} for "retry policy"'
        if variant == 2:
            request = 'Find documentation, not code, for "retry policy"'
        if variant == 3:
            request = 'Find code, not documentation, for "retry policy"'
        tool = "search_code" if source == "code" else "search_docs"
        expected = [step(tool, query="retry policy")]
        facts = ["retry_policy" if tool == "search_code" else "exponential backoff"]
    elif family == "calculations":
        left, right = offset + 2, index + 2
        operation = "add"
        request = f"Calculate {left} plus {right}"
        if variant == 1:
            request, operation = f"Subtract {right} from {left}", "subtract"
        if variant == 2:
            request, operation = f"Calculate {right} minus {left}", "subtract"
            left, right = right, left
        if variant in (3, 4, 5, 6):
            operation = {3: "multiply", 4: "divide", 5: "subtract", 6: "add"}[variant]
            request = f"Calculate {left} {dict(multiply='times', divide='divided by', subtract='minus', add='plus')[operation]} {right}"
        if variant == 7:
            request, kind, any_facts = f"Add {left} to", "clarify", ["number", "operand", "add to", "value"]
        else:
            value = {
                "add": lambda: left + right,
                "subtract": lambda: left - right,
                "multiply": lambda: left * right,
                "divide": lambda: left / right,
            }[operation]()
            expected = [step("calculate", operation=operation, left=float(left), right=float(right))]
            facts = [str(round(value, 6)) if operation == "divide" else str(value)]
    elif family == "comparisons":
        first, second = (other, issue) if variant in (2, 4, 6) else (issue, other)
        request = f"Compare source {first} with target {second}"
        if variant == 1:
            request = f"Compare issue {first} against issue {second}"
        expected = [step("lookup_issue", issue_id=first), step("lookup_issue", issue_id=second)]
        facts = [first, second, "open", "resolved"]
        if variant == 5:
            context.grants = [first]
            kind, expected, facts, any_facts = (
                "clarify",
                [],
                [],
                ["access", "permission", "authorized", "restricted", "grant"],
            )
    elif family == "linked":
        request = f"Get issue {issue} and its associated test results"
        if variant == 1:
            request = f"Retrieve issue {issue} then linked test run results"
        chosen_run = run
        if variant == 4:
            chosen_run = f"TR-{offset + 1}"
            states["acme"]["issues"][issue]["test_run_id"] = chosen_run
        expected = [step("lookup_issue", issue_id=issue), step("lookup_test_results", test_run_id=chosen_run)]
        facts = [issue, chosen_run, "open", states["acme"]["test_runs"][chosen_run]["outcome"]]
        if variant in (2, 6):
            request = f"Get just issue {issue}, without associated tests"
            expected, facts = [step("lookup_issue", issue_id=issue)], [issue, "open"]
        if variant == 7:
            request, kind, expected, facts, any_facts = (
                "Get issue and associated tests",
                "clarify",
                [],
                [],
                ["issue", "identifier"],
            )
    else:
        request = "Explain recursion"
        kind, any_facts = "direct", ["itself", "self", "base case"]
        if variant in (1, 2, 3, 5, 6, 7):
            request = ["Get issue status", "Show deployed version", "Get stored test results"][variant % 3]
            kind = "clarify"
            any_facts = {
                0: ["issue", "eng-"],
                1: ["service", "environment"],
                2: ["test run", "test-run", "run id", "test_run_id", "tr-"],
            }[variant % 3]
        if variant == 4:
            request = f"Show issue {issue}"
            context.capabilities = ["search_docs"]
            kind, any_facts = (
                "clarify",
                ["access", "permission", "authorized", "capability", "cannot", "can't"],
            )
    if (
        (family == "tests" and variant == 7)
        or (family == "comparisons" and variant == 5)
        or (family == "direct" and variant == 4)
    ):
        kind = "abstain"
    case_id = f"{split}-{family}-{index:02}"
    # Novel development wording is distinct from both successful history phrases.
    # This is a prespecified derivation from the reviewed family rules; the
    # held-out requests remain untouched by development calibration.
    if split == "dev" and index == 1:
        request = {
            "issues": f"Fetch details for issue {issue}",
            "deployments": "Check current version of service gateway on staging",
            "tests": f"Show stored outcome for {run}",
            "sources": 'Find actual implementation for "retry policy"',
            "calculations": f"Please compute: subtract {index + 2} from {offset + 2}",
            "comparisons": f"Show both issue {issue} and issue {other}",
            "linked": f"Fetch issue {issue} with its linked test results",
            "direct": request,
        }[family]
    return {
        "id": case_id,
        "cluster": case_id,
        "split": split,
        "family": family,
        "input": RequestInput(request=request, context=context).model_dump(),
        "state": states,
        "reference": {
            "kind": kind,
            "acceptable_paths": [expected],
            "facts": facts,
            "any_facts": any_facts,
            "provenance": "derived reference from family contract; not individually human approved",
        },
    }


def build_dataset():
    return [
        build_case(split, family, i)
        for split, count in (("history", 2), ("dev", 3), ("test", 8))
        for family in FAMILIES
        for i in range(count)
    ]
