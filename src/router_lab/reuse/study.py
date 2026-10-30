from __future__ import annotations

import json
import random
import tarfile
import time
from pathlib import Path

from ..budget import Budget, run_lock
from ..util import append_jsonl, digest, now, read_jsonl, write_json
from .bank import admit_history
from .contracts import ExecutionRecord, PlanTemplate, RequestInput, ReuseSettings
from .dataset import FAMILIES, FAMILY_CONTRACTS, build_dataset
from .provider import LiveModel, committed_cost
from .runtime import execute_request
from .scoring import score
from .service import contracts, resource_key, tool_service


def source_hash():
    return digest({str(p): digest(p) for p in sorted(Path("src/router_lab").rglob("*.py"))})


def load_config(root):
    return ReuseSettings.model_validate_json((root / "settings.json").read_text())


def load_bank(root):
    return (
        [PlanTemplate.model_validate(p) for p in json.loads((root / "bank.json").read_text())]
        if (root / "bank.json").exists()
        else []
    )


def fingerprint(root, settings):
    names = [
        "inputs.jsonl",
        "references-history.jsonl",
        "references-dev.jsonl",
        "references-test.jsonl",
        "family-contracts.json",
        "settings.json",
        "bank.json",
        "reviews.jsonl",
    ]
    return {
        "files": {name: digest(root / name) for name in names if (root / name).exists()},
        "source": source_hash(),
        "model_settings": settings.model_dump(),
        "tool_contracts": contracts(),
        "provider_endpoint": __import__("os").getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "pricing_assumptions": settings.pricing_note,
    }


def prepare(root):
    if (root / "inputs.jsonl").exists():
        raise ValueError("prepared study exists; use a fresh results directory to change data")
    archive = root / "archive" / now().replace(":", "").replace("+", "_")
    archive.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive / "source-config.tar.gz", "w:gz") as out:
        for name in ("src", "config", "pyproject.toml", "uv.lock"):
            out.add(name, filter=lambda entry: None if "__pycache__" in entry.name else entry)
    write_json(root / "settings.json", ReuseSettings().model_dump())
    write_json(root / "family-contracts.json", FAMILY_CONTRACTS)
    write_json(root / "bank.json", [])
    for case in build_dataset():
        append_jsonl(root / "inputs.jsonl", {k: v for k, v in case.items() if k != "reference"})
        append_jsonl(root / f"references-{case['split']}.jsonl", {"id": case["id"], **case["reference"]})
    text = "# Family contracts for review\n\nReview these eight rules before paid construction or execution. "
    text += "All generated substitutions are derived references, not individually human approved.\n\n"
    for family, contract in FAMILY_CONTRACTS.items():
        text += f"## {family}\n\n{contract['rule']}\n\n- Positive: {contract['positive']}\n- Adverse: {contract['adverse']}\n\n"
    text += "Record each approval with `router-lab reuse review-family --family NAME --reviewer NAME --approve --note TEXT`.\n"
    (root / "family-review.md").write_text(text)
    write_json(
        root / "prepared.json",
        {
            "timestamp": now(),
            "source_hash": source_hash(),
            "counts": {"history": 16, "dev": 24, "test": 64},
            "archive": str(archive),
        },
    )
    return {
        "prepared": str(root),
        "review": str(root / "family-review.md"),
        "history": 16,
        "dev": 24,
        "test": 64,
    }


def review_family(root, family, reviewer, note, approved):
    if (root / "frozen.json").exists():
        raise ValueError("reviews are frozen")
    contracts_file = json.loads((root / "family-contracts.json").read_text())
    record = {
        "family": family,
        "reviewer": reviewer,
        "note": note,
        "approved": approved,
        "contract_hash": digest(contracts_file[family]),
        "timestamp": now(),
    }
    append_jsonl(root / "reviews.jsonl", record)
    return record


def require_reviews(root):
    latest = {r["family"]: r for r in read_jsonl(root / "reviews.jsonl")}
    contracts_file = json.loads((root / "family-contracts.json").read_text())
    missing = [
        f
        for f in FAMILIES
        if not latest.get(f, {}).get("approved") or latest[f]["contract_hash"] != digest(contracts_file[f])
    ]
    if missing:
        raise ValueError(
            "family review required: " + ", ".join(missing) + f"; see {root / 'family-review.md'}"
        )


