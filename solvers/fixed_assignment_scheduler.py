"""
FixedAssignmentScheduler — gurobipy MILP for scheduling with fixed position assignments.

Given a fixed assignment {aircraft_id: position}, optimises the timing/sequencing
of aircraft within their positions.  Dramatically faster than the full Pyomo MILP
because all position-assignment binary variables are eliminated.

The model aggregates each aircraft to a single block [S_r, F_r = S_r + D_r].
Job-level start times are recovered deterministically from S_r (chain order).

Compared to the full MILP (milp_pyomo.py):
  - Variables removed: vAircraftPosition, vJobPosition, vJobOrder (replaced by
    same-position ordering binaries q_{r,r'} which are O(pairs-per-position))
  - Constraints added: same-position minimum separation (δ), which was absent
    from the Pyomo model and caused milp_fix1 to undercount feasibility cost.
  - Blocking variables retained but simplified (position guard terms collapse to
    constants since every aircraft's position is fixed).

Usage
-----
    from solvers.fixed_assignment_scheduler import FixedAssignmentScheduler

    scheduler = FixedAssignmentScheduler()
    scheduler.configure(time_limit_s=30, min_separation=10.0,
                        weight_makespan=0.1, weight_delay=1.0, weight_movements=10)
    solution = scheduler.solve(instance_data, assignment)
    # assignment: {aircraft_id: position_id}
"""
from __future__ import annotations

import time

import gurobipy as gp
from gurobipy import GRB


