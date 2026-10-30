# Submission status

The submission centers on the completed [workflow reuse experiment](reuse-study.md), summarized in the [README](../README.md), [short explanation](submission.md) and [overview PDF](../output/pdf/arize-submission-overview.pdf). The [six-minute path](walkthrough.md) leads through the [measured Phoenix gallery](phoenix-measured/README.md) to the executable notebook and technical appendix.

## Reuse: measured, human answer audit pending

The final frozen held-out matrix contains 768 endpoints: 64 base clusters, six conditions and two repetitions. Exact warm reuse and fused warm planning each achieved 122/128 mechanical successes: 100 completed responses and 22 appropriate clarifications, with six unresolved abstentions. Exact reduced cost per mechanical success by 39.7% and median latency by 45.7%. Ordinary semantic reuse accepted 18 incorrect paths among 94 hits and achieved 106/128 success. Verified reuse preserved 122/128 success, with 38.4% lower cost per success and 44.9% lower median latency. The supported recommendation is exact reuse for v1 on this recurring local workload.

Mechanical grades check ordered tools/arguments, required current facts and response status. They do not establish full answer quality. A [24-endpoint diagnostic human audit](reuse-answer-audit/README.md) is prepared across all eight families; actual candidate judgments remain pending. Appropriate abstention is separate from successful resolution. No human identity, notes or approval have been generated. Completed judgments and later adjudication must remain distinct from the frozen original scores.

Phoenix traces reconstruct saved measured executions. Publication is outside endpoint latency. Existing grades are mechanical CODE evaluations. Four portable captures and their selected records distinguish visible span fields from saved-record-only retrieval scores and rejection reasons. The subtraction failure's answer notices the wrong operation; it still fails to resolve the request.

All frozen runtime code, configurations, family reviews, raw measurements, journals, locks and 38 bundled evidence hashes are preserved. The notebook independently recomputes the saved observations without credentials, application source or external connections. Historical verification remains in `results/reuse/*verification.json`; the fresh packaging receipt is [separate](../output/submission/verification.json). No new paid experiment, recording, push or publication is included.

## Privacy extension: controlled development observations

The separate `router-lab privacy` implementation captured 72 canonical answers over 36 synthetic bases and 192 development model judgments. Raw, pseudonym and relation views each produced 48/48 decisions matching fixture labels; blanket produced 48 abstentions. Both deterministic code baselines match that development pattern. The judge receives explicit identity-semantics instructions, and trusted local extraction defines admitted evidence. These observations establish neither model superiority nor a production privacy guarantee.

Human answerability audits and 384 held-out model judgments remain pending. Saved development publication consists of 12 Phoenix experiments. Historical proposals in [research](research/README.md) remain design records with their original hypotheses; the [study guide](privacy-study.md) and [historical continuation checklist](privacy-next-steps.md) explain the separate protocol. Existing [privacy verification](../results/privacy-verification.json) records the earlier checks; it is not refreshed by submission packaging.

## Routing extension: implemented, measured conclusions pending

The original benchmark implements 120 authored examples, eight actions, Decisions-only/LLM-only/hybrid policies, dev-only gate selection, matched-rate random control, freeze/resume, clustered uncertainty and a tool/answer demo. The [routing study guide](routing-study.md) retains its commands and trust boundaries. `results/offline-example/` contains synthetic test data, not a measured model benchmark.

Human label reviews, live benchmark development/test runs, selected gate and measured routing conclusions remain pending. Setup screenshots in `docs/evidence/` show mocked integration checks and are distinct from the reuse gallery. The original [take-home email](../takehomeemail.md) and [research report](../deep-research-report.md) remain preserved.
# Fresh submission verification

The [submission receipt](../output/submission/verification.json) records 135 passing
tests, offline notebook reproduction, preserved source/evidence hashes and PDF review.
Ruff passes for application code, scripts, tests and the gallery verifier. A whole-tree
scan reports eight pre-existing findings in the frozen notebook code cells. The full
format check reports the existing difference in `src/router_lab/experiments.py`.
These frozen files are preserved; new authoring and audit files pass formatting.