def conditions(case, subset):
    output = [(p, "warm") for p in ("fused", "exact", "ordinary", "verified")]
    if subset and int(case["id"].rsplit("-", 1)[1]) >= 2:
        output.remove(("ordinary", "warm"))
    return output + [("fused", "empty"), ("verified", "empty")]


def config_hash(root, settings):
    return digest(fingerprint(root, settings))


def history_hash(root, settings):
    value = fingerprint(root, settings)
    value["files"].pop("bank.json", None)
    return digest(value)


def verify_freeze(root, settings):
    frozen = json.loads((root / "frozen.json").read_text())
    if frozen["fingerprint"] != fingerprint(root, settings):
        raise ValueError("frozen study inputs, source, model, endpoint, pricing, reviews or bank changed")
    if frozen["calibration_hash"] != digest(root / "calibration.json"):
        raise ValueError("frozen calibration changed")
    if frozen["source_archive_hash"] != digest(root / "frozen-source.tar.gz"):
        raise ValueError("frozen source archive changed")
    development = [r for r in read_jsonl(root / "runs.jsonl") if r["split"] != "test"]
    if frozen["development_hash"] != digest(development):
        raise ValueError("frozen history/development results changed")
    return frozen


def assert_no_pending(root):
    journal = {r["run_id"]: r for r in read_jsonl(root / "endpoints.jsonl")}
    pending = [key for key, row in journal.items() if row["state"] == "started"]
    if pending:
        raise ValueError(
            "interrupted endpoint(s) require manual reconciliation; never automatically replay: "
            + ", ".join(pending)
        )


def evaluate(record, reference, inp):
    result = score(record, reference)
    result["authorization_violations"] = sum(
        e["tool"] not in inp.context.capabilities
        or e["tenant"] != inp.context.tenant
        or (bool(inp.context.grants) and resource_key(e["tool"], e["arguments"]) not in inp.context.grants)
        for e in record.executions
    )
    result["wrong_returned_bindings"] = record.error in (
        "wrong returned binding",
        "missing returned bindings",
        "returned tenant/state mismatch",
    )
    return result


def execute_endpoint(root, case, reference, policy, state, repetition, settings, reuse_settings, model, bank):
    # Include configuration identity: a resumed process may not silently mix configurations.
    configuration = (
        history_hash(root, settings) if case["split"] == "history" else config_hash(root, settings)
    )
    identity = f"{case['id']}:{policy}:{state}:{repetition}:{configuration[:16]}"
    run_id = digest([identity, configuration])[:24]
    rows = read_jsonl(root / "runs.jsonl")
    old = next((r for r in rows if r["identity"] == identity), None)
    if old:
        if old["run_id"] != run_id:
            raise ValueError("checkpoint configuration differs; use a fresh study directory")
        return old
    completed = {r["run_id"]: r for r in read_jsonl(root / "endpoints.jsonl")}
    if completed.get(run_id, {}).get("state") == "completed":
        raise ValueError(
            "paid outcome already completed but reporting checkpoint is missing; reconcile saved outcome, never replay"
        )
    started = time.perf_counter()
    append_jsonl(
        root / "endpoints.jsonl",
        {"run_id": run_id, "identity": identity, "state": "started", "timestamp": now()},
    )
    inp = RequestInput.model_validate(case["input"])
    model.run_id = run_id
    with tool_service(case["state"]) as adapter:
        record, plan = execute_request(
            inp,
            policy,
            bank if state == "warm" else [],
            reuse_settings,
            model,
            adapter,
            run_id,
            bank_state=state,
        )
        persistence = time.perf_counter()
        # Required outcome persistence is inside the latency interval. Reporting and
        # scoring below are offline. A crash before the final commit blocks replay.
        write_json(root / "outcomes" / f"{run_id}.json", record.model_dump())
        append_jsonl(root / "endpoints.jsonl", {"run_id": run_id, "state": "completed", "timestamp": now()})
        record.timings_ms["persistence"] = (time.perf_counter() - persistence) * 1000
        record.timings_ms["end_to_end"] = (time.perf_counter() - started) * 1000
    row = {
        "run_id": run_id,
        "identity": identity,
        "case_id": case["id"],
        "cluster": case["cluster"],
        "split": case["split"],
        "family": case["family"],
        "policy": policy,
        "bank_state": state,
        "repetition": repetition,
        "configuration": config_hash(root, settings),
        "record": record.model_dump(),
        "evaluation": evaluate(record, reference, inp),
        "plan": plan.model_dump() if plan else None,
    }
    append_jsonl(root / "runs.jsonl", row)
    return row


