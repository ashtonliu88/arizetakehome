"""Verify the portable submission and write a fresh receipt, without changing historical evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/submission"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_links(expected_receipt):
    files = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    files += [ROOT / "notebooks/evidence/README.md", ROOT / "output/cookbook/README.md"]
    checked = 0
    missing = []
    for path in files:
        if path.name == "scriptashtonliu-systems-guide.md":
            continue  # Unrelated authoring notes are deliberately outside the submission.
        for target in re.findall(r"!?\[[^\]]*\]\(([^)\s]+)\)", path.read_text()):
            parsed = urlsplit(target.strip("<>"))
            if parsed.scheme or not parsed.path:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve()
            checked += 1
            if not destination.exists() and destination != expected_receipt.resolve():
                missing.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not missing, "Missing document targets: " + "; ".join(missing)
    return checked


def audit_check():
    packet = ROOT / "docs/reuse-answer-audit"
    manifest = json.loads((packet / "manifest.json").read_text())
    source = (packet / manifest["source_root"]).resolve()
    for name, expected in manifest["source_hashes"].items():
        assert sha(source / name) == expected, name
    for name, expected in manifest["artifact_hashes"].items():
        assert sha(packet / name) == expected, name
    assert manifest["endpoint_count"] == 24
    assert len(manifest["families"]) == 8
    status = json.loads((packet / "status/report.json").read_text())
    assert status["completed_reviews"] == 0 and status["pending_reviews"] == 24
    return {
        "selected_endpoints": 24,
        "families": 8,
        "source_hashes_verified": len(manifest["source_hashes"]),
        "packet_artifact_hashes_verified": len(manifest["artifact_hashes"]),
        "human_reviews_completed": 0,
        "human_reviews_pending": 24,
        "status": "pending at candidate request; diagnostic sample, not a rate estimate",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--report", type=Path, default=OUT / "verification.json")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    receipt = {
        "verified_at": datetime.now(UTC).isoformat(),
        "scope": "Offline submission verification; no provider calls or Phoenix publication",
    }
    baseline = OUT / "preserved-sha256.json"
    originals = json.loads(baseline.read_text())
    for name, expected in originals.items():
        assert sha(ROOT / name) == expected, name
    receipt["protected_original_files_unchanged"] = len(originals)
    local_only = json.loads((OUT / "local-only-sha256.json").read_text())
    available = 0
    for name, expected in local_only.items():
        if (ROOT / name).exists():
            assert sha(ROOT / name) == expected, name
            available += 1
    receipt["local_only_originals"] = {
        "hashes_recorded": len(local_only),
        "available_and_unchanged": available,
        "excluded_from_submission_tree": len(local_only) - available,
    }
    receipt["recorded_project_checks"] = json.loads((OUT / "project-checks.json").read_text())
    receipt["frozen_study"] = json.loads((OUT / "freeze-verification.json").read_text())
    notebook = json.loads((ROOT / "notebooks/trace-evidence-lab.ipynb").read_text())
    actual = [
        hashlib.sha256(json.dumps(cell["source"]).encode()).hexdigest()
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ]
    assert actual == json.loads((OUT / "notebook-code-sha256.json").read_text())
    receipt["notebook_code_cells_unchanged"] = len(actual)
    command = [
        sys.executable,
        str(ROOT / "scripts/verify_cookbook.py"),
        "--original-hashes",
        str(baseline),
        "--report",
        str(OUT / "cookbook-verification.json"),
    ]
    for option in ("portable", "render"):
        if getattr(args, option):
            command.append("--" + option)
    subprocess.run(command, check=True, cwd=ROOT, stdout=subprocess.PIPE, text=True)
    receipt["cookbook"] = json.loads((OUT / "cookbook-verification.json").read_text())
    receipt["local_document_links_checked"] = local_links(args.report)
    receipt["human_audit"] = audit_check()
    gallery = subprocess.run(
        [sys.executable, str(ROOT / "docs/phoenix-measured/verify.py")],
        check=True,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    receipt["phoenix_gallery"] = json.loads(gallery.stdout)
    overview = ROOT / "output/pdf/arize-submission-overview.pdf"
    reader = PdfReader(overview)
    assert 2 <= len(reader.pages) <= 3, len(reader.pages)
    text = "\n".join(page.extract_text() for page in reader.pages)
    for fact in ("39.7%", "45.7%", "122/128", "106/128", "pending", "CODE"):
        assert fact in text, fact
    image_count = sum(len(list(page.images)) for page in reader.pages)
    assert image_count == 3, image_count
    receipt["overview"] = {"pages": len(reader.pages), "images": image_count, "sha256": sha(overview)}
    visual_path = OUT / "visual-review.json"
    if visual_path.exists():
        visual = json.loads(visual_path.read_text())
        for entry in visual["pdfs"]:
            assert sha(ROOT / entry["path"]) == entry["sha256"], "Visual review is stale"
        receipt["visual_review"] = visual
    if args.render:
        destination = ROOT / "tmp/pdfs/submission"
        destination.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["pdftoppm", "-r", "140", "-png", str(overview), str(destination / "page")], check=True
        )
        receipt["overview"]["rendered_pages"] = len(list(destination.glob("page-*.png")))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Verified submission; receipt: {args.report}")


if __name__ == "__main__":
    main()
