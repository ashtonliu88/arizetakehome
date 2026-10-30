"""Verify the portable measured gallery against its saved sources (standard library)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def verify(root: Path) -> dict[str, int]:
    gallery = root / "docs/phoenix-measured"
    sidecar = json.loads((gallery / "selected-records.json").read_text())
    for source in sidecar["provenance"]["source_files"]:
        data = (root / source["path"]).read_bytes()
        if len(data) != source["bytes"]:
            raise ValueError(f"source size mismatch: {source['path']}")
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    for screenshot in sidecar["screenshots"]:
        if hashlib.sha256((gallery / screenshot["file"]).read_bytes()).hexdigest() != screenshot["sha256"]:
            raise ValueError(f"screenshot hash mismatch: {screenshot['file']}")
    measurements = {
        row["run_id"]: row
        for line in (root / "results/reuse/runs.jsonl").read_text().splitlines()
        if (row := json.loads(line))
    }
    cases = {
        row["id"]: row
        for line in (root / "results/reuse/inputs.jsonl").read_text().splitlines()
        if (row := json.loads(line))
    }
    records = sidecar["selected_records"]
    if len(records) != 6 or len({r["run_id"] for r in records}) != 6:
        raise ValueError("expected six unique saved endpoints")
    for selected in records:
        row = measurements[selected["run_id"]]
        if row != selected["measurement"]:
            raise ValueError(f"measurement differs: {selected['run_id']}")
        outcome = json.loads((root / f"results/reuse/outcomes/{selected['run_id']}.json").read_text())
        if selected["saved_outcome"] != outcome or selected["case"] != cases[row["case_id"]]:
            raise ValueError(f"saved record differs: {selected['run_id']}")
        if (row["split"], row["bank_state"], row["repetition"]) != ("test", "warm", 1):
            raise ValueError("gallery endpoints must use held-out warm repetition 1")
        root_span = next(
            s for s in selected["phoenix_spans"] if s["span_id"] == selected["publication"]["span_id"]
        )
        attrs = root_span["attributes"]
        if attrs["input"]["value"] != selected["case"]["input"]["request"]:
            raise ValueError("Phoenix root request differs from saved request")
        if attrs["output"]["value"] != row["record"]["answer"]:
            raise ValueError("Phoenix root output differs from saved response")
        annotations = {a["name"]: a for a in root_span["annotations"]}
        grade = annotations["reuse_success"]
        if grade["annotator_kind"] != "CODE" or grade["score"] != float(row["evaluation"]["success"]):
            raise ValueError("Phoenix CODE success differs from mechanical score")
        for span in selected["phoenix_spans"]:
            if span["span_kind"] != "TOOL":
                continue
            execution = next(x for x in outcome["executions"] if x["tool"] == span["name"])
            if json.loads(span["attributes"]["input"]["value"]) != execution["arguments"]:
                raise ValueError("Phoenix tool arguments differ from saved execution")
            if json.loads(span["attributes"]["output"]["value"]) != execution["result"]:
                raise ValueError("Phoenix tool result differs from saved execution")
    by_id = {r["run_id"]: r["measurement"]["record"] for r in records}
    ordinary = by_id["83242cc6e90cc893d8ee33f5"]
    verified = by_id["6746aed7c4ba5a7f7013cdd1"]
    if ordinary["executions"][0]["arguments"] != {"operation": "add", "left": 4.0, "right": 10408.0}:
        raise ValueError("ordinary screenshot selection changed")
    if ordinary["executions"][0]["result"]["value"] != 10412.0:
        raise ValueError("ordinary numerical evidence changed")
    if (
        verified["executions"][0]["arguments"]["operation"] != "subtract"
        or verified["executions"][0]["result"]["value"] != -10404.0
    ):
        raise ValueError("verified numerical evidence changed")
    if (
        len(by_id["739adfc3b1192b1ced846a2f"]["calls"]) != 1
        or len(by_id["8af6c5419626dfdbcfbf60db"]["calls"]) != 2
    ):
        raise ValueError("paired issue LLM counts changed")
    return {
        "selected_endpoints": len(records),
        "screenshots": len(sidecar["screenshots"]),
        "source_hashes": len(sidecar["provenance"]["source_files"]),
    }


if __name__ == "__main__":
    print(json.dumps(verify(Path(__file__).resolve().parents[2]), sort_keys=True))
