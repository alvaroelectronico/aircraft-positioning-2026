"""
Job-level MILP for aircraft positioning with refined blocking semantics
(paper #2, work in progress).

Relation to the existing job-level model
----------------------------------------
``milp_jobs_pyomo.py`` (legacy) and ``milp_aircraft_pyomo.py`` (paper #1)
both treat blocking as a function of aircraft entry/exit instants only,
which is why the aircraft-level model can collapse each aircraft into
a single uninterrupted block ``[s_r, s_r + D_r]`` without losing
expressive power.

This module relaxes that assumption: blocking is allowed to depend on
the timing of individual jobs within an aircraft.  The implication is
that the aircraft-as-a-single-block collapse is no longer valid, and
the decision variables must include per-job start times even when the
solver outputs only aircraft-level metrics.

Design intent
-------------
The public API mirrors ``milp_jobs_pyomo``:
    * ``model`` is an AbstractModel.
    * ``prepare_data(raw_data, min_separation, w_makespan, w_delay,
      w_movements) -> dict`` returns the Pyomo data dict.
    * ``get_solution(instance, result, raw_data) -> dict`` returns the
      same JSON schema produced by the legacy job-level and the
      aircraft-level models, so downstream consumers (``check_solution``,
      ``plot_schedule``, ``aggregate_results``) work unmodified.

TODO
----
1. Define the new blocking semantics formally (problem statement in
   ``papers/jobs_extension/`` once written).
2. Decide which sets/parameters of the legacy ``milp_jobs_pyomo`` carry
   over verbatim and which need replacement.
3. Implement constraints.  Start from ``milp_jobs_pyomo.py`` and replace
   only the blocking block.
4. Add a gurobipy mirror (``milp_jobs_v2_gurobipy.py``) once the Pyomo
   version is validated against a small reference instance.
"""
from __future__ import annotations

# Intentional placeholder.  The Pyomo abstract model will be built
# incrementally as paper #2's formulation crystallises.
raise NotImplementedError(
    "milp_jobs_v2_pyomo is a stub for paper #2 (job-level extension). "
    "See papers/jobs_extension/paper.tex and the module docstring."
)
