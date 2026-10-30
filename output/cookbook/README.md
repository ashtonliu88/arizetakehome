# Measured workflow reuse: technical appendix

The authoring source is [the notebook](../../notebooks/trace-evidence-lab.ipynb). Its
narrative and local analysis generate [Markdown](../../docs/cookbook.md), the editable
Typst edition and the full cookbook PDF. The current cookbook contains **19 pages and
six figures**. It is the technical appendix to the [short submission](../../docs/submission.md)
and [overview PDF](../pdf/arize-submission-overview.pdf). Original study sources,
configurations, measurements, journals and dependency locks are preserved.

From the repository root, rebuild both PDFs in the separate authoring environment:

```sh
/tmp/trace-evidence-authoring/bin/python scripts/build_cookbook.py
/tmp/trace-evidence-authoring/bin/python scripts/build_submission.py
/tmp/trace-evidence-authoring/bin/python scripts/verify_submission.py --portable --render
```

Environment setup is in the cookbook and `notebooks/requirements-cookbook.txt`.
Default execution needs no credentials, application source, Phoenix or external
connection. The builder rejects paid/publication opt-in flags. The 38-file evidence
snapshot is verified, never refreshed by these commands.

To compile a manually edited Typst edition using its repository-relative figures:

```sh
typst compile --root . output/cookbook/trace-evidence-lab.typ \
  output/cookbook/trace-evidence-lab.pdf
```

The next full build overwrites generated editions, so make lasting narrative changes
in the notebook. The Typst template is `docs/cookbook-template.typ`.

`analysis/metrics.json` contains recomputed results; PNG/SVG files contain the six
figures. Historical `validation.json` remains preserved. Fresh integrity, portability,
link, audit and PDF checks write the separate [submission receipt](../submission/verification.json).
Temporary page renders live under `tmp/pdfs/`. The 24-endpoint human answer audit
remains pending by the candidate's choice; mechanical findings do not certify answer quality.
