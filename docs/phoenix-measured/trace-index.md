# Saved measured trace index

> **Phoenix traces reconstruct saved measured executions. Publication is outside endpoint latency. Existing grades are mechanical CODE evaluations.**

All six endpoints use the final frozen configuration, held-out split, warm bank, repetition 1. Live links require the existing local Phoenix project. The linked raw files and [sidecar](selected-records.json) are the portable evidence.

| Case | Policy | Saved run | LLM calls | Mechanical success |
|---|---|---|---:|---|
| `test-calculations-02` | ordinary | [83242cc6e90cc893d8ee33f5](../../results/reuse/outcomes/83242cc6e90cc893d8ee33f5.json) | 1 | False |
| `test-calculations-02` | verified | [6746aed7c4ba5a7f7013cdd1](../../results/reuse/outcomes/6746aed7c4ba5a7f7013cdd1.json) | 2 | True |
| `test-calculations-02` | exact | [5086d1ba278592ebf29faadb](../../results/reuse/outcomes/5086d1ba278592ebf29faadb.json) | 2 | True |
| `test-calculations-02` | fused | [1769fbe65c69d12890199adc](../../results/reuse/outcomes/1769fbe65c69d12890199adc.json) | 2 | True |
| `test-issues-00` | exact | [739adfc3b1192b1ced846a2f](../../results/reuse/outcomes/739adfc3b1192b1ced846a2f.json) | 1 | True |
| `test-issues-00` | fused | [8af6c5419626dfdbcfbf60db](../../results/reuse/outcomes/8af6c5419626dfdbcfbf60db.json) | 2 | True |

## Trace identifiers and saved diagnostics

Retrieval diagnostics below are **saved-record-only**. They are not fields displayed in the screenshots. End-to-end timing is the finalized saved endpoint measurement, not publication time or UI-rounded latency.

### ordinary: test-calculations-02

