"""Verify both MILP solvers accept and solve a new integer instance.

Generates a small instance with the updated generator, then runs:
  - MILPSolver        (job-level Pyomo model)
  - MILPAircraftSolver (aircraft-level Pyomo model)

Both should reach optimum and the per-aircraft check_solution should pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "input_data"))
sys.path.insert(0, str(_ROOT / "scripts" / "output_data"))
sys.path.insert(0, str(_ROOT / "solvers"))

from generate_benchmark import generate_instance                # noqa: E402
from milp_jobs_solver import MILPSolver                         # noqa: E402
from milp_aircraft_solver import MILPAircraftSolver             # noqa: E402
from check_solution import check_solution                       # noqa: E402


def main() -> None:
    # Small instance: triangle, tight, R=5 — MILP-tractable in <1s
    inst = generate_instance(
        topology="triangle",
        slack="tight",
        n_positions=5,
        n_aircraft=5,
        tasks_range=(3, 5),
        seed=1,
    )
    print(f"  R={len(inst['aircrafts'])}  jobs={len(inst['jobs'])}  "
          f"arcs={len(inst['hangar']['blocking_arcs'])}")
    print(f"  min_separation (from instance): {inst['min_separation']}")
    print(f"  durations sample: {[j['duration'] for j in inst['jobs'][:5]]}")
    print(f"  earliest_start range: "
          f"min={min(a['earliest_start'] for a in inst['aircrafts'])} "
          f"max={max(a['earliest_start'] for a in inst['aircrafts'])}")

    # Set min_separation=1.0 in the config to confirm the JSON value (0.5)
    # actually overrides this fallback when present.
    common = dict(
        min_separation=1.0,
        weight_makespan=0.1,
        weight_delay=1.0,
        weight_movements=10.0,
        time_limit_s=60,
        MIPGap=0.0,
    )

    print("\n=== job-level MILP ===")
    s_job = MILPSolver(backend="gurobi")
    s_job.configure_solver(**common)
    sol_job = s_job.solve(inst)
    print(f"  status={sol_job['status']}  obj={sol_job['objective']}  "
          f"makespan={sol_job['metrics']['makespan']}  "
          f"delay={sol_job['metrics']['total_delay']}  "
          f"mov={sol_job['metrics']['movements']}")
    r_job = check_solution(sol_job, inst)
    print(f"  check_solution overall: {r_job}")

    print("\n=== aircraft-level MILP ===")
    s_ac = MILPAircraftSolver()
    s_ac.configure_solver(**common)
    sol_ac = s_ac.solve(inst)
    print(f"  status={sol_ac['status']}  obj={sol_ac['objective']}  "
          f"makespan={sol_ac['metrics']['makespan']}  "
          f"delay={sol_ac['metrics']['total_delay']}  "
          f"mov={sol_ac['metrics']['movements']}")
    r_ac = check_solution(sol_ac, inst)
    print(f"  check_solution returned: {type(r_ac).__name__}")

    diff = abs(sol_job["objective"] - sol_ac["objective"])
    print(f"\n  parity diff: {diff:.4f}  ({'OK' if diff < 1e-3 else 'MISMATCH'})")


if __name__ == "__main__":
    main()
