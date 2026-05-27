"""Quick parity check: aircraft-level MILP vs job-level MILP on the easy R=4 set.

Both should reach gap=0 and identical objective on these trivial instances.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "input_data"))
sys.path.insert(0, str(_ROOT / "solvers"))
sys.path.insert(0, str(_ROOT / "models"))

from instance_io import load_json                             # noqa: E402
from milp_solver import MILPSolver                            # noqa: E402
from milp_aircraft_solver import MILPAircraftSolver           # noqa: E402


INST_DIR = _ROOT / "data" / "instances_202605" / "scn_easy_loose_P5_R4"
COMMON = dict(
    min_separation=1.0,
    weight_makespan=10.0,
    weight_delay=100.0,
    weight_movements=1.0,
)


def solve(seed: int) -> tuple[float, float]:
    path = INST_DIR / f"scn_easy_loose_P5_R4_seed{seed}.json"
    data = load_json(str(path))

    job_mlp = MILPSolver(backend="gurobi")
    job_mlp.configure_solver(**COMMON, MIPGap=0.0, TimeLimit=60)
    sol_job = job_mlp.solve(data)

    ac_mlp = MILPAircraftSolver()
    ac_mlp.configure_solver(**COMMON, MIPGap=0.0, TimeLimit=60)
    sol_ac = ac_mlp.solve(data)

    return sol_job["objective"], sol_ac["objective"]


def main() -> None:
    seeds = [int(sys.argv[1])] if len(sys.argv) > 1 else list(range(1, 11))
    print(f"{'seed':>4}  {'job-MILP':>10}  {'ac-MILP':>10}  {'diff':>10}  status")
    print("-" * 60)
    for s in seeds:
        oj, oa = solve(s)
        diff = abs(oj - oa)
        ok = "OK" if diff < 1e-3 else "MISMATCH"
        print(f"{s:>4}  {oj:>10.4f}  {oa:>10.4f}  {diff:>10.4f}  {ok}")


if __name__ == "__main__":
    main()
