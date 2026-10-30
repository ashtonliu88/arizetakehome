#set document(title: "Measured workflow reuse", author: "Ashton Liu")
#set page(paper: "us-letter", margin: (x: 0.65in, top: 0.55in, bottom: 0.55in),
  header: context { if counter(page).get().first() > 1 {
    text(size: 7.5pt, fill: rgb("64748b"))[ASHTON LIU / MEASURED WORKFLOW REUSE]
  } },
  footer: context align(right, text(size: 7.5pt, fill: rgb("64748b"), counter(page).display("1"))))
#set text(font: "Libertinus Serif", size: 9.5pt, fill: rgb("14283f"))
#set par(justify: false, leading: 0.5em, spacing: 0.6em)
#set heading(numbering: none)
#show heading.where(level: 1): it => block(above: 0pt, below: 6pt, sticky: true,
  text(size: 22pt, weight: "bold", fill: rgb("123e59"), it.body))
#show heading.where(level: 2): it => block(above: 8pt, below: 4pt, sticky: true,
  text(size: 13pt, weight: "bold", fill: rgb("126d73"), it.body))
#show raw: set text(font: "DejaVu Sans Mono", size: 8pt)
#show link: set text(fill: rgb("0c7287"))
#show image: it => align(center, it)
#set image(width: 100%)
#set figure(gap: 4pt)
#show figure.caption: set text(size: 8pt, fill: rgb("475569"))
= Reuse the workflow, fetch the current facts
<reuse-the-workflow-fetch-the-current-facts>
Ashton Liu | Arize take-home | October 29, 2026

#strong[Question:] can recurring support requests skip model planning
without reusing stale answers? Exact workflow reuse delivered
#strong[39.7% lower cost per mechanical success] and #strong[45.7% lower
median latency] than fresh planning. Both achieved #strong[122/128
successes]: 100 completed responses and 22 appropriate clarifications.
Six abstentions remain unresolved. These are real model measurements
over controlled local synthetic fixtures, not production traffic or
human answer-quality certification.

== Motivation and implementation
<motivation-and-implementation>
Support requests often repeat a workflow with a new issue, deployment,
test run or operand.
#link("https://arxiv.org/abs/2506.14852")[Agentic Plan Caching]
motivates storing structured plans while obtaining current external
data. Related
#link("https://arxiv.org/abs/2602.18922")[structured-intent] and
#link("https://arxiv.org/abs/2605.20630")[temporal semantic caching]
studies motivate checking parameters and intent beyond textual
similarity. My contribution is a measured efficiency/correctness
boundary in a small, inspectable implementation.

The Python prototype stores resource-free plans: typed slots, ordered
steps, dependencies and provenance. It stores no historical answers or
result payloads. A deterministic binder extracts current identifiers and
operands. Exact lookup compares normalized wording skeletons; semantic
retrieval uses local word/bigram TF-IDF. Misses fall back to the same
structured planning model. Every accepted plan still executes current
loopback HTTP tools and the common answer path. Capability, tenant,
schema and returned-binding guards remain active.

Four policies isolate the tradeoff: fresh fused planning; exact reuse;
ordinary semantic reuse; and verified semantic reuse with compatibility
checks. Ordinary skips semantic compatibility, retaining execution
guards. This read-only diagnostic tests whether authorization and
argument validity alone protect intent.

== Controlled comparison
<controlled-comparison>
The frozen bank admitted 14 plans from 16 history attempts. Development
calibrated retrieval before freeze. Held-out evaluation covered eight
families, 64 base clusters, six policy/bank conditions and two
repetitions: #strong[768 endpoints]. Sources, settings, references,
reviewed family contracts and dependency locks remain frozen. No
held-out execution enters the bank.

#figure(image("../../results/reuse/analysis/test/quality-cost.png"),
  caption: [
    Measured held-out quality and cost. Success includes required
    clarification; abstention remains unresolved.
  ]
)

