# Deep Research: Arize Phoenix and the Strongest Take-Home Project Ideas

## Executive recommendation

The strongest interpretation of this assignment is **not** “build the most sophisticated agent.” It is:

> **Pick a timely AI-engineering question, build the smallest system that lets you answer it experimentally, use Phoenix to expose why the system behaves the way it does, then turn the results into a lesson another developer could use.**

That interpretation fits both the take-home rubric you received and Arize’s current product direction. Phoenix is increasingly oriented around tracing agent trajectories, attaching evaluations to those traces, turning failures into datasets, comparing changes through experiments, and making the resulting context available to coding agents through CLI/MCP interfaces. Arize explicitly describes traces, evals, experiments, and feedback as a verification layer for agentic systems. citeturn6view0turn7view2

My **highest-confidence recommendation** is:

> **“Do decision models make better agent routers? Benchmark an LLM router vs. the new OpenAI Decisions API, then add confidence-gated fallback.”**

This topic is unusually well timed. OpenAI made its Decisions API generally available on **October 22, 2026**, just five days before the date of this report. It is designed for bounded classification/routing decisions and returns choices, probabilities, or scores rather than free-form text. citeturn9search0 Phoenix added dedicated **`DECISION` spans on October 1, 2026**, specifically for routers, classifiers, and models that choose among options, and Phoenix's OpenAI integration can automatically trace Decisions API calls. citeturn10search0turn10search7 Phoenix also already ships specialized **Tool Selection** and **Tool Invocation** evaluators, giving you an almost tailor-made eval stack for this experiment. citeturn3view4

That gives the project a very clean story:

**recent industry development → prototype → tracing reveals failure modes → dataset/evals quantify them → experiment improves system → developer takeaway.**

My ranking of the best concepts is:

| Project concept | Timeliness | Phoenix fit | Demo value | Implementation risk | Overall recommendation |
|---|---:|---:|---:|---:|---:|
| **Decision-model router benchmark** | 5/5 | 5/5 | 5/5 | Low–medium | **Best choice** |
| **How many tools is too many? MCP/tool-overload benchmark** | 4.5/5 | 5/5 | 5/5 | Low–medium | **Excellent** |
| **Agent Skills portability benchmark** | 5/5 | 5/5 | 4.5/5 | Medium | **Excellent, but differentiate carefully** |
| **Agent debugging another agent through Phoenix MCP** | 4.5/5 | 5/5 | 5/5 | High | **Great stretch project** |
| **Real-time voice routing with decision models** | 5/5 | 4.5/5 | 5/5 | High | Strong but riskier |
| **Long-session memory strategy benchmark** | 3.5/5 | 4.5/5 | 4/5 | Low–medium | Solid |
| **Trajectory-aware eval vs. answer-only eval** | 4/5 | 5/5 | 4/5 | Low | Good but less novel |
| **Prompt-injection/agent-permissions demo** | 5/5 | 5/5 | 5/5 | Medium | **Avoid as primary idea: Arize just did it** |

The rest of this report explains why.

## What Phoenix actually is

Phoenix is Arize's open-source platform for **AI observability, evaluation, experimentation, and debugging**. The central workflow is to send structured traces from an AI application into Phoenix, inspect what happened inside individual runs, attach evaluations to those runs, collect examples into datasets, and rerun controlled experiments to determine whether a proposed change really improved the application. citeturn6view0turn6view1

That distinction matters for the take-home. Phoenix is not merely a logging dashboard.

### Tracing and observability

Phoenix accepts OpenTelemetry telemetry and uses the OpenInference semantic conventions to give AI operations meaningful structure. A trace can distinguish LLM calls, tools, agents, retrievers, chains, guardrails, evaluators, and—in recent releases—decision-model calls. citeturn3view1turn10search11

For example, an agent might appear conceptually as:

```text
USER REQUEST
    │
    ▼
AGENT
    │
    ├── DECISION: which tool should handle this?
    │       └── chosen tool + confidence
    │
    ├── TOOL: execute chosen tool
    │       └── arguments + result
    │
    └── LLM: formulate final response
            └── answer
```

That decomposition is valuable because an incorrect answer may originate from completely different failures: bad routing, malformed tool arguments, a bad tool result, hallucination after a correct result, or unnecessary loops. Phoenix's tracing documentation specifically frames observability around answering questions such as whether the failure came from retrieval, the wrong tool, a bad path through an agent loop, or a regression after a change. citeturn3view1

Phoenix provides auto-instrumentation across popular model providers and frameworks, while custom logic can be manually instrumented when necessary. Its current integrations include OpenAI, Anthropic, LangGraph, OpenAI Agents, Vercel AI SDK, LlamaIndex, DSPy, CrewAI, Google tooling, and others. citeturn6view0turn6view1

