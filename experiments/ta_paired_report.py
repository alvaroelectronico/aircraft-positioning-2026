"""theory_assisted (v02) vs cached MILP — paired report.

Thin wrapper over experiments/gap_summary.py + paired_report.py that swaps the
heuristic label from v01's ``igvnd_*`` to v02's ``ta_igvnd_*`` before reusing
the canonical gap/summary formatting.  The MILP baseline labels and the
cached-MILP rule are unchanged.

Usage:  py -3 experiments/ta_paired_report.py [results.csv] > report.txt
"""
from __future__ import annotations
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "experiments"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

import gap_summary as gs
import paired_report as pr

_TA_PROFILES = [
    ("wMK",  "milp_job_wMK",  "ta_igvnd_wMK",  "100/1/1  makespan-priority"),
    ("wDLY", "milp_job_wDLY", "ta_igvnd_wDLY", "1/100/1  delay-priority"),
    ("wMOV", "milp_job_wMOV", "ta_igvnd_wMOV", "1/1/100  movement-priority"),
]
gs.PROFILES = _TA_PROFILES
pr.PROFILES = _TA_PROFILES

csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _ROOT / "outputs" / "solutions" / "results.csv"
records = gs._records_from_csv(csv_path)
print(gs.format_gap_table(records))
print()
print(pr.detail_block(records))
