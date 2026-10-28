"""Authoring source. Deterministic export; no model-generated labels or test peeking."""

import json
from pathlib import Path

# Each pair is a request and a rationale explaining the unique next action.
# First five per action are development. Remaining ten are held out.
EXAMPLES = {
    "search_docs": [
        (
            "Find the documented way to disable SDK retries.",
            "Requests supported retry configuration, not its source implementation.",
        ),
        (
            "Show the authentication guide for setting the API key.",
            "Asks for project documentation about authentication.",
        ),
        (
            "First retrieve the rollback runbook; after that we can check the deployment.",
            "Explicit first step is retrieving the runbook.",
        ),
        (
            "The pagination code is confusing, but I only want the documented page-size limit.",
            "Distractor mentions code; requested fact is the documented limit.",
        ),
        (
            "What default cache TTL does our documentation specify?",
            "Project-specific documented configuration requires documentation retrieval.",
        ),
        ("Where do the webhook docs describe signature verification?", "Requests documented webhook usage."),
        (
            "Find the supported log-level settings in the service manual.",
            "Requests documented configuration options.",
        ),
        (
            "According to the API reference, what is the request timeout option called?",
            "Reference material, not current runtime state or source, is requested.",
        ),
        (
            "Fetch the connection-pool tuning guide before we examine any implementation.",
            "Explicit prerequisite is a documented tuning guide.",
        ),
        (
            "Find our rate-limit policy; I am not asking for the limiter source.",
            "Requests documented policy despite source-related wording.",
        ),
        (
            "How does the health-check endpoint work according to its reference page?",
            "Project-specific API reference is the evidence needed.",
        ),
        ("Please retrieve the guide on environment-variable precedence.", "Requests a project guide."),
        ("Read the migration notes about deprecated endpoints.", "Migration notes are documentation."),
        (
            "A test failed while enabling traces. Find the tracing setup instructions first.",
            "Explicit first step is documentation, despite a test distractor.",
        ),
        (
            "I need the public API examples for configuring a proxy, not the proxy implementation.",
            "Usage examples belong to documentation.",
        ),
    ],
    "search_code": [
        (
            "Show the actual retry_delay function implementation.",
            "Requests actual source function, not retry configuration docs.",
        ),
        (
            "Find the source of auth_headers that constructs the Authorization header.",
            "Requests implementation of a specific function.",
        ),
        (
            "Before explaining pagination, locate the next_page source function.",
            "Explicit first step is locating implementation.",
        ),
        (
            "The cache guide mentions keys; show the actual cache_key code.",
            "Documentation is a distractor; actual code is requested.",
        ),
        (
            "Locate the implementation that serializes outgoing request bodies.",
            "Actual project implementation requires source retrieval.",
        ),
        (
            "Which repository function redacts secrets from logs? Show its implementation.",
            "Requests actual logging source.",
        ),
        (
            "Find the code path that verifies webhook signatures.",
            "Code path is implementation, even though documentation also covers this topic.",
        ),
        (
            "Open the function that parses the server's Retry-After header.",
            "Requests parser source rather than documented retry policy.",
        ),
        (
            "Show the source where database connections are returned to the pool.",
            "Requests pool implementation.",
        ),
        (
            "Locate the timeout exception handler in the client repository.",
            "Asks for implementation of exception handling.",
        ),
        (
            "Find the endpoint health-check handler source before reviewing its API docs.",
            "Explicit first step is source retrieval.",
        ),
        (
            "I know what a circuit breaker is; show our circuit-breaker implementation.",
            "General concept is already known; project source is needed.",
        ),
        (
            "Find the function that merges environment overrides into the config object.",
            "Requests actual configuration merge code.",
        ),
        (
            "Trace the source path that increments the failed-request metric.",
            "Requests source behavior, not current metric values.",
        ),
        (
            "The issue mentions a race. First locate the lock acquisition implementation.",
            "Explicit first step is code lookup, not issue lookup.",
        ),
    ],
    "lookup_issue": [
        (
            "What is the status and workaround for ENG-101?",
            "Specific issue ID makes issue lookup executable.",
        ),
        ("Has ENG-202 been resolved?", "Requests status of a named issue."),
        (
            "First read ENG-303, then we can inspect the cache code.",
            "Explicit first step is a named issue lookup.",
        ),
        (
            "Look up ENG-404 even if it is absent from the fixture tracker.",
            "An absent record still requires lookup, not clarification.",
        ),
        (
            "The test failed, but for now just retrieve ticket ENG-505.",
            "Test wording is a distractor; named ticket is the target.",
        ),
        (
            "Retrieve the owner and current state of ENG-601.",
            "Named issue lookup is the next action; missing fixture data is not missing input.",
        ),
        ("Check whether ENG-602 has a fix version.", "Requests a named issue record."),
        (
            "Before searching source, fetch the description of ENG-603.",
            "Explicit first step is issue lookup.",
        ),
        ("Does ENG-604 list a temporary workaround?", "Requests a fact from a specific issue."),
        ("Read the latest recorded update for ENG-605.", "Named issue record is required."),
        (
            "Find the severity recorded on ENG-606.",
            "Issue ID is supplied and the requested fact belongs to that record.",
        ),
        (
            "Someone said ENG-607 concerns docs; retrieve that issue first.",
            "Documentation wording does not change the explicit issue lookup.",
        ),
        ("Look up ticket ENG-608 and tell me if it is closed.", "Requests a named issue's status."),
        ("What reproduction steps are recorded in ENG-609?", "Requests information from a named issue."),
        (
            "Check the tracker record for ENG-610 before deciding whether to investigate deployment.",
            "Issue lookup is the explicit prerequisite.",
        ),
    ],
    "lookup_deployment": [
        (
            "Which version of payments is deployed in staging?",
            "Service and environment identify an actual deployment record.",
        ),
        (
            "Check the health of payments in production.",
            "Requests actual deployment state with both identifiers.",
        ),
        (
            "First get gateway's production rollout record; then consider a rollback.",
            "Named deployment lookup is the explicit first step.",
        ),
        (
            "Find mailer's staging deployment, even if no fixture exists.",
            "Supplied identifiers permit lookup; not found is an explicit result.",
        ),
        (
            "The source changed, but I need worker's actual development deployment version.",
            "Actual deployed state, not source, is requested.",
        ),
        (
            "What commit is running for inventory in production?",
            "Service/environment identify deployment state.",
        ),
        ("Retrieve catalog's staging rollout status.", "Actual rollout record requires deployment lookup."),
        (
            "Before checking a bug, get billing's production version.",
            "Named deployment is the explicit first step.",
        ),
        (
            "Which build of identity is deployed in development?",
            "Requests actual deployed build, not how deployment works.",
        ),
        ("Check search-api's production deployment health.", "Both deployment identifiers are present."),
        (
            "The docs may be stale; retrieve notifications' staging deployment record.",
            "Documentation distractor; actual state is needed.",
        ),
        (
            "Show the production rollout information for analytics.",
            "A specific deployment record is requested.",
        ),
        (
            "Find the deployed revision of frontend in staging.",
            "Service/environment fully identify the requested record.",
        ),
        (
            "First look up scheduler in development, then we can review its code.",
            "Deployment lookup is the explicit first step.",
        ),
        (
            "What version of audit-api is currently deployed in production?",
            "Actual version comes from the deployment record.",
        ),
    ],
    "lookup_test_results": [
        (
            "Retrieve the stored results for test run TR-101.",
            "A test-run ID is supplied; retrieval, not execution, is requested.",
        ),
        ("Did TR-202 pass?", "Requests outcome of a specific stored run."),
        (
            "First inspect TR-303, then we can look at the retry source.",
            "Stored run lookup is the explicit first step.",
        ),
        (
            "Look up TR-404 even if it is missing from local records.",
            "A missing record is not a missing identifier.",
        ),
        (
            "Ignore the deployment discussion and fetch the archived result for TR-505.",
            "Specific stored run is the requested target.",
        ),
        (
            "How many tests failed in TR-601?",
            "Requires named stored run results, not arithmetic over supplied operands.",
        ),
        (
            "Retrieve the failing test names from TR-602.",
            "Named test-run record contains the requested facts.",
        ),
        (
            "Before opening an issue, inspect the saved outcome of TR-603.",
            "Stored results lookup is the explicit first step.",
        ),
        ("Was the archived run TR-604 green?", "Requests outcome of a specific run."),
        (
            "Get the summary for completed test run TR-605.",
            "Retrieves an existing run without running tests.",
        ),
        (
            "The docs mention this test; fetch the actual recorded outcome of TR-606.",
            "Documentation distractor; existing run outcome is requested.",
        ),
        ("Read the stored failure report for TR-607.", "Named stored run lookup is executable."),
        ("Check the pass count in TR-608.", "Requests a fact from stored run results."),
        (
            "Show TR-609's result before we investigate the source failure.",
            "Explicit first step is stored result retrieval.",
        ),
        ("What status was saved for test run TR-610?", "Requests a named test-run record."),
    ],
    "calculate": [
        ("Calculate 12 plus 30.", "Explicit operands and addition define executable arithmetic."),
        ("Multiply 8 by 9.", "Explicit multiplication needs the calculator."),
        ("Divide 144 by 12 before discussing capacity.", "Arithmetic is the explicit first step."),
        ("How much is 50 minus 17?", "Explicit subtraction is executable arithmetic."),
        (
            "The test report says 6 passed and 4 failed; first add those two counts.",
            "Operands are already supplied; no test lookup is required.",
        ),
        ("Compute 17 plus 28.", "Explicit numeric addition."),
        ("What is 36 multiplied by 7?", "Explicit numeric multiplication."),
        ("Calculate 81 divided by 9.", "Explicit division."),
        ("Subtract 46 from 103.", "Both operands and subtraction are specified."),
        (
            "First multiply 25 by 16, then explain the budget implications.",
            "Arithmetic is the explicit first step.",
        ),
        (
            "We deployed 18 workers and added 5; calculate their sum using those values.",
            "Deployment is a distractor; all arithmetic inputs are supplied.",
        ),
        (
            "There are 96 calls over 12 requests. Divide 96 by 12.",
            "No external information is needed for specified arithmetic.",
        ),
        (
            "Take the difference between 1000 and 275, in that order.",
            "Explicit subtraction with operand order.",
        ),
        ("Add 2.5 and 3.75.", "Explicit decimal arithmetic."),
        (
            "Compute 9 times 0; do not look up any project data.",
            "Explicit multiplication, including zero, is well-defined.",
        ),
    ],
    "answer_directly": [
        ("Explain what idempotency means in general.", "General concept needs no project lookup."),
        ("What is a unit test, conceptually?", "General explanation rather than stored test results."),
        (
            "Explain the difference between latency and throughput without using our system data.",
            "General conceptual comparison excludes project facts.",
        ),
        ("What does a cache do in a typical application?", "Generic concept, not project configuration."),
        (
            "Describe why retries can amplify load in distributed systems.",
            "General mechanism can be explained directly.",
        ),
        (
            "What is dependency injection? Give a generic explanation.",
            "No project-specific implementation is requested.",
        ),
        ("Explain optimistic locking at a conceptual level.", "General explanation needs no lookup."),
        (
            "Why are floating-point sums sometimes imprecise? I need the concept, not a calculation.",
            "Asks for conceptual explanation, not explicit arithmetic execution.",
        ),
        (
            "What is the difference between authentication and authorization?",
            "General conceptual comparison.",
        ),
        (
            "Explain eventual consistency without referencing our services.",
            "Generic concept excludes project facts.",
        ),
        ("What is a race condition in concurrent programs?", "General concept needs no source retrieval."),
        (
            "How does cursor pagination work in principle?",
            "Generic mechanism rather than project API reference.",
        ),
        (
            "What is a deployment canary, conceptually?",
            "General explanation rather than actual deployment state.",
        ),
        (
            "Explain why test isolation matters, using a made-up example.",
            "General explanation does not require existing test records.",
        ),
        (
            "Define a probability distribution in plain language; no numeric computation needed.",
            "General definition rather than arithmetic execution.",
        ),
    ],
    "ask_for_clarification": [
        ("Which version of payments is deployed?", "Environment is essential and is missing."),
        ("Check the status of that issue.", "Issue ID is essential and absent."),
        ("Did the test run pass?", "Test-run ID is essential and absent."),
        ("Divide 40 by the other value.", "Second operand is essential and absent."),
        ("Can you check it?", "No target or task is specified."),
        (
            "What is deployed in production?",
            "Service identifier is missing; environment alone is insufficient.",
        ),
        (
            "Find the docs for the setting I mentioned earlier.",
            "No prior conversation or setting name identifies a retrieval target.",
        ),
        ("Show the implementation of that helper.", "No helper name or behavior is supplied."),
        (
            "I have ENG-777 and TR-777; check one of them.",
            "Two executable targets are supplied without a defined first step or selected target.",
        ),
        (
            "Calculate the total cost of the run.",
            "No numeric inputs or identifiable run provide essential operands.",
        ),
        (
            "Search our docs or source, whichever I meant.",
            "No topic or requested evidence type is specified.",
        ),
        ("Look up api-service in the usual place.", "No environment or clear lookup target is specified."),
        ("Compare the results of my two runs.", "Both run identifiers are absent."),
        (
            "Multiply 7 by the deployment's replica count.",
            "Replica count and deployment identifiers are missing, so no unique executable prerequisite exists.",
        ),
        ("Find the record with ID 808.", "Bare number does not identify issue versus test-run record type."),
    ],
}

rows = []
for action, pairs in EXAMPLES.items():
    assert len(pairs) == 15
    for i, (request, rationale) in enumerate(pairs):
        split = "dev" if i < 5 else "test"
        tags = ["straightforward"]
        if "first" in request.lower() or "before" in request.lower():
            tags = ["compound", "explicit_next_step"]
        if any(s in request.lower() for s in ["but", "ignore", "not ", "docs mention", "source changed"]):
            tags.append("distractor")
        if action in ["search_docs", "search_code"]:
            tags.append("overlap")
        if action == "answer_directly":
            tags.append("no_tool")
        if action == "ask_for_clarification":
            tags.extend(["missing_information", "clarification"])
        if action in ["calculate", "lookup_deployment", "lookup_test_results"]:
            tags.append("less_common_tool")
        rows.append(
            dict(
                example_id=f"{action}-{i + 1:02d}",
                request=request,
                expected_action=action,
                rationale=rationale,
                tags=tags,
                paraphrase_group=f"{action}-intent-{i + 1:02d}",
                split=split,
            )
        )
Path("data/benchmark.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
print(f"Wrote {len(rows)} authored examples. Human label review remains required.")
