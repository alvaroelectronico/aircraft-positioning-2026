"""Paired MILP-vs-heuristic comparison report for the job battery.

Builds a single self-contained comparison from ``outputs/solutions/results.csv``
WITHOUT re-running the MILP (its baseline is fixed and already cached there).
The report has, in this order:

  1. the relative-gap + per-component summary table (``gap_summary``), and
  2. a per-instance detail where, for every weight profile, the **MILP row is
     immediately followed by the heuristic row** for the same instance — the
     side-by-side view requested for the battery, with the per-instance
     objective gap ``(MILP - heur)/MILP``.

Instances are listed **seed-first** (seed 1 of every type, then seed 2 …) to
match the battery run order.

Usage:
    py -3 experiments/paired_report.py [results.csv] > paired_report.txt
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "experiments"))

from gap_summary import (PROFILES, _detect_heur_labels, _records_from_csv,
                         format_gap_table)


def _seed(stem: str) -> int:
    m = re.search(r"_seed(\d+)$", stem)
    return int(m.group(1)) if m else 0


def _type(stem: str) -> str:
    return re.sub(r"_seed\d+$", "", stem)


def _fmt(v, nd=2, width=10):
    if v is None:
        return f"{'-':>{width}}"
    return f"{v:>{width}.{nd}f}"


def detail_block(records: list[dict], heur_labels: dict | None = None) -> str:
    """Per-instance MILP-row-then-heuristic-row detail (seed-first), without
    the summary table — so callers can splice it into an existing log.

    ``heur_labels`` pins the heuristic label per profile; when omitted it is
    auto-detected from the records (mirroring ``gap_summary``)."""
    heur_labels = heur_labels or _detect_heur_labels(records)
    # index by (instance, label)
    by_key = {(r["instance"], r["experiment"]): r for r in records
              if r.get("error") is None and r.get("objective") is not None}
    instances = sorted({r["instance"] for r in records}, key=lambda s: (_seed(s), _type(s)))

    out = io.StringIO()
    sep = "=" * 86
    out.write(f"{sep}\n")
    out.write("  PER-INSTANCE DETAIL  —  MILP row followed by heuristic row (seed-first)\n")
    out.write("  gap = (MILP_obj - heur_obj) / MILP_obj ;  >0 => heuristic better\n")
    out.write(f"{sep}\n")
    hdr = (f"  {'Method':<7} {'Objective':>12} {'Makespan':>10} "
           f"{'Delay':>10} {'Mov':>6} {'Gap':>9}\n")

    for inst in instances:
        out.write(f"\n{inst}\n{'-' * len(inst)}\n")
        for pkey, milp_label, desc in PROFILES:
            heur_label = heur_labels[pkey]
            m = by_key.get((inst, milp_label))
            h = by_key.get((inst, heur_label))
            out.write(f"  [{pkey}  {desc}]\n")
            out.write(hdr)
            gap = None
            if m and h and m["objective"]:
                gap = (m["objective"] - h["objective"]) / m["objective"]
            for tag, r in (("MILP", m), ("heur", h)):
                if r is None:
                    out.write(f"  {tag:<7} {'(missing)':>12}\n")
                    continue
                g = f"{gap*100:>+8.2f}%" if (tag == "heur" and gap is not None) else f"{'':>9}"
                out.write(
                    f"  {tag:<7} {_fmt(r['objective'], 2, 12)} {_fmt(r.get('makespan'))} "
                    f"{_fmt(r.get('total_delay'))} {_fmt(r.get('movements'), 0, 6)} {g}\n"
                )
    out.write(f"\n{sep}\n")
    return out.getvalue()


def build(records: list[dict], heur_labels: dict | None = None) -> str:
    """Full report: summary gap table followed by the per-instance detail."""
    heur_labels = heur_labels or _detect_heur_labels(records)
    return (format_gap_table(records, heur_labels=heur_labels)
            + "\n\n" + detail_block(records, heur_labels=heur_labels))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    # Optional positional args: [results.csv] [heur_prefix]
    # When the CSV holds several heuristics per profile (igvnd / ta_brkga /
    # ta2_brkga …) pass a prefix like "ta2_brkga" to pin the comparison.
    args = sys.argv[1:]
    csv_arg = next((a for a in args if a.endswith(".csv") or "/" in a or "\\" in a), None)
    prefix = next((a for a in args if a is not csv_arg), None)
    csv_path = Path(csv_arg) if csv_arg else _ROOT / "outputs" / "solutions" / "results.csv"
    if not csv_path.exists():
        print(f"results.csv not found at {csv_path}", file=sys.stderr)
        sys.exit(1)
    records = _records_from_csv(csv_path)
    heur_labels = None
    if prefix:
        heur_labels = {pkey: f"{prefix}_{pkey}" for pkey, _, _ in PROFILES}
    print(build(records, heur_labels=heur_labels))
