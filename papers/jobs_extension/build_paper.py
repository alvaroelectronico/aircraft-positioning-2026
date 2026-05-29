"""Compile paper.tex to PDF using pdflatex + bibtex.

Usage
-----
    python papers/cejor_aircraft/build_paper.py             # full build (2 pdflatex + bibtex)
    python papers/cejor_aircraft/build_paper.py --fast      # single pdflatex pass (no bibtex)
    python papers/cejor_aircraft/build_paper.py --clean     # remove auxiliary files only
    python papers/cejor_aircraft/build_paper.py --open      # open PDF after build (Windows/Mac/Linux)
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PAPER_DIR = Path(__file__).parent.resolve()
MAIN_TEX  = "paper.tex"
MAIN_NAME = "paper"          # stem of .tex file (no extension)


def run(cmd: list[str], cwd: Path) -> int:
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


_MIKTEX_BIN = Path.home() / "AppData" / "Local" / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64"

def _find_tool(name: str) -> str:
    """Return full path to a LaTeX tool, checking MiKTeX on Windows first."""
    if platform.system() == "Windows":
        candidate = _MIKTEX_BIN / (name + ".exe")
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    return name  # let subprocess raise if truly missing


def check_tool(name: str) -> bool:
    found = shutil.which(name) is not None or (
        platform.system() == "Windows"
        and (_MIKTEX_BIN / (name + ".exe")).exists()
    )
    if not found:
        print(f"  WARNING: '{name}' not found — skipping.", file=sys.stderr)
    return found


def clean(paper_dir: Path) -> None:
    extensions = [
        ".aux", ".bbl", ".blg", ".log", ".out", ".toc",
        ".lof", ".lot", ".fls", ".fdb_latexmk", ".synctex.gz",
    ]
    removed = 0
    for ext in extensions:
        f = paper_dir / (MAIN_NAME + ext)
        if f.exists():
            f.unlink()
            removed += 1
    print(f"Removed {removed} auxiliary file(s) from {paper_dir}")


def build(paper_dir: Path, fast: bool = False) -> bool:
    has_pdflatex = check_tool("pdflatex")
    has_bibtex   = check_tool("bibtex")

    if not has_pdflatex:
        print("ERROR: pdflatex is required.", file=sys.stderr)
        return False

    pdflatex_cmd = [
        _find_tool("pdflatex"),
        "-interaction=nonstopmode",
        "-file-line-error",
        MAIN_TEX,
    ]

    # First pass
    rc = run(pdflatex_cmd, cwd=paper_dir)
    if rc != 0:
        print(f"\nERROR: pdflatex exited with code {rc}. "
              f"Check {paper_dir / (MAIN_NAME + '.log')} for details.",
              file=sys.stderr)
        return False

    if not fast and has_bibtex:
        # BibTeX pass
        run([_find_tool("bibtex"), MAIN_NAME], cwd=paper_dir)
        # Two more pdflatex passes to resolve cross-references
        run(pdflatex_cmd, cwd=paper_dir)
        run(pdflatex_cmd, cwd=paper_dir)

    pdf = paper_dir / (MAIN_NAME + ".pdf")
    if pdf.exists():
        print(f"\nBuild successful: {pdf}")
        return True
    else:
        print("\nERROR: PDF not produced.", file=sys.stderr)
        return False


def open_pdf(paper_dir: Path) -> None:
    pdf = paper_dir / (MAIN_NAME + ".pdf")
    if not pdf.exists():
        print("PDF not found — cannot open.", file=sys.stderr)
        return
    system = platform.system()
    if system == "Windows":
        os.startfile(str(pdf))           # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.run(["open", str(pdf)])
    else:
        subprocess.run(["xdg-open", str(pdf)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build aircraft-positioning paper PDF.")
    parser.add_argument("--fast",  action="store_true", help="Single pdflatex pass, skip bibtex.")
    parser.add_argument("--clean", action="store_true", help="Remove auxiliary files only.")
    parser.add_argument("--open",  action="store_true", help="Open PDF after build.")
    args = parser.parse_args()

    if args.clean:
        clean(PAPER_DIR)
        return

    success = build(PAPER_DIR, fast=args.fast)
    if success and args.open:
        open_pdf(PAPER_DIR)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
