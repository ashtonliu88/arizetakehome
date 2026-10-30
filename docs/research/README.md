> **Historical design record.** This document preserves the privacy proposal and its original hypotheses. The current submission centers on the completed [workflow reuse study](../submission.md). Privacy development observations exist, but human answerability audits and held-out judge conclusions remain pending; see [current status](../status.md). Proposal language below is not a claim of completed evidence.

# Research proposals for the Arize take-home

Prepared October 28, 2026. These documents are research and implementation proposals, not completed experiments or claims of new research findings.

**Selected direction: Topic 1.** Its implementation is available in `router-lab privacy`; the
[research workflow guide](../privacy-study.md) contains the offline, pilot, review, freeze, held-out,
and Phoenix commands. Human audits and measured model findings remain pending. Topic 2 stays a follow-up.

The purpose is to choose one investigation that demonstrates the work described in the [take-home email](../../takehomeemail.md): identify an important problem, read the closest prior work, build a useful prototype, use Phoenix to investigate its behavior, evaluate a change, and explain what other developers should learn.

## The two proposals

| Proposal | Central question | Strongest reason to choose it | Main research difficulty |
|---|---|---|---|
| [Topic 1: Privacy-preserving trace evaluation](topic-1-privacy-preserving-trace-evaluation.md) | Which trace transformations preserve the evidence an evaluator needs to detect an incorrect resource lookup? | A clear demonstration of how observability configuration affects the trustworthiness of evaluations; much of the experiment can replay fixed runs. | Separating loss of identifying evidence from ordinary judge variability, while ensuring no raw identifier leaks into another evaluator input. |
| Topic 2: Benchmark compatibility after tool changes (proposed; no separate study document) | After a tool contract changes, which benchmark examples remain valid, and which need human revalidation? | The closest continuation of the existing router, authored dataset, review hashes, frozen manifests, and Phoenix experiments. | Establishing independent, version-specific ground truth and distinguishing obsolete labels from genuine agent regressions. |

Both proposals include the method, intended achievements, importance, potential impact, technical complexity, repository integration, literature boundaries, stakeholder perspectives, implementation milestones, and panel preparation. The stakeholder sections describe reasonable questions and possible value; they do not represent actual statements or priorities from Arize executives.

## How to choose

Choose **Topic 1** if the preferred presentation is a concrete observability experiment: show the same agent run under several masking policies, explain which evidence survived, and measure whether the evaluator's judgment remained correct. A strong result can lead to a small reusable transformation and an explicit evidence requirement for an evaluator.

Choose **Topic 2** if the preferred presentation emphasizes evaluation lifecycle and release decisions: change a tool contract, demonstrate why an old test can become invalid, and test whether a compatibility audit finds the affected cases without concealing real regressions. A strong result can lead to a review workflow and a version-aware benchmark comparison.

Keep the other proposal as a possible follow-up. Implementing both at once would introduce two different sources of measurement error before either experiment is understood.

## The evidence boundary

The [current project overview](../../README.md), [completion status](../status.md), and [recorded verification](../../results/verification.json) document a working Python/Phoenix foundation. The verification artifact records 59 tests with no failures and zero live model calls. Those are recorded checks, not tests rerun for these proposals. Human label reviews and measured model findings remain pending. Existing offline charts are synthetic fixtures.

The original experiment asks whether decision-model confidence selects routing errors that a second model can rescue economically. The new proposals investigate the validity of the evidence used to evaluate an agent. They should use separate datasets, result directories, and experiment identities; they should not silently alter the original benchmark or reuse an incompatible freeze.

The repository's configured $50 ceiling and $5 demo reserve are shared safeguards. They are not separate allowances for each proposal or provider-enforced billing caps. A live pilot must estimate remaining work before a larger run.

## How to demonstrate the research process

1. **State the operational decision.** Identify who would use the result and what configuration or review decision it could change.
2. **Explain the closest prior work.** Name what is already established and the specific intervention or measurement this experiment adds. Neither proposal establishes that its broad subject is untouched by research.
3. **Write the falsifiable hypothesis.** Define the main outcome, controls, evaluation inputs, grouping of related examples, and what result would contradict the hypothesis before examining held-out results.
4. **Run a diagnostic pilot.** Establish that the transformations, labels, evidence isolation, and accounting work. A planted defect verifies the measuring apparatus; it is not evidence that a live model naturally makes that mistake.
5. **Freeze the experiment.** Record the dataset, transforms or catalog transitions, prompts, evaluator, models, configuration, review status, and source versions.
6. **Investigate disagreements.** Use Phoenix traces and independent human review to distinguish an agent error, evaluator error, missing evidence, invalid label, and infrastructure failure.
7. **Report the boundary of the result.** Include uncertainty, failed runs, null findings, synthetic-workload limits, API costs, and any manually measured review effort. Do not turn a small prototype into an unmeasured production ROI claim.
8. **Deliver a developer artifact.** Provide reproducible inputs, the comparison report, explanatory traces, and one configuration or review recommendation supported by observations.

## A defensible panel introduction

> I started with confidence-gated routing and found substantial overlap with existing Arize work. I used that discovery to refine the research question. The proposal I chose examines whether the evaluation evidence remains valid when a real deployment constraint changes. I am separating the existing implementation, the proposed method, and the findings that still need to be measured.

After implementation, replace the last sentence with the actual measured finding and its practical limit. Use the detailed proposal's questions and glossary to prepare for follow-up discussion.