### Evaluations

Phoenix allows evaluations to be attached to traces, spans, experiments, and datasets. Evaluators can be LLM-based, deterministic/code-based, or human annotations. citeturn6view0

That means you could simultaneously measure:

```text
task_success             deterministic / LLM judge
correct_tool             deterministic expected-vs-actual
tool_selection_quality   Phoenix evaluator
tool_arguments_valid     Phoenix evaluator
latency                  trace telemetry
number_of_tool_calls     trace-derived code metric
hallucination            Phoenix evaluator
human_preference         human annotation
```

Phoenix currently provides specialized evaluators for agent tool use. Its Tool Selection evaluator checks whether an agent chose the appropriate tool; its Tool Invocation evaluator checks whether the selected tool was called with appropriate parameters and safe/valid values. citeturn3view4

This distinction is exactly the sort of thing that can make a take-home interesting: **the final answer can be correct even though the trajectory is poor**.

Arize demonstrated this philosophy recently by benchmarking tool-description changes: several agent configurations answered all tasks correctly, but trace inspection exposed large differences in unnecessary skill loads and cost. One description change reduced unnecessary loads while preserving benchmark correctness. citeturn7view0

### Datasets and experiments

Phoenix datasets contain examples that can originate from production/staging traces, evaluations, manual examples, or uploaded data. Those datasets become repeatable test suites. citeturn0search5turn6view0

Experiments then run different versions of an application against the **same inputs**, with evaluators scoring the outputs. Phoenix supports both a Playground-driven workflow and programmatic SDK experiments. citeturn3view2

Conceptually:

```text
                    ┌─ baseline router ──► results + traces + evals
DATASET ────────────┼─ decision router ──► results + traces + evals
                    └─ hybrid router ────► results + traces + evals

                                │
                                ▼
                         compare experiments
```

Phoenix also supports repeated experiment runs, which is useful when agent behavior is stochastic rather than deterministic. citeturn11search1

This is probably the feature set I would emphasize most in the take-home because it lets you demonstrate a scientific workflow instead of a one-off demo.

### Prompt iteration and human feedback

Phoenix includes prompt versioning, a Playground, side-by-side model/prompt testing, and span replay, allowing real traces to become examples for subsequent iteration. citeturn6view0

Human annotation can provide ground truth for subjective properties, and Arize explicitly recommends using human labels to establish what “good” means before relying entirely on automated judges. citeturn1search8turn1search2

### Phoenix's newer agent-oriented direction

Phoenix has become substantially more agent-centric during 2026.

PXI, introduced in June 2026, is an AI engineering agent inside Phoenix that can inspect traces, diagnose failures, propose prompt changes, run experiments, author evaluators, and annotate spans. citeturn3view6

Phoenix also exposes observability context to coding agents. Current releases provide Phoenix integrations/plugins for Claude Code, Codex, and Cursor, plus an MCP endpoint and CLI interfaces through which those agents can inspect observability and experiment data. citeturn3view7turn4view2

September added direct Harbor integration for agent benchmarking: Harbor trials can arrive in Phoenix as experiments, verifier rewards can become evaluations, and full agent trajectories become traces. citeturn4view1turn3view5

October added dedicated `DECISION` spans and made eval results visible directly on trace-tree rows, making it easier to start debugging from a failing evaluation and work backward through the trajectory. citeturn3view3

The release notes currently list the October 16 update as the most recent documented Phoenix release; it added tracing support for Claude Managed Agents, among other integrations. citeturn4view0

The broader product thesis from Arize is particularly relevant to your take-home: Arize argues that as agent behavior becomes nondeterministic, traces increasingly become the record of what the software **actually did**, while evals and experiments become the mechanism through which humans or other agents verify whether a change helped. citeturn7view2

That tells you a lot about what will probably resonate with the team evaluating this exercise.

## What the best take-home should demonstrate

My read of the assignment is that the evaluator will care more about the **quality of the investigation** than about raw application complexity.

A mediocre submission could contain an impressive agent:

```text
RAG + five APIs + voice + memory + multi-agent planning
```

…but have little to say beyond “it works.”

A stronger Applied AI submission can be much smaller:

```text
Six tools
One router
One carefully designed benchmark
Three router variants
Five evals
Interesting failures
One improvement
Clear evidence
```

The latter naturally lets you discuss every item in the rubric.

### There should be a falsifiable question

Good:

> Does a dedicated decision model outperform general LLM tool routing on latency without sacrificing routing accuracy?

Better:

> Can confidence-gated fallback recover the hard cases while preserving most of a decision model's latency advantage?

Also good:

> Does tool-selection accuracy degrade as the number of semantically overlapping tools increases?

Or:

> Does the same Agent Skill improve different coding agents equally?

These are research questions.

By contrast:

> “I built a customer support agent.”

is primarily an application description.

### Phoenix should reveal something you could not see from the final response

This is especially aligned with Arize's current engineering philosophy. Their recent Harbor/tool-description experiment found configurations with identical correctness but different amounts of unnecessary work; the key insight required inspecting the traces rather than looking only at task success. citeturn7view0

Similarly, Arize's recent indirect-prompt-injection experiment found cases where looking only at the final answer was insufficient: a deterministic evaluator examining tool-call spans caught all 28 observed cross-account lookups, while a judge examining only final answers identified only 5 of them. citeturn8view0

That suggests an excellent design criterion for your project:

> **Create at least one metric where “the answer was correct” is not enough.**

Examples include unnecessary tools, wrong routing followed by recovery, excessive retries, poor confidence calibration, redundant skill loads, or high cost/latency despite eventual success.

### The project should have an iteration

Do not stop after benchmarking version A.

The narrative becomes substantially stronger when you show:

```text
baseline
   ↓
trace/eval failure analysis
   ↓
hypothesis about root cause
   ↓
change
   ↓
experiment
   ↓
measurable improvement or surprising non-improvement
```

This is almost exactly the workflow Phoenix is designed to support: traces → evaluation → experiment → iteration. citeturn6view0turn7view2

And importantly, **a failed hypothesis is completely acceptable** if the methodology is strong. “The specialized router was faster but failed badly on ambiguous compound requests” can make a better engineering story than “everything improved.”

## The strongest project ideas

### Decision Router Lab: specialized decision models versus LLM routing

**This is the project I would choose.**

The industry timing is exceptional. OpenAI launched the Decisions API generally on October 22, 2026. Unlike a standard generative model call, developers define bounded questions and allowed outputs; the API can return probabilities, predefined choices, or scores. OpenAI positions it for classification, routing, prioritization, and selecting the next action in an agent. citeturn9search0

The broader category is emerging simultaneously elsewhere. Cloudflare released its Clef decision models on October 1; they similarly consume state plus typed options and return probabilities across permitted answers rather than free-form text. citeturn9search1

Phoenix happened to add the `DECISION` span kind on October 1 precisely for routers, classifiers, and similar calls, and current OpenInference tooling can trace OpenAI Decisions API calls into those spans. citeturn10search0turn10search7

#### The question

> **For agent tool routing, when should you use a decision model instead of an ordinary LLM?**

Then make it more interesting:

> **Can a hybrid router use decision-model confidence to escalate ambiguous requests to a stronger LLM, achieving a better latency/quality frontier than either model alone?**

That gives you a genuine experiment rather than just an API demo.

#### The prototype

Build a small developer-support or operations agent with approximately six to ten tools.

For example:

```text
search_docs()
search_code()
run_tests()
lookup_issue()
lookup_deployment()
calculate()
create_ticket()
ask_for_clarification()
```

The actual backends can be simple local/deterministic functions. The intellectual subject of the demo is **routing**, so there is little value in spending half the project wiring unstable third-party APIs.

Then implement three router configurations:

```text
A. General-purpose LLM router
   user → LLM chooses tool → execute tool → answer

B. Decision-model router
   user → Decisions API chooses tool → execute tool → answer

C. Confidence-gated hybrid
   user → Decisions API
            │
            ├─ confidence >= threshold → execute choice
            │
            └─ confidence < threshold → stronger LLM router
```

A fourth optional experiment could use a second decision-model provider to ask whether the phenomenon is provider-specific.

#### The dataset

Create roughly balanced categories rather than a collection of random questions:

| Split | What it tests |
|---|---|
| Easy single-tool | obvious routing |
| Semantically overlapping tools | whether descriptions are distinguishable |
| No-tool questions | unnecessary tool use |
| Ambiguous requests | whether router should clarify |
| Compound requests | whether one route is insufficient |
| Distractor wording | robustness to irrelevant keywords |
| Rare tools | routing under class imbalance |

Phoenix supports dataset splits, making it straightforward to compare aggregate performance and then drill down by category. citeturn4view1turn11search1

#### The eval stack

This is where you demonstrate that you understand Phoenix.

Use a deterministic evaluator for:

```text
route_accuracy =
    selected_tool == expected_tool
```

Use the Phoenix Tool Selection evaluator as a semantic second opinion for examples where several routes might plausibly work. Use Tool Invocation evaluation for arguments. citeturn3view4