def inputs_and_references(root, split=None):
    splits = [split] if split else ["history", "dev", "test"]
    return read_jsonl(root / "inputs.jsonl"), {
        r["id"]: r for part in splits for r in read_jsonl(root / f"references-{part}.jsonl")
    }


def seed(root, settings, *, client=None):
    require_reviews(root)
    if (root / "frozen.json").exists():
        raise ValueError("bank is frozen; test-time admission disabled")
    assert_no_pending(root)
    if (root / "seed.json").exists():
        previous = json.loads((root / "seed.json").read_text())
        if previous.get("history_configuration") != history_hash(root, settings):
            raise ValueError("history configuration changed; use a fresh study directory")
        return previous
    reuse_settings = load_config(root)
    model = LiveModel(settings, reuse_settings, root, stage="core", client=client)
    cases, references = inputs_and_references(root, "history")
    bank, admitted = [], []
    # History calls must have a stable bank (empty); build only after all attempts.
    for case in (c for c in cases if c["split"] == "history"):
        row = execute_endpoint(
            root, case, references[case["id"]], "fused", "empty", 0, settings, reuse_settings, model, []
        )
        record = ExecutionRecord.model_validate(row["record"])
        # History-only offline evaluation certifies task success. Admission receives
        # a boolean certificate, no paths/facts and no development/held-out labels.
        if (
            record.status != "completed"
            or not row["plan"]
            or row["plan"]["kind"] != "tools"
            or record.replans
        ):
            continue
        if not record.executions or any(not e["result"].get("found") for e in record.executions):
            continue
        try:
            from .contracts import PlannedResponse

            plan = admit_history(
                record,
                PlannedResponse.model_validate(row["plan"]),
                {"history_run": row["run_id"], "source": source_hash()},
                history_success=row["evaluation"]["success"],
            )
        except ValueError:
            continue
        bank.append(plan)
        admitted.append(case["id"])
    write_json(root / "bank.json", [p.model_dump() for p in bank])
    result = {
        "attempted": 16,
        "admitted": len(bank),
        "history_ids": admitted,
        "construction_cost_usd": model.stage_spent(),
        "timestamp": now(),
        "history_configuration": history_hash(root, settings),
    }
    write_json(root / "seed.json", result)
    return result


def run_matrix(root, settings, *, split="dev", pilot=False, client=None):
    require_reviews(root)
    assert_no_pending(root)
    if not (root / "seed.json").exists():
        raise ValueError("seed the history bank before running")
    if split == "test":
        verify_freeze(root, settings)
    elif (root / "frozen.json").exists():
        raise ValueError("development is closed after freeze")
    reuse_settings = load_config(root)
    cases, references = inputs_and_references(root, split)
    cases = [c for c in cases if c["split"] == split]
    if pilot:
        cases = [next(c for c in cases if c["family"] == family) for family in FAMILIES]
    bank = load_bank(root)
    if not pilot:
        if not (root / "pilot.json").exists():
            raise ValueError("run the eight-cluster pilot before the full matrix")
        pilot_result = json.loads((root / "pilot.json").read_text())
        if not pilot_result["fits_full_matrix"] and not reuse_settings.ordinary_subset:
            raise ValueError(
                "pilot projection exceeds core budget; select the prespecified ordinary subset before continuing"
            )
    model = LiveModel(settings, reuse_settings, root, stage="pilot" if pilot else "core", client=client)
    completed = 0
    for case in cases:
        block = [
            (policy, state, rep)
            for policy, state in conditions(case, reuse_settings.ordinary_subset)
            for rep in range(2 if split == "test" else 1)
        ]
        random.Random(reuse_settings.seed + int(digest(case["id"])[:8], 16)).shuffle(block)
        for policy, state, rep in block:
            execute_endpoint(
                root, case, references[case["id"]], policy, state, rep, settings, reuse_settings, model, bank
            )
            completed += 1
    if pilot:
        costs = [r["record"]["cost_usd"] for r in read_jsonl(root / "runs.jsonl") if r["split"] == "dev"]
        projection = (sum(costs) / len(costs) if costs else 0) * (144 + 768) * 1.5
        result = {
            "endpoints": completed,
            "pilot_spent_usd": model.stage_spent("pilot"),
            "projected_full_matrix_usd_with_50pct_headroom": projection,
            "remaining_core_usd": reuse_settings.core_cap - model.stage_spent(),
            "fits_full_matrix": projection + model.stage_spent() <= reuse_settings.core_cap,
        }
        write_json(root / "pilot.json", result)
        return result
    return {
        "split": split,
        "endpoints": completed,
        "reuse_committed_usd": model.stage_spent(),
        "global_committed_usd": Budget(root.parent / "budget.jsonl").spent,
    }


