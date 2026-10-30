# Privacy continuation checklist (historical operational record)

**Submission status, October 29, 2026:** this extension is separate from the completed [reuse experiment](submission.md). All 72 canonical answers and 192 development model judgments are already captured. The generation stage below is historical; it is not a request to repeat paid work. Human audits and held-out judge comparisons remain pending. No paid continuation is authorized by submission packaging. Original protocol and hypotheses are retained below; see [current status](status.md).

# Commands after the completed development run

The development results are internally consistent: 192 valid model judgments; 24 PASS and 24 FAIL
in each of raw, pseudonym, and relation views; 48 abstentions under blanket masking. Both deterministic
baselines produce the same verdicts on these direct-lookup development cases. The saved view hashes
match the current episode evidence. No source or prompt changes are needed to reproduce those counts.

This is a deliberately constrained diagnostic. The judge receives normalized requested resources and
explicit identity semantics. The rubric explains that collapsed keys do not establish identity and
instructs abstention when necessary distinctions are missing. The code baselines abstain immediately
on collapsed identity. Consequently the clean development pattern is largely expected. It establishes
contract following and a coverage loss in this synthetic setting; it has not established an LLM benefit
over deterministic verification, a production false-approval effect, or a privacy guarantee. Twelve base
requests, not 192 independent tasks, underlie the development comparison. Human audits are still required.

Run each numbered stage in order. Stage 4 includes actual human review; do not run the later stages
until that review is complete. The commands below retain the existing experiment configuration. Editing
source, prompts, settings, the endpoint, or dependencies can invalidate the saved paid results.

## 1. Enter the project and inspect progress

```bash
cd /Users/liuschool/Documents/arizetakehom
uv run --env-file .env router-lab privacy status
```

Use the same `.env` and endpoint settings for generation, replay, analysis, status, and freeze.

## 2. Analyze the completed development comparisons

These commands make no model calls:

```bash
uv run --env-file .env router-lab privacy analyze --split dev --judge model
uv run --env-file .env router-lab privacy analyze --split dev --judge evidence
uv run --env-file .env router-lab privacy analyze --split dev --judge exact
open results/privacy/analysis
```

Compare `dev-model`, `dev-evidence`, and `dev-exact`. Each contains `summary.json`, `summary.csv`,
`judgments.csv`, `contingency.csv`, `slices.csv`, and `coverage-error.png`. The model and code baselines
agree on the development verdicts; the next families test aliases, permitted sets, links, and bindings.

## 3. Generate the remaining canonical answers

This is a paid generation step, with no held-out judge calls. There are 48 remaining canonical answers:

```bash
uv run --env-file .env router-lab privacy generate --split test
uv run --env-file .env router-lab privacy prepare
uv run --env-file .env router-lab privacy status
```

Expect 72 total model answers. `prepare` refreshes the view exports and the unapproved scratch review
queue; it does not overwrite the actual `reviews.jsonl` audit records. Canonical held-out evidence is
available for label review before freeze; held-out evaluator outputs remain blocked until freeze.

## 4. Export and review all 72 episodes

Create a local JSON audit packet per episode. This step makes no model calls and does not approve anything:

```bash
uv run --env-file .env python - <<'PY'
from pathlib import Path
from router_lab.privacy.contracts import REPRESENTATIONS
from router_lab.privacy.study import load_episodes
from router_lab.privacy.views import make_view
from router_lab.util import digest, write_json

directory = Path("results/privacy")
episodes = load_episodes(directory)
for episode in episodes:
    write_json(directory / "audit" / f"{episode.episode_id}.json", {
        "episode_hash": digest(episode.model_dump()),
        "canonical": episode.model_dump(mode="json"),
        "judge_inputs": {r: make_view(episode, r) for r in REPRESENTATIONS},
    })
print(f"Wrote {len(episodes)} audit packets to {directory / 'audit'}")
PY
open results/privacy/audit
```

For each packet, check the permitted scope, actual invocation, returned-record binding, fixture scope
label, transformed references, and what each view can establish. `INSUFFICIENT_EVIDENCE` chosen by a model
does not itself prove that a view is unanswerable. The independent human answerability audit must examine
the evidence. Generated prose can retain semantic clues after identifier masking. The primary rubric
ignores final prose when judging access scope; apply that same admitted-evidence contract in your audit.

Choose either review method below.

### File-based review

The current run has zero human reviews. Copy the fresh unapproved queue **once** and edit the working copy:

```bash
cp -n results/privacy/review-queue.jsonl results/privacy/reviews.jsonl
open -a TextEdit results/privacy/reviews.jsonl
```