class FixedAssignmentScheduler:
    """gurobipy MILP scheduler with fixed position assignments."""

    _DEFAULTS: dict = {
        "time_limit_s":     60.0,
        "min_separation":   10.0,
        "weight_makespan":  10.0,
        "weight_delay":     100.0,
        "weight_movements": 1.0,
        "MIPGap":           0.0,
    }

    def __init__(self) -> None:
        self._params: dict = dict(self._DEFAULTS)

    @property
    def name(self) -> str:
        return "fas"

    def configure(self, **kwargs) -> None:
        for k, v in kwargs.items():
            self._params[k] = v

    def solve(
        self,
        instance_data: dict,
        assignment: dict[str, str],
        candidates: dict[str, list[str]] | None = None,
    ) -> dict:
        """Solve the scheduling problem with fixed (or multi-candidate) position assignment.

        Parameters
        ----------
        instance_data:
            Raw instance dict from load_json.
        assignment:
            Dict mapping aircraft_id -> primary position_id.  Used as the sole
            candidate when *candidates* is None (backward-compatible).
        candidates:
            Optional dict mapping aircraft_id -> list of allowed position_ids.
            Aircraft with >1 candidate get binary position variables; the MILP
            jointly optimises position selection and timing.  If None, derived
            from *assignment* (each aircraft has exactly 1 candidate).

        Returns
        -------
        dict
            Solution dict compatible with the rest of the system.
        """
        t_build_start = time.perf_counter()

        # Per-instance epsilon overrides the config fallback.
        if "min_separation" in instance_data:
            self._params["min_separation"] = float(instance_data["min_separation"])
        params        = self._params
        min_sep       = params["min_separation"]
        w_M           = params["weight_makespan"]
        w_D           = params["weight_delay"]
        w_V           = params["weight_movements"]
        time_limit    = params["time_limit_s"]

        # ------------------------------------------------------------------
        # Pre-process instance
        # ------------------------------------------------------------------
        positions     = instance_data["hangar"]["positions"]
        blocking_arcs = instance_data["hangar"]["blocking_arcs"]

        ac_data = {a["id"]: a for a in instance_data["aircrafts"]}
        job_data = instance_data["jobs"]

        # Total duration per aircraft (sum of job chain)
        ac_dur: dict[str, float] = {}
        ac_jobs: dict[str, list[dict]] = {}
        for j in job_data:
            rid = j["aircraft_id"]
            ac_jobs.setdefault(rid, []).append(j)
        for rid, jobs in ac_jobs.items():
            # Sort jobs by chain order using is_first/is_last and precedences
            ordered = _sort_job_chain(jobs, instance_data.get("job_precedences", []))
            ac_jobs[rid] = ordered
            ac_dur[rid] = sum(j["duration"] for j in ordered)

        aircraft_ids = list(assignment.keys())
        earliest = {r: ac_data[r]["earliest_start"] for r in aircraft_ids}
        target   = {r: ac_data[r]["target_finish"]  for r in aircraft_ids}

        # Resolve candidates: default = single candidate from assignment
        if candidates is None:
            cands: dict[str, list[str]] = {r: [assignment[r]] for r in aircraft_ids}
        else:
            cands = {r: list(dict.fromkeys(candidates[r])) for r in aircraft_ids}

        # candidates_set per position: which aircraft CAN be at each position
        pos_candidates: dict[str, list[str]] = {p: [] for p in positions}
        for r, ps in cands.items():
            for p in ps:
                pos_candidates[p].append(r)

        # Big-M: loose upper bound on any finish time
        big_m = max(target.values()) + sum(ac_dur.values()) + min_sep * len(aircraft_ids)

        # ------------------------------------------------------------------
        # Build gurobipy model
        # ------------------------------------------------------------------
        mdl = gp.Model("FAS")
        mdl.Params.OutputFlag   = 0
        mdl.Params.TimeLimit    = time_limit
        mdl.Params.MIPGap       = params.get("MIPGap", 0.0)

        # Continuous variables
        S        = mdl.addVars(aircraft_ids, lb=0.0, name="S")
        F        = mdl.addVars(aircraft_ids, lb=0.0, name="F")
        delay    = mdl.addVars(aircraft_ids, lb=0.0, name="delay")
        makespan = mdl.addVar(lb=0.0, name="makespan")

        # Link finish to start + duration
        for r in aircraft_ids:
            mdl.addConstr(F[r] == S[r] + ac_dur[r], name=f"dur_{r}")
            mdl.addConstr(S[r] >= earliest[r],       name=f"es_{r}")
            mdl.addConstr(delay[r] >= F[r] - target[r], name=f"delay_{r}")
            mdl.addConstr(makespan >= F[r],          name=f"ms_{r}")

        # ------------------------------------------------------------------
        # Position assignment variables (only for aircraft with >1 candidate)
        # ------------------------------------------------------------------
        x: dict[tuple[str, str], gp.Var] = {}
        for r in aircraft_ids:
            if len(cands[r]) > 1:
                for p in cands[r]:
                    x[r, p] = mdl.addVar(vtype=GRB.BINARY, name=f"x_{r}_{p}")
                mdl.addConstr(
                    gp.quicksum(x[r, p] for p in cands[r]) == 1,
                    name=f"assign_{r}",
                )

        def _pos_ind(r: str, p: str):
            """Position indicator for r at p: float 1.0/0.0 (fixed) or gurobi Var."""
            if len(cands[r]) == 1:
                return 1.0 if cands[r][0] == p else 0.0
            return x.get((r, p), 0.0)  # 0.0 when p not in cands[r]

        def _is_zero(xi) -> bool:
            return isinstance(xi, float) and xi == 0.0

        def _is_one(xi) -> bool:
            return isinstance(xi, float) and xi == 1.0

        def _guard(xi) -> float | gp.LinExpr:
            """Return big_m*(1-xi) as a gurobi expression, or 0.0 when xi is fixed 1."""
            if _is_one(xi):
                return 0.0
            return big_m * (1 - xi)

        # ------------------------------------------------------------------
        # Same-position ordering + minimum separation
        # For each pair (r, rp) with r < rp, for every shared candidate position p.
        # ------------------------------------------------------------------
        q: dict[tuple[str, str, str], gp.Var] = {}
        aircraft_sorted = sorted(aircraft_ids)
        for i, r in enumerate(aircraft_sorted):
            for rp in aircraft_sorted[i + 1:]:
                shared = [p for p in cands[r] if p in cands[rp]]
                for p in shared:
                    xi_r  = _pos_ind(r, p)
                    xi_rp = _pos_ind(rp, p)
                    if _is_zero(xi_r) or _is_zero(xi_rp):
                        continue
                    v = mdl.addVar(vtype=GRB.BINARY, name=f"q_{r}_{rp}_{p}")
                    q[(r, rp, p)] = v
                    # q=1: r before rp  →  S[rp] >= F[r] + δ - M*(1-q) - M*(1-xi_r) - M*(1-xi_rp)
                    mdl.addConstr(
                        S[rp] >= F[r] + min_sep - big_m*(1-v) - _guard(xi_r) - _guard(xi_rp),
                        name=f"ord1_{r}_{rp}_{p}",
                    )
                    # q=0: rp before r  →  S[r] >= F[rp] + δ - M*q - M*(1-xi_r) - M*(1-xi_rp)
                    mdl.addConstr(
                        S[r] >= F[rp] + min_sep - big_m*v - _guard(xi_r) - _guard(xi_rp),
                        name=f"ord0_{r}_{rp}_{p}",
                    )

        # ------------------------------------------------------------------
        # Blocking variables
        # Enumerate all (r_front, r_rear, p_front, p_rear) where r_front can be at
        # p_front and r_rear can be at p_rear.
        # ------------------------------------------------------------------
        arc_set = {(arc["front"], arc["rear"]) for arc in blocking_arcs}
        blocking_pairs: list[tuple[str, str, str, str]] = []
        for (p_front, p_rear) in arc_set:
            for r_front in pos_candidates.get(p_front, []):
                for r_rear in pos_candidates.get(p_rear, []):
                    if r_front != r_rear:
                        blocking_pairs.append((r_front, r_rear, p_front, p_rear))

        if blocking_pairs:
            alphaIn  = mdl.addVars(blocking_pairs, vtype=GRB.BINARY, name="aIn")
            betaIn   = mdl.addVars(blocking_pairs, vtype=GRB.BINARY, name="bIn")
            uIn      = mdl.addVars(blocking_pairs, vtype=GRB.BINARY, name="uIn")
            alphaOut = mdl.addVars(blocking_pairs, vtype=GRB.BINARY, name="aOut")
            betaOut  = mdl.addVars(blocking_pairs, vtype=GRB.BINARY, name="bOut")
            uOut     = mdl.addVars(blocking_pairs, vtype=GRB.BINARY, name="uOut")

            for (r, rp, p, pp) in blocking_pairs:
                xi_r  = _pos_ind(r,  p)
                xi_rp = _pos_ind(rp, pp)
                guard_r  = _guard(xi_r)
                guard_rp = _guard(xi_rp)

                # --- Entry blocking: rp enters pp while r occupies p ---
                # alphaIn=1 iff S[rp] >= S[r]
                mdl.addConstr(S[rp] >= S[r]  - big_m * (1 - alphaIn[r, rp, p, pp]))
                mdl.addConstr(S[rp] <= S[r]  + big_m * alphaIn[r, rp, p, pp])
                # betaIn=1 iff S[rp] <= F[r] - min_sep (guarded by position)
                mdl.addConstr(S[rp] <= F[r] - min_sep + big_m * (1 - betaIn[r, rp, p, pp]) + guard_r + guard_rp)
                mdl.addConstr(S[rp] >= F[r] - big_m * betaIn[r, rp, p, pp])
                # uIn = alphaIn AND betaIn, also guarded by position assignments
                mdl.addConstr(uIn[r, rp, p, pp] <= alphaIn[r, rp, p, pp])
                mdl.addConstr(uIn[r, rp, p, pp] <= betaIn[r, rp, p, pp])
                mdl.addConstr(uIn[r, rp, p, pp] >= alphaIn[r, rp, p, pp] + betaIn[r, rp, p, pp] - 1)
                if not _is_one(xi_r):
                    mdl.addConstr(uIn[r, rp, p, pp] <= xi_r)
                if not _is_one(xi_rp):
                    mdl.addConstr(uIn[r, rp, p, pp] <= xi_rp)

                # --- Exit blocking: rp exits pp while r occupies p ---
                # alphaOut=1 iff F[rp] >= S[r]
                mdl.addConstr(F[rp] >= S[r]  - big_m * (1 - alphaOut[r, rp, p, pp]))
                mdl.addConstr(F[rp] <= S[r]  + big_m * alphaOut[r, rp, p, pp])
                # betaOut=1 iff F[rp] <= F[r] - min_sep (guarded)
                mdl.addConstr(F[rp] <= F[r] - min_sep + big_m*(1-betaOut[r, rp, p, pp]) + guard_r + guard_rp)
                mdl.addConstr(F[rp] >= F[r] - big_m * betaOut[r, rp, p, pp])
                # uOut = alphaOut AND betaOut, guarded
                mdl.addConstr(uOut[r, rp, p, pp] <= alphaOut[r, rp, p, pp])
                mdl.addConstr(uOut[r, rp, p, pp] <= betaOut[r, rp, p, pp])
                mdl.addConstr(uOut[r, rp, p, pp] >= alphaOut[r, rp, p, pp] + betaOut[r, rp, p, pp] - 1)
                if not _is_one(xi_r):
                    mdl.addConstr(uOut[r, rp, p, pp] <= xi_r)
                if not _is_one(xi_rp):
                    mdl.addConstr(uOut[r, rp, p, pp] <= xi_rp)

            movements_expr = 2 * gp.quicksum(
                uIn[bp] + uOut[bp] for bp in blocking_pairs
            )
        else:
            movements_expr = gp.LinExpr(0)

        # Objective
        mdl.setObjective(
            w_M * makespan
            + w_D * gp.quicksum(delay[r] for r in aircraft_ids)
            + w_V * movements_expr,
            GRB.MINIMIZE,
        )

        t_build_end = time.perf_counter()
        mdl.update()

        # ------------------------------------------------------------------
        # Solve
        # ------------------------------------------------------------------
        t_solve_start = time.perf_counter()
        mdl.optimize()
        t_solve_end = time.perf_counter()

        # ------------------------------------------------------------------
        # Extract solution
        # ------------------------------------------------------------------
        status_map = {
            GRB.OPTIMAL:    "optimal",
            GRB.TIME_LIMIT: "maxTimeLim",
            GRB.INFEASIBLE: "infeasible",
            GRB.INF_OR_UNBD: "infOrUnbd",
        }
        status = status_map.get(mdl.Status, f"gurobi_{mdl.Status}")

        if mdl.SolCount == 0:
            return {
                "status":    status,
                "objective": float("inf"),
                "metrics":   {"makespan": 0.0, "movements": 0, "total_delay": 0.0},
                "aircraft":  [],
                "_build_time_s": round(t_build_end - t_build_start, 3),
                "_solve_time_s": round(t_solve_end - t_solve_start, 3),
            }

        # Compute movements integer value
        if blocking_pairs:
            mov_val = int(round(sum(
                uIn[bp].X + uOut[bp].X for bp in blocking_pairs
            ) * 2))
        else:
            mov_val = 0

        ac_solutions = []
        for r in aircraft_ids:
            s_r = S[r].X
            f_r = F[r].X
            d_r = max(0.0, f_r - target[r])
            # Recover job start times from chain
            job_schedules = []
            t = s_r
            for j in ac_jobs[r]:
                job_schedules.append({
                    "id":     j["id"],
                    "start":  round(t, 4),
                    "finish": round(t + j["duration"], 4),
                })
                t += j["duration"]
            # Determine actual position: from x variable if multi-candidate
            if len(cands[r]) > 1:
                actual_pos = max(cands[r], key=lambda p: x[r, p].X)
            else:
                actual_pos = cands[r][0]
            ac_solutions.append({
                "id":       r,
                "position": actual_pos,
                "start":    round(s_r, 4),
                "finish":   round(f_r, 4),
                "delay":    round(d_r, 4),
                "jobs":     job_schedules,
            })

        obj_val = round(mdl.ObjVal, 2)
        total_delay = round(sum(max(0.0, F[r].X - target[r]) for r in aircraft_ids), 2)
        makespan_val = round(makespan.X, 2)

        try:
            obj_bound = mdl.ObjBound
            mip_gap = round(abs(obj_val - obj_bound) / abs(obj_val), 6) if abs(obj_val) > 1e-10 else None
        except AttributeError:
            mip_gap = None

        return {
            "status":    status,
            "objective": obj_val,
            "mip_gap":   mip_gap,
            "metrics": {
                "makespan":    makespan_val,
                "movements":   mov_val,
                "total_delay": total_delay,
            },
            "aircraft": ac_solutions,
            "_build_time_s": round(t_build_end - t_build_start, 3),
            "_solve_time_s": round(t_solve_end - t_solve_start, 3),
        }


# =============================================================================
#  Helpers
# =============================================================================

def _sort_job_chain(jobs: list[dict], precedences: list[dict]) -> list[dict]:
    """Return jobs sorted in chain order using precedence graph (topological sort)."""
    job_ids  = {j["id"] for j in jobs}
    job_map  = {j["id"]: j for j in jobs}
    # Build adjacency for jobs in this aircraft only
    succ: dict[str, str] = {}
    for p in precedences:
        if p["before"] in job_ids and p["after"] in job_ids:
            succ[p["before"]] = p["after"]
    # Find root: job with no predecessor
    has_pred = set(succ.values())
    roots = [jid for jid in job_ids if jid not in has_pred]
    if not roots:
        # Fallback: sort by id
        return sorted(jobs, key=lambda j: j["id"])
    chain = []
    cur = roots[0]
    while cur:
        chain.append(job_map[cur])
        cur = succ.get(cur)
    # Add any remaining jobs not reachable (shouldn't happen in well-formed data)
    seen = {j["id"] for j in chain}
    chain += [job_map[jid] for jid in job_ids if jid not in seen]
    return chain
