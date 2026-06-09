"""
FixedAssignmentSchedulerJob — gurobipy MILP for the job-as-scheduling-unit
problem with a fixed position assignment.

Given $\\pi: \\mathcal{R} \\to \\mathcal{P}$ (each aircraft pinned to a
position), solves for per-job start times $s_j$ and the interruption
counter $\\kappa_j$ under the three-mode blocking semantics of paper #2
(see papers/jobs_extension/milp.tex).

Substituting the fixed $\\pi$ collapses the full MILP:

* $x_{rp}$ becomes the constant $\\mathbf{1}[\\pi(r) = p]$ → dropped entirely;
  the partition constraint is only added for arcs whose $(\\pi(r), \\pi(r'))$
  pair lies in $\\mathcal{A}$.
* Same-position ordering binaries $q_{rr'p}$ collapse to the ones implied
  by the schedule itself; we add them only between aircraft pairs that
  share a position.

Public API mirrors ``FixedAssignmentSchedulerAircraft`` for runner
compatibility: ``configure``, ``solve(instance_data, assignment)``, ``name``.
"""
from __future__ import annotations

import time

import gurobipy as gp
from gurobipy import GRB


# Defaults if the instance does not carry the paper-#2 fields
_DEFAULT_MU    = 1.0
_DEFAULT_DELTA = 2.0
_DEFAULT_ETA   = 1.0


