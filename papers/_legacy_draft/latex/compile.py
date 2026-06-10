"""
compile.py — Compile aircraft_positioning.tex to PDF.

Usage
-----
    python documentation/latex/compile.py            # compile once
    python documentation/latex/compile.py --watch    # recompile on file changes

Requirements
------------
    A working LaTeX distribution must be on PATH (MiKTeX, TeX Live, etc.).
    pdflatex is used by default; pass --engine=xelatex or --engine=lualatex
    to override.

    For --watch mode:  pip install watchdog
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

LATEX_DIR  = Path(__file__).resolve().parent
MAIN_FILE  = LATEX_DIR / "aircraft_positioning.tex"
OUTPUT_DIR = LATEX_DIR / "output"

WATCHED_EXTENSIONS = {".tex"}


def compile_pdf(engine: str = "pdflatex") -> bool:
    """Run the LaTeX compiler twice (to resolve cross-references).

    Returns True on success, False on error.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    cmd = [
        engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={OUTPUT_DIR}",
        str(MAIN_FILE),
    ]

    print(f"\n[compile] {engine} {MAIN_FILE.name}  ->  {OUTPUT_DIR}/")

    for pass_num in (1, 2):
        print(f"  Pass {pass_num}/2 ...", end=" ", flush=True)
        result = subprocess.run(
            cmd,
            cwd=LATEX_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("FAILED")
            # Print only the last 30 lines of the log to keep output readable
            log_lines = result.stdout.splitlines()
            print("\n  --- LaTeX error (last 30 lines) ---")
            for line in log_lines[-30:]:
                print(f"  {line}")
            print("  -----------------------------------\n")
            return False
        print("OK")

    pdf_path = OUTPUT_DIR / MAIN_FILE.with_suffix(".pdf").name
    if pdf_path.exists():
        print(f"\n  PDF ready: {pdf_path}\n")
    return True


def _all_tex_files() -> list[Path]:
    return list(LATEX_DIR.glob("*.tex"))


def watch_and_compile(engine: str) -> None:
    """Recompile whenever any .tex file in the directory changes."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("watchdog not installed.  Run:  pip install watchdog")
        sys.exit(1)

    last_mtime: dict[Path, float] = {}

    def _update_mtimes() -> None:
        for f in _all_tex_files():
            last_mtime[f] = f.stat().st_mtime

    class TexHandler(FileSystemEventHandler):
        def __init__(self) -> None:
            self._pending = False

        def on_modified(self, event) -> None:
            if Path(event.src_path).suffix in WATCHED_EXTENSIONS:
                self._pending = True

        def on_created(self, event) -> None:
            self.on_modified(event)

    handler = TexHandler()
    observer = Observer()
    observer.schedule(handler, str(LATEX_DIR), recursive=False)
    observer.start()

    print(f"[watch] Watching {LATEX_DIR} for .tex changes.  Ctrl+C to stop.")
    _update_mtimes()
    compile_pdf(engine)

    try:
        while True:
            time.sleep(1)
            if handler._pending:
                handler._pending = False
                compile_pdf(engine)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile aircraft_positioning.tex to PDF")
    parser.add_argument(
        "--engine",
        default="pdflatex",
        choices=["pdflatex", "xelatex", "lualatex"],
        help="LaTeX engine to use (default: pdflatex)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Recompile automatically when any .tex file changes",
    )
    args = parser.parse_args()

    if args.watch:
        watch_and_compile(args.engine)
    else:
        ok = compile_pdf(args.engine)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
