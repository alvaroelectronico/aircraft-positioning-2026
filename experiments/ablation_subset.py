"""Fast ablation subset for the job-level heuristic.

Running the full 120-instance battery against the MILP takes hours, mostly in
the MILP's 60 s timeouts on R20/R30. But **the MILP baseline does not change
when we tweak the heuristic** — so to judge the impact of a heuristic change
we only need to:

  1. re-run the **heuristic** (`igvnd_*`) on a small, stratified subset, and
  2. pair it against the MILP objectives already stored in
     `outputs/solutions/results.csv` (cached from the full battery).

The subset is chosen to span the diagnosed failure modes and the controls:

  - control / easy        : none_R10                 (must stay ≈ 0 %)
  - R5 tight wDLY         : chain / hub R5 cells the MILP closes with delay 0
  - R10 wMK / wDLY losses : chain / hub / two_rows R10 cells with a proven optimum
  - wMOV guards           : chain R10 (deterministic stratum, floor 0)
  - scale guards          : chain R20, hub R30, two_rows R30 (no MILP reference)
  (refreshed 2026-09-02 for the no-Triangle benchmark; triangle/full retired)

Usage:
    py -3 experiments/ablation_subset.py            # run heuristic + report
    py -3 experiments/ablation_subset.py --report   # report only (no re-run)

The report prints the relative-gap and per-component (Δmakespan/Δdelay/Δmov)
tables restricted to the subset, reading both methods from results.csv.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "experiments"))

# Stratified subset (config stem with seed).  Keep small so the heuristic-only
# re-run finishes in tens of minutes, not hours.
SUBSET: list[str] = [
    "scn_none_tight_P5_R10_seed1",        # control: must stay ~0 %
    "scn_chain_tight_P5_R5_seed3",        # R5 tight wDLY: MILP delay 0 with 2 moves
    "scn_chain_tight_P5_R5_seed5",
    "scn_hub_tight_P5_R5_seed1",
    "scn_chain_loose_P5_R10_seed5",       # R10 wMK/wDLY losses (MILP optimal)
    "scn_chain_loose_P5_R10_seed8",
    "scn_chain_medium_P5_R10_seed1",
    "scn_chain_medium_P5_R10_seed10",
    "scn_hub_tight_P5_R10_seed5",
    "scn_hub_loose_P5_R10_seed7",
    "scn_hub_loose_P5_R10_seed9",
    "scn_two_rows_loose_P5_R10_seed1",
    "scn_two_rows_loose_P5_R10_seed7",
    "scn_chain_tight_P5_R10_seed6",       # wMOV guards (deterministic stratum)
    "scn_chain_medium_P5_R10_seed2",
    "scn_chain_loose_P5_R20_seed1",       # scale guards (no MILP reference)
    "scn_hub_loose_P5_R30_seed1",
    "scn_two_rows_loose_P5_R30_seed1",
]

HEUR_LABELS = "igvnd_wMK,igvnd_wDLY,igvnd_wMOV"


def _run_heuristic() -> None:
    inst_filter = ",".join(s + "$" for s in SUBSET)   # exact-stem match
    cmd = [
        sys.executable, str(_ROOT / "experiments" / "run_experiments.py"),
        inst_filter, HEUR_LABELS, "data/instances_202605_02",
    ]
    print(f"Running heuristic on {len(SUBSET)} instances × 3 profiles …\n")
    subprocess.run(cmd, cwd=str(_ROOT))


def _report() -> None:
    from gap_summary import _records_from_csv, format_gap_table
    recs = _records_from_csv(_ROOT / "outputs" / "solutions" / "results.csv")
    subset = set(SUBSET)
    recs = [r for r in recs if r["instance"] in subset]
    print("\n" + "=" * 66)
    print(f"  ABLATION SUBSET  ({len(SUBSET)} instances; MILP reused from results.csv)")
    print("=" * 66)
    print(format_gap_table(recs))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    if "--report" not in sys.argv:
        _run_heuristic()
    _report()
