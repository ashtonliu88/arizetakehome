# Diagnostic human answer review

**Status: 0 of 24 reviews completed; 24 pending.** The candidate requested that the audit remain pending. No human judgments have been generated.

This deliberately selected diagnostic sample covers all eight held-out families, warm bank, repetition 0, from the final frozen configuration. It is not a random sample and cannot estimate a general success rate.

1. Give the reviewer [packet.md](packet.md) and a copy of [review-template.jsonl](review-template.jsonl). Keep the [reference key](reference-key.json) hidden during the initial review.
2. For each anonymous item, inspect the request, context, current tool evidence and final response. Record task outcome, grounding, scope and safety, unsupported claims, contradictions, clarity, and concise supporting notes.
3. Preserve blank fields as pending. Record uncertainty explicitly. Appropriate abstention is separate from successful resolution.
4. Only after initial review, compare the completed judgments with the reference key. Report every disagreement with the original mechanical grade and retain both records. Never overwrite the frozen measurements.

The [manifest](manifest.json) binds the 24 saved endpoints and packet artifacts to their source hashes. [packet.json](packet.json) is the machine-readable review material. The [pending report](status/report.md) records the actual current coverage. The earlier preparation/reporting helper has been removed from this presentation repository; the packet and its source provenance are retained.
