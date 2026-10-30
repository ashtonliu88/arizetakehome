# Privacy-preserving trace evaluation

For the current run with completed development judgments, use the ordered
[remaining commands and correctness notes](privacy-next-steps.md).

This is a privacy extension to the completed [workflow reuse submission](submission.md). The original [Topic 1 proposal](research/topic-1-privacy-preserving-trace-evaluation.md) remains a historical design record.
The implementation compares what a fixed evaluator can establish about resource scope from four views
of the **same execution**. The saved run has 72 canonical answers and 192 development model judgments; raw, pseudonym and relation each match all 48 fixture labels, while blanket abstains on all 48. Both code baselines agree. Human audits and held-out judge conclusions remain pending.
The original routing dataset, results, CLI commands, and gate-selection workflow are separate.

## Start offline

Run from the repository root:

```bash
uv sync --locked --group dev
uv run router-lab privacy prepare
uv run router-lab privacy replay --split dev --judge evidence
uv run router-lab privacy replay --split dev --judge exact
uv run router-lab privacy analyze --split dev --judge evidence
uv run router-lab privacy status
uv run pytest -q
```

These commands need neither credentials nor Phoenix. `results/privacy/` is the default study directory
and is gitignored. Use `router-lab --results-dir results/follow-up privacy ...` for a separate study;
its files will be under `results/follow-up/privacy/`. Every paid study still uses **the same**
`results/budget.jsonl` ledger and `results/.run.lock`.

Inspect these local artifacts:

| Artifact | Purpose |
|---|---|
| `episodes.jsonl` | Canonical synthetic executions, fixture oracle, entity registry, and captured answers; local raw control |
| `views/{raw,blanket,pseudonym,relation}.json` | Exported inputs with lineage outside the `input` object |
| `information-limit-control.json` | An opposite-label pair with identical blanket inputs, built with template prose; excluded from measured model metrics |
| `checks.json` | Seeded-identifier leakage, within-trace identity, cross-trace token, and collision checks |
| `review-queue.jsonl` | Regenerated scratch suggestions, all **unapproved**; do not store completed human reviews here |
| `reviews.jsonl` | Actual human decisions, bound to the full episode hash |
| `dev-*.jsonl`, `test-*.jsonl` | First terminal scheduled judgments, raw responses, usage, attempts, costs, timestamps, and order |
| `analysis/dev-evidence/` | JSON/CSV metrics, complete contingency table, domain/family slices, and portable `coverage-error.png` |

The offline checker should solve the declared relationship cases in raw, pseudonym, and relation views
and abstain on blanket views. This demonstrates the evidence contract and tests a strong code baseline.
It does not measure how an LLM responds to those views. If the code baseline captures all useful behavior,
present the result as a practical verification recipe rather than claiming a novel model capability.

## Design and evidence contract

There are 36 base requests, two controlled episodes per request, and nine whole task families. The three
direct-lookup families are development (12 bases, 24 episodes). Six declared-scope/relationship families
are held out (24 bases, 48 episodes). Both splits cover issues, deployment composite keys, and test runs.
There are 192 development and 384 held-out judgments per judge: episodes × four views × two repeats.

The builder invokes the existing typed handlers. The scenario adapter deliberately chooses the wrong
invocation or injects the wrong returned-record binding. These are seeded diagnostic interventions,
not observed autonomous-agent error rates. Matched records share independently sampled non-identifying
payloads. Cases include explicit aliases, multiple permitted resources, an issue-to-test-run join,
incorrect returned bindings despite correct arguments, and permitted not-found lookups.

`requested` and `linked_scope` normalize declarations in the request. This is a **trusted local parsing
contract**, not an LLM extraction result or a production authorization check. Result bindings are explicit
adapter metadata admitted in every representation. The fixture oracle expands permitted identities
independently for scoring and is never passed to the judge. Final-answer helpfulness and grounding do not
change the primary access-scope label.

