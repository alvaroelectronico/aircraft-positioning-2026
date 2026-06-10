"""
MILPSolver — wraps the job-level Pyomo MILP for the aircraft positioning problem.

This is the original job-level formulation (one decision variable per job),
kept as the legacy baseline.  The aircraft-level formulation lives in
``solvers/milp_aircraft_solver.py``.

Usage as a library
------------------
    from solvers.milp_jobs_solver import MILPSolver

    solver = MILPSolver()
    solver.configure_solver(NoRelHeurTime=10, MIPGap=10)
    solution = solver.solve(instance_data)   # instance_data: raw dict from load_json

Usage as a script (standalone debugging, no Application needed)
---------------------------------------------------------------
    python milp_jobs_solver.py [<instance_path>]
"""
from __future__ import annotations

import os
import sys

# Sibling model files (milp_jobs_pyomo) live in the same dir after restructure.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from milp_jobs_pyomo import model as _abstract_model, prepare_data, get_solution  # noqa: E402

# Keys consumed by this class as model parameters; everything else is forwarded
# verbatim to the backend solver (e.g. Gurobi options).
# Keys consumed by this class; everything else is forwarded verbatim to the backend.
# time_limit_s is a generic key (set via Application); it is translated to the
# backend-specific option (TimeLimit for Gurobi) inside solve().
_MODEL_KEYS = frozenset({
    "min_separation",
    "weight_makespan",
    "weight_delay",
    "weight_movements",
    "time_limit_s",
    "fix_positions_from",   # solution dict: fix vAircraftPosition from topology solution
    "build_time_limit_s",   # cap on Pyomo create_instance(); see solve()
})


class MILPSolver:
    """Solver for the aircraft positioning MILP via Pyomo.

    Parameters
    ----------
    backend:
        Pyomo solver name passed to ``SolverFactory`` (default ``"gurobi"``).
    """

    _DEFAULTS: dict = {
        "min_separation":   10.0,
        "weight_makespan":  10.0,
        "weight_delay":     100.0,
        "weight_movements": 1.0,
        "time_limit_s":     None,   # None = no limit
        # Cap on Pyomo's create_instance(): on big instances the abstract→concrete
        # expansion alone can take many minutes.  When this elapses we abandon the
        # build and report the problem as infeasible.
        "build_time_limit_s": 60.0,
    }

    def __init__(self, backend: str = "gurobi") -> None:
        self._backend = backend
        self._model_params: dict = dict(self._DEFAULTS)
        self._solver_options: dict = {}

    def configure_solver(self, **kwargs) -> None:
        """Set model parameters and/or backend solver options.

        Model parameters (consumed here, not forwarded to the backend):
            min_separation, weight_makespan, weight_delay, weight_movements

        All other keyword arguments are forwarded verbatim to the backend
        (e.g. ``NoRelHeurTime=10``, ``MIPGap=0.10`` for Gurobi).
        """
        for key, value in kwargs.items():
            if key in _MODEL_KEYS:
                self._model_params[key] = value
            else:
                self._solver_options[key] = value

    @property
    def name(self) -> str:
        """Short identifier used in filenames and the results table."""
        return "milp"

    def get_config(self) -> dict:
        """Return the full configuration (model params + backend options)."""
        return {**self._model_params, **self._solver_options}

    def solve(self, instance_data: dict) -> dict:
        """Solve *instance_data* and return the solution dict.

        Parameters
        ----------
        instance_data:
            Raw instance dict as returned by ``load_json`` / ``load_instance``.

        Returns
        -------
        dict
            Solution dict — see ``get_solution`` in milp_jobs_pyomo.py for schema.
        """
        import threading
        import time as _time
        from pyomo.environ import SolverFactory

        data = prepare_data(
            instance_data,
            self._model_params["min_separation"],
            self._model_params["weight_makespan"],
            self._model_params["weight_delay"],
            self._model_params["weight_movements"],
        )

        # ---- Build the concrete Pyomo instance under a wall-clock cap ----
        build_limit = self._model_params.get("build_time_limit_s")
        build_box: dict = {"instance": None, "error": None}

        def _build():
            try:
                build_box["instance"] = _abstract_model.create_instance(data)
            except Exception as exc:  # noqa: BLE001
                build_box["error"] = exc

        _t_build0 = _time.perf_counter()
        if build_limit is None or build_limit <= 0:
            _build()                                  # no cap requested
            build_elapsed = round(_time.perf_counter() - _t_build0, 3)
        else:
            t = threading.Thread(target=_build, daemon=True)
            t.start()
            t.join(timeout=float(build_limit))
            build_elapsed = round(_time.perf_counter() - _t_build0, 3)
            if t.is_alive():
                # Abandon the still-running build thread (daemon, will die with
                # the process) and report the problem as infeasible so the
                # batch runner can continue with the remaining experiments.
                print(
                    f"  MILP build exceeded {build_limit:.0f}s — abandoning, "
                    f"marking instance as infeasible."
                )
                return {
                    "status":    "feasible solution not found (build timeout)",
                    "objective": 0.0,
                    "mip_gap":   None,
                    "metrics": {
                        "makespan":    0.0,
                        "movements":   0,
                        "total_delay": 0.0,
                    },
                    "aircraft": [],
                    "_build_time_s": build_elapsed,
                    "_solve_time_s": 0.0,
                }

        if build_box["error"] is not None:
            raise build_box["error"]
        instance = build_box["instance"]

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
        sol = get_solution(instance, result)
        sol.setdefault("_build_time_s", build_elapsed)
        return sol


# =============================================================================
#  __main__ — standalone debugging without Application
# =============================================================================

if __name__ == "__main__":
    import json

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "input_data"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "output_data"))
    from instance_io import load_json as load_instance         # noqa: E402
    from check_solution import check_solution, print_check    # noqa: E402
    from plot_schedule import plot_schedule                    # noqa: E402

    _instance_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(
            os.path.dirname(__file__), "..", "data", "instances", "scn_many-medium_seed12_P5_pl20.json"
        )
    )

    _raw_data = load_instance(_instance_path)

    _solver = MILPSolver(backend="gurobi")
    _solver.configure_solver(
        min_separation=1,
        weight_makespan=10.0,
        weight_delay=100.0,
        weight_movements=1.0,
        NoRelHeurTime=10,
        MIPGap=10,
    )

    _solution = _solver.solve(_raw_data)
    print(json.dumps(_solution, indent=2))

    _report = check_solution(_solution, _raw_data)
    print_check(_report)

    plot_schedule(_solution)
