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


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _collect(records: list[dict]) -> dict:
    """Return {(type, profile_key): [(g, Δms, Δdelay, Δmov), ...]} plus the
    per-(type) aggregate under profile_key == 'ALL'.

    ``g`` is the relative objective gap ``(MILP-heur)/MILP``; the Δ's are the
    per-component differences ``heuristic − MILP`` (negative ⇒ heuristic
    better on that component)."""
    vals: dict[tuple[str, str], dict] = {}
    for r in records:
        if r.get("error") is None and r.get("objective") is not None:
            vals[(r["instance"], r["experiment"])] = {
                "obj": float(r["objective"]),
                "ms":  _num(r.get("makespan")),
                "dly": _num(r.get("total_delay")),
                "mov": _num(r.get("movements")),
            }

    def diff(a, b):
        return a - b if (a is not None and b is not None) else None

    instances = sorted({r["instance"] for r in records})
    data: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    for inst in instances:
        ctype = _config_type(inst)
        for pkey, milp_label, heur_label, _ in PROFILES:
            m = vals.get((inst, milp_label))
            h = vals.get((inst, heur_label))
            if m is None or h is None or m["obj"] == 0:
                continue
            row = ((m["obj"] - h["obj"]) / m["obj"],
                   diff(h["ms"], m["ms"]), diff(h["dly"], m["dly"]), diff(h["mov"], m["mov"]))
            data[(ctype, pkey)].append(row)
            data[(ctype, "ALL")].append(row)
    return data


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _stat_rows(data: dict, pkey: str) -> list[tuple]:
    """Relative-gap mean/min/max rows for a profile."""
    rows = []
    for (ctype, k), lst in data.items():
        if k != pkey or not lst:
            continue
        gs = [t[0] for t in lst]
        rows.append((ctype, len(gs), sum(gs) / len(gs), min(gs), max(gs)))
    rows.sort(key=lambda x: x[0])
    return rows


def _comp_rows(data: dict, pkey: str) -> list[tuple]:
    """Per-component mean-Δ rows (heuristic − MILP) for a profile."""
    rows = []
    for (ctype, k), lst in data.items():
        if k != pkey or not lst:
            continue
        rows.append((ctype, len(lst),
                     _mean([t[1] for t in lst]),
                     _mean([t[2] for t in lst]),
                     _mean([t[3] for t in lst])))
    rows.sort(key=lambda x: x[0])
    return rows


def _fmt_delta(v) -> str:
    return f"{v:+8.2f}" if v is not None else f"{'-':>8}"


def _write_comp_block(out: io.StringIO, title: str, rows: list[tuple]) -> None:
    out.write(f"  [{title}]\n")
    if not rows:
        out.write("    (no paired MILP/heuristic results yet)\n")
        return
    w_type = max(4, max(len(r[0]) for r in rows))
    out.write(f"    {'Type':<{w_type}}  {'N':>3}  {'Δmakespan':>10}  {'Δdelay':>10}  {'Δmov':>8}\n")
    out.write(f"    {'-' * (w_type + 3 + 10 + 10 + 8 + 6)}\n")
    for ctype, n, dms, ddly, dmov in rows:
        out.write(
            f"    {ctype:<{w_type}}  {n:>3}  {_fmt_delta(dms):>10}  "
            f"{_fmt_delta(ddly):>10}  {_fmt_delta(dmov):>8}\n"
        )


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
    data = _collect(records)
    out = io.StringIO()
    sep = "=" * 66
    out.write(f"{sep}\n")
    out.write("  HEURISTIC vs MILP  —  relative gap per instance type\n")
    out.write("  gap = (MILP_obj - heuristic_obj) / MILP_obj\n")
    out.write("  gap > 0  =>  heuristic BETTER (lower objective);  < 0  => worse\n")
    out.write(f"{sep}\n")
    out.write("  -- Relative objective gap, by weight profile --\n")
    for pkey, _, _, desc in PROFILES:
        _write_block(out, f"{pkey}  ({desc})", _stat_rows(data, pkey))
        out.write("\n")
    out.write("  -- Relative objective gap, aggregated over all profiles --\n")
    _write_block(out, "ALL profiles", _stat_rows(data, "ALL"))
    out.write("\n")
    out.write("  -- Per-component mean Δ (heuristic − MILP); negative = heuristic better --\n")
    out.write("  -- (relative gap is distorted when the optimum delay ≈ 0; read these too)\n")
    for pkey, _, _, desc in PROFILES:
        _write_comp_block(out, f"{pkey}  ({desc})", _comp_rows(data, pkey))
        out.write("\n")
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
    INSTANCE, LABEL, TIMESTAMP, OBJECTIVE, MAKESPAN, MOVEMENTS, DELAY = 0, 2, 3, 6, 7, 8, 9
    latest: dict[tuple[str, str], dict] = {}
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for cells in _csv.reader(fh):
            if len(cells) <= DELAY:
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
                               "objective": obj, "error": None, "timestamp": ts,
                               "makespan": _num(cells[MAKESPAN]),
                               "movements": _num(cells[MOVEMENTS]),
                               "total_delay": _num(cells[DELAY])}
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
