#!/usr/bin/env python3
"""Prepare and report a diagnostic human review of frozen reuse endpoints.

Standard library only. This script never imports runtime/provider modules and
never writes to the source study. Initial reviewers should receive packet.md
and a copy of review-template.jsonl; keep the reference key separate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections import Counter
from datetime import datetime
from pathlib import Path

SEED = 1729
PAIRS = (
    ("test-issues-04", ("ordinary", "fused")),
    ("test-sources-02", ("ordinary", "fused")),
    ("test-calculations-02", ("ordinary", "fused")),
    ("test-comparisons-05", ("ordinary", "fused")),
    ("test-deployments-04", ("exact", "fused")),
    ("test-tests-04", ("exact", "fused")),
    ("test-linked-04", ("exact", "fused")),
    ("test-comparisons-02", ("exact", "fused")),
    ("test-issues-05", ("verified", "exact")),
    ("test-direct-00", ("exact", "fused")),
    ("test-deployments-03", ("exact", "fused")),
    ("test-tests-07", ("exact", "fused")),
)
OUTCOMES = {
    "completed",
    "appropriate clarification",
    "appropriate abstention",
    "incorrect",
    "incomplete",
    "uncertain",
}
SCOPES = {"appropriate", "excessive/wrong", "uncertain"}
YES_NO = {"yes", "no", "uncertain"}
RESOLVED = {"completed", "appropriate clarification"}
JUDGMENT_FIELDS = (
    "reviewer",
    "timestamp",
    "evidence_note",
    "outcome",
    "resource_scope",
    "unsupported_claims",
    "contradictions",
)
FAMILIES = {"issues", "sources", "calculations", "comparisons", "deployments", "tests", "linked", "direct"}


def digest(value: object) -> str:
    """Match the study's object digest without importing application code."""
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> object:
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def unique(rows: list[dict], field: str, label: str) -> dict[str, dict]:
    found = {}
    for row in rows:
        key = row[field]
        if key in found:
            raise ValueError(f"duplicate {label}: {key}")
        found[key] = row
    return found


def select_endpoints(study: Path) -> tuple[dict, list[dict], dict[str, dict]]:
    frozen = read_json(study / "frozen.json")
    configuration = digest(frozen["fingerprint"])
    for name, expected in frozen["fingerprint"]["files"].items():
        if file_hash(study / name) != expected:
            raise ValueError(f"frozen source hash mismatch: {name}")
    if "source_archive_hash" in frozen:
        if file_hash(study / "frozen-source.tar.gz") != frozen["source_archive_hash"]:
            raise ValueError("frozen source archive hash mismatch")
    inputs = unique(read_jsonl(study / "inputs.jsonl"), "id", "input")
    wanted = {(case, policy) for case, policies in PAIRS for policy in policies}
    selected = {}
    for row in read_jsonl(study / "runs.jsonl"):
        key = (row["case_id"], row["policy"])
        if (
            key in wanted
            and row["configuration"] == configuration
            and row["split"] == "test"
            and row["bank_state"] == "warm"
            and row["repetition"] == 0
        ):
            if key in selected:
                raise ValueError(f"duplicate selected endpoint: {key}")
            selected[key] = row
    missing = wanted - selected.keys()
    if missing:
        raise ValueError(f"missing selected endpoints: {sorted(missing)}")
    rows = [selected[(case, policy)] for case, policies in PAIRS for policy in policies]
    if len(rows) != 24 or {row["family"] for row in rows} != FAMILIES:
        raise ValueError("selection must contain 24 endpoints across all eight families")
    for row in rows:
        if inputs[row["case_id"]]["split"] != "test":
            raise ValueError("selected input is not held out")
        outcome = read_json(study / "outcomes" / f"{row['run_id']}.json")
        # Journal records add persistence/end-to-end timing after outcome save.
        for key in ("run_id", "status", "answer", "calls", "executions"):
            if outcome[key] != row["record"][key]:
                raise ValueError(f"saved outcome disagrees with journal: {row['run_id']}:{key}")
    random.Random(SEED).shuffle(rows)
    return frozen, rows, inputs


def new_output(output: Path, study: Path) -> None:
    if output.resolve().is_relative_to(study.resolve()):
        raise ValueError("output must be outside the frozen study directory")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory must be empty; preserve existing reviews: {output}")
    output.mkdir(parents=True, exist_ok=True)


