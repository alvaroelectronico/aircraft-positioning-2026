"""Validate the easy_loose_P5_R4 instances:
  - MILP must reach optimal (gap = 0)
  - Constructive heuristic must match the MILP objective

Usage:
    python scripts/tests/validate_easy_instances.py [seed]   # default: all 10
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "input_data"))
sys.path.insert(0, str(_ROOT / "scripts" / "output_data"))
sys.path.insert(0, str(_ROOT / "solvers"))
sys.path.insert(0, str(_ROOT / "models"))

from instance_io import load_json                             # noqa: E402
from milp_solver import MILPSolver                            # noqa: E402
from constructive_heuristic import ConstructiveHeuristic     # noqa: E402


INST_DIR = _ROOT / "data" / "instances_202605" / "scn_easy_loose_P5_R4"
COMMON = dict(
    min_separation=1.0,
    weight_makespan=10.0,
    weight_delay=100.0,
    weight_movements=1.0,
)


def solve_one(seed: int) -> tuple[float, float]:
    path = INST_DIR / f"scn_easy_loose_P5_R4_seed{seed}.json"
    data = load_json(str(path))

    milp = MILPSolver(backend="gurobi")
    milp.configure_solver(**COMMON, MIPGap=0.0, TimeLimit=60)
    sol_m = milp.solve(data)

    heur = ConstructiveHeuristic()
    heur.configure_solver(**COMMON, time_limit_s=5, alpha=0.3, seed=42)
    sol_h = heur.solve(data)

    return sol_m["objective"], sol_h["objective"]


def main() -> None:
    seeds = [int(sys.argv[1])] if len(sys.argv) > 1 else list(range(1, 11))
    print(f"{'seed':>4}  {'MILP obj':>12}  {'Heur obj':>12}  {'gap %':>8}  status")
    print("-" * 60)
    for s in seeds:
        m, h = solve_one(s)
        gap = (h - m) / max(1e-9, abs(m)) * 100
        ok = "OK" if abs(gap) < 1e-3 else ("HEUR>MILP" if gap > 0 else "HEUR<MILP")
        print(f"{s:>4}  {m:>12.4f}  {h:>12.4f}  {gap:>7.3f}%  {ok}")


if __name__ == "__main__":
    main()
