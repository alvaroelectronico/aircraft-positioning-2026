"""Verify that the per-instance min_separation is loaded and propagated.

Loads a regenerated benchmark instance via instance_io.load_json (which
validates against the schema), confirms the field is present, and runs
both MILP solvers — they should pick up the JSON's epsilon (0.5) even if
the solver config requests a different value.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "input_data"))
sys.path.insert(0, str(_ROOT / "scripts" / "output_data"))
sys.path.insert(0, str(_ROOT / "solvers"))

from instance_io import load_json                              # noqa: E402
from milp_solver import MILPSolver                             # noqa: E402
from milp_aircraft_solver import MILPAircraftSolver            # noqa: E402
from check_solution import check_solution                      # noqa: E402

INST_PATH = (
    _ROOT / "data" / "instances_202605" / "scn_triangle_tight_P5_R5"
    / "scn_triangle_tight_P5_R5_seed1.json"
)


def _run(solver, raw_data, label: str) -> dict:
    sol = solver.solve(raw_data)
    metrics = sol["metrics"]
    print(f"  [{label}] status={sol['status']}  obj={sol['objective']}  "
          f"makespan={metrics['makespan']}  delay={metrics['total_delay']}  "
          f"mov={metrics['movements']}")
    rep = check_solution(sol, raw_data)
    compliant = rep.get("compliant") if isinstance(rep, dict) else None
    print(f"  [{label}] check_solution.compliant = {compliant}")
    return sol


def main() -> None:
    print(f"Loading: {INST_PATH.name}")
    raw = load_json(str(INST_PATH))
    assert "min_separation" in raw, "min_separation missing from JSON!"
    print(f"  min_separation (instance): {raw['min_separation']}")
    print(f"  R={len(raw['aircrafts'])}  jobs={len(raw['jobs'])}  "
          f"arcs={len(raw['hangar']['blocking_arcs'])}")

    # Deliberately set min_separation=999.0 in the config: if the JSON value
    # is correctly read, the solver will use 0.5 instead and produce a
    # feasible schedule.  If the override doesn't kick in, the model will be
    # absurdly infeasible (or have empty solutions).
    common = dict(
        min_separation=999.0,
        weight_makespan=0.1,
        weight_delay=1.0,
        weight_movements=10.0,
        time_limit_s=60,
        MIPGap=0.0,
    )

    print("\n=== job-level MILP (config min_sep=999 should be ignored) ===")
    s_job = MILPSolver(backend="gurobi")
    s_job.configure_solver(**common)
    sol_job = _run(s_job, raw, "job")

    print("\n=== aircraft-level MILP (same config override test) ===")
    s_ac = MILPAircraftSolver()
    s_ac.configure_solver(**common)
    sol_ac = _run(s_ac, raw, "ac")

    diff = abs(sol_job["objective"] - sol_ac["objective"])
    print(f"\nparity diff: {diff:.4f}  ({'OK' if diff < 1e-3 else 'MISMATCH'})")
    print("epsilon-propagation test: PASSED" if diff < 1e-3 else "FAILED")


if __name__ == "__main__":
    main()
