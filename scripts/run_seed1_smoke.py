"""One-off driver: run the four main methods x three weight profiles on
seed1 of every regenerated benchmark configuration.

Methods (recent log):
    milp_baseline, topology_ms6, fas_on_topo, safe_pipeline
Weight profiles:
    default (0.1, 1, 10), wB (1, 10, 0.1), wC (10, 0.1, 1)

Total runs:
    12 configurations x 4 methods x 3 weight profiles = 144 runs.

The log is written under data/logs/seed1_main_methods_<timestamp>.log.
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

# One JSON per subfolder (seed1).
instances = sorted(INSTANCES_DIR.glob("scn_*/scn_*_seed1.json"))

# Four main methods x three weight profiles (default, wB, wC).
INTERESTING = {
    # default profile (0.1, 1, 10)
    "milp_baseline", "topology_ms6", "fas_on_topo", "safe_pipeline",
    # wB: delay-priority (1, 10, 0.1)
    "milp_baseline_wB", "topology_ms6_wB", "fas_on_topo_wB", "safe_pipeline_wB",
    # wC: makespan-priority (10, 0.1, 1)
    "milp_baseline_wC", "topology_ms6_wC", "fas_on_topo_wC", "safe_pipeline_wC",
}
experiments = [e for e in EXPERIMENTS if e["label"] in INTERESTING]

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = _ROOT / "data" / "logs" / f"seed1_main_methods_{timestamp}.log"

print(f"Instances: {len(instances)}")
for p in instances:
    print(f"  {p.relative_to(_ROOT)}")
print(f"\nExperiments: {len(experiments)}")
for e in experiments:
    print(f"  {e['label']}")
print(f"\nLog: {log_path}\n")

summary = run_experiments(instances, experiments, log_path=log_path)
n_ok = sum(1 for r in summary if r.get("error") is None)
print(f"\nDone: {n_ok}/{len(summary)} ok")
print(f"Log saved: {log_path}")
