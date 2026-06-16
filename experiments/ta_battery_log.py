"""Single consolidated battery log for the theory_assisted method (v02/v03).

Emits ONE ``.log`` in the structure of the v01 reference
(``instances_main_methods_*_iterated_greedy_vnd_v01.log``):

  1. EXPERIMENT CONFIGURATIONS header (git state, instance order, weights),
  2. HEURISTIC vs MILP relative-gap tables (per type × profile + Δ components),
  3. SUMMARY — a compact one-row-per-run table, seed-first, with the cached
     **MILP row interleaved** before each heuristic row (instance × profile),
     and the per-instance gap on the heuristic row.

It reads ``outputs/solutions/results.csv`` so it works *during* a running
battery (partial) and after it finishes (full).  The shared ``gap_summary`` /
``paired_report`` modules are hard-wired to v01's ``igvnd_*`` labels, so this
wrapper swaps in the ``ta_igvnd_*`` labels (leaving those modules untouched,
since the paper's v01 reports depend on them).

Usage:
    py -3 experiments/ta_battery_log.py            # -> outputs/logs/ta_battery_202605_02.log
    py -3 experiments/ta_battery_log.py <out.log> [results.csv]
"""
from __future__ import annotations

import csv as _csv
import io
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "experiments"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

import gap_summary as gs

# (profile key, MILP label, heuristic label, description)
_PROFILES = [
    ("wMK",  "milp_job_wMK",  "ta_igvnd_wMK",  "100/1/1  makespan-priority"),
    ("wDLY", "milp_job_wDLY", "ta_igvnd_wDLY", "1/100/1  delay-priority"),
    ("wMOV", "milp_job_wMOV", "ta_igvnd_wMOV", "1/1/100  movement-priority"),
]
gs.PROFILES = _PROFILES  # so format_gap_table pairs ta_igvnd_* vs milp_job_*

_WEIGHTS = {"ta_igvnd_wMK": (100, 1, 1), "ta_igvnd_wDLY": (1, 100, 1),
            "ta_igvnd_wMOV": (1, 1, 100)}
_WANTED = {lbl for _, ml, hl, _ in _PROFILES for lbl in (ml, hl)}

# results.csv column layout (positional; the ledger has no header)
_C_INST, _C_LABEL, _C_TS, _C_TIME, _C_STATUS, _C_OBJ, _C_MK, _C_MOV, _C_DLY = \
    0, 2, 3, 4, 5, 6, 7, 8, 9


def _git_short() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=str(_ROOT), capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "?"
    except Exception:  # noqa: BLE001
        return "?"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _read_runs(csv_path: Path) -> dict:
    """Latest run per (instance, label) for the labels we care about.

    Each value: {obj, makespan, total_delay, movements, status, time}."""
    latest: dict[tuple[str, str], dict] = {}
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for c in _csv.reader(fh):
            if len(c) <= _C_DLY or c[_C_LABEL] not in _WANTED:
                continue
            obj = _num(c[_C_OBJ])
            if obj is None:
                continue
            key = (c[_C_INST], c[_C_LABEL])
            ts = c[_C_TS]
            if key not in latest or ts >= latest[key]["ts"]:
                latest[key] = {
                    "ts": ts, "obj": obj,
                    "makespan": _num(c[_C_MK]), "total_delay": _num(c[_C_DLY]),
                    "movements": _num(c[_C_MOV]), "status": c[_C_STATUS],
                    "time": _num(c[_C_TIME]),
                }
    return latest


def _seed(stem: str) -> int:
    m = re.search(r"_seed(\d+)$", stem)
    return int(m.group(1)) if m else 0


def _type(stem: str) -> str:
    return re.sub(r"_seed\d+$", "", stem)


