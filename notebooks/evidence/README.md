# Portable cookbook evidence

This bundle supports every default analysis cell in `../trace-evidence-lab.ipynb`.
It contains 38 byte-for-byte copies of saved artifacts (about 8.5 MB), including
the otherwise ignored privacy observations. All resource identifiers are synthetic.
Real model responses, usage and timings are saved measurements over local fixtures;
the routing rows are explicitly synthetic test fixtures.

`manifest.json` records source paths, byte counts and SHA-256 hashes. The notebook
checks every hash, the frozen reuse archive, configuration identity, paired matrix,
mechanical reference scores, privacy schedules and input hashes. Saved summaries
are cross-checks: the headline metrics are recomputed from row-level observations.
The bundle deliberately includes local raw controls and scoring oracles. It is not
a sanitized Phoenix export, and it contains no credentials or `.env` files.

- `routing/`: 120 authored benchmark requests plus the synthetic 72-row example.
- `reuse/`: all saved configurations, journals, references, inputs, frozen bank,
  calibration, reviews, summary and frozen source archive. Final comparisons select
  only the frozen configuration and held-out split. Reserved and measured journal
  entries share an identity; the final settlement is counted once.
- `privacy/`: 72 canonical episodes and four views; 192 development judgments per
  judge (model, exact code and evidence code), schedules and summaries; unapproved
  review suggestions and transformation controls. Code-baseline journals also retain
  earlier contexts, excluded by the current schedule. Held-out model judgments are absent.
- `protocol/`: saved model/pricing settings, describing the historical run.

Copy the notebook and this folder together and execute the notebook in the separate
environment described in `../requirements-cookbook.txt`. Set `COOKBOOK_EVIDENCE` to
override the snapshot location and `COOKBOOK_OUTPUT` to override analysis outputs.
No application import, original results directory or Phoenix server is needed.

This is a fixed, hash-checked snapshot of the saved study. No snapshot-refresh helper
is included; normal notebook execution reads these files without refreshing them.