Then measure final-task success separately.

For decision models returning probabilities, implement a calibration metric as a code evaluator—Brier score or expected calibration error, for example. That gives you a deeper question:

> When the router says 90% confidence, is it actually right about 90% of the time?

Then combine routing quality with operational metrics available through the traces such as latency and the number of calls. Phoenix surfaces latency, token, and cost information throughout trace views for supported call types, while current Decision spans use their own `decision.*` representation rather than being treated as ordinary LLM spans. citeturn4view0turn10search4

#### Where observability becomes interesting

Imagine this trace:

```text
User:
"Production checkout is timing out after yesterday's deploy."

Decision router:
  search_docs       0.06
  search_code       0.11
  lookup_issue      0.08
  lookup_deployment 0.61
  run_tests         0.14
                    ↓
lookup_deployment()

Result:
deployment itself healthy

LLM:
"Deployment succeeded; let's investigate application logs."
```

The final answer might look reasonable.

But Phoenix tells you:

```text
routing confidence = only 0.61
expected tool = search_code / deployment debugging
eventual success = yes
extra tool calls = 2
latency = high
```

That is exactly the sort of discrepancy worth teaching developers about.

#### The experiment-driven improvement

Instead of manually deciding that a confidence threshold of `0.7` “feels right,” test thresholds:

```text
0.50
0.60
0.70
0.80
0.90
```

For each threshold, compare:

```text
task success
route accuracy
fallback rate
latency
calls per request
calibration
```

Now the takeaway becomes:

> “Here is the empirical operating point where fallback becomes worthwhile.”

That is a genuinely useful developer lesson.

#### Why this is such a strong application

It simultaneously demonstrates:

**Curiosity:** You are testing technology released days before the assignment.

**Hands-on engineering:** You built the agent, router, instrumentation, dataset, evals, and experiment harness.

**Phoenix observability:** `AGENT → DECISION → TOOL → LLM` traces expose where routing fails.

**Phoenix experimentation:** multiple routing policies run against identical examples.

**Technical communication:** the result answers an emerging practical question developers actually have.

There is also a nice thematic match: Phoenix literally just added a visual representation for the thing you are researching. citeturn10search0

### Tool Overload Lab: how many tools is too many?

This is my second choice, and it could be combined with the first.

The modern agent ecosystem increasingly assumes agents have access to many tools and connectors. OpenAI's GPT-5.4 release specifically highlighted tool search as a mechanism for working efficiently across large tool/connector ecosystems, while MCP and similar ecosystems have made adding tools increasingly easy. citeturn2search24turn2search7

The research question is simple:

> **What happens to agent reliability when you keep adding tools?**

A particularly good experiment would build sets of:

```text
5 tools
15 tools
30 tools
50 tools
```

with increasing semantic overlap.

For example:

```text
search_docs
search_internal_docs
search_api_docs
search_code
search_repository
search_issues
search_resolved_issues
lookup_issue
lookup_pull_request
...
```

Then compare three approaches:

```text
Expose all tools directly
        vs.
Retrieve/search relevant tools first
        vs.
Use a dedicated decision-model pre-router
```

Phoenix's Tool Selection and Tool Invocation evaluators provide natural metrics for this experiment, while tracing gives you tool-call paths, retries, and unnecessary actions. citeturn3view4turn6view0

Possible dependent variables:

| Metric | Why it matters |
|---|---|
| Correct tool selection | basic routing quality |
| Task success | end result |
| Unnecessary calls | trajectory efficiency |
| Calls before correct tool | recovery behavior |
| Prompt/input tokens | tool-schema overhead |
| Latency | UX impact |
| Clarification rate | ambiguity handling |

The most compelling visualization would be a plot resembling:

```text
tool-selection accuracy
100% ┤●
 95% ┤  ●
 90% ┤
 85% ┤      ●
 80% ┤
 75% ┤              ●
     └─────────────────────
       5   15   30   50
         exposed tools
```

Obviously you would fill this with actual experimental results rather than expecting a particular curve.

A strong second phase would inspect traces for failures and discover *why* additional tools hurt:

```text
semantic overlap?
description length?
tool ordering?
rare-tool confusion?
keyword matching?
multi-intent prompts?
```

Then revise tool descriptions or insert a pre-router and rerun the dataset.

This project is perhaps slightly less “breaking news” than Decisions API specifically, but it may produce the **most broadly reusable developer guidance**.

A particularly strong title:

> **“Your Agent Has Too Many Tools: Evaluating Tool Overload, Search, and Routing with Phoenix”**

### Agent Skills portability: does one skill actually work across agents?

This is another highly timely topic.

