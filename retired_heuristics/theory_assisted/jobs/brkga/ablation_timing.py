"""Timing-gene cap ablation on the focused subset (controlled v1-vs-v2).

For each (config, seed, profile) it runs the solver at several
``timing_cap_factor`` values.  ``cap_factor = 0.0`` makes the timing genes inert
and reproduces the v1 (Mode-A/C, no timing) behaviour exactly, so it is the
controlled baseline; the other factors are the v2 variants.  The relative
comparison is valid at a reduced per-run budget (same budget across factors);
absolute gaps to the MILP would need the full 60 s.

Prints, per (config, profile), the mean objective over seeds for each cap factor
and the mean gap to the cached MILP, so the best cap can be chosen.

Usage:
    py -3 methods/theory_assisted/jobs/brkga/ablation_timing.py [budget_s]
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_JOBS = _HERE.parent
_ROOT = _JOBS.parent.parent.parent
for _p in (str(_JOBS), str(_ROOT / "shared"), str(_ROOT / "problems" / "jobs")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from instance_io import load_json                       # noqa: E402
from theory_assisted_job import TheoryAssistedJobSolver  # noqa: E402

_CONFIGS = [
    "scn_full_tight_P5_R10",
    "scn_full_tight_P5_R20",
    "scn_triangle_tight_P5_R10",
    "scn_two_rows_tight_P5_R10",
]
_SEEDS = [1, 2, 3]
_PROFILES = {"wMK": (100, 1, 1), "wDLY": (1, 100, 1), "wMOV": (1, 1, 100)}
_CAPS = [0.0, 0.5, 1.0, 2.0]
_INST_ROOT = _ROOT / "data" / "instances_202605_02"


def _milp_objs() -> dict[tuple[str, str], float]:
    """(instance_stem, profile) -> cached MILP objective."""
    out: dict[tuple[str, str], float] = {}
    label_prof = {"milp_job_wMK": "wMK", "milp_job_wDLY": "wDLY", "milp_job_wMOV": "wMOV"}
    latest_ts: dict[tuple[str, str], str] = {}
    with open(_ROOT / "outputs" / "solutions" / "results.csv", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if len(row) <= 9 or row[2] not in label_prof:
                continue
            key = (row[0], label_prof[row[2]])
            try:
                obj = float(row[6])
            except ValueError:
                continue
            if key not in latest_ts or row[3] >= latest_ts[key]:
                latest_ts[key] = row[3]
                out[key] = obj
    return out


def main() -> int:
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    milp = _milp_objs()

    # results[(config, profile, cap)] = list of (obj, gap)
    results: dict[tuple[str, str, float], list[tuple[float, float]]] = defaultdict(list)
    for config in _CONFIGS:
        for seed in _SEEDS:
            stem = f"{config}_seed{seed}"
            inst = load_json(_INST_ROOT / config / f"{stem}.json")
            for prof, (wM, wD, wMov) in _PROFILES.items():
                m = milp.get((stem, prof))
                for cap in _CAPS:
                    s = TheoryAssistedJobSolver()
                    s.configure_solver(time_limit_s=budget, weight_makespan=wM,
                                       weight_delay=wD, weight_movements=wMov,
                                       seed=seed, timing_cap_factor=cap)
                    sol = s.solve(inst)
                    obj = sol["objective"]
                    gap = (m - obj) / m if m else 0.0
                    results[(config, prof, cap)].append((obj, gap))

    print(f"\nTiming-cap ablation (budget {budget:.0f}s/run, seeds {_SEEDS}; "
          f"cap=0 ⇒ v1 baseline). gap=(MILP−obj)/MILP, >0 better.\n")
    hdr = f"{'config':28s} {'prof':5s} " + " ".join(f"cap{c:>4}" for c in _CAPS)
    print(hdr + "    | best")
    for config in _CONFIGS:
        for prof in _PROFILES:
            cells = []
            gaps = {}
            for cap in _CAPS:
                lst = results[(config, prof, cap)]
                mean_gap = sum(g for _, g in lst) / len(lst)
                gaps[cap] = mean_gap
                cells.append(f"{mean_gap*100:>6.1f}%")
            best = max(gaps, key=gaps.get)
            print(f"{config:28s} {prof:5s} " + " ".join(cells) + f"    | cap{best} ({gaps[best]*100:+.1f}% vs v1 {gaps[0.0]*100:+.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
