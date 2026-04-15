"""
Application — high-level interface for the aircraft positioning problem.

Encapsulates everything common to any solving method. The specific solver
is injected at construction time (dependency injection), so swapping from
MILP to CP or any other method only requires passing a different solver.

Usage
-----
    from aircraft_positioning import Application
    from solvers.milp_solver import MILPSolver

    app = Application(solver=MILPSolver())
    app.read_data("data/instance.json")
    app.configure_solver(NoRelHeurTime=10, MIPGap=10)
    app.solve()
    app.check_solution()
    app.plot_solution()

Solver contract
---------------
Any solver passed to Application must expose:
    configure_solver(**kwargs) -> None
    solve(instance_data: dict) -> dict   # returns solution dict
"""
from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — make sub-packages importable regardless of cwd
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "scripts" / "input_data"))
sys.path.insert(0, str(_ROOT / "scripts" / "output_data"))
sys.path.insert(0, str(_ROOT / "solvers"))

from instance_io import load_json, read_xlsx                          # noqa: E402
from check_solution import check_solution as _check_fn, print_check  # noqa: E402
from plot_schedule import plot_schedule                               # noqa: E402


class Application:
    """High-level interface for the aircraft positioning problem.

    Parameters
    ----------
    solver:
        A solver instance exposing ``configure_solver(**kwargs)`` and
        ``solve(instance_data: dict) -> dict``.
    """

    def __init__(self, solver) -> None:
        self.instance: dict | None = None   # raw instance data; filled by read_data()
        self.solution: dict | None = None   # solution dict;     filled by solve()
        self._solver = solver

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def read_data(self, path: str | Path) -> None:
        """Load and validate an instance file (JSON or xlsx).

        Parameters
        ----------
        path:
            Path to a ``.json`` or ``.xlsx`` instance file.
        """
        path = Path(path)
        if path.suffix == ".json":
            self.instance = load_json(path)
        else:
            self.instance = read_xlsx(path)

    # ------------------------------------------------------------------
    # Solver
    # ------------------------------------------------------------------

    def configure_solver(self, **kwargs) -> None:
        """Forward configuration kwargs to the solver.

        Model parameters (min_separation, weight_*) and backend options
        (e.g. NoRelHeurTime, MIPGap) are both accepted here and dispatched
        by the solver itself.
        """
        self._solver.configure_solver(**kwargs)

    def solve(self) -> None:
        """Solve the loaded instance and store the solution internally."""
        if self.instance is None:
            raise RuntimeError("No instance loaded. Call read_data() first.")
        self.solution = self._solver.solve(self.instance)

    def get_solution(self) -> dict:
        """Return the solution dict.

        Raises
        ------
        RuntimeError
            If the instance has not been solved yet.
        """
        if self.solution is None:
            raise RuntimeError("No solution available. Call solve() first.")
        return self.solution

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def check_solution(self) -> dict:
        """Verify the solution against all requirements and print the report.

        Returns
        -------
        dict
            Compliance report — see check_solution.py for schema.
        """
        if self.solution is None or self.instance is None:
            raise RuntimeError("Solve the instance before checking the solution.")
        report = _check_fn(self.solution, self.instance)
        print_check(report)
        return report

    def plot_solution(self) -> None:
        """Display the Gantt chart for the current solution."""
        if self.solution is None:
            raise RuntimeError("No solution to plot. Call solve() first.")
        plot_schedule(self.solution)


# =============================================================================
#  __main__ — top-level entry point
# =============================================================================

if __name__ == "__main__":
    import json
    from milp_solver import MILPSolver  # noqa: E402

    _instance_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else str(_ROOT / "data" / "scn_custom_many_tight_pl10.json")
    )

    app = Application(solver=MILPSolver())
    app.read_data(_instance_path)
    app.configure_solver(
        min_separation=10,
        weight_makespan=10.0,
        weight_delay=100.0,
        weight_movements=1.0,
        NoRelHeurTime=10,
        MIPGap=10,
    )
    app.solve()
    print(json.dumps(app.get_solution(), indent=2))
    app.check_solution()
    app.plot_solution()
