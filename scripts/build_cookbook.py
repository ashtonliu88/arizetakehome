"""Execute the notebook, export via nbconvert/Pandoc, and compile its Typst edition."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import nbformat
from nbconvert import MarkdownExporter
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/trace-evidence-lab.ipynb"
OUT = ROOT / "output/cookbook"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-execute", action="store_true", help="Export already executed notebook")
    args = parser.parse_args()
    # Publishing and paid execution must never inherit an opt-in during a document build.
    for key in ("COOKBOOK_RUN_PAID", "COOKBOOK_PUBLISH_PHOENIX"):
        if os.getenv(key) == "1":
            raise SystemExit(f"Unset {key}: authoring always uses the offline default")
    manifest = json.loads((ROOT / "notebooks/evidence/manifest.json").read_text())
    for relative, entry in manifest["files"].items():
        assert sha(ROOT / "notebooks/evidence" / relative) == entry["sha256"], relative
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    if not args.no_execute:
        # Use the builder interpreter, avoiding a machine-specific installed kernel.
        from tempfile import TemporaryDirectory

        from jupyter_client import KernelManager
        from jupyter_client.kernelspec import KernelSpecManager

        with TemporaryDirectory(prefix="cookbook-kernel-") as temp:
            kernel = Path(temp) / "cookbook"
            kernel.mkdir()
            (kernel / "kernel.json").write_text(
                json.dumps(
                    {
                        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                        "display_name": "Cookbook offline",
                        "language": "python",
                    }
                )
            )
            manager = KernelSpecManager(kernel_dirs=[temp])
            executor = ExecutePreprocessor(timeout=180, kernel_name="cookbook")
            kernel_manager = KernelManager(kernel_name="cookbook", kernel_spec_manager=manager)
            try:
                executor.preprocess(
                    notebook, {"metadata": {"path": str(ROOT / "notebooks")}}, km=kernel_manager
                )
            finally:
                if kernel_manager.has_kernel:
                    kernel_manager.shutdown_kernel(now=True)
        nbformat.write(notebook, NOTEBOOK)
    templates = Path(sys.prefix) / "share/jupyter/nbconvert/templates"
    exporter = MarkdownExporter(
        template_paths=[
            str(templates / "markdown"),
            str(templates / "base"),
            str(templates),
        ]
    )
    from nbconvert.preprocessors import TagRemovePreprocessor

    exporter.register_preprocessor(TagRemovePreprocessor(remove_input_tags={"hide-input"}), enabled=True)
    exporter.exclude_input_prompt = True
    exporter.exclude_output_prompt = True
    markdown, resources = exporter.from_notebook_node(notebook, resources={"unique_key": "cookbook"})
    markdown = "\n".join("" if not line.strip() else line for line in markdown.splitlines()).rstrip() + "\n"
    assets = ROOT / "docs/cookbook-assets"
    assets.mkdir(exist_ok=True)
    for name, content in resources.get("outputs", {}).items():
        filename = Path(name).name
        (assets / filename).write_bytes(content)
        markdown = markdown.replace(name, f"cookbook-assets/{filename}")
    (ROOT / "docs/cookbook.md").write_text(markdown)
    pandoc = shutil.which("pandoc")
    if not pandoc:
        import pypandoc

        pandoc = pypandoc.get_pandoc_path()
    OUT.mkdir(parents=True, exist_ok=True)
    # Pandoc owns the Markdown -> Typst translation; styling stays in a small template.
    intermediate = OUT / "edition.md"
    typst_markdown = re.sub(r"(!\[[^\]]*\]\()cookbook-assets/", r"\1../../docs/cookbook-assets/", markdown)
    intermediate.write_text(typst_markdown)
    subprocess.run(
        [
            pandoc,
            str(intermediate),
            "--from=markdown-implicit_figures",
            "--to=typst",
            "--standalone",
            f"--template={ROOT / 'docs/cookbook-template.typ'}",
            f"--output={OUT / 'trace-evidence-lab.typ'}",
            "--metadata=title:Trace Evidence Lab",
        ],
        check=True,
        cwd=ROOT,
    )
    # The Markdown edition carries explicit numbered captions. Keep each caption
    # with its image rather than allowing Pandoc's separate blocks to split pages.
    typst_path = OUT / "trace-evidence-lab.typ"
    typst_source, count = re.subn(
        r"(#box\(image\([^\n]+\)\)\n\nFigure [1-6]\. .*?)(?=\n\n)",
        lambda match: "#block(breakable: false)[\n" + match.group(1) + "\n]",
        typst_path.read_text(),
        flags=re.DOTALL,
    )
    assert count == 6, "Expected all six numbered figures and captions"
    typst_path.write_text(typst_source)
    subprocess.run(
        [
            "typst",
            "compile",
            "--root",
            str(ROOT),
            str(OUT / "trace-evidence-lab.typ"),
            str(OUT / "trace-evidence-lab.pdf"),
        ],
        check=True,
        cwd=ROOT,
    )
    intermediate.unlink()
    print("Executed and exported notebook -> Markdown -> Typst -> PDF")


if __name__ == "__main__":
    main()
