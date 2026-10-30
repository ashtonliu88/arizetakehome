"""Offline/reference-only scoring, never an input to execution or admission."""

from __future__ import annotations

import re


def score(record, reference):
    executions = record.executions
    actual = [{"tool": e["tool"], "arguments": e["arguments"]} for e in executions]
    path_ok = actual in reference["acceptable_paths"]
    text = record.answer.lower().replace(",", "")
    facts_ok = all(str(f).lower().replace("_", " ") in text.replace("_", " ") for f in reference["facts"])
    if reference["any_facts"]:
        facts_ok = facts_ok and any(f.lower() in text for f in reference["any_facts"])
    # Allow rounding for division, but never a wrong argument order or operation.
    if not facts_ok and reference["facts"] and len(actual) == 1 and actual[0]["tool"] == "calculate":
        target = float(reference["facts"][0])
        numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)]
        facts_ok = any(abs(n - target) <= 1e-4 * max(1, abs(target)) for n in numbers)
    kind_ok = (
        record.status
        == {"tools": "completed", "direct": "completed", "clarify": "clarified", "abstain": "abstained"}[
            reference["kind"]
        ]
    )
    success = (
        path_ok
        and facts_ok
        and kind_ok
        and record.status not in ("safe_failure", "semantic_failure", "transport_failure", "pending")
        and reference["kind"] != "abstain"
    )
    return {
        "success": success,
        "resource_correct": path_ok,
        "answer_facts_correct": facts_ok,
        "unnecessary_clarification": record.status == "clarified" and reference["kind"] != "clarify",
        "unnecessary_refusal": record.status == "abstained" and reference["kind"] != "abstain",
        "appropriate_abstention": record.status == "abstained"
        and reference["kind"] == "abstain"
        and path_ok
        and facts_ok,
        "unresolved": not success,
        "incorrect_accepted_reuse": record.cache_hit and not path_ok,
        "bad_result_reached_answer": bool(record.answer) and not path_ok,
        "authorization_violations": 0,  # Independently recomputed below by the study evaluator.
        "metric_scope": "mechanical execution-path and required-answer-fact checks; no semantic judge",
    }
