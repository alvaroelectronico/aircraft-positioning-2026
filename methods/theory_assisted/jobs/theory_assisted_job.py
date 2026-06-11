"""Theory-assisted solver for paper #2 (job-level extension).

STUB — replace ``solve`` with your implementation.

The class implements the contract from ``shared/application.py``:

    name                       : str  (property)
    configure_solver(**kwargs) -> None
    solve(instance_data)       -> dict   # solution
    get_config()               -> dict

The solution dict must be in the shape consumed by
``problems/jobs/checker.py``:

    {
        "status":    str,                   # solver's own status string
        "objective": float | None,          # weighted objective (see weights below)
        "metrics":   {
            "makespan":     float,
            "total_delay":  float,
            "movements":    int,
        },
        "aircraft": [
            {
                "id":       str,
                "position": str,
                "jobs": [
                    {"id": str, "start": float, "finish": float, ...}
                ],
            },
            ...
        ],
    }

Read ``problems/jobs/problem_statement.md`` and ``problems/jobs/checker.py``
for the full feasibility rules.  Read ``literature_review/`` for the
methodological background that informs this method.  Do NOT read
``methods/manual/`` or ``methods/autoresearch/`` — see CLAUDE.md.
"""
from __future__ import annotations


class TheoryAssistedJobSolver:
    """Stub solver.  Replace ``solve`` with your implementation."""

    name = "theory_assisted_job"

    def __init__(self) -> None:
        self._config: dict = {}

    def configure_solver(self, **kwargs) -> None:
        """Store any tunable parameters.  ``time_limit_s`` is the only
        key Application guarantees to set; everything else is yours."""
        self._config.update(kwargs)

    def get_config(self) -> dict:
        return dict(self._config)

    def solve(self, instance_data: dict) -> dict:
        """Return a solution dict (see module docstring for the shape).

        Implementation guidance:
        - Read the instance: ``instance_data`` is the JSON loaded by
          ``shared/instance_io.load_json`` from a path under
          ``problems/jobs/instances/``.
        - Honour ``self._config.get("time_limit_s")``.
        - Honour the weight keys
          ``weight_makespan`` / ``weight_delay`` / ``weight_movements``
          when computing ``objective``; see the contract in
          ``shared/application.py``.
        - Return a feasible solution per ``problems/jobs/checker.py``.
        """
        raise NotImplementedError(
            "TheoryAssistedJobSolver.solve is not yet implemented. "
            "See methods/theory_assisted/README.md for the start sequence."
        )


if __name__ == "__main__":
    # Minimal smoke-test entry point.  Once solve() is implemented,
    # this should print the objective and pass the checker.
    import sys
    from pathlib import Path

    _HERE = Path(__file__).resolve().parent              # methods/theory_assisted/jobs/
    _ROOT = _HERE.parent.parent.parent                   # repo root
    sys.path.insert(0, str(_ROOT / "shared"))            # instance_io
    sys.path.insert(0, str(_ROOT / "problems" / "jobs")) # checker

    from instance_io import load_json                    # noqa: E402
    from checker     import check_solution, print_check  # noqa: E402

    default = _ROOT / "problems" / "jobs" / "instances" / \
              "scn_triangle_tight_P5_R5" / "scn_triangle_tight_P5_R5_seed1.json"
    path = sys.argv[1] if len(sys.argv) > 1 else str(default)
    inst = load_json(path)

    solver = TheoryAssistedJobSolver()
    solver.configure_solver(time_limit_s=20)
    sol = solver.solve(inst)
    print_check(check_solution(sol, inst))
