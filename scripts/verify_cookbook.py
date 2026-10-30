"""Verify cookbook evidence, cross-edition claims, portable execution and PDF rendering."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import nbformat
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/cookbook"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_execution():
    from jupyter_client import KernelManager
    from jupyter_client.kernelspec import KernelSpecManager
    from nbconvert.preprocessors import ExecutePreprocessor

    with tempfile.TemporaryDirectory(prefix="trace-evidence-portable-") as directory:
        temp = Path(directory)
        shutil.copytree(ROOT / "notebooks/evidence", temp / "evidence")
        notebook_path = temp / "trace-evidence-lab.ipynb"
        shutil.copy2(ROOT / "notebooks/trace-evidence-lab.ipynb", notebook_path)
        guard = temp / "network-guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(
            "import socket\n"
            "_connect = socket.socket.connect\n"
            "def connect(self, address):\n"
            "    if isinstance(address, tuple) and address[0] not in "
            "('127.0.0.1', '::1', 'localhost', '0.0.0.0'):\n"
            "        raise RuntimeError('Outbound network disabled in portable cookbook check')\n"
            "    return _connect(self, address)\n"
            "socket.socket.connect = connect\n"
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if not any(word in key.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET"))
            and not key.startswith(("OPENAI", "PHOENIX", "COOKBOOK"))
        }
        env["PYTHONPATH"] = str(guard)
        env["COOKBOOK_OUTPUT"] = str(temp / "analysis")
        kernel = temp / "kernels/cookbook"
        kernel.mkdir(parents=True)
        (kernel / "kernel.json").write_text(
            json.dumps(
                {
                    "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                    "display_name": "Portable cookbook",
                    "language": "python",
                }
            )
        )
        manager = KernelManager(
            kernel_name="cookbook", kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernel.parent)])
        )
        manager.start_kernel(env=env, cwd=str(temp))
        notebook = nbformat.read(notebook_path, as_version=4)
        try:
            ExecutePreprocessor(timeout=180, kernel_name="cookbook").preprocess(
                notebook, {"metadata": {"path": str(temp)}}, km=manager
            )
        finally:
            manager.shutdown_kernel(now=True)
        measured = json.loads((temp / "analysis/metrics.json").read_text())
        assert measured == json.loads((OUT / "analysis/metrics.json").read_text())
        assert len(list((temp / "analysis").glob("*.png"))) == 6
        return {
            "passed": True,
            "application_source_present": False,
            "credentials_removed": True,
            "external_socket_connections_blocked": True,
            "metrics_equal": True,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--original-hashes", type=Path)
    parser.add_argument(
        "--report", type=Path, help="Write a fresh receipt without replacing historical validation"
    )
    args = parser.parse_args()
    report = {}
    evidence = ROOT / "notebooks/evidence"
    manifest = json.loads((evidence / "manifest.json").read_text())
    source_matches = 0
    for name, entry in manifest["files"].items():
        assert sha(evidence / name) == entry["sha256"], name
        source = ROOT / entry["source"]
        if source.exists():
            assert sha(source) == entry["sha256"], str(source)
            source_matches += 1
    report["bundle_files_verified"] = len(manifest["files"])
    report["available_original_sources_unchanged"] = source_matches
    if args.original_hashes:
        original = json.loads(args.original_hashes.read_text())
        for name, expected in original.items():
            assert sha(ROOT / name) == expected, name
        report["protected_original_files_unchanged"] = len(original)
    notebook = nbformat.read(ROOT / "notebooks/trace-evidence-lab.ipynb", as_version=4)
    nbformat.validate(notebook)
    code = [c for c in notebook.cells if c.cell_type == "code"]
    assert [c.execution_count for c in code] == list(range(1, len(code) + 1))
    assert not any(o.output_type == "error" for c in code for o in c.outputs)
    report["default_code_cells_passed"] = len(code)
    markdown = (ROOT / "docs/cookbook.md").read_text()
    typst = (OUT / "trace-evidence-lab.typ").read_text()
    visible = sum("hide-input" not in c.metadata.get("tags", []) for c in code)
    assert markdown.count("```python") == typst.count("```python") == visible
    report["visible_python_examples_preserved"] = visible
    reader = PdfReader(OUT / "trace-evidence-lab.pdf")
    text = "\n".join(page.extract_text() for page in reader.pages)
    report["pdf_pages"] = len(reader.pages)
    assert all(page.extract_text().strip() for page in reader.pages)
    # Figure captions and the headline facts must survive each export.
    for figure in range(1, 7):
        for edition in (markdown, typst, text):
            assert f"Figure {figure}." in edition, figure
    for fact in ("39.7%", "45.7%", "38.4%", "44.9%", "48/48", "122/128", "768", "192"):
        for edition in (markdown, typst, text):
            assert fact in edition, fact
    assets = re.findall(r"!\[[^\]]*\]\((cookbook-assets/[^)]+)\)", markdown)
    assert len(assets) == 6
    analysis_pngs = {sha(p) for p in (OUT / "analysis").glob("*.png")}
    assert {sha(ROOT / "docs" / name) for name in assets} == analysis_pngs
    report["figures_identical_across_exports"] = 6
    report["headline_claims_present_in_all_editions"] = True
    report["pdf_link_annotations"] = sum(
        1
        for page in reader.pages
        for annotation in page.get("/Annots", [])
        if annotation.get_object().get("/Subtype") == "/Link"
    )
    report["edition_sha256"] = {
        str(path.relative_to(ROOT)): sha(path)
        for path in (
            ROOT / "notebooks/trace-evidence-lab.ipynb",
            ROOT / "docs/cookbook.md",
            OUT / "trace-evidence-lab.typ",
            OUT / "trace-evidence-lab.pdf",
        )
    }
    report["python_package_versions"] = {
        name: importlib.metadata.version(name) for name in ("nbconvert", "numpy", "pandas", "matplotlib")
    }
    if args.portable:
        report["portable_execution"] = portable_execution()
    if args.render:
        destination = ROOT / "tmp/pdfs/cookbook"
        destination.mkdir(parents=True, exist_ok=True)
        for page in destination.glob("page-*.png"):
            page.unlink()
        subprocess.run(
            ["pdftoppm", "-r", "110", "-png", str(OUT / "trace-evidence-lab.pdf"), str(destination / "page")],
            check=True,
        )
        report["rendered_pdf_pages"] = len(list(destination.glob("page-*.png")))
        assert report["rendered_pdf_pages"] == report["pdf_pages"]
    report_path = args.report or OUT / "validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
