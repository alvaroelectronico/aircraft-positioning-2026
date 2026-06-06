"""
snapshot.py — manage snapshots of the working copy of topology_heuristic_job.py.

Subcommands:
    save <slug> --note <path>   atomic save of code + eval + note; auto-restore on rejection.
    restore <id-or-'best'>      overwrite the working copy with that snapshot.
    list                        tabular view of the journal (iter, slug, score, status, lesson).
    log                         dump JOURNAL.md to stdout.

Every iteration produces a folder ``iterations/iter_NNNN_<slug>/`` containing:
  topology_heuristic_job.py   — the working copy at that point
  eval.json                   — the eval result
  note.md                     — human / agent rationale (see template below)

JOURNAL.md gets one appended entry per save, accepted or rejected.

The notion of "current best" lives in best.txt and is updated by save when
the score strictly improves.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent

_WORKING_COPY  = _HERE / "topology_heuristic_job.py"
_ITERATIONS    = _HERE / "iterations"
_JOURNAL       = _HERE / "JOURNAL.md"
_BEST          = _HERE / "best.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_iter_id() -> int:
    """Return the next sequential iter ID (0000-padded → int 0)."""
    _ITERATIONS.mkdir(exist_ok=True)
    existing = [p.name for p in _ITERATIONS.iterdir() if p.is_dir()]
    ids = []
    for name in existing:
        m = re.match(r"^iter_(\d{4})_", name)
        if m:
            ids.append(int(m.group(1)))
    return (max(ids) + 1) if ids else 0


def _slug_ok(slug: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", slug))


def _best_iter_dir() -> Path | None:
    if not _BEST.exists():
        return None
    target = _BEST.read_text(encoding="utf-8").strip()
    if not target:
        return None
    candidate = _ITERATIONS / target
    return candidate if candidate.is_dir() else None


def _read_best_score() -> float:
    """Return the score of the current best iteration, or +inf if none."""
    best = _best_iter_dir()
    if best is None:
        return math.inf
    eval_path = best / "eval.json"
    if not eval_path.exists():
        return math.inf
    with open(eval_path, encoding="utf-8") as f:
        e = json.load(f)
    s = e.get("score")
    if s in (None, "inf", float("inf")):
        return math.inf
    try:
        return float(s)
    except (TypeError, ValueError):
        return math.inf


def _resolve_iter_dir(spec: str) -> Path:
    """Resolve 'best' or a partial slug / full folder name to an iter folder."""
    if spec == "best":
        d = _best_iter_dir()
        if d is None:
            raise SystemExit("No 'best' snapshot is set (best.txt missing or empty).")
        return d
    cand = _ITERATIONS / spec
    if cand.is_dir():
        return cand
    # Try a prefix match
    matches = [p for p in _ITERATIONS.iterdir() if p.is_dir() and p.name.startswith(spec)]
    if not matches:
        # Try substring match
        matches = [p for p in _ITERATIONS.iterdir() if p.is_dir() and spec in p.name]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SystemExit(f"No iteration matches {spec!r}.")
    raise SystemExit(f"Ambiguous spec {spec!r}; candidates: {[p.name for p in matches]}")


def _append_journal(entry: str) -> None:
    if not _JOURNAL.exists():
        _JOURNAL.write_text(
            "# JOURNAL — autoresearch loop on `topology_heuristic_job`\n\n",
            encoding="utf-8",
        )
    with open(_JOURNAL, "a", encoding="utf-8") as f:
        f.write(entry)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_save(args: argparse.Namespace) -> int:
    """Save a snapshot of the working copy + eval + note; accept or reject."""
    slug = args.slug.strip()
    if not _slug_ok(slug):
        raise SystemExit(f"Invalid slug {slug!r}; must match [A-Za-z0-9_-]{{1,60}}.")

    note_path = Path(args.note).resolve() if args.note else None
    eval_path_in = Path(args.eval).resolve() if args.eval else None

    if not _WORKING_COPY.exists():
        raise SystemExit(f"Working copy {_WORKING_COPY} does not exist.")
    if eval_path_in is None or not eval_path_in.exists():
        raise SystemExit(
            "Must provide --eval <path> pointing to the JSON verdict from evaluate.py."
        )
    if note_path is None or not note_path.exists():
        raise SystemExit("Must provide --note <path> with the iteration's note.md.")

    with open(eval_path_in, encoding="utf-8") as f:
        verdict = json.load(f)
    score = verdict.get("score")
    if score in (None, "inf"):
        score = math.inf
    else:
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = math.inf

    # Best score BEFORE this save
    best_score = _read_best_score()
    accepted = math.isfinite(score) and score < best_score - 1e-9
    decision = "accepted" if accepted else "rejected"

    iter_id  = _next_iter_id()
    iter_dir = _ITERATIONS / f"iter_{iter_id:04d}_{slug}"
    iter_dir.mkdir(parents=True, exist_ok=True)

    # Copy code + eval + note
    shutil.copy2(_WORKING_COPY, iter_dir / "topology_heuristic_job.py")
    shutil.copy2(eval_path_in, iter_dir / "eval.json")
    shutil.copy2(note_path,   iter_dir / "note.md")

    # Update best.txt if accepted
    score_str = f"{score:+.4f}" if math.isfinite(score) else "+inf"
    best_str  = f"{best_score:+.4f}" if math.isfinite(best_score) else "+inf"
    if accepted:
        _BEST.write_text(iter_dir.name, encoding="utf-8")

    # Optional lesson: parse "Lessons" section from note.md (one line)
    lesson = _extract_lesson(note_path)

    # Journal entry
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## {iter_dir.name}  ({decision})\n"
        f"*{timestamp}*  score {score_str}  (best {best_str})\n\n"
        f"{lesson}\n"
    )
    _append_journal(entry)

    # If rejected, restore the working copy from the previous best
    restored = False
    if not accepted:
        best = _best_iter_dir()
        if best is not None and best != iter_dir:
            shutil.copy2(best / "topology_heuristic_job.py", _WORKING_COPY)
            restored = True

    # Report
    print(f"\nsnapshot.py save:")
    print(f"  iter:      {iter_dir.name}")
    print(f"  decision:  {decision}")
    print(f"  score:     {score_str}")
    print(f"  best:      {best_str}{'  → updated' if accepted else ''}")
    if restored:
        print(f"  restored:  working copy reverted to {_BEST.read_text(encoding='utf-8').strip()}")
    print(f"  journal:   {_JOURNAL}")
    return 0 if accepted else 1   # exit code: 0 = accepted, 1 = rejected


def _extract_lesson(note_path: Path) -> str:
    """Return the 'Lessons' section content (or a placeholder)."""
    text = note_path.read_text(encoding="utf-8")
    # Match "## Lessons" or "**Lessons**" sections (case-insensitive)
    m = re.search(r"(?im)^(?:##\s*|^\*\*)\s*Lessons?(?:\*\*)?\s*$", text, re.MULTILINE)
    if not m:
        return "(no Lessons section in note.md)"
    tail = text[m.end():].strip()
    # Take until the next heading or EOF, keep first ~4 lines
    next_h = re.search(r"(?im)^(?:##\s|^\*\*\w)", tail, re.MULTILINE)
    if next_h:
        tail = tail[:next_h.start()].strip()
    lines = [l for l in tail.splitlines() if l.strip()]
    if not lines:
        return "(empty Lessons section)"
    return "\n".join(lines[:4])


def cmd_restore(args: argparse.Namespace) -> int:
    target = _resolve_iter_dir(args.spec)
    src = target / "topology_heuristic_job.py"
    if not src.exists():
        raise SystemExit(f"{src} does not exist; cannot restore from {target.name}.")
    shutil.copy2(src, _WORKING_COPY)
    print(f"Restored working copy from {target.name}")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    if not _ITERATIONS.exists():
        print("(no iterations yet)")
        return 0
    rows = []
    for d in sorted(_ITERATIONS.iterdir()):
        if not d.is_dir():
            continue
        eval_path = d / "eval.json"
        score_str = "?"
        n_str     = "?"
        if eval_path.exists():
            with open(eval_path, encoding="utf-8") as f:
                v = json.load(f)
            s = v.get("score")
            if s in (None, "inf"):
                score_str = "+inf"
            else:
                try:
                    score_str = f"{float(s):+.4f}"
                except (TypeError, ValueError):
                    score_str = str(s)
            n_str = f"{v.get('n_compliant')}/{v.get('n_total')}"
        rows.append((d.name, score_str, n_str))
    best = _BEST.read_text(encoding="utf-8").strip() if _BEST.exists() else None
    print(f"\n{'ITER':<48} {'SCORE':>10}  {'COMP':>6}   BEST")
    print("-" * 78)
    for name, score_str, n_str in rows:
        marker = "  *" if name == best else "   "
        print(f"{name:<48} {score_str:>10}  {n_str:>6}  {marker}")
    if best:
        print(f"\nbest = {best}")
    return 0


def cmd_log(_args: argparse.Namespace) -> int:
    if not _JOURNAL.exists():
        print("(JOURNAL.md is empty)")
        return 0
    print(_JOURNAL.read_text(encoding="utf-8"))
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_save = sub.add_parser("save",    help="save the working copy as a new iteration")
    p_save.add_argument("slug")
    p_save.add_argument("--note", required=True, help="path to the iteration's note.md")
    p_save.add_argument("--eval", required=True, help="path to the eval JSON verdict")
    p_save.set_defaults(func=cmd_save)

    p_rest = sub.add_parser("restore", help="restore the working copy from a snapshot")
    p_rest.add_argument("spec", help="iter folder name, prefix, or 'best'")
    p_rest.set_defaults(func=cmd_restore)

    p_list = sub.add_parser("list",    help="list iterations in a tabular view")
    p_list.set_defaults(func=cmd_list)

    p_log  = sub.add_parser("log",     help="dump JOURNAL.md to stdout")
    p_log.set_defaults(func=cmd_log)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
