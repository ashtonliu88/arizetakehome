"""Small artificial analysis fixture. These are NOT benchmark observations."""

import json
from pathlib import Path

from router_lab.evaluation import outcome
from router_lab.models import ACTIONS, CallRecord, RouteResult, Usage
from router_lab.util import write_json

rows = []
for i, expected in enumerate(ACTIONS):
    for rep in range(1, 4):
        decision_action = ACTIONS[(i + 1) % 8] if i in (1, 4, 6) else expected
        llm_action = ACTIONS[(i + 1) % 8] if i in (2, 6) else expected
        confidence = [0.95, 0.35, 0.45, 0.85, 0.55, 0.75, 0.4, 1.0][i]
        probs = {a: 0.3 / 7 for a in ACTIONS}
        probs[decision_action] = 0.7
        usage_d = Usage(input_tokens=600, cache_read_tokens=100)
        usage_l = Usage(input_tokens=800, output_tokens=30, cache_read_tokens=200)
        d = CallRecord(
            kind="decisions",
            action=decision_action,
            confidence=confidence,
            probabilities=probs,
            usage=usage_d,
            cost_usd=0.000051,
            raw={"synthetic": True},
            latency_ms=40 + i + rep,
        )
        llm = CallRecord(
            kind="llm",
            action=llm_action,
            usage=usage_l,
            cost_usd=0.00152,
            raw={"synthetic": True},
            latency_ms=180 + i * 5 + rep * 3,
        )
        for policy in ("llm", "decisions", "hybrid"):
            fallback = policy == "hybrid" and confidence < 0.7
            calls = [llm] if policy == "llm" else ([d, llm] if fallback else [d])
            initial = llm if policy == "llm" else d
            final = calls[-1]
            r = RouteResult(
                initial_action=initial.action,
                final_action=final.action,
                decision_confidence=confidence if policy != "llm" else None,
                option_probabilities=probs if policy != "llm" else {},
                fallback=fallback,
                fallback_reason="confidence" if fallback else None,
                calls=calls,
                cost_usd=sum(c.cost_usd for c in calls),
                latency_ms=sum(c.latency_ms for c in calls),
                usage=Usage(**{k: sum(getattr(c.usage, k) for c in calls) for k in Usage.model_fields}),
            )
            rows.append(
                {
                    "synthetic": True,
                    "example_id": f"synthetic-{i}",
                    "split": "synthetic",
                    "policy": policy,
                    "repetition": rep,
                    "expected_action": expected,
                    "configuration_hash": "synthetic-fixture-v1",
                    "tags": ["synthetic"],
                    "result": r.model_dump(mode="json"),
                    **outcome(r, expected),
                }
            )
path = Path("results/offline-example/runs.jsonl")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("".join(json.dumps(r) + "\n" for r in rows))
write_json(
    path.parent / "manifest.json",
    {
        "measurement": "SYNTHETIC FIXTURE — no model calls",
        "purpose": "Exercise offline analysis and charts. No scientific finding can be inferred.",
        "questions": 8,
        "repetitions": 3,
        "threshold": 0.7,
        "seed": 1729,
    },
)
print(f"Wrote {len(rows)} SYNTHETIC fixture rows; no API calls.")
