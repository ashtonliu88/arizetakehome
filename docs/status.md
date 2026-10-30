# Project evidence status

The [project overview](../project-overview.pdf) covers all three studies. Application source, frozen configurations, measurements, reviews, journals, dependency locks and the 38-file notebook evidence bundle are preserved.

| Study | Completed | Pending / limits |
|---|---|---|
| Workflow reuse | 768 held-out endpoints, 64 base clusters, six conditions, two repetitions. Exact and fused each have 122/128 mechanical successes: 100 responses and 22 appropriate clarifications. Exact saves 39.7% per mechanical success and 45.7% median latency. Candidate-confirmed diagnostic answer review: 24/24 completed; 17 scope-sensitive successes agree with mechanical grades. | Six unresolved abstentions per condition. Review is diagnostic and candidate-confirmed, with no independent blinded review claimed. Recurring local synthetic workload, shared family wording, provider token caching and miss-path tails limit transfer. |
| Privacy | 72 controlled canonical executions and 192 real development judge calls. Raw, pseudonym and relation match 48/48 fixture labels each; blanket abstains on all 48. Code baselines match. | Human answerability audits and 384 held-out model judgments remain pending. Trusted local extraction is part of the observation contract. No model-superiority or production-privacy claim. |
| Routing | 120 authored examples, eight actions, split controls, freeze/resume, development-only gate selection and matched-rate random control. Explicitly synthetic offline demonstration. | Human label review, measured development/test routing results and measured conclusions remain pending. |

## Presentation and repository cleanup

There is one [four-page PDF](../project-overview.pdf). Superseded PDFs, authoring tools, standalone helper scripts, speaking notes and historical design drafts were archived outside the working project. The application package, its tests, the analysis notebook, measured screenshots and frozen evidence remain available.

The [verification receipt](verification.json) records current checks and preserved hashes. Existing whole-tree notebook lint findings and the formatting difference in frozen `src/router_lab/experiments.py` remain unchanged. Application and test Ruff checks pass.

The [Phoenix gallery](phoenix-measured/README.md) reconstructs saved measured executions. Publication is outside endpoint latency. Existing grades are mechanical CODE evaluations. Saved retrieval diagnostics are distinguished from visible UI fields.
