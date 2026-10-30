# Diagnostic human answer review

**Status: 24 of 24 judgments confirmed by Ashton Liu; 0 pending.** The candidate confirmed the reviewed judgments on 2026-10-30. This is a candidate-confirmed diagnostic review; no independent blinded review is claimed.

The [report](status/report.md) records 15 completed answers within scope, one completed answer with an unnecessary lookup, two appropriate clarifications, three appropriate abstentions, two incomplete responses and one incorrect response. The 17 successes under the existing scope-sensitive rule agree with the mechanical grades.

This deliberately selected diagnostic sample covers all eight held-out families, warm bank, repetition 0, from the final frozen configuration. It is not a random sample and cannot estimate a general success rate.

For an additional independent review:

1. Give the reviewer [packet.md](packet.md) and a copy of [review-template.jsonl](review-template.jsonl). Keep the [reference key](reference-key.json) hidden during the initial review.
2. For each anonymous item, inspect the request, context, current tool evidence and final response. Record task outcome, grounding, scope and safety, unsupported claims, contradictions, clarity, and concise supporting notes.
3. Preserve blank fields as pending. Record uncertainty explicitly. Appropriate abstention is separate from successful resolution.
4. Only after initial review, compare the completed judgments with the reference key. Report every disagreement with the original mechanical grade and retain both records. Never overwrite the frozen measurements.

The [manifest](manifest.json) binds the 24 saved endpoints and packet artifacts to their source hashes. [packet.json](packet.json) is the machine-readable review material. The [completed report](status/report.md) records the actual current coverage. The earlier preparation/reporting helper has been removed from this presentation repository; the packet and its source provenance are retained.
