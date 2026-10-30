# Diagnostic human answer audit

**Pending: 0/24 actual human judgments received.** The [current status report](status/report.md) and [JSON report](status/report.json) validate the blank template and explicitly record all 24 reviews as pending. The packet is prepared; a blank template is not a completed audit. This sample is **deliberately selected and diagnostic**. It supports individual failure analysis, not an estimate of general success rates.

Give the candidate [packet.md](packet.md) (or [packet.json](packet.json)) and a copy of [review-template.jsonl](review-template.jsonl). The packet hides policy names, run IDs, and mechanical grades. Keep [reference-key.json](reference-key.json) and [manifest.json](manifest.json) separate until initial judgments are recorded. Source paths in the provenance manifest can reveal the saved runs to an investigator.

The 24 endpoints are twelve prescribed pairs from the final frozen configuration, held-out test split, warm bank, repetition 0. They cover all eight families and are shuffled with seed 1729. This is independent of the repetition 1 Phoenix subtraction investigation. Each item includes the request, permission context, active tenant's current synthetic fixture facts, saved tool evidence, response status, and answer. Preparation never calls a provider or changes the original study.

The candidate must supply their own name, timestamp with timezone, evidence-specific note, and four judgments for every item. Allowed values are documented in the packet. Notes must explain a concrete fact in the request, tool evidence, or answer; minimum length validation alone cannot establish their quality. Appropriate clarification counts as successful resolution when it requests necessary missing context. Appropriate abstention is reported separately and does not count as successful resolution.

Copy the template to a distinct file, then edit that copy:

```bash
cp docs/reuse-answer-audit/review-template.jsonl /tmp/reuse-human-reviews.jsonl
# Candidate reviews packet.md and fills /tmp/reuse-human-reviews.jsonl.
python3 scripts/reuse_answer_audit.py report \
  --reviews /tmp/reuse-human-reviews.jsonl \
  --output docs/reuse-answer-audit/completed
```

The default report rejects missing or duplicate IDs, incomplete reviews, invalid judgments, missing identity/timestamps/notes, altered packet artifacts, and source hash mismatches. The completed report includes outcome counts, disagreements with mechanical success, scope errors, uncertainties, unsupported claims, contradictions, and individual examples. It preserves the input judgments byte for byte in a separate report directory and hashes them. Do not overwrite initial judgments. Record any later adjudication in another file with reviewer, timestamp, reason, and the original anonymous ID.

For an explicit progress report, use `--allow-incomplete` and a new output directory. Blank or partial rows remain pending; valid supplied fields are checked. This does not convert the packet into human evidence. Human judgments can qualify the submission's interpretation; they never alter frozen measurements or mechanical CODE grades.

To reproduce preparation in an empty directory:

```bash
python3 scripts/reuse_answer_audit.py prepare --output /tmp/reuse-audit-packet
```

The manifest records SHA-256 hashes of the frozen source archive, frozen configuration files, input cases, measured run journal, all selected saved outcomes, and packet artifacts. Reporting rechecks them and reconstructs the exact selection without importing application or provider clients. Existing output directories containing files are refused to preserve prior work.
