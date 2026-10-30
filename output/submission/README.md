# Submission verification

The submission centers on the measured reuse experiment. The candidate requested that
the diagnostic human audit remain **pending: 0 of 24 reviews completed** for this commit.

`verification.json` is the fresh offline verification receipt. It covers the 38-file
portable evidence bundle, protected original hashes, unchanged notebook code, links,
audit provenance, PDF structure, and isolated notebook execution. `project-checks.json`
records the full 135-test suite and Ruff checks. `cookbook-verification.json` describes
the current technical appendix. The older `output/cookbook/validation.json` remains
unchanged as a historical record and describes the earlier edition.

`preserved-sha256.json` records 1,185 protected files included in the submission.
`local-only-sha256.json` records another 117 local files (ignored privacy originals
and a run lock), which remain preserved locally and are excluded from the commit.
Together these cover all 1,302 files observed before submission edits.
`notebook-code-sha256.json` separately protects the 15 notebook code cells.
The application freeze fingerprint is checked against `results/reuse/frozen.json`;
measurements, original scores, reviews, journals, configurations and locks are preserved.

Rebuild and verify from the repository root in the separate cookbook authoring
environment described in the main README:

```sh
/tmp/trace-evidence-authoring/bin/python scripts/build_cookbook.py
/tmp/trace-evidence-authoring/bin/python scripts/build_submission.py
/tmp/trace-evidence-authoring/bin/python scripts/verify_submission.py --portable --render
```

`git-allowlist.txt` defines the paths selected for the local commit. Credentials,
the Phoenix database, caches, internal review reports and unrelated authoring files
are excluded. No paid run, publication, push, or recording is part of this package.

Visual review and the clean-checkout reproduction are recorded in the final receipt.

Ruff passes for application code, scripts, tests and the gallery verifier. The
whole-tree scan has eight existing findings in frozen notebook code cells; the
full format check has one existing difference in `src/router_lab/experiments.py`.
Both are preserved and recorded in `project-checks.json`. New authoring and audit
files pass formatting checks.