All views use one allowlisted schema. Structured arguments are normalized to whole resource references
in **every** treatment. Raw retains fabricated identifiers. Blanket collapses identities by type.
Pseudonyms preserve equality using opaque tokens with a fresh deterministic trace-local seed. The
local seed/map never enters an exported input. Deployment resources use a composite service/environment
key; unbound component mentions in prose are collapsed to component placeholders. Separate component
pseudonyms are a future ablation, not part of this study. Replacement is recursive, longest-first and
boundary-aware, including JSON-encoded fields; JSON string formatting may be normalized.

Relation views preserve requested references, observed final-answer resource mentions, admitted aliases, linked-scope rules, tool targets,
returned bindings, observed links, ordering, and found/error status. They omit narrative, other payload,
and metadata. Final-answer mentions are extracted deterministically; they are not a semantic claim or
answer-grounding verdict. Graph equality is a **derived verification signal** from trusted local observation, not
a free inference by the judge. Transformations never consult the gold label or hidden allowed set.

The exact baseline abstains outside single-reference equality cases. The evidence baseline handles
explicit aliases, sets, links, and bindings. Both abstain when identity has collapsed. The model sees
one fresh evidence object per call, the same rubric/schema/configuration for all treatments, and no
treatment name, scenario tag, gold label, counterpart, fixture map, or lineage metadata.

## Run a small paid pilot

Add your own `OPENAI_API_KEY` to `.env`. The existing `config/settings.json` supplies the answer/judge
model, token limits, retry rules, and price assumptions. Revalidate its price assumptions before a paid
run. The study fixes **two** judgments per view, independently of the original router repetition count.

```bash
uv run --env-file .env router-lab privacy generate --split dev --max-bases 3
uv run --env-file .env router-lab privacy replay --split dev --judge model --max-bases 3
uv run router-lab privacy analyze --split dev --judge model
uv run router-lab privacy status
```

This covers three base requests across the three domains: six answer generations and 48 scheduled
judgments before retries. Inspect every view sent to the judge, operational errors, raw outputs, token
usage, latency, and the shared ledger. A partial analysis retains all 192 scheduled development slots:
missing results remain in denominators and count as operationally incomplete. Pilot estimates must
replace speculative cost arithmetic before scaling.

Every paid command checks a conservative remaining-work projection; every attempt also uses durable
reservations and the existing retry/settlement code. The $50 ceiling and $5 reserve are shared with
all earlier router, smoke, and demo work. Reservations are local safeguards, not provider billing caps.
Answer-generation cost and evaluator cost are reported separately. Usage-unknown or interrupted charges
remain in the global ledger even when no complete study row exists.

Study model calls use a local tracer with no live exporter or automatic instrumentation. Provider outputs
are saved in local control files, with judge call logs separated by representation. Publishing saved
views to Phoenix is a later explicit step. This does **not** implement a production PII detector or
guarantee sanitization across arbitrary instrumentation, logs, provider systems, or live exporters.

## Finish development and audit

Finalize the rubric and transformations on development examples, then complete canonical answers:

```bash
uv run --env-file .env router-lab privacy generate --split dev
uv run --env-file .env router-lab privacy generate --split test
uv run --env-file .env router-lab privacy replay --split dev --judge model
uv run router-lab privacy prepare
```

The MVP needs 72 final-answer generations plus 576 scheduled model judgments in total, before retries.
Generation does not run routing or argument extraction. Held-out canonical answer generation precedes
freeze; held-out **judgments** are blocked until freeze. The generated answers stay identical across
their four views. Independent generated prose can retain semantic hints even after identifier masking;
do not assume live blanket pairs remain byte-identical. The separately marked template control preserves
the information-limit demonstration without claiming a live-model result.

Get an episode ID from `episodes.jsonl` or `review-queue.jsonl`, then replace `<episode-id>` below:

```bash
uv run router-lab privacy inspect --episode "<episode-id>"
uv run router-lab privacy review --episode "<episode-id>" \
  --reviewer "Your name" --note "Explain the scope label, bindings, transform integrity, and answerability" \
  --answerable "raw,pseudonym,relation" --approve
```

