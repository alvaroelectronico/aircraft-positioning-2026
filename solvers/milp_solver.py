"""
MILPSolver — wraps the Pyomo MILP model for the aircraft positioning problem.

Usage as a library
------------------
    from solvers.milp_solver import MILPSolver

    solver = MILPSolver()
    solver.configure_solver(NoRelHeurTime=10, MIPGap=10)
    solution = solver.solve(instance_data)   # instance_data: raw dict from load_json

Usage as a script (standalone debugging, no Application needed)
---------------------------------------------------------------
    python milp_solver.py [<instance_path>]
"""
from __future__ import annotations

import os
import sys

# Make the models directory importable regardless of cwd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "models"))

from milp_pyomo import model as _abstract_model, prepare_data, get_solution  # noqa: E402

# Keys consumed by this class as model parameters; everything else is forwarded
# verbatim to the backend solver (e.g. Gurobi options).
_MODEL_KEYS = frozenset({"min_separation", "weight_makespan", "weight_delay", "weight_movements"})


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

    def solve(self, instance_data: dict) -> dict:
        """Solve *instance_data* and return the solution dict.

        Parameters
        ----------
        instance_data:
            Raw instance dict as returned by ``load_json`` / ``load_instance``.

        Returns
        -------
        dict
            Solution dict — see ``get_solution`` in milp_pyomo.py for schema.
        """
        from pyomo.environ import SolverFactory

        data = prepare_data(
            instance_data,
            self._model_params["min_separation"],
            self._model_params["weight_makespan"],
            self._model_params["weight_delay"],
            self._model_params["weight_movements"],
        )
        instance = _abstract_model.create_instance(data)
        solver = SolverFactory(self._backend)
        for k, v in self._solver_options.items():
            solver.options[k] = v
        result = solver.solve(instance, tee=True)
        return get_solution(instance, result)


# =============================================================================
#  __main__ — standalone debugging without Application
# =============================================================================

if __name__ == "__main__":
    import json

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "input_data"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "output_data"))
    from load_instance import load_instance                    # noqa: E402
    from check_solution import check_solution, print_check    # noqa: E402
    from plot_schedule import plot_schedule                    # noqa: E402

    _instance_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(
            os.path.dirname(__file__), "..", "data", "scn_custom_many_tight_pl10"
        )
    )

    _raw_data = load_instance(_instance_path)

    _solver = MILPSolver(backend="gurobi")
    _solver.configure_solver(
        min_separation=10,
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
