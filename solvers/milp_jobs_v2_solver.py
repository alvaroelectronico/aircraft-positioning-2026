"""
MILPJobsV2Solver — wraps the native-gurobipy job-level MILP for the
job-as-scheduling-unit problem (papers/jobs_extension/milp.tex).

Mirrors the contract of MILPAircraftSolver so it slots into the
Application pipeline and run_experiments.py harness transparently.

Usage as a library
------------------
    from solvers.milp_jobs_v2_solver import MILPJobsV2Solver

    solver = MILPJobsV2Solver()
    solver.configure_solver(MIPGap=0.0, TimeLimit=60)
    solution = solver.solve(instance_data)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "models"))

# Keys consumed by this class as model parameters; everything else is
# forwarded verbatim to the Gurobi backend.
_MODEL_KEYS = frozenset({
    "min_separation",
    "weight_makespan",
    "weight_delay",
    "weight_movements",
    "time_limit_s",
})


class MILPJobsV2Solver:
    """Native gurobipy MILP solver for the job-as-scheduling-unit problem."""

    _DEFAULTS: dict = {
        "min_separation":   0.5,
        "weight_makespan":  0.1,
        "weight_delay":     1.0,
        "weight_movements": 10.0,
        "time_limit_s":     None,
    }

    def __init__(self) -> None:
        self._model_params:   dict = dict(self._DEFAULTS)
        self._solver_options: dict = {}

    @property
    def name(self) -> str:
        return "milp_jobs_v2"

    def configure_solver(self, **kwargs) -> None:
        """Set model parameters and/or Gurobi options.

        Model parameters (consumed here):
            min_separation, weight_makespan, weight_delay, weight_movements,
            time_limit_s.

        Anything else (e.g. ``MIPGap``, ``NoRelHeurTime``, ``Threads``) is
        forwarded verbatim to ``m.setParam``.
        """
        for k, v in kwargs.items():
            if k in _MODEL_KEYS:
                self._model_params[k] = v
            else:
                self._solver_options[k] = v

    def get_config(self) -> dict:
        return {**self._model_params, **self._solver_options}

    def solve(self, instance_data: dict) -> dict:
        from milp_jobs_v2_gurobipy import prepare_data, build_model, get_solution  # noqa: E402

        data = prepare_data(
            instance_data,
            self._model_params["min_separation"],
            self._model_params["weight_makespan"],
            self._model_params["weight_delay"],
            self._model_params["weight_movements"],
        )
        m = build_model(data)

        if self._model_params["time_limit_s"] is not None:
            m.setParam("TimeLimit", self._model_params["time_limit_s"])
        for k, v in self._solver_options.items():
            m.setParam(k, v)

        m.optimize()
        return get_solution(m, instance_data)


# ----------------------------------------------------------------------
#  __main__ — standalone debugging
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import json

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "input_data"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "output_data"))
    from instance_io           import load_json as load_instance      # noqa: E402
    from check_solution_jobs_v2 import check_solution, print_check     # noqa: E402

    _default = os.path.join(
        os.path.dirname(__file__), "..",
        "data", "instances_202605_02",
        "scn_triangle_tight_P5_R5", "scn_triangle_tight_P5_R5_seed1.json",
    )
    _path = sys.argv[1] if len(sys.argv) > 1 else _default
    _raw  = load_instance(_path)

    _solver = MILPJobsV2Solver()
    _solver.configure_solver(time_limit_s=60, MIPGap=0.0)
    _sol = _solver.solve(_raw)

    print(json.dumps(
        {"status": _sol["status"], "objective": _sol["objective"],
         "metrics": _sol["metrics"]},
        indent=2,
    ))

    print_check(check_solution(_sol, _raw))
