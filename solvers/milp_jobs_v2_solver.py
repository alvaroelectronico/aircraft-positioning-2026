"""
MILPJobsV2Solver — wraps the job-level MILP with refined blocking
semantics from ``models/milp_jobs_v2_pyomo.py`` (paper #2, work in
progress).

Drop-in replacement for ``MILPSolver`` / ``MILPAircraftSolver`` in the
``Application`` pipeline once implemented.

TODO
----
1. Mirror the configure_solver / solve / get_config contract of
   ``MILPAircraftSolver`` so the experiment runner can dispatch to it
   transparently.
2. Decide whether the v2 solver should support both Pyomo and gurobipy
   backends from day one (recommended) or start Pyomo-only and add
   gurobipy after validation.
3. Add a ``__main__`` standalone debug entry point analogous to
   ``milp_jobs_solver.py``.
"""
from __future__ import annotations

import os
import sys

# Make the models directory importable regardless of cwd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "models"))


class MILPJobsV2Solver:
    """Solver wrapper for the job-level v2 MILP (paper #2)."""

    @property
    def name(self) -> str:
        return "milp_jobs_v2"

    def configure_solver(self, **kwargs) -> None:
        raise NotImplementedError(
            "MILPJobsV2Solver is a stub for paper #2 (job-level extension). "
            "See models/milp_jobs_v2_pyomo.py and papers/jobs_extension/paper.tex."
        )

    def solve(self, instance_data: dict) -> dict:
        raise NotImplementedError(
            "MILPJobsV2Solver is a stub for paper #2 (job-level extension)."
        )

    def get_config(self) -> dict:
        return {}
