"""
MILPAircraftSolver — wraps the aircraft-level MILP for aircraft positioning.

Mirrors the contract of ``MILPSolver`` so it is a drop-in replacement in the
``Application`` pipeline and the experiment runner.  Two model backends are
supported:

* ``"gurobipy"`` (default) — native gurobipy build; significantly faster for
  large instances.  Requires gurobipy to be installed and a Gurobi 13+ licence.
* ``"pyomo"``  — the original Pyomo/AbstractModel path, useful as a fallback
  or for comparison.

Usage as a library
------------------
    from solvers.milp_aircraft_solver import MILPAircraftSolver

    solver = MILPAircraftSolver()                  # gurobipy by default
    solver.configure_solver(MIPGap=0.0, TimeLimit=60)
    solution = solver.solve(instance_data)

    solver_pyomo = MILPAircraftSolver(model_backend="pyomo")
    solver_pyomo.configure_solver(MIPGap=0.0, TimeLimit=60)
    solution = solver_pyomo.solve(instance_data)

Usage as a script
-----------------
    python milp_aircraft_solver.py [<instance_path>]
"""
from __future__ import annotations

import os
import sys

# Make sibling model files (milp_aircraft_gurobipy / _pyomo) importable
# regardless of cwd.  After the restructure they live in the same dir.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    "cuts",                 # "none" | "phase1" | "all" — LP-tightening level (gurobipy only)
})


class MILPAircraftSolver:
    """Aircraft-level MILP solver with selectable model backend."""

    _DEFAULTS: dict = {
        "min_separation":   10.0,
        "weight_makespan":  10.0,
        "weight_delay":     100.0,
        "weight_movements": 1.0,
        "time_limit_s":     None,
        "cuts":             "all",
    }

    def __init__(
        self,
        model_backend: str = "gurobipy",
        gurobi_backend: str = "gurobi",
    ) -> None:
        """
        Parameters
        ----------
        model_backend : "gurobipy" | "pyomo"
            Which model-building path to use.  Defaults to "gurobipy".
        gurobi_backend : str
            Pyomo solver name passed to SolverFactory when model_backend=="pyomo".
            Ignored for the gurobipy path.
        """
        if model_backend not in ("gurobipy", "pyomo"):
            raise ValueError(f"model_backend must be 'gurobipy' or 'pyomo', got {model_backend!r}")
        self._model_backend  = model_backend
        self._gurobi_backend = gurobi_backend
        self._model_params: dict = dict(self._DEFAULTS)
        self._solver_options: dict = {}

    def configure_solver(self, **kwargs) -> None:
        """Set model parameters and/or backend solver options.

        Model parameters (consumed here, not forwarded to the backend):
            min_separation, weight_makespan, weight_delay, weight_movements,
            time_limit_s, fix_positions_from.

        All other keyword arguments are forwarded verbatim to the backend
        (e.g. ``MIPGap=0.0``, ``NoRelHeurTime=10``, ``Threads=4``).
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

    # ------------------------------------------------------------------
    # Public solve entry-point
    # ------------------------------------------------------------------

    def solve(self, instance_data: dict) -> dict:
        """Solve *instance_data* and return the solution dict."""
        if self._model_backend == "gurobipy":
            return self._solve_gurobipy(instance_data)
        return self._solve_pyomo(instance_data)

    # ------------------------------------------------------------------
    # gurobipy path
    # ------------------------------------------------------------------

    def _solve_gurobipy(self, instance_data: dict) -> dict:
        from milp_aircraft_gurobipy import prepare_data, build_model, get_solution  # noqa: E402

        data = prepare_data(
            instance_data,
            self._model_params["min_separation"],
            self._model_params["weight_makespan"],
            self._model_params["weight_delay"],
            self._model_params["weight_movements"],
        )
        m = build_model(data, cuts=self._model_params["cuts"])

        # Optional: fix position assignments from a warm solution.
        fix_sol = self._model_params.get("fix_positions_from")
        if fix_sol is not None:
            x = m._v["x"]
            pos_map = {ac["id"]: ac["position"] for ac in fix_sol["aircraft"]}
            for r in data["aircraft"]:
                for p in data["positions"]:
                    val = 1.0 if pos_map.get(r) == p else 0.0
                    x[r, p].lb = val
                    x[r, p].ub = val

        # Apply solver options (TimeLimit, MIPGap, NoRelHeurTime, …)
        if self._model_params["time_limit_s"] is not None:
            m.setParam("TimeLimit", self._model_params["time_limit_s"])
        for k, v in self._solver_options.items():
            m.setParam(k, v)

        m.optimize()
        return get_solution(m, instance_data)

    # ------------------------------------------------------------------
    # Pyomo path (original implementation)
    # ------------------------------------------------------------------

    def _solve_pyomo(self, instance_data: dict) -> dict:
        from pyomo.environ import SolverFactory  # noqa: E402
        from milp_aircraft_pyomo import (        # noqa: E402
            model as _abstract_model,
            prepare_data,
            get_solution,
        )

        data     = prepare_data(
            instance_data,
            self._model_params["min_separation"],
            self._model_params["weight_makespan"],
            self._model_params["weight_delay"],
            self._model_params["weight_movements"],
        )
        instance = _abstract_model.create_instance(data)

        # Optional: fix vAircraftPosition from a warm solution.
        fix_sol = self._model_params.get("fix_positions_from")
        if fix_sol is not None:
            pos_map = {ac["id"]: ac["position"] for ac in fix_sol["aircraft"]}
            for (r, p) in instance.vAircraftPosition:
                if pos_map.get(r) == p:
                    instance.vAircraftPosition[r, p].fix(1)
                else:
                    instance.vAircraftPosition[r, p].fix(0)

        solver = SolverFactory(self._gurobi_backend)
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
    _raw_data      = load_instance(_instance_path)

    _solver = MILPAircraftSolver(model_backend="gurobipy")
    _solver.configure_solver(
        min_separation=0.5,
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
