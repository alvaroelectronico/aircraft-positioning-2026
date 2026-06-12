"""Heuristic-vs-MILP relative-gap summary for the job-level battery.

Gap convention (as requested):

    gap = (MILP_obj - heuristic_obj) / MILP_obj

so **gap > 0 means the heuristic is better** (lower objective, a
minimisation problem) and gap < 0 means it is worse.

For every instance *type* (the configuration, i.e. the instance stem with
its ``_seed<N>`` suffix stripped) the table reports the mean, min and max
gap across that type's seeds, both **disaggregated per weight profile**
and **aggregated over all profiles**.

Two entry points:

* ``format_gap_table(records)`` — used by ``run_experiments.py`` to prepend
  the table to the run log.  ``records`` is the in-memory ``summary`` list
  (dicts with ``instance``, ``experiment``, ``objective``, ``error``).
* ``python experiments/gap_summary.py`` — standalone, reads
  ``outputs/solutions/results.csv`` (latest row per instance+label) and
  prints the table for whatever has been run so far.
"""
from __future__ import annotations

import io
import re
from collections import defaultdict

# (weight-profile key, MILP label, heuristic label, human description)
PROFILES = [
    ("wMK",  "milp_job_wMK",  "igvnd_wMK",  "100/1/1  makespan-priority"),
    ("wDLY", "milp_job_wDLY", "igvnd_wDLY", "1/100/1  delay-priority"),
    ("wMOV", "milp_job_wMOV", "igvnd_wMOV", "1/1/100  movement-priority"),
]


def _config_type(stem: str) -> str:
    """Instance type = stem without the trailing _seed<N>."""
    return re.sub(r"_seed\d+$", "", stem)


def _collect(records: list[dict]) -> dict:
    """Return {(type, profile_key): [gap, ...]} plus the per-(type) aggregate
    under profile_key == 'ALL'."""
    # objective lookup: (instance, experiment) -> objective
    obj: dict[tuple[str, str], float] = {}
    for r in records:
        if r.get("error") is None and r.get("objective") is not None:
            obj[(r["instance"], r["experiment"])] = float(r["objective"])

    instances = sorted({r["instance"] for r in records})
    gaps: dict[tuple[str, str], list[float]] = defaultdict(list)
    for inst in instances:
        ctype = _config_type(inst)
        for pkey, milp_label, heur_label, _ in PROFILES:
            mo = obj.get((inst, milp_label))
            ho = obj.get((inst, heur_label))
            if mo is None or ho is None or mo == 0:
                continue
            g = (mo - ho) / mo
            gaps[(ctype, pkey)].append(g)
            gaps[(ctype, "ALL")].append(g)
    return gaps


def _stat_rows(gaps: dict, pkey: str) -> list[tuple[str, int, float, float, float]]:
    rows = []
    for (ctype, k), vals in gaps.items():
        if k != pkey or not vals:
            continue
        n = len(vals)
        rows.append((ctype, n, sum(vals) / n, min(vals), max(vals)))
    rows.sort(key=lambda x: x[0])
    return rows


def _write_block(out: io.StringIO, title: str, rows: list[tuple]) -> None:
    out.write(f"  [{title}]\n")
    if not rows:
        out.write("    (no paired MILP/heuristic results yet)\n")
        return
    w_type = max(4, max(len(r[0]) for r in rows))
    out.write(f"    {'Type':<{w_type}}  {'N':>3}  {'Mean':>8}  {'Min':>8}  {'Max':>8}\n")
    out.write(f"    {'-' * (w_type + 3 + 3*10)}\n")
    for ctype, n, mean, lo, hi in rows:
        out.write(
            f"    {ctype:<{w_type}}  {n:>3}  "
            f"{mean*100:>+7.2f}%  {lo*100:>+7.2f}%  {hi*100:>+7.2f}%\n"
        )


def format_gap_table(records: list[dict]) -> str:
    """Render the heuristic-vs-MILP relative-gap summary as text."""
    gaps = _collect(records)
    out = io.StringIO()
    sep = "=" * 66
    out.write(f"{sep}\n")
    out.write("  HEURISTIC vs MILP  —  relative gap per instance type\n")
    out.write("  gap = (MILP_obj - heuristic_obj) / MILP_obj\n")
    out.write("  gap > 0  =>  heuristic BETTER (lower objective);  < 0  => worse\n")
    out.write(f"{sep}\n")
    out.write("  -- Disaggregated by weight profile --\n")
    for pkey, _, _, desc in PROFILES:
        _write_block(out, f"{pkey}  ({desc})", _stat_rows(gaps, pkey))
        out.write("\n")
    out.write("  -- Aggregated over all weight profiles --\n")
    _write_block(out, "ALL profiles", _stat_rows(gaps, "ALL"))
    out.write(f"{sep}\n")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Standalone: build records from outputs/solutions/results.csv
# ---------------------------------------------------------------------------

def _records_from_csv(csv_path) -> list[dict]:
    """Read results.csv positionally (the long-lived ledger has no reliable
    header) and keep, per (instance, label), the latest objective.  Only rows
    whose label is one of our six experiment labels are retained."""
    import csv as _csv
    wanted = {lbl for _, ml, hl, _ in PROFILES for lbl in (ml, hl)}
    # column order written by Application.save_solution
    INSTANCE, LABEL, TIMESTAMP, OBJECTIVE = 0, 2, 3, 6
    latest: dict[tuple[str, str], dict] = {}
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for cells in _csv.reader(fh):
            if len(cells) <= OBJECTIVE:
                continue
            label = cells[LABEL]
            if label not in wanted:
                continue
            try:
                obj = float(cells[OBJECTIVE])
            except ValueError:
                continue
            inst, ts = cells[INSTANCE], cells[TIMESTAMP]
            key = (inst, label)
            if key not in latest or ts >= latest[key]["timestamp"]:
                latest[key] = {"instance": inst, "experiment": label,
                               "objective": obj, "error": None, "timestamp": ts}
    return list(latest.values())


if __name__ == "__main__":
    import sys
    from pathlib import Path

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    root = Path(__file__).resolve().parents[1]
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "outputs" / "solutions" / "results.csv"
    if not csv_path.exists():
        print(f"results.csv not found at {csv_path}", file=sys.stderr)
        sys.exit(1)
    print(format_gap_table(_records_from_csv(csv_path)))