- Saved run: `83242cc6e90cc893d8ee33f5`; [measurement JSON](../../results/reuse/outcomes/83242cc6e90cc893d8ee33f5.json).
- [Open existing Phoenix root](http://localhost:6006/projects/UHJvamVjdDoyMQ==/spans/7b41ec5869c99d894ac728d28904a985?selectedSpanNodeId=U3BhbjozMTk2); trace `7b41ec5869c99d894ac728d28904a985`, root span `07c81e3022138880`.
- Span sequence: `ordinary / warm` (`07c81e3022138880`), `calculate` (`ff7ff61678ea2af7`), `answer` (`8a16199ec4a6448d`).
- Saved diagnostics: cache hit `True`, candidate `ea1c859e996822c18e76`, retrieval score `0.4840876523177682`, margin `0.276761819330045`, rejection `None`.
- Finalized endpoint: 2034.599 ms, cost $0.00066200, 1 recorded model calls.

### verified: test-calculations-02

- Saved run: `6746aed7c4ba5a7f7013cdd1`; [measurement JSON](../../results/reuse/outcomes/6746aed7c4ba5a7f7013cdd1.json).
- [Open existing Phoenix root](http://localhost:6006/projects/UHJvamVjdDoyMQ==/spans/7d2b6e925c3d03952b2d6d7c65765a2f?selectedSpanNodeId=U3BhbjozMjIw); trace `7d2b6e925c3d03952b2d6d7c65765a2f`, root span `574bb94b6008c8e9`.
- Span sequence: `verified / warm` (`574bb94b6008c8e9`), `planning` (`d720a140cca7055e`), `calculate` (`503b22cec383b3aa`), `answer` (`7f8e3f55938907a2`).
- Saved diagnostics: cache hit `False`, candidate `ea1c859e996822c18e76`, retrieval score `0.4840876523177682`, margin `0.276761819330045`, rejection `semantic_signature`.
- Finalized endpoint: 3222.779 ms, cost $0.00136340, 2 recorded model calls.

### exact: test-calculations-02

- Saved run: `5086d1ba278592ebf29faadb`; [measurement JSON](../../results/reuse/outcomes/5086d1ba278592ebf29faadb.json).
- [Open existing Phoenix root](http://localhost:6006/projects/UHJvamVjdDoyMQ==/spans/11a4037b76464868f7132292de473a98?selectedSpanNodeId=U3BhbjozMTkz); trace `11a4037b76464868f7132292de473a98`, root span `5ec2123bffa9bdd5`.
- Span sequence: `exact / warm` (`5ec2123bffa9bdd5`), `planning` (`3410506d38d60783`), `calculate` (`b0de816c6fac9793`), `answer` (`139a188dabaad969`).
- Saved diagnostics: cache hit `False`, candidate `None`, retrieval score `0.0`, margin `0.0`, rejection `no_candidate`.
- Finalized endpoint: 3291.782 ms, cost $0.00136340, 2 recorded model calls.

### fused: test-calculations-02

- Saved run: `1769fbe65c69d12890199adc`; [measurement JSON](../../results/reuse/outcomes/1769fbe65c69d12890199adc.json).
- [Open existing Phoenix root](http://localhost:6006/projects/UHJvamVjdDoyMQ==/spans/f3996c5633d602e9d026bf18a7f73399?selectedSpanNodeId=U3BhbjozMjE2); trace `f3996c5633d602e9d026bf18a7f73399`, root span `305884c7ceea6f9a`.
- Span sequence: `fused / warm` (`305884c7ceea6f9a`), `planning` (`b66a6d05c9512900`), `calculate` (`2e427e7d5302d81a`), `answer` (`8c765f8baa20234b`).
- Saved diagnostics: cache hit `False`, candidate `None`, retrieval score `0`, margin `0`, rejection `None`.
- Finalized endpoint: 3437.113 ms, cost $0.00137340, 2 recorded model calls.

### exact: test-issues-00

- Saved run: `739adfc3b1192b1ced846a2f`; [measurement JSON](../../results/reuse/outcomes/739adfc3b1192b1ced846a2f.json).
- [Open existing Phoenix root](http://localhost:6006/projects/UHJvamVjdDoyMQ==/spans/884b62871869777a45389e01777e1dac?selectedSpanNodeId=U3BhbjoxODAx); trace `884b62871869777a45389e01777e1dac`, root span `e03d3fc803fd5741`.
- Span sequence: `exact / warm` (`e03d3fc803fd5741`), `lookup_issue` (`c78f5dd3d9a2a5b7`), `answer` (`bc2dfb54f1734728`).
- Saved diagnostics: cache hit `True`, candidate `f8242edb8a292b282604`, retrieval score `1.0`, margin `1.0`, rejection `None`.
- Finalized endpoint: 1725.289 ms, cost $0.00071000, 1 recorded model calls.

### fused: test-issues-00

- Saved run: `8af6c5419626dfdbcfbf60db`; [measurement JSON](../../results/reuse/outcomes/8af6c5419626dfdbcfbf60db.json).
- [Open existing Phoenix root](http://localhost:6006/projects/UHJvamVjdDoyMQ==/spans/c205131c82cddcbd60f4c88438b80f67?selectedSpanNodeId=U3BhbjoxODA4); trace `c205131c82cddcbd60f4c88438b80f67`, root span `dbba38531abed6a4`.
- Span sequence: `fused / warm` (`dbba38531abed6a4`), `planning` (`9ddff6ac6b8b54f6`), `lookup_issue` (`73773c3b7ba7afe5`), `answer` (`5b3bc7c85aea737a`).
- Saved diagnostics: cache hit `False`, candidate `None`, retrieval score `0`, margin `0`, rejection `None`.
- Finalized endpoint: 3065.691 ms, cost $0.00148910, 2 recorded model calls.

The ordinary subtraction run is mechanically unsuccessful and unresolved. Its response identifies the wrong addition operation instead of completing the subtraction. The verified comparator rejects the candidate with `semantic_signature` and freshly plans a correct subtraction. The exact subtraction comparator has a `no_candidate` miss and also freshly plans; it does not demonstrate a successful cached subtraction. Fused subtraction provides the independent fresh-planning comparator.

For the positive issue pair, exact reuses a plan while executing the current issue lookup; fused plans and executes the same lookup. Both have mechanically successful responses. No human grading is claimed.

## Integrity and portability

The [sidecar](selected-records.json) contains six original `runs.jsonl` rows, six original outcome files, two case inputs with fixture states, existing Phoenix span/annotation records, screenshot capture geometry, and hashes for twelve source files and four screenshots. The measurement record includes persistence/end-to-end timing finalized after outcome-file persistence; the original outcome files retain nulls for those two values. Both forms remain preserved.

Run `python3 docs/phoenix-measured/verify.py` from the repository root. It checks source and image hashes, selected rows, original outcomes, request/answer agreement, CODE success, tool inputs/results, the arithmetic operations, and the one-versus-two issue model-call comparison. It needs only the standard library and does not access Phoenix or provider clients.
