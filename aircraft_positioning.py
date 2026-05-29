"""
Application — high-level interface for the aircraft positioning problem.

Encapsulates everything common to any solving method. The specific solver
is injected at construction time (dependency injection), so swapping from
MILP to CP or any other method only requires passing a different solver.

Usage
-----
    from aircraft_positioning import Application
    from solvers.milp_jobs_solver import MILPSolver

    app = Application(solver=MILPSolver())
    app.read_data("data/instances/instance.json")
    app.configure_solver(NoRelHeurTime=10, MIPGap=10)
    app.solve()
    app.check_solution()
    app.plot_solution()

Solver contract
---------------
Any solver passed to Application must expose:
    name:                      str   (property) — short identifier, e.g. "milp"
    configure_solver(**kwargs) -> None
    solve(instance_data: dict) -> dict   # returns solution dict
    get_config()               -> dict   # full config (model params + backend options)

    Recognised generic keys for configure_solver (all solvers must honour them):
        time_limit_s : float | None  — wall-clock time limit in seconds (None = no limit)
                                       translated internally to the backend-specific option
"""
from __future__ import annotations

import csv
import datetime
import json
import sys
import time
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
        self.instance: dict | None = None        # raw instance data; filled by read_data()
        self.solution: dict | None = None        # solution dict;     filled by solve()
        self._solver = solver
        self._instance_name: str | None = None   # stem of the loaded file, e.g. "scn_X"
        self._solve_time_s:  float | None = None # wall-clock seconds spent in solve()

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
        self._instance_name = path.stem
        if path.suffix == ".json":
            self.instance = load_json(path)
        else:
            self.instance = read_xlsx(path)

    # ------------------------------------------------------------------
    # Solver
    # ------------------------------------------------------------------

    def configure_solver(self, **kwargs) -> None:
        """Forward configuration kwargs to the solver.

        Generic parameters (handled by every solver):
            time_limit_s (float | None): wall-clock time limit in seconds.

        Model parameters (min_separation, weight_*) and backend-specific options
        (e.g. NoRelHeurTime, MIPGap for Gurobi) are also accepted and dispatched
        by the solver itself.
        """
        self._solver.configure_solver(**kwargs)

    def solve(self) -> None:
        """Solve the loaded instance and store the solution internally."""
        if self.instance is None:
            raise RuntimeError("No instance loaded. Call read_data() first.")
        t0 = time.perf_counter()
        self.solution = self._solver.solve(self.instance)
        self._solve_time_s = round(time.perf_counter() - t0, 3)

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

    def save_solution(
        self,
        solutions_dir: str | Path | None = None,
        label: str | None = None,
    ) -> Path:
        """Persist the solution to disk and update the results summary.

        Two files are written / updated:

        * ``<solutions_dir>/<instance>__<label>__<timestamp>.json``
          Full record: metadata + complete solution dict.

        * ``<solutions_dir>/results.csv``
          One row per run with the key metrics — easy to load with pandas
          for cross-method / cross-instance comparisons.

        Parameters
        ----------
        solutions_dir:
            Directory where files are written.
            Defaults to ``<project_root>/data/solutions/``.
        label:
            Experiment label used in the filename and the CSV ``solver``
            column.  Falls back to the solver's own ``name`` attribute (or
            its class name) when not provided.

        Returns
        -------
        Path
            Path to the JSON file that was written.
        """
        if self.solution is None or self.instance is None:
            raise RuntimeError("No solution to save. Call solve() first.")

        solutions_dir = Path(solutions_dir) if solutions_dir else _ROOT / "data" / "solutions"
        solutions_dir.mkdir(parents=True, exist_ok=True)

        timestamp   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        solver_name = getattr(self._solver, "name", type(self._solver).__name__.lower())
        file_label  = label if label is not None else solver_name
        config      = self._solver.get_config() if hasattr(self._solver, "get_config") else {}

        # ---- JSON (full record) ----------------------------------------
        record = {
            "instance":     self._instance_name,
            "solver":       solver_name,
            "label":        file_label,
            "config":       config,
            "timestamp":    timestamp,
            "solve_time_s": self._solve_time_s,
            **self.solution,
        }
        json_path = solutions_dir / f"{self._instance_name}__{file_label}__{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)

        # ---- CSV (summary row) -----------------------------------------
        metrics = self.solution["metrics"]
        row = {
            "instance":     self._instance_name,
            "solver":       solver_name,
            "label":        file_label,
            "timestamp":    timestamp,
            "solve_time_s": self._solve_time_s,
            "status":       self.solution["status"],
            "objective":    self.solution["objective"],
            "makespan":     metrics["makespan"],
            "movements":    metrics["movements"],
            "total_delay":  metrics["total_delay"],
            "config":       json.dumps(config),
        }
        csv_path = solutions_dir / "results.csv"
        write_header = not csv_path.exists()
        with open(csv_path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(row)

        print(f"Solution saved : {json_path}")
        print(f"Results updated: {csv_path}")

        # ---- LOG (written only when the solver produced one) -----------
        if hasattr(self._solver, "get_log"):
            log_lines = self._solver.get_log()
            if log_lines:
                logs_dir = _ROOT / "data" / "logs_heuristic"
                logs_dir.mkdir(parents=True, exist_ok=True)
                log_path = logs_dir / f"{json_path.stem}.log"
                with open(log_path, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(log_lines) + "\n")
                print(f"Log saved      : {log_path}")

        return json_path


# =============================================================================
#  __main__ — top-level entry point
# =============================================================================

if __name__ == "__main__":
    import argparse

    _parser = argparse.ArgumentParser(description="Aircraft positioning solver")
    _parser.add_argument("instance", nargs="?",
                         default=str(_ROOT / "data" / "instances" / "scn_custom_many_tight_pl10.json"),
                         help="Path to the instance file (.json or .xlsx)")
    _parser.add_argument("--solver", choices=["milp", "constructive"], default="milp",
                         help="Solver to use (default: milp)")
    _parser.add_argument("--time-limit", type=float, default=None,
                         help="Wall-clock time limit in seconds")
    _args = _parser.parse_args()

    if _args.solver == "milp":
        from milp_jobs_solver import MILPSolver  # noqa: E402
        _solver = MILPSolver()
        _solver_config = dict(
            min_separation=10,
            weight_makespan=10.0,
            weight_delay=100.0,
            weight_movements=1.0,
            NoRelHeurTime=10,
            MIPGap=10,
        )
    else:
        from constructive_heuristic import ConstructiveHeuristic  # noqa: E402
        _solver = ConstructiveHeuristic()
        _solver_config = dict(
            min_separation=10,
            weight_makespan=10.0,
            weight_delay=100.0,
            weight_movements=1.0,
            alpha=0.3,
            seed=None,
        )

    if _args.time_limit is not None:
        _solver_config["time_limit_s"] = _args.time_limit

    app = Application(solver=_solver)
    app.read_data(_args.instance)
    app.configure_solver(**_solver_config)
    app.solve()
    app.save_solution()
    app.check_solution()
    app.plot_solution()
