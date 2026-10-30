"""Diagnostic audit tooling tests; all filled judgments here are test fixtures."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reuse_answer_audit.py"
SPEC = importlib.util.spec_from_file_location("reuse_answer_audit", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


@pytest.fixture
def study(tmp_path):
    """Build small saved records, including lookalike rows outside the selection."""
    root = tmp_path / "study"
    (root / "outcomes").mkdir(parents=True)
    inputs = []
    for case, _ in audit.PAIRS:
        inputs.append(
            {
                "id": case,
                "split": "test",
                "input": {"request": f"Request {case}", "context": {"tenant": "acme", "capabilities": []}},
                "state": {"acme": {"facts": "synthetic fixture"}},
            }
        )
    (root / "inputs.jsonl").write_text(audit.jsonl(inputs))
    frozen = {"fingerprint": {"files": {"inputs.jsonl": audit.file_hash(root / "inputs.jsonl")}}}
    audit.write_json(root / "frozen.json", frozen)
    configuration = audit.digest(frozen["fingerprint"])
    runs = []
    for case, policies in audit.PAIRS:
        for policy in policies:
            run_id = f"{case}-{policy}"
            record = {
                "run_id": run_id,
                "status": "completed",
                "answer": "Fixture answer",
                "calls": [],
                "executions": [],
            }
            runs.append(
                {
                    "run_id": run_id,
                    "case_id": case,
                    "family": case.split("-")[1],
                    "configuration": configuration,
                    "split": "test",
                    "bank_state": "warm",
                    "repetition": 0,
                    "policy": policy,
                    "record": record,
                    "evaluation": {"success": policy != "ordinary"},
                }
            )
            audit.write_json(root / "outcomes" / f"{run_id}.json", record)
    for overrides in ({"repetition": 1}, {"bank_state": "empty"}, {"split": "dev"}, {"configuration": "old"}):
        runs.append({**runs[0], **overrides})
    (root / "runs.jsonl").write_text(audit.jsonl(runs))
    return root


@pytest.fixture
def prepared(study, tmp_path):
    packet = tmp_path / "packet"
    audit.prepare(study, packet)
    return study, packet


def complete_reviews(packet, output):
    """Unit test identities/notes are never presented as a real human audit."""
    rows = audit.read_jsonl(packet / "review-template.jsonl")
    for row in rows:
        row.update(
            reviewer="Unit test reviewer",
            timestamp="2026-10-29T13:00:00+00:00",
            evidence_note="Test fixture evidence: the saved answer resolves the synthetic request.",
            outcome="completed",
            resource_scope="appropriate",
            unsupported_claims="no",
            contradictions="no",
        )
    output.write_text(audit.jsonl(rows))
    return rows


def test_exact_selection_and_blinding(prepared, tmp_path):
    study, packet = prepared
    _, rows, _ = audit.select_endpoints(study)
    expected = {(case, policy) for case, policies in audit.PAIRS for policy in policies}
    assert len(rows) == 24
    assert {(row["case_id"], row["policy"]) for row in rows} == expected
    assert {row["family"] for row in rows} == audit.FAMILIES
    assert all(
        row["repetition"] == 0 and row["split"] == "test" and row["bank_state"] == "warm" for row in rows
    )
    again = tmp_path / "second-packet"
    audit.prepare(study, again)
    for name in ("packet.json", "packet.md", "reference-key.json", "review-template.jsonl"):
        assert (packet / name).read_bytes() == (again / name).read_bytes()
    items = audit.read_json(packet / "packet.json")
    assert [item["audit_id"] for item in items] == [f"A{i:02d}" for i in range(1, 25)]
    assert all("policy" not in item and "mechanical_evaluation" not in item for item in items)
    assert all(
        not any(row[field] for field in audit.JUDGMENT_FIELDS)
        for row in audit.read_jsonl(packet / "review-template.jsonl")
    )
    manifest, _ = audit.validate_provenance(packet / "manifest.json")
    assert len(manifest["source_hashes"]) == 27


def test_real_frozen_selection_and_source_hashes():
    root = SCRIPT.parents[1] / "results" / "reuse"
    frozen, rows, _ = audit.select_endpoints(root)
    assert len(rows) == 24
    assert len({row["run_id"] for row in rows}) == 24
    assert {row["family"] for row in rows} == audit.FAMILIES
    assert {row["configuration"] for row in rows} == {audit.digest(frozen["fingerprint"])}
    assert {(row["case_id"], row["policy"]) for row in rows} == {
        (case, policy) for case, policies in audit.PAIRS for policy in policies
    }


@pytest.mark.parametrize("change", ["duplicate", "missing"])
def test_bad_endpoint_selection_is_rejected(study, tmp_path, change):
    rows = audit.read_jsonl(study / "runs.jsonl")
    if change == "duplicate":
        rows.append(rows[0])
    else:
        rows.pop(0)
    (study / "runs.jsonl").write_text(audit.jsonl(rows))
    with pytest.raises(ValueError, match=change):
        audit.prepare(study, tmp_path / "packet")


def test_frozen_input_hash_mismatch_is_rejected(study, tmp_path):
    with (study / "inputs.jsonl").open("a") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="frozen source hash mismatch"):
        audit.prepare(study, tmp_path / "packet")


def test_outcome_and_journal_must_agree(study, tmp_path):
    row = audit.read_jsonl(study / "runs.jsonl")[0]
    path = study / "outcomes" / f"{row['run_id']}.json"
    audit.write_json(path, {**row["record"], "answer": "Altered answer"})
    with pytest.raises(ValueError, match="saved outcome disagrees"):
        audit.prepare(study, tmp_path / "packet")


@pytest.mark.parametrize("change", ["duplicate", "missing", "unexpected"])
def test_bad_human_review_rows_are_rejected(prepared, tmp_path, change):
    _, packet = prepared
    reviews = tmp_path / "reviews.jsonl"
    rows = complete_reviews(packet, reviews)
    if change == "duplicate":
        rows.append(rows[0])
    elif change == "missing":
        rows.pop()
    else:
        rows[-1]["audit_id"] = "A99"
    reviews.write_text(audit.jsonl(rows))
    with pytest.raises(ValueError, match="duplicate|missing/unexpected"):
        audit.report(packet / "manifest.json", reviews, tmp_path / "report")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outcome", "passed"),
        ("resource_scope", "good"),
        ("unsupported_claims", "false"),
        ("contradictions", "none"),
        ("reviewer", ""),
        ("timestamp", "yesterday"),
        ("timestamp", "2026-10-29T13:00:00"),
        ("evidence_note", "Fine"),
    ],
)
def test_invalid_judgments_are_rejected(prepared, tmp_path, field, value):
    _, packet = prepared
    reviews = tmp_path / "reviews.jsonl"
    rows = complete_reviews(packet, reviews)
    rows[0][field] = value
    reviews.write_text(audit.jsonl(rows))
    with pytest.raises(ValueError):
        audit.report(packet / "manifest.json", reviews, tmp_path / "report")


def test_incomplete_reviews_are_pending_never_counted_as_human_evidence(prepared, tmp_path):
    _, packet = prepared
    reviews = packet / "review-template.jsonl"
    with pytest.raises(ValueError, match="incomplete human review"):
        audit.report(packet / "manifest.json", reviews, tmp_path / "rejected")
    result = audit.report(packet / "manifest.json", reviews, tmp_path / "pending", allow_incomplete=True)
    assert result["completed_reviews"] == 0
    assert result["pending_reviews"] == 24
    assert result["individual_examples"] == []
    assert result["status"] == "pending actual human judgments"


def test_source_hash_mismatch_after_preparation_is_rejected(prepared, tmp_path):
    study, packet = prepared
    with (study / "runs.jsonl").open("a") as handle:
        handle.write("\n")
    reviews = tmp_path / "reviews.jsonl"
    complete_reviews(packet, reviews)
    with pytest.raises(ValueError, match="source hash mismatch"):
        audit.report(packet / "manifest.json", reviews, tmp_path / "report")


def test_packet_hash_mismatch_is_rejected(prepared, tmp_path):
    _, packet = prepared
    with (packet / "packet.md").open("a") as handle:
        handle.write("changed")
    reviews = tmp_path / "reviews.jsonl"
    complete_reviews(packet, reviews)
    with pytest.raises(ValueError, match="packet artifact hash mismatch"):
        audit.report(packet / "manifest.json", reviews, tmp_path / "report")


def test_disagreements_scope_uncertainty_and_abstention_stay_separate(prepared, tmp_path):
    study, packet = prepared
    before = {str(path): audit.file_hash(path) for path in study.rglob("*") if path.is_file()}
    reviews = tmp_path / "reviews.jsonl"
    rows = complete_reviews(packet, reviews)
    key = audit.read_json(packet / "reference-key.json")
    ordinary = next(row["audit_id"] for row in key if row["policy"] == "ordinary")
    success = next(row["audit_id"] for row in key if row["policy"] != "ordinary")
    for row in rows:
        if row["audit_id"] == ordinary:
            row["resource_scope"] = "excessive/wrong"
            row["unsupported_claims"] = "yes"
            row["contradictions"] = "uncertain"
        if row["audit_id"] == success:
            row["outcome"] = "appropriate abstention"
    reviews.write_text(audit.jsonl(rows))
    result = audit.report(packet / "manifest.json", reviews, tmp_path / "report")
    assert result["completed_reviews"] == 24
    assert result["successful_resolution_count"] == 23
    assert result["appropriate_abstention_count"] == 1
    assert result["mechanical_disagreements"] == 5  # Four ordinary paths plus one abstention.
    assert result["scope_errors"] == result["uncertainties"] == result["unsupported_claims"] == 1
    assert len(result["individual_examples"]) == 24
    assert (tmp_path / "report" / "judgments.jsonl").read_bytes() == reviews.read_bytes()
    assert before == {str(path): audit.file_hash(path) for path in study.rglob("*") if path.is_file()}


def test_preserve_existing_reviews_and_frozen_source_directory(study, tmp_path):
    with pytest.raises(ValueError, match="outside the frozen"):
        audit.prepare(study, study / "audit")
    output = tmp_path / "packet"
    output.mkdir()
    (output / "existing-human-notes.txt").write_text("Preserve me")
    with pytest.raises(ValueError, match="preserve existing reviews"):
        audit.prepare(study, output)
    assert (output / "existing-human-notes.txt").read_text() == "Preserve me"
