"""Theory-assisted solver for paper #2 (job-level extension).

Candidate C — BRKGA with a mixed-chromosome decoder and a greedy/NEH warm-start
(second independent, isolated attempt; see ``methods/theory_assisted/CLAUDE.md``
and ``jobs/notes/design.md``).

The class implements the contract from ``shared/application.py``:

    name                       : str  (property)
    configure_solver(**kwargs) -> None
    solve(instance_data)       -> dict   # solution
    get_config()               -> dict

The solution dict shape consumed by ``problems/jobs/checker.py`` is built by
``brkga.decoder.to_solution_dict`` (aircraft-level start/finish included, which
the checker requires for RQ07/RQ08).

Implementation lives under ``methods/theory_assisted/jobs/brkga/``:
``instance`` (model) · ``state`` · ``windows`` (interval algebra) · ``access``
(Mode-A/B/C semantics, faithful to the checker) · ``decoder`` · ``warm_start``
(greedy/NEH seed) · ``engine`` (own BRKGA loop) · ``smoke`` (validation).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the sibling ``brkga`` package importable when this module is loaded by
# experiments/run_experiments.py (by file path) or run directly.  Only this
# method's own ``jobs`` directory is added — never another method's path.  The
# repo-relative ``problems/jobs`` (the compliance checker) is also ensured on
# the path because the Mode-C improvement validates candidates with the real
# checker; ``shared`` likewise for the instance loader in __main__.
_HERE = Path(__file__).resolve().parent              # methods/theory_assisted/jobs/
_ROOT = _HERE.parent.parent.parent                   # repo root
for _p in (str(_HERE), str(_ROOT / "problems" / "jobs"), str(_ROOT / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from brkga.instance import build_model               # noqa: E402
from brkga.decoder import to_solution_dict           # noqa: E402
from brkga.engine import run_brkga                   # noqa: E402


class TheoryAssistedJobSolver:
    """BRKGA solver (Candidate C)."""

    name = "theory_assisted_job"

    def __init__(self) -> None:
        self._config: dict = {}

    def configure_solver(self, **kwargs) -> None:
        """Store tunable parameters.  ``time_limit_s`` is guaranteed by
        Application; ``weight_makespan`` / ``weight_delay`` /
        ``weight_movements`` and ``seed`` are also honoured."""
        self._config.update(kwargs)

    def get_config(self) -> dict:
        return dict(self._config)

    def solve(self, instance_data: dict) -> dict:
        model = build_model(instance_data)

        # Fitness uses the CONFIGURED weights, not the application defaults.
        weights = {
            "makespan": float(self._config.get("weight_makespan", 0.1)),
            "delay": float(self._config.get("weight_delay", 1.0)),
            "movements": float(self._config.get("weight_movements", 10.0)),
        }
        time_limit = self._config.get("time_limit_s") or 60.0
        seed = int(self._config.get("seed", 1))

        # Profile gate (derived empirically here, not from any other method):
        # Mode C buys time (delay/makespan) at the price of +2 movements per
        # access.  When the movement weight dominates the time weights (the wMOV
        # profile) that trade never pays, and the Mode-C build's per-rear
        # overhead only steals BRKGA generations from the Mode-A search — so
        # disable it and keep the full generation budget.  An explicit
        # ``allow_mode_c`` config value overrides the gate.
        wmov = weights["movements"]
        gate = wmov <= max(weights["makespan"], weights["delay"])
        allow_mode_c = bool(self._config.get("allow_mode_c", gate))

        # BRKGA searches assignment + sequencing.  With Mode-C enabled the
        # fitness uses the in-sweep Mode-C decoder validated by the real checker
        # (see brkga/decoder.decode); otherwise the fast Mode-A-only decoder.
        obj, state, generations = run_brkga(
            model, weights, float(time_limit), seed=seed,
            allow_mode_c=allow_mode_c,
            instance=instance_data if allow_mode_c else None,
        )
        mode = "A+C" if allow_mode_c else "A"
        status = f"brkga ({generations} generations, mode {mode})"
        return to_solution_dict(state, model, weights, status)


if __name__ == "__main__":
    # Minimal smoke-test entry point.
    _ROOT = _HERE.parent.parent.parent                   # repo root
    sys.path.insert(0, str(_ROOT / "shared"))            # instance_io
    sys.path.insert(0, str(_ROOT / "problems" / "jobs")) # checker

    from instance_io import load_json                    # noqa: E402
    from checker import check_solution, print_check       # noqa: E402

    default = _ROOT / "data" / "instances_202605_02" / \
        "scn_triangle_tight_P5_R5" / "scn_triangle_tight_P5_R5_seed1.json"
    path = sys.argv[1] if len(sys.argv) > 1 else str(default)
    inst = load_json(path)

    solver = TheoryAssistedJobSolver()
    solver.configure_solver(time_limit_s=10, weight_makespan=1, weight_delay=100,
                            weight_movements=1, seed=1)
    sol = solver.solve(inst)
    print(f"objective = {sol['objective']:.2f}  metrics = {sol['metrics']}")
    print_check(check_solution(sol, inst))
