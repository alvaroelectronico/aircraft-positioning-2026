"""
MILPAircraftSolver — wraps the aircraft-level Pyomo MILP for aircraft positioning.

Mirrors the contract of ``MILPSolver`` so it is a drop-in replacement in the
``Application`` pipeline and the experiment runner.  Internally it relies on
``models/milp_aircraft.py``, where the job concept is eliminated from the
optimisation model: each aircraft is treated as a single block
[s_r, s_r + D_r] with D_r computed offline.  Job-level timings are recovered
deterministically from s_r by walking the precedence chain (see
``milp_aircraft.get_solution``).

Usage as a library
------------------
    from solvers.milp_aircraft_solver import MILPAircraftSolver

    solver = MILPAircraftSolver()
    solver.configure_solver(MIPGap=0.0, TimeLimit=60)
    solution = solver.solve(instance_data)

Usage as a script
-----------------
    python milp_aircraft_solver.py [<instance_path>]
"""
from __future__ import annotations

import os
import sys

# Make the models directory importable regardless of cwd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "models"))

from milp_aircraft import (  # noqa: E402
    model as _abstract_model,
    prepare_data,
    get_solution,
)

# Keys consumed by this class; everything else is forwarded verbatim to the
# backend solver.  time_limit_s is the generic time-limit key set by
# Application; it is translated to the backend option (TimeLimit for Gurobi).
_MODEL_KEYS = frozenset({
    "min_separation",
    "weight_makespan",
    "weight_delay",
    "weight_movements",
    "time_limit_s",
    "fix_positions_from",   # solution dict: fix vAircraftPosition from a prior solution
})


class MILPAircraftSolver:
    """Aircraft-level Pyomo MILP solver."""

    _DEFAULTS: dict = {
        "min_separation":   10.0,
        "weight_makespan":  10.0,
        "weight_delay":     100.0,
        "weight_movements": 1.0,
        "time_limit_s":     None,
    }

    def __init__(self, backend: str = "gurobi") -> None:
        self._backend = backend
        self._model_params: dict = dict(self._DEFAULTS)
        self._solver_options: dict = {}

    def configure_solver(self, **kwargs) -> None:
        """Set model parameters and/or backend solver options.

        Model parameters (consumed here, not forwarded to the backend):
            min_separation, weight_makespan, weight_delay, weight_movements,
            time_limit_s, fix_positions_from.

        All other keyword arguments are forwarded verbatim to the backend
        (e.g. ``MIPGap=0.0`` or ``NoRelHeurTime=10`` for Gurobi).
        """
        for key, value in kwargs.items():
            if key in _MODEL_KEYS:
                self._model_params[key] = value
            else:
                self._solver_options[key] = value

    @property
    def name(self) -> str:
        """Short identifier used in filenames and the results table."""
        return "milp_aircraft"

    def get_config(self) -> dict:
        return {**self._model_params, **self._solver_options}

    def solve(self, instance_data: dict) -> dict:
        """Solve *instance_data* and return the solution dict."""
        from pyomo.environ import SolverFactory

        data = prepare_data(
            instance_data,
            self._model_params["min_separation"],
            self._model_params["weight_makespan"],
            self._model_params["weight_delay"],
            self._model_params["weight_movements"],
        )
        instance = _abstract_model.create_instance(data)

        # Optional: fix vAircraftPosition from a warm solution (e.g. topology).
        fix_sol = self._model_params.get("fix_positions_from")
        if fix_sol is not None:
            pos_map = {ac["id"]: ac["position"] for ac in fix_sol["aircraft"]}
            for (r, p) in instance.vAircraftPosition:
                if pos_map.get(r) == p:
                    instance.vAircraftPosition[r, p].fix(1)
                else:
                    instance.vAircraftPosition[r, p].fix(0)

        solver = SolverFactory(self._backend)
        for k, v in self._solver_options.items():
            solver.options[k] = v
        if self._model_params["time_limit_s"] is not None:
            solver.options["TimeLimit"] = self._model_params["time_limit_s"]

        result = solver.solve(instance, tee=True)
        return get_solution(instance, result, instance_data)


# =============================================================================
#  __main__ — standalone debugging without the Application wrapper
# =============================================================================

if __name__ == "__main__":
    import json

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "input_data"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "output_data"))
    from instance_io import load_json as load_instance      # noqa: E402
    from check_solution import check_solution, print_check  # noqa: E402

    _default_instance = os.path.join(
        os.path.dirname(__file__), "..",
        "data", "instances_202605", "scn_easy_loose_P5_R4",
        "scn_easy_loose_P5_R4_seed1.json",
    )
    _instance_path = sys.argv[1] if len(sys.argv) > 1 else _default_instance

    _raw_data = load_instance(_instance_path)

    _solver = MILPAircraftSolver(backend="gurobi")
    _solver.configure_solver(
        min_separation=1.0,
        weight_makespan=0.1,
        weight_delay=1.0,
        weight_movements=10.0,
        time_limit_s=60,
        MIPGap=0.0,
    )

    _solution = _solver.solve(_raw_data)
    print(json.dumps(_solution, indent=2))

    _report = check_solution(_solution, _raw_data)
    print_check(_report)