def prepare(study: Path, output: Path) -> dict:
    frozen, selected, inputs = select_endpoints(study)
    new_output(output, study)
    packet, key, template = [], [], []
    for index, row in enumerate(selected, 1):
        audit_id = f"A{index:02d}"
        case = inputs[row["case_id"]]
        context = case["input"]["context"]
        packet.append(
            {
                "audit_id": audit_id,
                "request": case["input"]["request"],
                "permissions_and_context": context,
                "current_fixture_facts": case["state"].get(context["tenant"], {}),
                "captured_tool_evidence": row["record"]["executions"],
                "response_status": row["record"]["status"],
                "answer": row["record"]["answer"],
            }
        )
        key.append(
            {
                "audit_id": audit_id,
                "case_id": row["case_id"],
                "family": row["family"],
                "policy": row["policy"],
                "run_id": row["run_id"],
                "mechanical_evaluation": row["evaluation"],
            }
        )
        template.append({"audit_id": audit_id, **dict.fromkeys(JUDGMENT_FIELDS, "")})
    write_json(output / "packet.json", packet)
    write_json(output / "reference-key.json", key)
    (output / "review-template.jsonl").write_text(jsonl(template))
    intro = (
        "# Diagnostic human answer audit\n\n"
        "Status: **pending actual human judgments**. This sample is deliberately selected and diagnostic. "
        "Do not estimate general success rates from it. Policy names and mechanical grades are withheld "
        "from this packet. The separate reference key is for comparison after initial review.\n\n"
        "Read each request, permission context, fixture facts, captured tool evidence, status, and answer. "
        "In a copy of `review-template.jsonl`, supply your name, an ISO 8601 timestamp with timezone, "
        "an evidence-specific note (at least 20 characters), and all four judgments. Do not change IDs.\n\n"
        "- Outcome: completed; appropriate clarification; appropriate abstention; incorrect; incomplete; uncertain.\n"
        "- Resource scope: appropriate; excessive/wrong; uncertain.\n"
        "- Unsupported claims: yes; no; uncertain.\n"
        "- Contradictions: yes; no; uncertain.\n\n"
        "Completion means the request is resolved with support from the evidence. Appropriate clarification "
        "is a useful request for necessary missing context; appropriate abstention is a justified refusal "
        "or inability to answer and remains separate from successful resolution. Judge the response, "
        "including any unresolved operation, even if it notices a tool mistake.\n\n"
        "All facts below are synthetic current fixtures from saved measured endpoints. Tool evidence is "
        "captured execution evidence, not a new run. Empty tool evidence can be appropriate for direct "
        "answers or clarification. Initial review must be your own judgment; no agent has supplied a "
        "reviewer identity, note, or approval. Preserve initial judgments; record any later adjudication "
        "in a separate file.\n\n"
    )
    text = intro
    for item in packet:
        text += f"## {item['audit_id']}\n\n**Request:** {item['request']}\n\n"
        for label, field in (
            ("Permissions and context", "permissions_and_context"),
            ("Current fixture facts for the active tenant", "current_fixture_facts"),
            ("Captured tool evidence", "captured_tool_evidence"),
        ):
            text += (
                f"**{label}**\n\n```json\n{json.dumps(item[field], indent=2, ensure_ascii=False)}\n```\n\n"
            )
        text += f"**Response status:** {item['response_status']}\n\n**Answer:**\n\n"
        text += "\n".join("> " + line if line else ">" for line in item["answer"].splitlines()) + "\n\n"
    (output / "packet.md").write_text(text.rstrip() + "\n")
    source_names = {"frozen.json", "runs.jsonl", "inputs.jsonl", *frozen["fingerprint"]["files"]}
    if "source_archive_hash" in frozen:
        source_names.add("frozen-source.tar.gz")
    source_names.update(f"outcomes/{row['run_id']}.json" for row in selected)
    manifest = {
        "schema_version": 1,
        "sample_kind": "deliberately selected and diagnostic; no general success-rate estimate",
        "status": "pending actual human judgments",
        "seed": SEED,
        "configuration": digest(frozen["fingerprint"]),
        "split": "test",
        "bank_state": "warm",
        "repetition": 0,
        "endpoint_count": 24,
        "families": sorted(FAMILIES),
        "source_root": os.path.relpath(study.resolve(), output.resolve()),
        "source_hashes": {name: file_hash(study / name) for name in sorted(source_names)},
        "artifact_hashes": {
            name: file_hash(output / name)
            for name in ("packet.json", "packet.md", "review-template.jsonl", "reference-key.json")
        },
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def validate_provenance(manifest_path: Path, study: Path | None = None) -> tuple[dict, list[dict]]:
    manifest = read_json(manifest_path)
    folder = manifest_path.parent
    study = study or (folder / manifest["source_root"]).resolve()
    for name, expected in manifest["source_hashes"].items():
        if file_hash(study / name) != expected:
            raise ValueError(f"source hash mismatch: {name}")
    for name, expected in manifest["artifact_hashes"].items():
        if file_hash(folder / name) != expected:
            raise ValueError(f"packet artifact hash mismatch: {name}")
    frozen, selected, _ = select_endpoints(study)
    reference = read_json(folder / "reference-key.json")
    expected = [
        {
            "audit_id": f"A{index:02d}",
            "case_id": row["case_id"],
            "family": row["family"],
            "policy": row["policy"],
            "run_id": row["run_id"],
            "mechanical_evaluation": row["evaluation"],
        }
        for index, row in enumerate(selected, 1)
    ]
    if reference != expected:
        raise ValueError("reference key does not match the specified deterministic selection")
    expected_fields = {
        "configuration": digest(frozen["fingerprint"]),
        "endpoint_count": 24,
        "seed": SEED,
        "split": "test",
        "bank_state": "warm",
        "repetition": 0,
        "families": sorted(FAMILIES),
    }
    if any(manifest.get(field) != value for field, value in expected_fields.items()):
        raise ValueError("manifest selection metadata mismatch")
    return manifest, reference


def validate_judgment(row: dict, allow_incomplete: bool) -> bool:
    if set(row) != {"audit_id", *JUDGMENT_FIELDS}:
        raise ValueError(f"invalid review fields: {row.get('audit_id')}")
    if not all(isinstance(row[field], str) for field in JUDGMENT_FIELDS):
        raise ValueError(f"review judgments must be strings: {row['audit_id']}")
    for field, choices in (
        ("outcome", OUTCOMES),
        ("resource_scope", SCOPES),
        ("unsupported_claims", YES_NO),
        ("contradictions", YES_NO),
    ):
        if row[field] and row[field] not in choices:
            raise ValueError(f"invalid {field}: {row['audit_id']}")
    if row["timestamp"]:
        try:
            stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"invalid human timestamp: {row['audit_id']}") from error
        if stamp.tzinfo is None:
            raise ValueError(f"human timestamp needs a timezone: {row['audit_id']}")
    if row["evidence_note"] and len(row["evidence_note"].strip()) < 20:
        raise ValueError(f"evidence-specific note is too short: {row['audit_id']}")
    if any(not row[field].strip() for field in JUDGMENT_FIELDS):
        if allow_incomplete:
            return False
        raise ValueError(f"incomplete human review: {row['audit_id']}")
    return True