Manually inspect each episode and edit its row. Supply your actual `reviewer`, a substantive `note`,
the four `answerable` boolean values, and `approved: true` only when the canonical scope label and all
views pass your audit. Keep the current episode ID/hash. The queue's suggested answerability values
are starting points, not established labels. Do not use a script to set every row approved. Editing
`proposed_scope_pass` in a review does not change the canonical oracle; a mistaken oracle requires a
separate corpus correction and revalidation. Record rejected or ambiguous cases as unapproved.

### Per-episode CLI review

Alternatively, replace the ID and note with an episode you actually audited, then repeat for each episode:

```bash
uv run --env-file .env router-lab privacy inspect --episode "PASTE_EPISODE_ID"
uv run --env-file .env router-lab privacy review \
  --episode "PASTE_EPISODE_ID" \
  --reviewer "Your name" \
  --note "Your episode-specific scope, binding, transformation, and answerability findings" \
  --answerable "raw,pseudonym,relation" \
  --approve
```

Set `--answerable` to the representations your actual review supports. The example list is not mandatory.
This command records approval of the existing canonical scope label; do not approve if that label is wrong.

Validate completeness after finishing either method:

```bash
uv run --env-file .env python - <<'PY'
from pathlib import Path
from router_lab.privacy.study import audited_reviews, load_episodes

directory = Path("results/privacy")
episodes = load_episodes(directory)
reviews = audited_reviews(directory, episodes, required=True)
print(f"{len(reviews)}/{len(episodes)} current approved human audits")
PY
uv run --env-file .env router-lab privacy status
```

Expect `72/72` current approved audits. This validation checks completeness and hash binding; it cannot
establish that a human review was thoughtful or correct.

## 5. Freeze the study

```bash
uv run --env-file .env router-lab privacy freeze
```

Freeze requires all 72 current model answers, all current human audits, and all 192 current development
model judgments. After freezing, keep the source, settings, endpoint, reviews, and development results
fixed. Do not retune this study after observing held-out judgments.

## 6. Run all held-out comparisons

The model command schedules 384 judgments before retries. The two code baselines make no model calls:

```bash
uv run --env-file .env router-lab privacy replay --split test --judge model --frozen
uv run --env-file .env router-lab privacy replay --split test --judge evidence --frozen
uv run --env-file .env router-lab privacy replay --split test --judge exact --frozen
```

Repeat a command to resume completed work. Preserve terminal operational failures as observations.
If an unfinished paid-call marker appears, use the interruption-review procedure in `privacy-study.md`;
do not delete the marker or budget ledger to force a retry.

## 7. Analyze all held-out results

```bash
uv run --env-file .env router-lab privacy analyze --split test --judge model
uv run --env-file .env router-lab privacy analyze --split test --judge evidence
uv run --env-file .env router-lab privacy analyze --split test --judge exact
uv run --env-file .env router-lab privacy status
open results/privacy/analysis
```

Inspect aliases, deployment sets, issue-to-test-run links, and wrong returned bindings separately in
`slices.csv`. Use `judgments.csv` and `contingency.csv` to audit disagreements. Examine coverage beside
false approvals, and use human answerability metrics only after audits exist. A degenerate bootstrap
interval reflects uniform observed clusters, not certainty on future workloads. If the deterministic
checker matches the model, report the contribution as a practical evidence/verification contract.

## 8. Publish saved results to Phoenix

If Phoenix is not already running, start it in a separate terminal and leave that terminal open:

```bash
cd /Users/liuschool/Documents/arizetakehom
PHOENIX_WORKING_DIR="$PWD/.phoenix" uv run --env-file .env phoenix serve
```

In your research terminal, publish all saved comparisons. These commands make zero model calls:

```bash
uv run --env-file .env router-lab privacy publish --split dev --judge model
uv run --env-file .env router-lab privacy publish --split dev --judge evidence
uv run --env-file .env router-lab privacy publish --split dev --judge exact
uv run --env-file .env router-lab privacy publish --split test --judge model
uv run --env-file .env router-lab privacy publish --split test --judge evidence
uv run --env-file .env router-lab privacy publish --split test --judge exact
open http://localhost:6006
```

Each publication creates a representation-specific dataset/experiment with exact saved inputs and
outputs. Reference labels remain outside model input. Capture screenshots from representative correct,
incorrect, insufficient-evidence, and disagreement cases that actually occurred. Do not invent an
incorrect judgment if the model made none. Export the JSON/CSV/PNG artifacts with the project.