Review **each of the 72 episodes and its four views**. The answerable list is a human decision, not a
required value: use only the representations whose admitted evidence supports a verdict. A model may
write prose that changes a blanket view's answerability. The queue's suggested values require scrutiny.
For file-based review, copy the current queue to a working file, manually audit/edit every row, and save
the completed records as `results/privacy/reviews.jsonl`. Supply `approved`, `reviewer`, a substantive
`note`, and four boolean `answerable` values. Do not script or manufacture approvals. An episode change
invalidates its review. If an oracle label or observation is wrong, fix the corpus and rerun affected work.

Run the evidence and exact baselines again after answer generation if you want analyses of current views.
Resume keys bind the actual episode evidence, view, source/configuration, rubric, judge, and repetition.
Changing a prompt, source, model, endpoint, lock, or relevant package invalidates prior work. Planned
repeats always use separate calls. Already completed operational failures remain terminal observations.

## Freeze, evaluate held-out views, and analyze

```bash
uv run router-lab privacy freeze
uv run --env-file .env router-lab privacy replay --split test --judge model --frozen
uv run router-lab privacy replay --split test --judge evidence --frozen
uv run router-lab privacy replay --split test --judge exact --frozen
uv run router-lab privacy analyze --split test --judge model
uv run router-lab privacy analyze --split test --judge evidence
uv run router-lab privacy analyze --split test --judge exact
```

Freeze requires current model-generated answers, all human audits, and all 192 development model
judgments, including explicitly recorded operational failures. The manifest hashes source, prompts,
transform/oracle implementation, model settings, packages, lock, endpoint, canonical corpus, reviews,
and development evidence. Test commands verify it before constructing a model client. Human reviews,
answers, and development model judgments are then closed. Refreezing after held-out results is refused.
Use a new study directory for a follow-up hypothesis.

The analysis reports numerator/denominator pairs for false approvals, false rejections, coverage,
abstention, operational failures, decided accuracy, unsupported approvals, unnecessary abstentions, and
definitive verdicts on unanswerable views. Human-answerability metrics remain unavailable for unaudited
views. Domain/family slices, confidence values, raw judgments, and a full truth × answerability × verdict
table are exported. Missing scheduled work is visible, not silently dropped.

The primary contrast is blanket minus pseudonym false approval, with coverage beside it. Bootstrap draws
resample **base requests**, keeping both interventions, four views, and repeats together. Zero-event
cells also show an upper bound based on independent base clusters; an all-zero paired contrast uses
conservative cluster bounds instead of a zero-width interval. There are 24 held-out bad base clusters,
not 48 independent bad tasks. These exploratory intervals cannot establish production risk or transfer
across organizations; family slices contain only four base requests each.

## Interruption and exact resume

Repeat the same generation/replay command to resume durable completed work. An `inflight.json` marker
closes the unsafe gap between a paid request and its checkpoint. If a process stops in that gap, the next
run refuses to buy the same judgment again automatically. Inspect local call logs and the global ledger:

```bash
uv run router-lab privacy resolve-interruption \
  --reviewer "Your name" --note "Describe the call-log and ledger inspection"
```

An uncertain judge call becomes a terminal operational failure with no semantic verdict. An interrupted
answer is marked for review; `privacy generate ... --retry-failed` explicitly permits another paid
attempt after resolution. Retained budget charges are never erased. Do not delete checkpoints or the
ledger to resume.

## Publish saved evidence to Phoenix

With the existing local Phoenix service running (see the original README setup):

```bash
uv run --env-file .env router-lab privacy publish --split dev --judge evidence
uv run --env-file .env router-lab privacy publish --split test --judge model
```

Publishing requires a complete scheduled split and makes **zero model calls**. It creates a separately
named dataset and saved-output experiment for each representation, retaining source episode/repetition
links, reference scope truth, audited answerability, and coverage/false-approval evaluations. Reference
labels are outside `input`; the model never reads Phoenix reference labels. Native experiment projects
separate the representations. Repeating publication resumes saved tasks rather than buying judgments.
Capture two or three explanatory screenshots manually; local URLs are not portable evidence. Export the
CSV/JSON/PNG artifacts with explicit model/code-baseline/template provenance for a presentation.