def freeze(root, settings):
    require_reviews(root)
    assert_no_pending(root)
    if (root / "frozen.json").exists():
        return verify_freeze(root, settings)
    rows = read_jsonl(root / "runs.jsonl")
    if any(r["split"] == "test" for r in rows):
        raise ValueError("held-out execution already exists; retuning prohibited")
    cfg = load_config(root)
    cases, _ = inputs_and_references(root)
    dev = [r for r in rows if r["split"] == "dev" and r["configuration"] == config_hash(root, settings)]
    expected = {
        (c["id"], p, s) for c in cases if c["split"] == "dev" for p, s in conditions(c, cfg.ordinary_subset)
    }
    actual = {(r["case_id"], r["policy"], r["bank_state"]) for r in dev}
    if expected != actual or len(actual) != len(dev):
        raise ValueError("complete development matrix with the exact final configuration before freeze")
    if any(r["evaluation"]["incorrect_accepted_reuse"] for r in dev if r["policy"] == "verified"):
        raise ValueError("verified development reuse has incorrect accepted plans")
    if not (root / "calibration.json").exists():
        raise ValueError("run analyze --calibrate on development data first")
    calibration = json.loads((root / "calibration.json").read_text())
    if calibration["bank_hash"] != digest(root / "bank.json") or calibration["references_hash"] != digest(
        root / "references-dev.jsonl"
    ):
        raise ValueError("calibration bank or development references changed")
    if calibration["selected"] != {"threshold": cfg.threshold, "margin": cfg.margin}:
        raise ValueError(
            "apply selected calibration settings, rerun development, and recalibrate before freeze"
        )
    pilot = json.loads((root / "pilot.json").read_text())
    if not pilot["fits_full_matrix"] and not cfg.ordinary_subset:
        raise ValueError("budget projection requires ordinary subset before freeze")
    spent = committed_cost(root)
    remaining_runs = sum(len(conditions(c, cfg.ordinary_subset)) * 2 for c in cases if c["split"] == "test")
    projection = sum(r["record"]["cost_usd"] for r in dev) / len(dev) * remaining_runs * 1.5
    if projection + spent > cfg.core_cap:
        raise ValueError("remaining matrix exceeds core cap even with selected subset; stop at pilot")
    frozen = {
        "timestamp": now(),
        "fingerprint": fingerprint(root, settings),
        "development_hash": digest([r for r in rows if r["split"] != "test"]),
        "calibration_hash": digest(root / "calibration.json"),
        "remaining_projection_usd": projection,
        "held_out_endpoints": remaining_runs,
        "label_review_scope": "eight family contracts; substitutions are derived references",
    }
    with tarfile.open(root / "frozen-source.tar.gz", "w:gz") as archive:
        for name in ("src", "config", "tests", "pyproject.toml", "uv.lock"):
            archive.add(name, filter=lambda entry: None if "__pycache__" in entry.name else entry)
        for name in frozen["fingerprint"]["files"]:
            archive.add(root / name, arcname=f"study/{name}")
    frozen["source_archive_hash"] = digest(root / "frozen-source.tar.gz")
    write_json(root / "frozen.json", frozen)
    return frozen


def locked(function, *args, **kwargs):
    # Same lock as the historical study and same global ledger. No concurrent paid runs.
    with run_lock():
        return function(*args, **kwargs)
