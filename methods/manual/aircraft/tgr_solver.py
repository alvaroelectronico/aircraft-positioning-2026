"""
TGRSolver — Topology-Guided Restricted MILP solver.

Pipeline
--------
1. TopologyHeuristicAircraft generates K diverse position assignments (fast GRASP, no LS).
2. FixedAssignmentSchedulerAircraft solves the scheduling MILP for each assignment.
3. Return the best schedule across all assignments (min objective).

This separates the two sub-problems cleanly:
  - Spatial assignment: topology heuristic (fast, combinatorial intuition)
  - Temporal scheduling: exact MILP (optimal within the fixed assignment)

Usage
-----
    from solvers.tgr_solver import TGRSolver

    solver = TGRSolver()
    solver.configure_solver(
        time_limit_s=60,
        n_assignments=5,
        time_topology_s=10,
        weight_makespan=0.1,
        weight_delay=1.0,
        weight_movements=10,
    )
    solution = solver.solve(instance_data)
"""
from __future__ import annotations

import time

from topology_heuristic_aircraft import TopologyHeuristicAircraft, _prepare_instance, _solve_single
from fixed_assignment_scheduler_aircraft import FixedAssignmentSchedulerAircraft
from constructive_heuristic import _objective


class TGRSolver:
    """Topology-Guided Restricted MILP: topology assigns, MILP schedules."""

    _DEFAULTS: dict = {
        "time_limit_s":     60.0,
        "n_assignments":    5,
        "time_topology_s":  10.0,   # total topology budget (split across assignments)
        "time_per_milp_s":  None,   # if None: computed from remaining budget / n_assignments
        "min_separation":   10.0,
        "weight_makespan":  10.0,
        "weight_delay":     100.0,
        "weight_movements": 1.0,
        "weight_topology":  1.0,
        "alpha":            0.3,
        "seed":             1,
        "MIPGap":           0.0,
    }

    def __init__(self) -> None:
        self._params: dict = dict(self._DEFAULTS)

    @property
    def name(self) -> str:
        return "tgr"

    def configure_solver(self, **kwargs) -> None:
        for k, v in kwargs.items():
            self._params[k] = v

    def get_config(self) -> dict:
        return dict(self._params)

    def solve(self, instance_data: dict) -> dict:
        # Per-instance epsilon overrides the config fallback; propagated to
        # the sub-solvers (TopologyHeuristicAircraft, FixedAssignmentSchedulerAircraft) which
        # apply the same override on their own solve() entrypoints.
        if "min_separation" in instance_data:
            self._params["min_separation"] = float(instance_data["min_separation"])
        params       = self._params
        total_budget = params["time_limit_s"]
        n_assign     = max(1, int(params["n_assignments"]))
        t_topo       = min(params["time_topology_s"], total_budget * 0.5)
        time_per_assign = t_topo / n_assign

        t0 = time.perf_counter()

        # Step 1 — generate diverse assignments
        print(f"  [TGR] generating {n_assign} assignments  ({t_topo:.1f}s topology budget)")
        topo = TopologyHeuristicAircraft()
        topo.configure_solver(**{
            k: params[k] for k in (
                "min_separation", "weight_makespan", "weight_delay",
                "weight_movements", "weight_topology", "alpha", "seed",
            )
        })
        assignments = topo.generate_assignments(
            instance_data, k=n_assign, time_per_assign=time_per_assign,
        )
        print(f"  [TGR] got {len(assignments)} unique assignments"
              f"  (topology elapsed={time.perf_counter()-t0:.1f}s)")

        if not assignments:
            return {"status": "no_assignments", "objective": float("inf"),
                    "metrics": {"makespan": 0, "movements": 0, "total_delay": 0},
                    "aircraft": []}

        # Step 2 — schedule each assignment with FAS MILP
        remaining = total_budget - (time.perf_counter() - t0)
        t_per_milp = (
            params["time_per_milp_s"]
            if params["time_per_milp_s"] is not None
            else max(5.0, remaining / len(assignments))
        )
        print(f"  [TGR] scheduling {len(assignments)} assignments"
              f"  ({t_per_milp:.1f}s per MILP)")

        fas = FixedAssignmentSchedulerAircraft()
        fas.configure(
            min_separation   = params["min_separation"],
            weight_makespan  = params["weight_makespan"],
            weight_delay     = params["weight_delay"],
            weight_movements = params["weight_movements"],
            MIPGap           = params.get("MIPGap", 0.0),
        )

        best_sol = None
        best_obj = float("inf")

        for idx, assign in enumerate(assignments):
            remaining_budget = total_budget - (time.perf_counter() - t0)
            if remaining_budget < 2.0:
                print(f"  [TGR] budget exhausted after {idx} assignments")
                break

            fas.configure(time_limit_s=min(t_per_milp, remaining_budget))
            sol = fas.solve(instance_data, assign)

            obj = sol["objective"]
            build_t = sol.get("_build_time_s", 0)
            solve_t = sol.get("_solve_time_s", 0)
            print(f"  [TGR] assign {idx+1}/{len(assignments)}"
                  f"  status={sol['status']}  obj={obj:.2f}"
                  f"  build={build_t:.2f}s  solve={solve_t:.2f}s")

            if obj < best_obj - 1e-6:
                best_obj = obj
                best_sol = sol

        elapsed = time.perf_counter() - t0
        print(f"  [TGR] done  best_obj={best_obj:.2f}  total={elapsed:.2f}s")

        best_sol["status"] = f"tgr ({len(assignments)} assignments)"
        return best_sol
