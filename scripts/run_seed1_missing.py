"""Run the two configurations missing from the previous batch:
   scn_triangle_tight_P5_R5  and  scn_two_rows_tight_P5_R10
(seed1 only, same 12 experiments as run_seed1_smoke.py).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "input_data"))
sys.path.insert(0, str(_ROOT / "scripts" / "output_data"))
sys.path.insert(0, str(_ROOT / "solvers"))

from run_experiments import run_experiments, EXPERIMENTS  # noqa: E402

INSTANCES_DIR = _ROOT / "data" / "instances_202605"

instances = [
    INSTANCES_DIR / "scn_triangle_tight_P5_R5"  / "scn_triangle_tight_P5_R5_seed1.json",
    INSTANCES_DIR / "scn_two_rows_tight_P5_R10" / "scn_two_rows_tight_P5_R10_seed1.json",
]
for p in instances:
    assert p.exists(), f"missing: {p}"

INTERESTING = {
    "milp_baseline", "topology_ms6", "fas_on_topo", "safe_pipeline",
    "milp_baseline_wB", "topology_ms6_wB", "fas_on_topo_wB", "safe_pipeline_wB",
    "milp_baseline_wC", "topology_ms6_wC", "fas_on_topo_wC", "safe_pipeline_wC",
}
experiments = [e for e in EXPERIMENTS if e["label"] in INTERESTING]

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = _ROOT / "data" / "logs" / f"seed1_main_methods_extra_{timestamp}.log"

print(f"Instances: {len(instances)}")
for p in instances:
    print(f"  {p.relative_to(_ROOT)}")
print(f"Experiments: {len(experiments)}")
print(f"Log: {log_path}\n")

summary = run_experiments(instances, experiments, log_path=log_path)
n_ok = sum(1 for r in summary if r.get("error") is None)
print(f"\nDone: {n_ok}/{len(summary)} ok")
print(f"Log saved: {log_path}")
