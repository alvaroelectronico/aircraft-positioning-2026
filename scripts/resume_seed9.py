"""
resume_seed9.py

Retries the 3 failed runs from run_experiments_20260526_212343.log:
  scn_full_tight_P5_R20_seed9     x milp_baseline    (aborted)
  scn_full_tight_P5_R20_seed9     x milp_baseline_wB (aborted)
  scn_triangle_tight_P5_R30_seed9 x fas_on_topo_wC   (OOM)

Also re-runs topology_ms6_wC and safe_pipeline_wC for R30 to rebuild
the warm-cache dependency and update the pipeline result if fas succeeds.

Appends a RESUME section to run_experiments_20260526_212343.log.
"""
from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "solvers"))
sys.path.insert(0, str(_ROOT / "scripts" / "input_data"))
sys.path.insert(0, str(_ROOT / "scripts" / "output_data"))

from run_experiments import (   # noqa: E402
    run_experiments,
    EXPERIMENTS,
    _format_summary,
)
from aircraft_positioning import Application   # noqa: E402  (sets up remaining paths)

EXISTING_LOG = _ROOT / "data" / "logs" / "run_experiments_20260526_212343.log"

_INST_R20 = (
    _ROOT / "data" / "instances_202605"
    / "scn_full_tight_P5_R20" / "scn_full_tight_P5_R20_seed9.json"
)
_INST_R30 = (
    _ROOT / "data" / "instances_202605"
    / "scn_triangle_tight_P5_R30" / "scn_triangle_tight_P5_R30_seed9.json"
)

_by_label = {e["label"]: e for e in EXPERIMENTS}

# R20: standalone MILP runs, no warm-cache dependencies
EXPS_R20 = [_by_label[l] for l in ("milp_baseline", "milp_baseline_wB")]

# R30: topology_ms6_wC must run first to populate the cache for fas_on_topo_wC;
#      safe_pipeline_wC follows to pick up any improvement from the new fas result.
EXPS_R30 = [_by_label[l] for l in ("topology_ms6_wC", "fas_on_topo_wC", "safe_pipeline_wC")]


if __name__ == "__main__":
    solutions_dir = _ROOT / "data" / "solutions"

    print(f"\n{'='*66}")
    print("  RESUME — retrying 3 failed runs from seed9 batch")
    print(f"  Log: {EXISTING_LOG.name}")
    print(f"{'='*66}\n")

    summary_r20 = run_experiments([_INST_R20], EXPS_R20, solutions_dir=solutions_dir)
    summary_r30 = run_experiments([_INST_R30], EXPS_R30, solutions_dir=solutions_dir)

    all_new = summary_r20 + summary_r30

    # Append a RESUME section to the existing log
    buf = io.StringIO()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    buf.write(f"\n\n{'='*66}\n")
    buf.write(f"  RESUME — {ts}  ({len(all_new)} re-runs)\n")
    buf.write(
        f"  Retried: milp_baseline, milp_baseline_wB (scn_full_tight_P5_R20_seed9)\n"
        f"           topology_ms6_wC, fas_on_topo_wC, safe_pipeline_wC"
        f" (scn_triangle_tight_P5_R30_seed9)\n"
    )
    buf.write(f"{'='*66}\n")
    _format_summary(buf, all_new)

    with EXISTING_LOG.open("a", encoding="utf-8") as fh:
        fh.write(buf.getvalue())

    print(f"\nAppended to: {EXISTING_LOG}")