class FixedAssignmentSchedulerJob:
    """Job-level gurobipy MILP scheduler with fixed position assignments."""

    _DEFAULTS: dict = {
        "time_limit_s":     60.0,
        "min_separation":   0.5,
        "weight_makespan":  0.1,
        "weight_delay":     1.0,
        "weight_movements": 10.0,
        "MIPGap":           0.0,
    }

    def __init__(self) -> None:
        self._params: dict = dict(self._DEFAULTS)

    @property
    def name(self) -> str:
        return "fas_job"

    def configure(self, **kwargs) -> None:
        for k, v in kwargs.items():
            self._params[k] = v

    def get_config(self) -> dict:
        return dict(self._params)

    def solve(
        self,
        instance_data: dict,
        assignment:    dict[str, str],
    ) -> dict:
        """Solve the job-level FAS with the given fixed assignment.

        Returns a solution dict in the standard schema (compatible with
        ``check_solution_jobs_v2``).
        """
        t_build_start = time.perf_counter()

        # ---- Per-instance parameter overrides --------------------------
        if "min_separation" in instance_data:
            self._params["min_separation"] = float(instance_data["min_separation"])

        p_min_sep = self._params["min_separation"]
        p_mu      = instance_data.get("mu",    _DEFAULT_MU)
        p_delta   = instance_data.get("delta", _DEFAULT_DELTA)
        p_eta     = instance_data.get("eta",   _DEFAULT_ETA)
        w_M, w_D, w_S = (
            self._params["weight_makespan"],
            self._params["weight_delay"],
            self._params["weight_movements"],
        )

        # ---- Instance unpacking ---------------------------------------
        aircraft_ids  = list(assignment.keys())
        ac_data       = {a["id"]: a for a in instance_data["aircrafts"]}
        blocking_arcs = [
            (arc["front"], arc["rear"])
            for arc in instance_data["hangar"]["blocking_arcs"]
        ]

        # Group jobs by aircraft and respect the precedence chain order
        jobs_by_ac: dict[str, list[dict]] = {}
        for j in instance_data["jobs"]:
            jobs_by_ac.setdefault(j["aircraft_id"], []).append(j)
        next_of = {p["before"]: p["after"]
                   for p in instance_data.get("job_precedences", [])}
        chain_of: dict[str, list[dict]] = {}
        for r in aircraft_ids:
            ids = [j["id"] for j in jobs_by_ac.get(r, [])]
            succ_targets = {next_of[i] for i in next_of if i in ids}
            roots = [i for i in ids if i not in succ_targets]
            ordered_ids = []
            cur = roots[0] if roots else (ids[0] if ids else "")
            visited: set[str] = set()
            while cur and cur not in visited:
                ordered_ids.append(cur)
                visited.add(cur)
                cur = next_of.get(cur, "")
            for jid in ids:
                if jid not in visited:
                    ordered_ids.append(jid)
            jmap = {j["id"]: j for j in jobs_by_ac.get(r, [])}
            chain_of[r] = [jmap[jid] for jid in ordered_ids]

        # Big-M: loose upper bound on any time variable
        total_dur = sum(
            sum(j["duration"] for j in chain_of[r]) for r in aircraft_ids
        )
        max_e = max((float(ac_data[r]["earliest_start"]) for r in aircraft_ids),
                    default=0.0)
        big_m = (
            max_e + total_dur + p_min_sep * len(aircraft_ids)
            + p_delta * 4 * len(aircraft_ids)
            + max(p_mu, p_eta) * len(blocking_arcs) * 4
        )
        # Cap on per-job kappa (heuristic upper bound)
        K_max = max(2, 2 * (len(aircraft_ids) - 1))

        # ---- Build model ----------------------------------------------
        mdl = gp.Model("FAS_job")
        mdl.Params.OutputFlag = 0
        mdl.Params.TimeLimit  = self._params["time_limit_s"]
        mdl.Params.MIPGap     = self._params.get("MIPGap", 0.0)

        # Per-job decision variables
        s: dict[str, gp.Var]   = {}
        f: dict[str, gp.Var]   = {}
        k: dict[str, gp.Var]   = {}   # kappa_j
        for r in aircraft_ids:
            for j in chain_of[r]:
                jid = j["id"]
                s[jid] = mdl.addVar(lb=0.0,  ub=big_m, name=f"s_{jid}")
                f[jid] = mdl.addVar(lb=0.0,  ub=big_m, name=f"f_{jid}")
                k[jid] = mdl.addVar(lb=0.0,  ub=K_max, vtype=GRB.INTEGER,
                                    name=f"k_{jid}")
                if not bool(j.get("interruptible", False)):
                    # Non-interruptible job: kappa must stay 0
                    mdl.addConstr(k[jid] == 0, name=f"non_int_{jid}")
                # f_j = s_j + D_j + delta * kappa_j
                mdl.addConstr(
                    f[jid] == s[jid] + float(j["duration"]) + p_delta * k[jid],
                    name=f"dur_{jid}",
                )

        # Chain precedences within each aircraft
        for r in aircraft_ids:
            chain = chain_of[r]
            for i in range(len(chain) - 1):
                mdl.addConstr(
                    s[chain[i + 1]["id"]] >= f[chain[i]["id"]],
                    name=f"chain_{chain[i]['id']}_{chain[i+1]['id']}",
                )

        # Aircraft-level shortcuts s_r = s_{j_1^r}, f_r = f_{j_{N_r}^r}
        s_r = {r: s[chain_of[r][0]["id"]]  for r in aircraft_ids}
        f_r = {r: f[chain_of[r][-1]["id"]] for r in aircraft_ids}

        # Earliest start
        for r in aircraft_ids:
            mdl.addConstr(s_r[r] >= float(ac_data[r]["earliest_start"]),
                          name=f"es_{r}")

        # Same-position sequencing (only for aircraft pairs that share a position)
        same_pos_pairs: list[tuple[str, str, str]] = []
        for r1 in aircraft_ids:
            for r2 in aircraft_ids:
                if r1 < r2 and assignment[r1] == assignment[r2]:
                    same_pos_pairs.append((r1, r2, assignment[r1]))
        # Binary q[r1, r2] = 1 iff r1 precedes r2 at their shared position
        q: dict[tuple[str, str], gp.Var] = {}
        for (r1, r2, _p) in same_pos_pairs:
            q[r1, r2] = mdl.addVar(vtype=GRB.BINARY, name=f"q_{r1}_{r2}")
            q[r2, r1] = mdl.addVar(vtype=GRB.BINARY, name=f"q_{r2}_{r1}")
            mdl.addConstr(q[r1, r2] + q[r2, r1] == 1, name=f"qsum_{r1}_{r2}")
            mdl.addConstr(
                s_r[r2] >= f_r[r1] + p_min_sep - big_m * (1 - q[r1, r2]),
                name=f"sep_{r1}_{r2}",
            )
            mdl.addConstr(
                s_r[r1] >= f_r[r2] + p_min_sep - big_m * (1 - q[r2, r1]),
                name=f"sep_{r2}_{r1}",
            )

        # Active blocking pairs (under the fixed assignment)
        # For each (front aircraft r, rear aircraft r') with (pi(r), pi(r')) in A:
        active_arcs: list[tuple[str, str]] = []
        for r in aircraft_ids:
            for rp in aircraft_ids:
                if r == rp:
                    continue
                if (assignment[r], assignment[rp]) in [(f_p, r_p) for (f_p, r_p) in blocking_arcs]:
                    active_arcs.append((r, rp))

        # Partition indicators for each (r, r', a) where a in {in, out}
        # z_minus, z_plus, b_B[k], b_C[j]
        z_minus: dict[tuple[str, str, str], gp.Var] = {}
        z_plus:  dict[tuple[str, str, str], gp.Var] = {}
        b_B: dict[tuple[str, str, str, int], gp.Var] = {}    # (r, rp, a, gap_idx)
        b_C: dict[tuple[str, str, str, str], gp.Var] = {}    # (r, rp, a, job_id)

        for (r, rp) in active_arcs:
            chain_r = chain_of[r]
            for a in ("in", "out"):
                zm = mdl.addVar(vtype=GRB.BINARY, name=f"z-_{r}_{rp}_{a}")
                zp = mdl.addVar(vtype=GRB.BINARY, name=f"z+_{r}_{rp}_{a}")
                z_minus[r, rp, a] = zm
                z_plus[r, rp, a]  = zp
                # Mode B indicators (one per inter-job gap of r)
                bB_list = []
                for gi in range(len(chain_r) - 1):
                    var = mdl.addVar(vtype=GRB.BINARY, name=f"bB_{r}_{rp}_{a}_{gi}")
                    b_B[r, rp, a, gi] = var
                    bB_list.append(var)
                # Mode C indicators (one per job of r); guarded by interruptible
                bC_list = []
                for j in chain_r:
                    var = mdl.addVar(vtype=GRB.BINARY, name=f"bC_{r}_{rp}_{a}_{j['id']}")
                    b_C[r, rp, a, j["id"]] = var
                    if not bool(j.get("interruptible", False)):
                        mdl.addConstr(var == 0, name=f"non_int_C_{r}_{rp}_{a}_{j['id']}")
                    bC_list.append(var)
                # Exhaustive partition: exactly one mode fires
                mdl.addConstr(
                    zm + zp + gp.quicksum(bB_list) + gp.quicksum(bC_list) == 1,
                    name=f"part_{r}_{rp}_{a}",
                )

        # Timing constraints linking indicators to s_j, f_j, tau
        for (r, rp) in active_arcs:
            chain_r = chain_of[r]
            for a in ("in", "out"):
                tau = s_r[rp] if a == "in" else f_r[rp]
                zm = z_minus[r, rp, a]
                zp = z_plus[r, rp, a]
                # z_minus: tau <= s_r - eta + M*(1 - zm)
                mdl.addConstr(
                    tau <= s_r[r] - p_eta + big_m * (1 - zm),
                    name=f"zm_{r}_{rp}_{a}",
                )
                # z_plus: tau >= f_r + eta - M*(1 - zp)
                mdl.addConstr(
                    tau >= f_r[r] + p_eta - big_m * (1 - zp),
                    name=f"zp_{r}_{rp}_{a}",
                )
                # Mode B: tau in [f_{j_k}, s_{j_{k+1}}]
                for gi in range(len(chain_r) - 1):
                    bB = b_B[r, rp, a, gi]
                    jk_id  = chain_r[gi]["id"]
                    jk1_id = chain_r[gi + 1]["id"]
                    mdl.addConstr(tau >= f[jk_id]  - big_m * (1 - bB),
                                  name=f"bB_lb_{r}_{rp}_{a}_{gi}")
                    mdl.addConstr(tau <= s[jk1_id] + big_m * (1 - bB),
                                  name=f"bB_ub_{r}_{rp}_{a}_{gi}")
                # Mode B gap requirement: cumulative mu
                for gi in range(len(chain_r) - 1):
                    jk_id  = chain_r[gi]["id"]
                    jk1_id = chain_r[gi + 1]["id"]
                    # Gap >= mu * (number of accesses using this gap across all
                    # active (front=r, rear=*) pairs and both access sides)
                    cum_B = gp.quicksum(
                        b_B[r, rp2, a2, gi]
                        for (r2, rp2) in active_arcs
                        for a2 in ("in", "out")
                        if r2 == r
                    )
                    mdl.addConstr(s[jk1_id] - f[jk_id] >= p_mu * cum_B,
                                  name=f"bB_gap_{r}_{gi}")
                # Mode C: s_j + eta <= tau <= s_j + D_j + delta*(kappa_j - bC) - eta
                for j in chain_r:
                    jid = j["id"]
                    bC  = b_C[r, rp, a, jid]
                    D_j = float(j["duration"])
                    mdl.addConstr(
                        tau >= s[jid] + p_eta - big_m * (1 - bC),
                        name=f"bC_lb_{r}_{rp}_{a}_{jid}",
                    )
                    mdl.addConstr(
                        tau <= s[jid] + D_j + p_delta * (k[jid] - bC) - p_eta
                               + big_m * (1 - bC),
                        name=f"bC_ub_{r}_{rp}_{a}_{jid}",
                    )

        # kappa_j = sum of Mode-C events against job j
        for r in aircraft_ids:
            for j in chain_of[r]:
                jid = j["id"]
                cum_C = gp.quicksum(
                    b_C[r, rp, a, jid]
                    for (r2, rp) in active_arcs
                    for a in ("in", "out")
                    if r2 == r
                )
                # cum_C may be empty if r has no active rear neighbours
                mdl.addConstr(k[jid] == cum_C, name=f"kappa_{jid}")

        # Movement count n = 2 * sum of B + C events
        movs = mdl.addVar(lb=0.0, ub=10_000, name="movs")
        mdl.addConstr(
            movs == 2 * gp.quicksum(
                b_B[r, rp, a, gi]
                for (r, rp) in active_arcs
                for a in ("in", "out")
                for gi in range(len(chain_of[r]) - 1)
            )
            + 2 * gp.quicksum(
                b_C[r, rp, a, j["id"]]
                for (r, rp) in active_arcs
                for a in ("in", "out")
                for j in chain_of[r]
            ),
            name="movs_def",
        )

        # Aircraft-level delay and makespan
        delay = mdl.addVars(aircraft_ids, lb=0.0, name="delay")
        mks   = mdl.addVar(lb=0.0, name="makespan")
        for r in aircraft_ids:
            mdl.addConstr(delay[r] >= f_r[r] - float(ac_data[r]["target_finish"]),
                          name=f"delay_{r}")
            mdl.addConstr(mks >= f_r[r], name=f"mks_{r}")

        # Objective
        mdl.setObjective(
            w_M * mks + w_D * gp.quicksum(delay[r] for r in aircraft_ids) + w_S * movs,
            GRB.MINIMIZE,
        )

        build_time = time.perf_counter() - t_build_start
        t_solve_start = time.perf_counter()
        mdl.optimize()
        solve_time = time.perf_counter() - t_solve_start

        # ---- Extract solution -----------------------------------------
        status = mdl.Status
        if mdl.SolCount == 0:
            return {
                "status": _gurobi_status_string(status),
                "objective": float("inf"),
                "mip_gap": None,
                "metrics": {"makespan": 0.0, "movements": 0, "total_delay": 0.0},
                "aircraft": [],
                "_build_time_s": round(build_time, 4),
                "_solve_time_s": round(solve_time, 4),
            }

        aircraft_list: list[dict] = []
        for r in aircraft_ids:
            chain = chain_of[r]
            jobs_out = []
            for j in chain:
                jobs_out.append({
                    "id":     j["id"],
                    "start":  round(s[j["id"]].X, 4),
                    "finish": round(f[j["id"]].X, 4),
                })
            aircraft_list.append({
                "id":       r,
                "position": assignment[r],
                "start":    round(s_r[r].X, 4),
                "finish":   round(f_r[r].X, 4),
                "delay":    round(delay[r].X, 4),
                "jobs":     jobs_out,
            })

        try:
            mip_gap = round(mdl.MIPGap, 6)
        except Exception:
            mip_gap = None

        return {
            "status":    _gurobi_status_string(status),
            "objective": round(mdl.ObjVal, 4),
            "mip_gap":   mip_gap,
            "metrics": {
                "makespan":    round(mks.X, 4),
                "movements":   int(round(movs.X)),
                "total_delay": round(sum(delay[r].X for r in aircraft_ids), 4),
            },
            "aircraft":      aircraft_list,
            "_build_time_s": round(build_time, 4),
            "_solve_time_s": round(solve_time, 4),
        }


