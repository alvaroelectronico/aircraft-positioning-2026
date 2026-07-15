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
that originally informed this method — those folders stay in the
theory_assisted scaffold and are out of scope for this graduated
method (see CLAUDE.md).  Do NOT read any other ``methods/<X>/`` —
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
from brkga_engine import run_brkga             # noqa: E402


class BRKGAJobSolver:
    """BRKGA with a mixed-chromosome decoder (Candidate C — see jobs/notes/)."""

    name = "brkga_job"

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
        w_mk = float(cfg.get("weight_makespan", 0.1))
        w_dly = float(cfg.get("weight_delay", 1.0))
        w_mov = float(cfg.get("weight_movements", 10.0))
        weights = (w_mk, w_dly, w_mov)

        # Profile-gated Mode-C (P1).  Mode C trades +2 movements (and a +delta
        # job extension) for a cheaper access window; it only pays off when a
        # movement is cheap relative to the makespan/delay it saves.  Enable it
        # iff the movement weight does NOT dominate — W^S <= max(W^M, W^D).
        # This enables Mode C under wMK/wDLY (1 <= 100) and disables it under
        # wMOV (100 <= 1 is false) and the default profile (10 <= 1 is false),
        # where the v2 battery showed it is pure overhead (the fixpoint decode
        # is ~8x slower and starves the GA without buying objective gains).
        # An explicit allow_mode_c in the config overrides the gate (ablations).
        if "allow_mode_c" in cfg:
            allow_mode_c = bool(cfg["allow_mode_c"])
        else:
            allow_mode_c = w_mov <= max(w_mk, w_dly)

        ctx = DecoderContext(instance_data, weights, allow_mode_c=allow_mode_c)
        self._log = []
        self._log.append(f"allow_mode_c={allow_mode_c} (wMK={w_mk} wDLY={w_dly} wMOV={w_mov})")

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

    _HERE = Path(__file__).resolve().parent              # methods/brkga_v02/jobs/
    _ROOT = _HERE.parent.parent.parent                   # repo root
    sys.path.insert(0, str(_ROOT / "shared"))            # instance_io
    sys.path.insert(0, str(_ROOT / "problems" / "jobs")) # checker

    from instance_io import load_json                    # noqa: E402
    from checker     import check_solution, print_check  # noqa: E402

    default = _ROOT / "data" / "instances_202605_02" / \
              "scn_triangle_tight_P5_R5" / "scn_triangle_tight_P5_R5_seed1.json"
    path = sys.argv[1] if len(sys.argv) > 1 else str(default)
    inst = load_json(path)

    solver = BRKGAJobSolver()
    solver.configure_solver(time_limit_s=20)
    sol = solver.solve(inst)
    print_check(check_solution(sol, inst))
