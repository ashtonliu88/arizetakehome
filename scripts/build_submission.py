"""Build the three-page submission overview from its Markdown source using Pandoc/Typst."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / "docs/submission.md").read_text()
    assert source.count("<!-- overview-page -->") == 2, "Expected three authored pages"
    # Move the positive comparison to the recommendation page to keep both captures readable.
    pattern = r"!\[Paired issue lookup:[^\]]*\]\(phoenix-measured/exact-versus-fresh\.png\)"
    paired = re.search(pattern, source)
    assert paired, "Missing measured positive comparison"
    source = source.replace(paired.group(), "")
    pages = source.split("<!-- overview-page -->")
    pages[2] += "\n\n" + paired.group() + "\n"
    source = "\n\n```{=typst}\n#pagebreak()\n```\n\n".join(pages)

    # Resolve every source link from docs/ into the PDF's output/pdf/ directory.
    def resolve(match):
        prefix, target, suffix = match.groups()
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            return match.group()
        if target.startswith("../"):
            target = "../../" + target[3:]
        else:
            target = "../../docs/" + target
        return prefix + target + suffix

    source = re.sub(r"(!?\[[^\]]*\]\()([^\s)]+)(\))", resolve, source)
    out = ROOT / "output/pdf"
    out.mkdir(parents=True, exist_ok=True)
    temporary = out / "arize-submission-overview.md"
    typst = out / "arize-submission-overview.typ"
    temporary.write_text(source)
    pandoc = shutil.which("pandoc")
    if not pandoc:
        import pypandoc

        pandoc = pypandoc.get_pandoc_path()
    try:
        subprocess.run(
            [
                pandoc,
                str(temporary),
                "--from=markdown+raw_attribute",
                "--to=typst",
                "--standalone",
                f"--template={ROOT / 'docs/submission-template.typ'}",
                f"--output={typst}",
            ],
            check=True,
            cwd=ROOT,
        )
        subprocess.run(
            ["typst", "compile", "--root", str(ROOT), str(typst), str(out / "arize-submission-overview.pdf")],
            check=True,
            cwd=ROOT,
        )
    finally:
        temporary.unlink(missing_ok=True)
    print("Built output/pdf/arize-submission-overview.pdf from docs/submission.md")


if __name__ == "__main__":
    main()
