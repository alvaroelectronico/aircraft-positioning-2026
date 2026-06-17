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
for the full feasibility rules.  Read the curated material under
``methods/theory_assisted/inspiration/`` (and its digests in
``methods/theory_assisted/digest/``) for the methodological background
that informs this method.  Do NOT read any other ``methods/<X>/`` —
see CLAUDE.md.
"""
from __future__ import annotations

import os
import sys

# Make sibling modules importable whether loaded as a package or flat file.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from decoder import DecoderContext, decode    # noqa: E402
from brkga import run_brkga                    # noqa: E402


class TheoryAssistedJobSolver:
    """BRKGA with a mixed-chromosome decoder (Candidate C — see jobs/notes/)."""

    name = "theory_assisted_job"

    def __init__(self) -> None:
        self._config: dict = {}
        self._log: list[str] = []

    def configure_solver(self, **kwargs) -> None:
        """Store any tunable parameters.  ``time_limit_s`` is the only
        key Application guarantees to set; everything else is yours."""
        self._config.update(kwargs)

    def get_config(self) -> dict:
        return dict(self._config)

    def get_log(self) -> list[str]:
        return list(self._log)

    def solve(self, instance_data: dict) -> dict:
        """Return a feasible solution dict via the BRKGA decoder pipeline."""
        cfg = self._config
        weights = (
            float(cfg.get("weight_makespan", 0.1)),
            float(cfg.get("weight_delay", 1.0)),
            float(cfg.get("weight_movements", 10.0)),
        )
        ctx = DecoderContext(instance_data, weights)
        self._log = []

        def decode_fn(keys):
            return decode(keys, ctx)

        time_limit = cfg.get("time_limit_s")
        time_limit = 30.0 if time_limit is None else float(time_limit)

        best_sol, _ = run_brkga(
            n_keys=2 * ctx.n_air,
            decode_fn=decode_fn,
            time_limit_s=time_limit,
            seed=int(cfg.get("seed", 0)),
            pop_size=cfg.get("pop_size"),
            log=self._log,
        )
        return best_sol


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

    default = _ROOT / "data" / "instances_202605_02" / \
              "scn_triangle_tight_P5_R5" / "scn_triangle_tight_P5_R5_seed1.json"
    path = sys.argv[1] if len(sys.argv) > 1 else str(default)
    inst = load_json(path)

    solver = TheoryAssistedJobSolver()
    solver.configure_solver(time_limit_s=20)
    sol = solver.solve(inst)
    print_check(check_solution(sol, inst))