On October 22, 2026, Anthropic announced that it was donating Agent Skills to the Agentic AI Foundation. Anthropic describes a skill as a folder centered around a `SKILL.md` file containing specialized procedural knowledge, scripts, or supporting materials; Anthropic also said the standard had been integrated across more than 70 agent platforms including ChatGPT, Cursor, GitHub Copilot, and VS Code. citeturn2search4

That creates a fantastic experimental question:

> **“Portable” is a file-format property—but are Agent Skills behaviorally portable?**

In other words:

> If Claude Code, Codex, and another coding agent consume the exact same skill, do they discover it at the right time and follow it equally well?

Use a small set of reproducible coding tasks in sandbox environments.

For example, create a skill teaching an agent your fictional company's release workflow:

```text
When fixing an issue:
1. inspect issue
2. reproduce bug
3. modify source
4. run targeted tests
5. run regression tests
6. update changelog
7. produce release note
```

Benchmark configurations such as:

```text
agent without skill
agent + short skill
agent + detailed skill
agent + detailed skill with scripts/examples
```

Potential evals:

```text
tests_pass
correct_files_changed
required_steps_completed
unnecessary_steps
skill_loaded
skill_loaded_when_relevant
skill_loaded_when_irrelevant
iterations
tokens
task success
```

Phoenix's Harbor integration is especially well suited to this design. A Harbor benchmark can run each agent configuration in a sandbox; Phoenix receives one experiment per agent configuration, the verifier's reward as evaluations, and the agent's trajectory as a trace. citeturn4view1turn3view5

So your Phoenix view could effectively compare:

```text
                Success    Steps    Skill loads    Tokens
Claude + skill    ...
Codex + skill     ...
Agent C + skill   ...
No-skill base     ...
```

Then inspect individual trajectories when scores disagree.

The important caveat is that Arize published a very recent Harbor/Phoenix article examining how changing an agent tool description affected unnecessary skill loading and benchmark cost. citeturn7view0

Therefore, **do not make your project simply “optimize skill descriptions.”**

Differentiate it around:

> **cross-agent portability and behavioral consistency of a newly standardized artifact.**

That makes it feel like a reaction to the October 22 standards news rather than a reproduction of Arize's October 12 work.

### Agent debugging another agent with Phoenix

This is the most “Arize-native” project.

Phoenix now exposes its data to coding agents through MCP/CLI interfaces, and Arize's articulated direction is toward closing the loop:

```text
agent runs
    ↓
Phoenix traces/evals
    ↓
coding agent diagnoses failure
    ↓
coding agent proposes change
    ↓
experiment reruns
    ↓
new traces/evals
```

Arize explicitly describes this trace → evaluate → diagnose → fix → rerun loop as a direction for agentic development. citeturn7view2 Phoenix's current coding-agent plugins support Claude Code and Cursor, with Codex integration available as well, and error-analysis workflows can be exposed through MCP. citeturn3view7

You could turn this into a demo:

> **Can a coding agent use failed Phoenix traces to improve another agent?**

Build a deliberately mediocre tool-using agent.

Run your evaluation set.

Then prompt a coding agent along the lines of:

```text
Inspect failed experiment examples in Phoenix.
Find a common failure mode.
Propose the smallest change that should improve it.
Do not modify the benchmark or evaluator.
Implement the change.
Rerun the experiment.
Compare against baseline.
```

Now you are evaluating not only the application but an **AI engineering loop**.

A beautiful result would be:

```text
Baseline
67% routing accuracy

↓ Phoenix trace analysis

Coding agent hypothesis:
"search_docs and search_api_docs have overlapping descriptions"

↓ edit

Experiment 2
82%

↓ remaining failures

Second diagnosis:
ambiguous requests need clarification route

↓ edit

Experiment 3
89%
```

This would be an extremely strong demo of Phoenix “as a user,” but I would use it as a **stretch layer on top of one of the simpler experiments**, rather than making it the entire project. Otherwise you risk spending too much engineering effort on the meta-agent rather than producing an insightful result.

### Real-time voice agent with a fast decision layer

This is the high-demo-value choice.

OpenAI's October 22 Decisions launch specifically includes integration with its live voice stack, positioning fast decisions for operations such as deciding whether to clarify, route, escalate, or select another next action during a live conversation. citeturn9search0

Phoenix also documents tracing for LiveKit Agents using OpenTelemetry, including agent sessions, turns, speaking activity, and model calls. citeturn0search32

You could create:

> **A voice support agent whose next-action router uses either a full LLM or a decision model.**

Then measure:

```text
routing correctness
time to next action
unnecessary clarification
wrong escalation
session goal completion
user friction
```