_GUROBI_STATUS: dict[int, str] = {
    GRB.OPTIMAL:     "optimal",
    GRB.TIME_LIMIT:  "maxTimeLim",
    GRB.INFEASIBLE:  "infeasible",
    GRB.INF_OR_UNBD: "infeasible",
    GRB.SUBOPTIMAL:  "feasible",
}


def _gurobi_status_string(status: int) -> str:
    return _GUROBI_STATUS.get(status, "unknown")


# =============================================================================
#  CLI — standalone smoke test
# =============================================================================

if __name__ == "__main__":
    import json
    import os
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "input_data"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "output_data"))
    from instance_io           import load_json as load_instance       # noqa: E402
    from check_solution_jobs_v2 import check_solution, print_check     # noqa: E402

    default_path = os.path.join(
        os.path.dirname(__file__), "..",
        "data", "instances_202605",
        "scn_triangle_tight_P5_R5", "scn_triangle_tight_P5_R5_seed1.json",
    )
    instance_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    raw = load_instance(instance_path)

    # Trivial assignment: spread aircraft across positions
    positions = raw["hangar"]["positions"]
    aircraft_ids = [a["id"] for a in raw["aircrafts"]]
    assignment = {aid: positions[i % len(positions)] for i, aid in enumerate(aircraft_ids)}

    solver = FixedAssignmentSchedulerJob()
    solver.configure(time_limit_s=20)
    sol = solver.solve(raw, assignment)

    print(json.dumps(
        {"status": sol["status"], "objective": sol["objective"], "metrics": sol["metrics"]},
        indent=2,
    ))

    report = check_solution(sol, raw)
    print_check(report)