def _config_header(runs: dict) -> str:
    n_heur = sum(1 for (_, lbl) in runs if lbl in _WEIGHTS)
    insts = {inst for (inst, lbl) in runs if lbl in _WEIGHTS}
    sep = "=" * 118
    b = io.StringIO()
    b.write(f"{sep}\n")
    b.write("  EXPERIMENT CONFIGURATIONS  (3 experiments — theory_assisted ta_igvnd_*)\n")
    b.write(f"  Code state (git): {_git_short()}\n")
    b.write("  Instance order  : by seed, then config (seed1 of all types first)\n")
    b.write(f"  Heuristic runs in results.csv so far: {n_heur}  over {len(insts)} instance(s)\n")
    b.write(f"{sep}\n")
    b.write("  Shared parameters:\n")
    b.write("    time_limit_s=60               NoRelHeurTime=0\n")
    b.write("    MIPGap=0.0                    seed=1\n\n")
    b.write("  Per-experiment parameters:\n")
    b.write("  Label          Solver                      weight_makespan  weight_delay  weight_movements\n")
    b.write("  " + "-" * 88 + "\n")
    for lbl, (m, d, s) in _WEIGHTS.items():
        b.write(f"  {lbl:<14} IteratedGreedyVNDJobSolver  {m:<16} {d:<13} {s:<15}\n")
    b.write(f"{sep}\n\n")
    return b.getvalue()


def _gap_tables(runs: dict) -> str:
    records = [{"instance": inst, "experiment": lbl, "error": None,
                "objective": r["obj"], "makespan": r["makespan"],
                "total_delay": r["total_delay"], "movements": r["movements"]}
               for (inst, lbl), r in runs.items()]
    return gs.format_gap_table(records)


def _fmt(v, nd=2, w=10):
    return f"{'-':>{w}}" if v is None else f"{v:>{w}.{nd}f}"


def _summary(runs: dict) -> str:
    """Compact one-row-per-run table, seed-first, MILP interleaved before
    each heuristic row, gap on the heuristic row."""
    instances = sorted({inst for (inst, _) in runs}, key=lambda s: (_seed(s), _type(s)))
    w_inst = max([len(i) for i in instances], default=20)
    w_exp = max([len(l) for (_, l) in runs], default=14)
    sep = "=" * 118
    b = io.StringIO()
    b.write(f"{sep}\n")
    n_pairs = sum(1 for inst in instances for _, ml, hl, _ in _PROFILES
                  if (inst, hl) in runs)
    b.write(f"  SUMMARY  —  {n_pairs} heuristic run(s) vs cached MILP "
            f"(MILP row interleaved; gap on the heur row)\n")
    b.write(f"{sep}\n")
    hdr = (f"  {'Instance':<{w_inst}}  {'Experiment':<{w_exp}}  {'Status':<10}  "
           f"{'Obj':>11}  {'Makespan':>9}  {'Delay':>9}  {'Mov':>4}  {'Gap':>8}  {'Time(s)':>7}")
    b.write(hdr + "\n")
    b.write("  " + "-" * (len(hdr) - 2) + "\n")
    for inst in instances:
        for pkey, ml, hl, _ in _PROFILES:
            m = runs.get((inst, ml))
            h = runs.get((inst, hl))
            for lbl, r, gap in ((ml, m, None),
                                (hl, h,
                                 ((m["obj"] - h["obj"]) / m["obj"])
                                 if (m and h and m["obj"]) else None)):
                if r is None:
                    continue
                mov = "" if r["movements"] is None else f"{int(r['movements']):>4}"
                gtxt = "-" if gap is None else f"{gap*100:+.2f}%"
                ttxt = "-" if r["time"] is None else f"{r['time']:.1f}"
                b.write(f"  {inst:<{w_inst}}  {lbl:<{w_exp}}  {str(r['status'])[:10]:<10}  "
                        f"{_fmt(r['obj'], 2, 11)}  {_fmt(r['makespan'], 2, 9)}  "
                        f"{_fmt(r['total_delay'], 2, 9)}  {mov:>4}  {gtxt:>8}  {ttxt:>7}\n")
    b.write(f"{sep}\n")
    return b.getvalue()


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        _ROOT / "outputs" / "logs" / "ta_battery_202605_02.log"
    csv_path = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        _ROOT / "outputs" / "solutions" / "results.csv"

    runs = _read_runs(csv_path)
    b = io.StringIO()
    b.write(_config_header(runs))
    b.write(_gap_tables(runs))
    b.write("\n")
    b.write(_summary(runs))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(b.getvalue(), encoding="utf-8")
    print(f"wrote {out_path}  ({len(runs)} run rows)")


if __name__ == "__main__":
    main()
