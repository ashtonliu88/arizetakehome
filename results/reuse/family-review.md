# Family contracts for review

Review these eight rules before paid construction or execution. All generated substitutions are derived references, not individually human approved.

## issues

Retrieve the requested issue only; negated distractors are excluded. Ambiguous aliases require clarification.

- Positive: Show issue ENG-101 → lookup_issue(ENG-101), current issue status.
- Adverse: Get ENG-102, not ENG-101 → only ENG-102. Alias incident → two issues requires clarification.

## deployments

Service AND environment identify a deployment; environment comes from the request or independent context.

- Positive: Show service gateway in staging → gateway/staging, current version.
- Adverse: Missing environment requires clarification; production must never silently bind to staging.

## tests

Retrieve stored results for the requested run; never claim to execute tests.

- Positive: Get stored results TR-101 → lookup_test_results(TR-101), current outcome.
- Adverse: Run tests for TR-101 cannot be fulfilled by a stored-result lookup; clarify unavailable execution.

## sources

Use documentation for documented behavior and code for actual implementation; preserve query text.

- Positive: Search documentation for `retry policy` → search_docs. Search code → search_code.
- Adverse: Find code, not documentation → code only. Never substitute a documentation hit.

## calculations

Compute explicit operands with correct order and operation; missing operands require clarification.

- Positive: Subtract 3 from 11 → subtract(left=11,right=3), 8.
- Adverse: 11 minus 3 is 8; 3 minus 11 is -8. A missing right operand must not be invented.

## comparisons

Retrieve both resources in the specified role order; one result is incomplete.

- Positive: Compare source ENG-101 with target ENG-102 → both issues, in that order.
- Adverse: Role-swapped request requires reversed argument order; permission denial must not execute a forbidden lookup.

## linked

Retrieve the issue and follow its current authoritative test_run_id; never reuse a historical run ID.

- Positive: Get ENG-101 and its associated test results → issue then current linked run.
- Adverse: Get just ENG-101, without associated tests → issue only. Changed linkage must fetch the new run.

## direct

Conceptual explanations need no tool; missing required fields need a specific clarification. No reuse templates.

- Positive: Explain recursion → direct explanation, no tools, no second answer-generation call.
- Adverse: Get issue status (no ID) → ask for issue identifier. Capability denial must not execute a tool.

Record each approval with `router-lab reuse review-family --family NAME --reviewer NAME --approve --note TEXT`.
