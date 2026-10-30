# Benchmark audit

`benchmark.jsonl` is the versioned experiment dataset. The authored dataset is committed for inspection. Each example has a stable ID, request, one next-action label, rationale, category tags, paraphrase group, and dev/test split. The validator checks exact counts, unique normalized requests and IDs, valid labels and group leakage.

The examples were authored during implementation and have **not been certified as human reviewed**. `review-label` records a real reviewer's decision against an exact example hash; do not batch-generate approvals. If a label is unresolved, rewrite it and rerun the validator before freezing. Paraphrase-group auditing also requires semantic human judgment: unique IDs alone cannot prove absence of near-paraphrases.

Some specific identifiers intentionally have no fixture record. Their routing labels remain lookup actions: an absent record is an execution result, while an absent essential identifier requires clarification. The benchmark evaluates route selection, not the fixture lookup success rate.

The demo uses each action's `-01` development example. Expected answer-fact checks are in `demo.py`, separate from benchmark ground truth and excluded from all routing inputs. Human answer review supplements those limited heuristic checks.