Exact warm reuse cost #strong[\$0.001117 per mechanical success], versus
#strong[\$0.001853] for fused warm planning. Median latency was
#strong[1,896 ms versus 3,490 ms]. Exact accepted 64 hits with no
observed incorrect accepted path. Verified accepted 68 and preserved
122/128 success, but its 38.4% cost and 44.9% median reductions did not
improve the exact headline. Costs include failed endpoints, saved usage
and frozen prices. Latency includes retrieval, inference, current tools
and required durable storage; later scoring and publication are
excluded.

#pagebreak()
== The failure Phoenix helps explain
<the-failure-phoenix-helps-explain>
Ordinary semantic reuse accepted #strong[18 incorrect paths among 94
hits] and achieved #strong[106/128 successes]. The failures span issues,
sources, calculations and comparisons. Zero observed authorization
violations did not imply intent correctness.

For `test-calculations-02`, warm repetition 1, ordinary reuse matched an
addition plan to a subtraction request. It executed
`calculate(add, 4, 10408)`, returning #strong[10412], instead of
subtraction yielding #strong[\-10404]. The final answer noticed the
operation mismatch. This was unsuccessful resolution, not a confidently
wrong numerical answer. Verified rejected the mismatch and called the
fresh planner; exact and fused comparators also used subtraction.

#figure(image("../../docs/phoenix-measured/ordinary-failure-root.png"),
  caption: [
    Saved ordinary failure in Phoenix: request, final response, trace
    tree and failed mechanical evaluation.
  ]
)

#strong[Phoenix traces reconstruct saved measured executions.
Publication is outside endpoint latency. Existing grades are mechanical
CODE evaluations.] Root spans expose policy, bank state, hit, status and
cost; children expose model calls and authoritative tool
arguments/results. The gallery follows the failure from root to wrong
operation, then to the verified comparator. A paired issue lookup shows
exact reuse making one LLM call versus fresh planning's two, while both
execute current tools.

The
#link("../../docs/phoenix-measured/README.md")[portable gallery and trace index]
include selected saved records and provenance. Retrieval scores and
rejection reasons are saved-record evidence, not Phoenix-visible fields.
Images remain usable without a local server.

#pagebreak()
== Challenges, recommendation and limits
<challenges-recommendation-and-limits>
The main engineering challenge was preserving the distinction between a
valid tool invocation and the requested workflow. Another was accounting
across crashes: endpoint, model-call and outcome journals prevent an
ambiguous interruption from silently becoming a free call or duplicate
retry. Paired analysis keeps both repetitions within their base cluster;
768 endpoints do not mean 768 independent tasks.

Use #strong[exact reuse for v1] on this workload. It met the local
efficiency targets with the simpler policy. Semantic verification
remains useful defense, but its four additional hits did not earn better
observed efficiency. History construction cost \$0.0730; estimated exact
break-even is 105 requests at the observed recurrence, excluding
engineering and review labor.

Limits remain material. This small, deliberately recurring, read-only
fixture workload uses shared family wording and provider token caching.
A zero-event bound across 64 clusters still permits about 4.6%
harmful-cluster incidence under independence. Exact misses had 4,735 ms
p95; verified empty-bank p95 was 8.2% higher than fresh empty-bank
planning. Warm median savings establish no tail-latency guarantee.

A #strong[deliberately selected and diagnostic] 24-endpoint human audit
covers all eight families. Preparation is complete; actual reviewer
judgments remain pending. Mechanical scoring cannot establish full
grounding, helpfulness or satisfaction. Appropriate abstention stays
separate from successful resolution. Future disagreements must change
the interpretation while preserving original measurements.

Privacy and routing remain labeled extensions: privacy has controlled
development observations with human/held-out judgments pending; routing
has implemented controls and synthetic demonstrations with measured
conclusions pending. The
#link("../../notebooks/trace-evidence-lab.ipynb")[notebook],
#link("../../output/cookbook/trace-evidence-lab.pdf")[technical appendix],
#link("../../docs/reuse-study.md")[study guide] and
#link("../../docs/walkthrough.md")[six-minute path] support offline
review without new paid calls.

#figure(image("../../docs/phoenix-measured/exact-versus-fresh.png"),
  caption: [
    Paired issue lookup: exact reuse removes planning while preserving
    current tool execution.
  ]
)