Phoenix now has a built-in User Friction evaluator, and session-level evaluation workflows can score properties such as goal completion and conversational coherence over entire multi-turn interactions rather than individual messages. citeturn4view2turn5search1

This would make for a visually compelling demo, but it introduces many unrelated variables—speech recognition, streaming, interruptions, audio UX—so I would choose it only if voice systems are something you specifically want to learn.

### Memory and context strategies for long-running agents

A quieter but technically excellent experiment would ask:

> **What should an agent remember?**

Build a multi-turn assistant and compare:

```text
full conversation history
rolling summary
structured memory
retrieved episodic memory
hybrid memory
```

Then simulate longer sessions with facts introduced earlier and evaluate:

```text
fact recall
contradiction rate
goal completion
coherence
token use
latency
```

Phoenix supports session-level traces and annotations, and its session-evaluation cookbook explicitly demonstrates that individual turns can all appear locally acceptable while coherence, frustration, or goal completion fails across the conversation as a whole. citeturn5search1

The learning here is excellent, but the news hook is weaker than the decision-model or Agent Skills concepts.

### Trace-aware evaluation versus answer-only evaluation

This is probably the easiest project that could still produce serious insight.

Research question:

> **How much agent misconduct or inefficiency do we miss when our evaluator only sees the final answer?**

Create intentional cases such as:

```text
agent calls wrong tool, then recovers
agent retrieves sensitive/unnecessary data but omits it from answer
agent makes three redundant calls
agent retries endlessly before succeeding
agent claims an operation happened when its tool failed
```

Evaluate each run with:

```text
A. answer-only judge

B. judge with full trajectory

C. deterministic checks over tool spans
```

Then compare precision/recall against human labels.

This is strongly justified by Arize's own recent prompt-injection experiment: an answer-only LLM judge detected only 5 of 28 cross-account lookup incidents, whereas a deterministic check of tool-call spans detected all 28. citeturn8view0

That result is also a reason **not** to reproduce the exact prompt-injection demo—they have already published it. Instead, make the evaluation methodology itself the topic.

A great title would be:

> **“Your Agent's Final Answer Is Lying to Your Evals: Evaluating Outcomes vs. Trajectories.”**

## What I would build for the actual submission

I would combine the two strongest ideas into one compact project:

# **The Agent Router Lab**
### *When should an agent use an LLM, a decision model, or both?*

The core system would be deliberately simple.

```text
                        ┌───────────────────┐
                        │ User request      │
                        └────────┬──────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
          baseline experiment              new experiment
                 │                               │
                 ▼                               ▼
          General LLM                      Decision model
          tool router                      router
                 │                               │
                 │                     confidence < T?
                 │                         /          \
                 │                       yes           no
                 │                        │             │
                 │                   LLM fallback      │
                 │                        │             │
                 └─────────────┬──────────┴─────────────┘
                               ▼
                            tool call
                               │
                               ▼
                         final response
```

Every request would produce Phoenix traces resembling:

```text
AGENT
├── DECISION or LLM router
├── TOOL
└── LLM response
```

Phoenix's current trace tree can show eval summaries directly on span rows, making failed tool-selection or invocation evaluations visible without opening every span. citeturn3view3

### Dataset design

I would build approximately six conceptual categories:

| Category | Example |
|---|---|
| Straightforward | “Find the docs for OAuth callbacks.” |
| Semantic overlap | “Find where OAuth handling is implemented.” |
| Clarification needed | “The deployment broke.” |
| Multi-intent | “Check yesterday's deploy and open an issue if tests fail.” |
| No tool | “Explain what exponential backoff is.” |
| Distractor | “The issue mentions deployment but actually asks about billing docs.” |

Use a held-out test split so the threshold or prompt is not optimized on the same examples that produce the final reported result. Phoenix supports dataset splits for exactly this kind of structured experimental workflow. citeturn4view1turn11search1

### Experimental progression

The story should have clear chapters.

**Baseline experiment**

General-purpose LLM chooses the tool.

Measure:

```text
route accuracy
task success
tool invocation quality
latency
calls/request
```

**Decision-model experiment**

Replace only routing.

This cleanly isolates one independent variable.

**Failure analysis**

Use Phoenix traces to categorize failures:

```text
ambiguous intent
overlapping descriptions
multi-tool task
wrong no-tool decision
underconfident correct route
overconfident incorrect route
```

**Hybrid experiment**

Introduce the confidence threshold.

For example:

```python
if decision.confidence < threshold:
    return llm_router(request)
return decision.choice
```

The actual threshold should emerge from the experiment rather than being selected by intuition.

**Tool-overload experiment**

Optional but excellent:

```text
8 tools → 16 tools → 32 tools
```

Ask whether the same routing approaches degrade differently as tool count grows.

At that point your project answers two genuinely interesting questions:

> Are specialized decision models good routers?

and

> Do they become more or less valuable as agent toolboxes grow?

### Phoenix workflow to showcase

I would explicitly demonstrate **both** workflows requested in the take-home rather than choosing only one.

**Observability**

Show one successful trace and one surprising failed trace.

Point to:

```text
router choice
probability/confidence
tool call
tool parameters
tool output
final response
eval badges
latency
```

Phoenix's decision spans are particularly useful here because decision-model calls no longer need to look like ordinary chat-generation calls. citeturn10search0

**Experimentation**

Upload/create the benchmark dataset and run:

```text
experiment: llm-router
experiment: decisions-router
experiment: hybrid-threshold-0.6
experiment: hybrid-threshold-0.7
experiment: hybrid-threshold-0.8
```

Phoenix's experiment workflow is specifically designed to run different application versions on a shared dataset with configured evaluators. citeturn3view2

The experiment table then becomes one of the central artifacts in your presentation.

### What could become the developer lesson

Do not decide the lesson before running the experiment.

Frame possible hypotheses such as:

> “A specialized decision model will be faster, but its errors may cluster around multi-intent prompts.”

> “Decision confidence may make a useful fallback signal—but only after calibration.”

> “Task success may hide bad routing because stronger downstream models recover from mistakes.”

> “Adding tools may hurt an ordinary LLM router faster than a bounded decision router.”

> “The best system may not be the model with highest standalone route accuracy; it may be the router/fallback combination with the best quality-latency tradeoff.”

Those are **hypotheses**, not claims. Whatever the actual experiments show becomes the post.

That distinction is important because it makes the project feel like Applied AI research instead of marketing.

## How to make the submission stand out

The most important artifact is probably not the UI.

It is the **story of one surprising trace**.

Imagine your README opening:

> We expected OpenAI's new Decisions API to be a drop-in replacement for LLM tool routing. Across our benchmark it was considerably faster, but the aggregate accuracy number hid a failure mode: compound requests were routed confidently to a single tool. Phoenix traces showed that the final-answer model often recovered, making task-level evals look healthier than the router really was. We added a trajectory-level route evaluator and confidence-gated fallback, then reran the benchmark.

That tells the reviewers immediately that you understand the job.

A polished frontend is optional.

A clear experiment is not.

### A strong repository structure

Something like this would make the project easy to inspect:

```text
agent-router-lab/
│
├── README.md
├── pyproject.toml
│
├── src/
│   ├── agent.py
│   ├── tools.py
│   ├── routers/
│   │   ├── llm_router.py
│   │   ├── decision_router.py
│   │   └── hybrid_router.py
│   ├── tracing.py
│   └── evals.py
│
├── dataset/
│   ├── examples.jsonl
│   └── README.md
│
├── experiments/
│   ├── run_baseline.py
│   ├── run_decisions.py
│   ├── run_threshold_sweep.py
│   └── analyze.py
│
├── results/
│   ├── summary.csv
│   └── figures/
│
└── demo/
    └── screenshots/
```

Phoenix can be run locally with the Phoenix package, and its current CLI can assist with instrumentation setup for supported stacks. citeturn6view1

### The README should answer the rubric almost verbatim

**What I built and why**

> Decision models became a major agent-routing topic in October 2026, so I wanted to understand when they are actually preferable to general LLM routing.

Support that framing with OpenAI's October 22 launch and Phoenix's October 1 Decision-span release. citeturn9search0turn10search0

**Phoenix workflows explored**

Show both:

```text
Tracing:
router → tool → response

Experiments:
same dataset × multiple router configurations
```

**Challenges encountered**

The best challenges are methodological:

```text
How do I define "correct route" for ambiguous questions?
How should multi-tool tasks be represented?
Can confidence be treated as calibrated?
Should task success and route success be separate?
How much repetition is necessary?
```

These communicate much more engineering maturity than “I had trouble configuring an API key.”

**Learnings for other developers**

Aim for approximately three concrete conclusions:

```text
Finding A:
when decision models work

Finding B:
where they fail

Finding C:
what hybrid architecture worked better
```

Ideally each is backed by an experiment result and one illustrative trace.

### Add one small human-annotation pass

Even if most ground truth is deterministic, manually review a subset of ambiguous examples and annotate whether the expected route is genuinely unambiguous.

Phoenix supports human annotations as ground truth and uses them in eval-driven development workflows. citeturn1search5turn1search2

That would let you say something quite sophisticated:

> “Before measuring model accuracy, I audited the benchmark itself.”

That is exactly the sort of evaluation maturity that matters in real Applied AI work.

### Add one failure taxonomy

Instead of merely reporting:

```text
router accuracy = 87%
```

break errors into:

```text
semantic collision          5
multi-intent                 3
should-have-clarified       2
unnecessary tool            1
invalid arguments           1
```

Then show one Phoenix trace for each major category.

This turns a benchmark into actionable engineering insight.

### Optional killer stretch goal: let the coding agent use Phoenix

Once the main project works, connect your coding agent to Phoenix and ask it to analyze the failed experiment.

Phoenix now supports coding-agent access via MCP/plugin workflows, and Arize's stated direction is precisely to make traces, evaluations, and experiment data usable by agents as well as humans. citeturn3view7turn7view2

Your demo could end with:

```text
You:
Analyze the failed tool-selection evals in experiment
"decision-router-v1". What is the most common failure mode?

Coding agent via Phoenix:
8/13 failures involve search_code vs search_docs...
The tool descriptions overlap around "implementation"...
I suggest...

You:
Make the change and rerun the experiment.
```

That would directly demonstrate curiosity about Phoenix itself, rather than merely using it as a passive tracing backend.

## Final prioritization

I would make the decision based on what you want the reviewers to remember about you.

### Best overall: decision-model routing

**Project title:**

> **Do Agents Need LLMs to Make Every Decision? Benchmarking Decision Models for Tool Routing with Phoenix**

Why I would choose it:

It is tied to an industry release from **October 22, 2026**. citeturn9search0

It intersects with a Phoenix feature introduced **October 1, 2026**. citeturn10search0

It naturally produces both traces and controlled experiments.

It has deterministic metrics, so you are not dependent entirely on an LLM judge.

It creates obvious follow-up hypotheses involving calibration, fallback, tool overload, and routing architecture.

It can remain technically small while producing a sophisticated analysis.

### Best developer-education topic: tool overload

**Project title:**

> **How Many Tools Is Too Many? Measuring Agent Tool Confusion with Phoenix**

Choose this if you want the project's main artifact to be a compelling engineering article. Tool-selection and trajectory metrics make it particularly well matched to Phoenix's current evaluator stack. citeturn3view4

### Best “I keep up with everything” topic: Agent Skills

**Project title:**

> **Portable File, Portable Behavior? Benchmarking Agent Skills Across Coding Agents**

The October 22 Agent Skills standardization news makes it exceptionally current. citeturn2search4

I would only choose it if you explicitly differentiate from Arize's own very recent Harbor/tool-description benchmarking work. citeturn7view0

### Best high-risk/high-reward demo: agents debugging agents

**Project title:**

> **Can Codex Debug an Agent from Its Phoenix Traces? Closing the Eval-Driven Development Loop**

This aligns most directly with Arize's vision of coding agents consuming telemetry and proving their own changes through traces, evaluations, and experiments. citeturn7view2

It is probably better as a stretch component than the starting point.

### Topics I would deprioritize

I would **not** submit a generic RAG chatbot unless the actual research question concerns retrieval behavior. Phoenix already has extensive RAG, agentic RAG, retrieval-evaluation, talk-to-your-data, and related cookbook material, so a straightforward RAG demo is unlikely to differentiate you. citeturn5search0turn4view1

I would also avoid building essentially the same indirect prompt-injection demo Arize published in October 2026; their existing project already covers poisoned pages, cross-account access, trace-level detection, deterministic versus LLM evaluation, and scoped tool guardrails. citeturn8view0

Likewise, I would avoid making a software-factory demo the core idea unless you have a distinctly new research question, because Arize has just published an agentic software-factory project that traces stages and uses generated verdicts to improve prompts. citeturn8view1

The strongest submission therefore is not the biggest prototype. It is the one where reviewers can see a complete Applied AI loop:

```text
CURRENT AI DEVELOPMENT
        ↓
INTERESTING QUESTION
        ↓
SMALL PROTOTYPE
        ↓
PHOENIX TRACING
        ↓
DATASET + EVALS
        ↓
BASELINE EXPERIMENT
        ↓
FAILURE ANALYSIS
        ↓
ENGINEERING CHANGE
        ↓
COMPARATIVE EXPERIMENT
        ↓
DEVELOPER TAKEAWAY
```

For this particular take-home, **the decision-router experiment offers the cleanest version of that loop**: it is unusually current, closely matched to Phoenix's newest observability primitives, measurable without an elaborate application, expandable into tool-overload or self-debugging experiments, and likely to give you something genuinely useful to teach other developers even if the results contradict your initial hypothesis.