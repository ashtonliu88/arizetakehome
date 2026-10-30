# Reliable agent workflows with Phoenix

A Python project investigating three questions: **when to route to a larger model, when to reuse a tool workflow, and how much trace evidence an evaluator needs after identifiers are transformed.** Phoenix connects the decisions to model calls, current tool executions, and evaluation results.

**Start with the [four-page project overview](project-overview.pdf).** It explains the entire project, the measured findings, the failure case, and the remaining work.

## What the project shows

| Study | What is built | Evidence and conclusion |
|---|---|---|
| [Workflow reuse](docs/reuse-study.md) | A frozen bank of resource-free plans, fresh argument binding, current HTTP tools, exact and semantic retrieval | 768 held-out endpoints across 64 clusters. Exact reuse reduced cost per mechanical success by **39.7%** and median latency by **45.7%**, preserving **122/128 mechanical successes**. Prefer exact reuse for this workload. |
| [Privacy evaluation](docs/privacy-study.md) | Raw, blanket, pseudonym and relation views of the same execution; model and deterministic judges | 192 real development judgments on controlled synthetic executions. Identity-preserving views matched 48/48 fixture labels each; blanket masking produced 48 abstentions. Human audits and held-out judgments remain pending. |
| [Confidence routing](docs/routing-study.md) | Decisions-only, LLM-only and confidence-gated hybrid policies; development-only gate selection and a matched-rate random control | 120 authored examples across eight actions. Offline mechanics are demonstrated with explicitly synthetic data; measured routing conclusions remain pending. |

Reuse success includes 100 completed responses and 22 appropriate clarifications; six abstentions remain unresolved. These mechanical checks do not certify full answer quality. The diagnostic human audit is **pending: 0/24 reviewed**.

## Explore the evidence

- [Measured Phoenix gallery and trace index](docs/phoenix-measured/README.md): an addition plan incorrectly reused for subtraction, its verified comparator, and one versus two LLM calls.
- [Executable analysis notebook](notebooks/trace-evidence-lab.ipynb): recomputes saved observations from a [38-file hashed evidence bundle](notebooks/evidence/README.md), without credentials or paid calls.
- [Human audit packet](docs/reuse-answer-audit/README.md), [study status](docs/status.md), and [cleanup verification](docs/verification.json).

Phoenix traces reconstruct saved measured executions. Publication is outside endpoint latency; existing grades are mechanical CODE evaluations. Screenshots and selected records work offline.

## Run the application and checks

```sh
uv sync --locked --group dev
uv run pytest -q
uv run ruff check src tests
uv run router-lab --help
```

Keep credentials in the ignored `.env`. The study guides describe the existing application CLI; paid study execution is a separate explicit action. The repository contains application code, tests, a notebook and evidence, with no standalone helper or presentation scripts.

`src/router_lab/` contains the application; `config/`, `data/` and `fixtures/` define the controlled workloads; `results/` retains the original measurements and journals. The overview is the only PDF in the project.
