# Measured workflow reuse with Phoenix

**Can a support assistant reuse a tool workflow while still fetching current data?** In this completed local experiment, exact reuse achieved **39.7% lower cost per mechanical success** and **45.7% lower median latency** than fresh planning, with **122/128 successes for both**.

Those successes comprise **100 completed responses and 22 appropriate clarifications** in each condition. Six abstentions remain unresolved. These are mechanical path, required-fact and status checks on real model calls over local synthetic fixtures; human answer-quality review remains pending.

The Python prototype caches resource-free plans, binds current identifiers and operands, executes current HTTP tools, and falls back to a structured planner on misses. Phoenix connects aggregate findings to saved executions, model calls, tool arguments and mechanical evaluations. The adverse result matters: ordinary semantic reuse accepted **18 incorrect paths among 94 hits**, achieving only **106/128 successes**. The evidence supports **exact reuse for v1**.

![Measured held-out quality and cost across the four warm-bank policies](results/reuse/analysis/test/quality-cost.png)

The motivation follows [Agentic Plan Caching](https://arxiv.org/abs/2506.14852): recurring tasks can share a plan even when current data changes. Related [structured-intent](https://arxiv.org/abs/2602.18922) and [temporal semantic caching](https://arxiv.org/abs/2605.20630) work motivates checking intent and parameters alongside similarity. This project measures that boundary in one implementation; it does not claim to invent plan caching.

Start with the [overview PDF](output/pdf/arize-submission-overview.pdf), [short submission](docs/submission.md), [six-minute reading path](docs/walkthrough.md), and [measured Phoenix gallery](docs/phoenix-measured/README.md). The [executable notebook](notebooks/trace-evidence-lab.ipynb) and [full cookbook PDF](output/cookbook/trace-evidence-lab.pdf) provide the technical appendix.

## Evidence status

| Study | Available evidence | Interpretation / remaining work |
|---|---|---|
| [Reuse](docs/reuse-study.md) | 768 held-out endpoints, 64 clusters, six conditions, two repetitions; frozen raw records and measured Phoenix captures | Exact and verified reuse preserved mechanical success. Small recurring workload; diagnostic human answer audit pending. |
| [Privacy extension](docs/privacy-study.md) | 72 controlled synthetic executions; 192 real development judge calls and deterministic baselines | Identity-preserving views enabled decisions; blanket masking caused abstention. Human audits and held-out judge results pending. |
| [Routing extension](docs/routing-study.md) | Implemented benchmark, controls, freeze/resume and synthetic offline demonstration | Measured routing conclusions and human label review pending. |

## Reproduce without model calls

Run from the repository root. Application checks use the committed lock:

```sh
uv sync --locked --group dev
uv run pytest -q
uv run ruff check src scripts tests
```

Build the notebook editions in a separate authoring environment; this does not refresh the [38-file evidence bundle](notebooks/evidence/README.md):

```sh
uv venv --python 3.12 /tmp/trace-evidence-authoring
uv pip install --python /tmp/trace-evidence-authoring/bin/python -r notebooks/requirements-cookbook.txt
/tmp/trace-evidence-authoring/bin/python scripts/build_cookbook.py
/tmp/trace-evidence-authoring/bin/python scripts/build_submission.py
/tmp/trace-evidence-authoring/bin/python scripts/verify_submission.py --portable --render
```

The build also needs Typst. Default notebook execution needs no credentials, application source, Phoenix, or external connection. Review the [diagnostic human audit instructions](docs/reuse-answer-audit/README.md) separately: a deliberately selected sample cannot estimate general success rates.

Phoenix traces reconstruct saved measured executions. Publication is outside endpoint latency. Existing grades are mechanical CODE evaluations. Retrieval scores and rejection reasons require saved records, as explained in the gallery. Miss-path tails, shared wording, provider token caching and the unresolved abstentions limit the headline result; see the [status](docs/status.md) and submission for details. No new paid runs, video, push or publication are part of this package.