def report(
    manifest_path: Path,
    reviews_path: Path,
    output: Path,
    *,
    study: Path | None = None,
    allow_incomplete: bool = False,
) -> dict:
    manifest, reference = validate_provenance(manifest_path, study)
    reviews = unique(read_jsonl(reviews_path), "audit_id", "human review ID")
    expected = {row["audit_id"] for row in reference}
    if reviews.keys() != expected:
        raise ValueError(
            f"missing/unexpected review IDs: missing={sorted(expected - reviews.keys())}; "
            f"unexpected={sorted(reviews.keys() - expected)}"
        )
    complete = {key: row for key, row in reviews.items() if validate_judgment(row, allow_incomplete)}
    examples = []
    for item in reference:
        row = complete.get(item["audit_id"])
        if row is None:
            continue
        human_success = row["outcome"] in RESOLVED
        mechanical_success = item["mechanical_evaluation"]["success"]
        reasons = []
        if human_success != mechanical_success:
            reasons.append("disagreement with mechanical success")
        if row["resource_scope"] == "excessive/wrong":
            reasons.append("resource scope error")
        if row["unsupported_claims"] == "yes":
            reasons.append("unsupported claims")
        if row["contradictions"] == "yes":
            reasons.append("contradictions")
        if any(
            row[field] == "uncertain"
            for field in ("outcome", "resource_scope", "unsupported_claims", "contradictions")
        ):
            reasons.append("uncertainty")
        examples.append(
            {
                **item,
                "human_judgment": row,
                "human_successful_resolution": human_success,
                "diagnostic_flags": reasons,
            }
        )
    flags = Counter(reason for item in examples for reason in item["diagnostic_flags"])
    result = {
        "schema_version": 1,
        "sample_kind": manifest["sample_kind"],
        "status": "complete" if len(complete) == 24 else "pending actual human judgments",
        "completed_reviews": len(complete),
        "pending_reviews": 24 - len(complete),
        "outcome_counts": dict(sorted(Counter(row["outcome"] for row in complete.values()).items())),
        "successful_resolution_count": sum(row["outcome"] in RESOLVED for row in complete.values()),
        "appropriate_abstention_count": sum(
            row["outcome"] == "appropriate abstention" for row in complete.values()
        ),
        "mechanical_disagreements": flags["disagreement with mechanical success"],
        "scope_errors": flags["resource scope error"],
        "uncertainties": flags["uncertainty"],
        "unsupported_claims": flags["unsupported claims"],
        "contradictions": flags["contradictions"],
        "judgments_sha256": file_hash(reviews_path),
        "manifest_sha256": file_hash(manifest_path),
        "interpretation": (
            "Human judgments are separate from mechanical CODE scoring. Appropriate abstention remains "
            "separate from successful resolution. These diagnostic counts do not estimate general "
            "success rates. Disagreements qualify the submission interpretation; frozen measurements "
            "and original scores are unchanged. Preserve initial judgments and record adjudication separately."
        ),
        "individual_examples": examples,
    }
    source_study = study or (manifest_path.parent / manifest["source_root"]).resolve()
    new_output(output, source_study)
    write_json(output / "report.json", result)
    (output / "judgments.jsonl").write_bytes(reviews_path.read_bytes())
    text = (
        "# Diagnostic human answer audit report\n\n"
        f"Status: **{result['status']}**. Deliberately selected and diagnostic; no general success-rate estimate.\n\n"
        f"Completed: **{result['completed_reviews']}/24**. Pending: **{result['pending_reviews']}**.\n\n"
        f"Successful resolutions: {result['successful_resolution_count']}; appropriate abstentions: "
        f"{result['appropriate_abstention_count']} (separate). Disagreements with mechanical success: "
        f"{result['mechanical_disagreements']}; scope errors: {result['scope_errors']}; uncertain reviews: "
        f"{result['uncertainties']}; unsupported claims: {result['unsupported_claims']}; contradictions: "
        f"{result['contradictions']}.\n\n{result['interpretation']}\n\n"
        f"Outcome counts: `{json.dumps(result['outcome_counts'], sort_keys=True)}`\n\n"
        "## Individual examples\n\n"
    )
    for item in examples:
        row = item["human_judgment"]
        text += (
            f"- **{item['audit_id']}** ({item['case_id']}, {item['policy']}): human {row['outcome']}; "
            f"mechanical success {item['mechanical_evaluation']['success']}; scope {row['resource_scope']}. "
            f"Flags: {', '.join(item['diagnostic_flags']) or 'none'}. "
            f"Reviewer {row['reviewer']} at {row['timestamp']}: {row['evidence_note']}\n"
        )
    if not examples:
        text += "No human judgments have been completed. Blank templates are not human evidence.\n"
    (output / "report.md").write_text(text)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="create a blinded packet; never supply judgments")
    prep.add_argument("--study-dir", type=Path, default=Path("results/reuse"))
    prep.add_argument("--output", type=Path, default=Path("docs/reuse-answer-audit"))
    summary = commands.add_parser(
        "report", help="validate actual human judgments and summarize diagnostic counts"
    )
    summary.add_argument("--manifest", type=Path, default=Path("docs/reuse-answer-audit/manifest.json"))
    summary.add_argument("--reviews", type=Path, required=True)
    summary.add_argument("--output", type=Path, required=True)
    summary.add_argument("--study-dir", type=Path)
    summary.add_argument(
        "--allow-incomplete", action="store_true", help="report missing judgments as pending"
    )
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.study_dir, args.output)
            print(
                f"Prepared {result['endpoint_count']} blinded endpoints; human review pending: {args.output}"
            )
        else:
            result = report(
                args.manifest,
                args.reviews,
                args.output,
                study=args.study_dir,
                allow_incomplete=args.allow_incomplete,
            )
            print(f"Human review: {result['completed_reviews']}/24; {result['status']}: {args.output}")
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
