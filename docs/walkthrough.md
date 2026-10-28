# Panel walkthrough and capture checklist

Target 6–8 minutes. Use only saved **live** results for the research conclusion.

1. State the question: can confidence find recoverable mistakes, beyond buying more inference? Acknowledge Arize's preceding experiment.
2. Show the fixed catalog, one next-action example, evaluator-only rationale, 40/80 split and frozen manifest. Explain the balanced-workload limitation.
3. Open the Phoenix dataset and compare named policy/split/repetition experiments. Show automated exact-route grades and a human development annotation.
4. Show the accuracy/cost figure, paired question-level uncertainty, latency and matched-rate random replay control. Report a negative result plainly if the hybrid fails to save cost at LLM accuracy.
5. Open one wrong initial decision and, if present, an actual rescue. Contrast initial provider-span grade with final policy-span grade. Show one both-wrong case to explain uncertainty without recoverability. Never construct a rescue for the presentation.
6. Open a demo AGENT trace: route, typed argument extraction, local tool evidence and final answer. Show argument/answer checks and semantic second opinions separately from route accuracy.
7. Close with three observations supported by actual results and the drift follow-up.

Before sharing:

- Review all 120 labels and inspect ambiguous development traces. Keep signed local review hashes and Phoenix human annotations.
- Ensure live smoke, persistence, dataset splits, both automatic span kinds and correct annotation placement pass.
- Run dev only, select gate, freeze, then run test. Preserve raw results and cost ledger.
- Review all 24 demo answers, including unsupported claims and tool failures.
- Capture the experiment comparison, initial/final decision trace and demo trace as PNG files in `docs/evidence/`.
- Make a short screen recording of the same walkthrough; export a portable video and verify playback. A local URL is not submission evidence.
- Copy observed metrics and uncertainty from `results/analysis/summary.json` into the README's status/result discussion; replace pending status only after reviewing evidence.
- Verify no `.env`, credential, `.phoenix` database or private report content is accidentally published. Share the repository only when requested.

The current synthetic figures demonstrate artifact rendering only. Live screenshots and the research walkthrough recording remain pending model access and human review.
