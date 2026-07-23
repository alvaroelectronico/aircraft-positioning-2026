"""
Native gurobipy MILP for the job-as-scheduling-unit problem with
refined blocking semantics (papers/jobs_extension/milp.tex).

Full formulation: solves the assignment AND timing jointly under the
three-mode access logic (Mode A vacant front, Mode B inter-job gap
with parameter mu, Mode C strict-interior of an interruptible job
with parameter delta).

Public API (matches models/milp_aircraft_gurobipy.py):
    prepare_data(raw_data, min_sep, w_mks, w_dly, w_mov) -> dict
    build_model(data) -> gp.Model
    get_solution(m, raw_data) -> dict
"""
from __future__ import annotations

import gurobipy as gp
from gurobipy import GRB


# Defaults if the instance does not carry the paper-#2 fields
_DEFAULT_MU    = 1.0
_DEFAULT_DELTA = 2.0
_DEFAULT_ETA   = 1.0


# ============================================================
#  Chain helper
# ============================================================

def _sort_job_chain(jobs: list[dict], precedences: list[dict]) -> list[dict]:
    """Sort *jobs* in linear-chain order via the precedence graph."""
    job_ids = {j["id"] for j in jobs}
    job_map = {j["id"]: j for j in jobs}
    succ: dict[str, str] = {}
    for p in precedences:
        if p["before"] in job_ids and p["after"] in job_ids:
            succ[p["before"]] = p["after"]
    has_pred = set(succ.values())
    roots = [jid for jid in job_ids if jid not in has_pred]
    if not roots:
        return sorted(jobs, key=lambda j: j["id"])
    chain: list[dict] = []
    cur: str | None = roots[0]
    visited: set[str] = set()
    while cur and cur not in visited:
        chain.append(job_map[cur])
        visited.add(cur)
        cur = succ.get(cur)
    for jid in job_ids:
        if jid not in visited:
            chain.append(job_map[jid])
    return chain


# ============================================================
#  Data preparation
# ============================================================

def prepare_data(
    raw_data: dict,
    min_separation: float,
    weight_makespan: float,
    weight_delay: float,
    weight_movements: float,
) -> dict:
    """Convert JSON instance data to a flat dict for build_model."""
    aircraft_data = raw_data["aircrafts"]
    job_data      = raw_data["jobs"]
    hangar        = raw_data["hangar"]
    precedences   = raw_data.get("job_precedences", [])
    if "min_separation" in raw_data:
        min_separation = float(raw_data["min_separation"])

    aircraft      = [a["id"] for a in aircraft_data]
    positions     = list(hangar["positions"])
    blocking_arcs = [(arc["front"], arc["rear"]) for arc in hangar["blocking_arcs"]]

    by_ac: dict[str, list[dict]] = {}
    for j in job_data:
        by_ac.setdefault(j["aircraft_id"], []).append(j)
    chains: dict[str, list[dict]] = {
        r: _sort_job_chain(by_ac.get(r, []), precedences) for r in aircraft
    }

    # Cache for downstream solution recovery
    raw_data["__ac_chain__"] = chains

    mu    = float(raw_data.get("mu",    _DEFAULT_MU))
    delta = float(raw_data.get("delta", _DEFAULT_DELTA))
    eta   = float(raw_data.get("eta",   _DEFAULT_ETA))

    n_ac      = len(aircraft)
    total_dur = sum(sum(j["duration"] for j in chains[r]) for r in aircraft)
    max_es    = max((a["earliest_start"] for a in aircraft_data), default=0.0)
    # Upper bound on any time variable: worst-case sequential schedule plus
    # interruption-extension budget.
    horizon_ub = (
        max_es + total_dur + min_separation * max(0, n_ac - 1)
        + delta * 2 * n_ac
        + max(mu, eta) * 4 * max(1, len(blocking_arcs))
    )
    big_m = horizon_ub + max(min_separation, mu, delta, eta) + 1.0

    K_max = max(2, 2 * max(1, n_ac - 1))

    return {
        "aircraft":          aircraft,
        "positions":         positions,
        "blocking_arcs":     blocking_arcs,
        "chains":            chains,
        "earliest_start":    {a["id"]: float(a["earliest_start"]) for a in aircraft_data},
        "target_finish":     {a["id"]: float(a["target_finish"])  for a in aircraft_data},
        "min_separation":    min_separation,
        "mu":                mu,
        "delta":             delta,
        "eta":               eta,
        "horizon_ub":        horizon_ub,
        "big_m":             big_m,
        "k_max":             K_max,
        "weight_makespan":   weight_makespan,
        "weight_delay":      weight_delay,
        "weight_movements":  weight_movements,
    }


# ============================================================
#  Model construction
# ============================================================

def build_model(data: dict) -> gp.Model:
    """Build the full job-level MILP as a gurobipy Model.

    Returns an un-solved model.  Attaches:
        m._d  — the data dict
        m._v  — dict of variable collections keyed by name
    """
    aircraft      = data["aircraft"]
    positions     = data["positions"]
    blocking_arcs = data["blocking_arcs"]
    chains        = data["chains"]
    E             = data["earliest_start"]
    L             = data["target_finish"]
    eps           = data["min_separation"]
    mu            = data["mu"]
    delta         = data["delta"]
    eta           = data["eta"]
    M             = data["big_m"]
    H             = data["horizon_ub"]
    K_max         = data["k_max"]
    wM            = data["weight_makespan"]
    wD            = data["weight_delay"]
    wS            = data["weight_movements"]

    arc_set = set(blocking_arcs)

    m = gp.Model("milp_jobs_v2")

    # ---- Assignment binaries ---------------------------------------
    x = m.addVars(aircraft, positions, vtype=GRB.BINARY, name="x")
    m.addConstrs(
        (gp.quicksum(x[r, p] for p in positions) == 1 for r in aircraft),
        name="assign",
    )

    # ---- Per-job timing variables ----------------------------------
    s: dict[str, gp.Var] = {}
    f: dict[str, gp.Var] = {}
    k: dict[str, gp.Var] = {}
    for r in aircraft:
        for j in chains[r]:
            jid = j["id"]
            s[jid] = m.addVar(lb=0.0, ub=H,     name=f"s_{jid}")
            f[jid] = m.addVar(lb=0.0, ub=H,     name=f"f_{jid}")
            k[jid] = m.addVar(lb=0.0, ub=K_max, vtype=GRB.INTEGER, name=f"k_{jid}")
            interruptible = bool(j.get("interruptible", False))
            if not interruptible:
                m.addConstr(k[jid] == 0, name=f"non_int_{jid}")
            m.addConstr(
                f[jid] == s[jid] + float(j["duration"]) + delta * k[jid],
                name=f"dur_{jid}",
            )

    # Chain precedences
    for r in aircraft:
        chain = chains[r]
        for i in range(len(chain) - 1):
            m.addConstr(
                s[chain[i + 1]["id"]] >= f[chain[i]["id"]],
                name=f"chain_{chain[i]['id']}_{chain[i+1]['id']}",
            )

    # Aircraft-level shortcut variables (kept as separate continuous vars
    # bound to the chain endpoints so that constraints can reference them
    # without indexing into the chain repeatedly).
    s_r = {r: s[chains[r][0]["id"]]  for r in aircraft}
    f_r = {r: f[chains[r][-1]["id"]] for r in aircraft}

    # Earliest start (aircraft level)
    for r in aircraft:
        m.addConstr(s_r[r] >= E[r], name=f"es_{r}")

    # ---- Same-position sequencing (general: q activates only when both r, r' at p) ----
    q: dict[tuple[str, str, str], gp.Var] = {}
    for p in positions:
        for r in aircraft:
            for rp in aircraft:
                if r >= rp:
                    continue
                q[r, rp, p] = m.addVar(vtype=GRB.BINARY, name=f"q_{r}_{rp}_{p}")
                q[rp, r, p] = m.addVar(vtype=GRB.BINARY, name=f"q_{rp}_{r}_{p}")
                # When both share p, exactly one direction holds; otherwise both 0
                m.addConstr(q[r, rp, p] + q[rp, r, p] >= x[r, p] + x[rp, p] - 1,
                            name=f"qLB_{r}_{rp}_{p}")
                m.addConstr(q[r, rp, p] + q[rp, r, p] <= 1,
                            name=f"qUB_{r}_{rp}_{p}")
                m.addConstr(q[r, rp, p] <= x[r, p], name=f"qx1_{r}_{rp}_{p}")
                m.addConstr(q[r, rp, p] <= x[rp, p], name=f"qx2_{r}_{rp}_{p}")
                m.addConstr(q[rp, r, p] <= x[rp, p], name=f"qx3_{rp}_{r}_{p}")
                m.addConstr(q[rp, r, p] <= x[r, p], name=f"qx4_{rp}_{r}_{p}")
                # Sequencing with epsilon separation
                m.addConstr(
                    s_r[rp] >= f_r[r] + eps - M * (1 - q[r, rp, p]),
                    name=f"sep_{r}_{rp}_{p}",
                )
                m.addConstr(
                    s_r[r] >= f_r[rp] + eps - M * (1 - q[rp, r, p]),
                    name=f"sep_{rp}_{r}_{p}",
                )

    # ---- Placement-compatibility y_{rr'pp'} ------------------------
    y: dict[tuple[str, str, str, str], gp.Var] = {}
    for (p_f, p_r) in blocking_arcs:
        for r in aircraft:
            for rp in aircraft:
                if r == rp:
                    continue
                yv = m.addVar(vtype=GRB.BINARY, name=f"y_{r}_{rp}_{p_f}_{p_r}")
                y[r, rp, p_f, p_r] = yv
                m.addConstr(yv <= x[r, p_f],  name=f"yub1_{r}_{rp}_{p_f}_{p_r}")
                m.addConstr(yv <= x[rp, p_r], name=f"yub2_{r}_{rp}_{p_f}_{p_r}")
                m.addConstr(yv >= x[r, p_f] + x[rp, p_r] - 1,
                            name=f"ylb_{r}_{rp}_{p_f}_{p_r}")

    # ---- Partition indicators for each (r, rp, p_f, p_r) and access side --
    # Mode A z- / z+, Mode B per gap of r, Mode C per job of r
    z_minus: dict[tuple, gp.Var] = {}
    z_plus:  dict[tuple, gp.Var] = {}
    b_B:     dict[tuple, gp.Var] = {}   # (r, rp, p_f, p_r, a, gap_idx)
    b_C:     dict[tuple, gp.Var] = {}   # (r, rp, p_f, p_r, a, job_id)

    for (p_f, p_r) in blocking_arcs:
        for r in aircraft:
            chain_r = chains[r]
            for rp in aircraft:
                if r == rp:
                    continue
                yv = y[r, rp, p_f, p_r]
                for a in ("in", "out"):
                    zm = m.addVar(vtype=GRB.BINARY, name=f"z-_{r}_{rp}_{p_f}_{p_r}_{a}")
                    zp = m.addVar(vtype=GRB.BINARY, name=f"z+_{r}_{rp}_{p_f}_{p_r}_{a}")
                    z_minus[r, rp, p_f, p_r, a] = zm
                    z_plus [r, rp, p_f, p_r, a] = zp

                    bB_list = []
                    for gi in range(len(chain_r) - 1):
                        var = m.addVar(vtype=GRB.BINARY,
                                       name=f"bB_{r}_{rp}_{p_f}_{p_r}_{a}_{gi}")
                        b_B[r, rp, p_f, p_r, a, gi] = var
                        bB_list.append(var)

                    bC_list = []
                    for j in chain_r:
                        jid = j["id"]
                        var = m.addVar(vtype=GRB.BINARY,
                                       name=f"bC_{r}_{rp}_{p_f}_{p_r}_{a}_{jid}")
                        b_C[r, rp, p_f, p_r, a, jid] = var
                        if not bool(j.get("interruptible", False)):
                            m.addConstr(var == 0,
                                        name=f"non_int_C_{r}_{rp}_{p_f}_{p_r}_{a}_{jid}")
                        bC_list.append(var)

                    # Exhaustive partition: equals y (1 only when both placed at arc)
                    m.addConstr(
                        zm + zp + gp.quicksum(bB_list) + gp.quicksum(bC_list) == yv,
                        name=f"part_{r}_{rp}_{p_f}_{p_r}_{a}",
                    )

    # ---- Timing constraints linking indicators to s_j, f_j ---------
    for (p_f, p_r) in blocking_arcs:
        for r in aircraft:
            chain_r = chains[r]
            for rp in aircraft:
                if r == rp:
                    continue
                for a in ("in", "out"):
                    tau = s_r[rp] if a == "in" else f_r[rp]
                    zm = z_minus[r, rp, p_f, p_r, a]
                    zp = z_plus [r, rp, p_f, p_r, a]

                    # Mode-A (before/after) clearance: the front position is
                    # vacant at tau iff tau lies outside the front's stay
                    # [s_r, f_r] — closed bounds, matching the checker's
                    # semantics (which accepts accesses in the width-eta band
                    # immediately outside the stay).  The previous formulation
                    # required a full eta clearance (tau <= s_r - eta /
                    # tau >= f_r + eta), which was strictly more conservative
                    # than the problem statement and cut off feasible
                    # schedules at +-epsilon of a front stay (audited
                    # 2026-07-23: two_rows_loose seed8 wDLY, 4 band accesses).
                    m.addConstr(tau <= s_r[r] + M * (1 - zm),
                                name=f"zm_{r}_{rp}_{p_f}_{p_r}_{a}")
                    m.addConstr(tau >= f_r[r] - M * (1 - zp),
                                name=f"zp_{r}_{rp}_{p_f}_{p_r}_{a}")

                    # Mode B window
                    for gi in range(len(chain_r) - 1):
                        bB     = b_B[r, rp, p_f, p_r, a, gi]
                        jk_id  = chain_r[gi]["id"]
                        jk1_id = chain_r[gi + 1]["id"]
                        m.addConstr(tau >= f[jk_id]  - M * (1 - bB),
                                    name=f"bB_lb_{r}_{rp}_{p_f}_{p_r}_{a}_{gi}")
                        m.addConstr(tau <= s[jk1_id] + M * (1 - bB),
                                    name=f"bB_ub_{r}_{rp}_{p_f}_{p_r}_{a}_{gi}")

                    # Mode C window (strict interior)
                    for j in chain_r:
                        jid = j["id"]
                        bC  = b_C[r, rp, p_f, p_r, a, jid]
                        D_j = float(j["duration"])
                        m.addConstr(tau >= s[jid] + eta - M * (1 - bC),
                                    name=f"bC_lb_{r}_{rp}_{p_f}_{p_r}_{a}_{jid}")
                        m.addConstr(
                            tau <= s[jid] + D_j + delta * (k[jid] - bC) - eta
                                   + M * (1 - bC),
                            name=f"bC_ub_{r}_{rp}_{p_f}_{p_r}_{a}_{jid}",
                        )

    # ---- Mode B cumulative-gap rule (per front aircraft, per gap) ---
    # Gap >= mu * (number of Mode-B events that use this gap, across all
    # rear neighbours and both access sides).
    for r in aircraft:
        chain_r = chains[r]
        for gi in range(len(chain_r) - 1):
            jk_id  = chain_r[gi]["id"]
            jk1_id = chain_r[gi + 1]["id"]
            cum_B = gp.quicksum(
                b_B[r, rp, p_f, p_r, a, gi]
                for (p_f, p_r) in blocking_arcs
                for rp in aircraft
                if rp != r
                for a in ("in", "out")
            )
            m.addConstr(s[jk1_id] - f[jk_id] >= mu * cum_B,
                        name=f"bB_gap_{r}_{gi}")

    # ---- kappa_j == sum of Mode-C events ---------------------------
    for r in aircraft:
        for j in chains[r]:
            jid = j["id"]
            cum_C = gp.quicksum(
                b_C[r, rp, p_f, p_r, a, jid]
                for (p_f, p_r) in blocking_arcs
                for rp in aircraft
                if rp != r
                for a in ("in", "out")
            )
            m.addConstr(k[jid] == cum_C, name=f"kappa_{jid}")

    # ---- Movement count, delay, makespan ---------------------------
    n = m.addVar(lb=0.0, name="n")
    if b_B or b_C:
        m.addConstr(
            n == 2 * (
                gp.quicksum(b_B.values()) + gp.quicksum(b_C.values())
            ),
            name="movements",
        )
    else:
        m.addConstr(n == 0, name="movements")

    delay = m.addVars(aircraft, lb=0.0, name="delay")
    mks   = m.addVar(lb=0.0, name="makespan")
    for r in aircraft:
        m.addConstr(delay[r] >= f_r[r] - L[r], name=f"delay_{r}")
        m.addConstr(mks      >= f_r[r],         name=f"mks_{r}")

    # ---- Objective -------------------------------------------------
    m.setObjective(
        wM * mks + wD * gp.quicksum(delay[r] for r in aircraft) + wS * n,
        GRB.MINIMIZE,
    )

    m._d = data
    m._v = {
        "x": x, "s": s, "f": f, "k": k,
        "s_r": s_r, "f_r": f_r,
        "y": y, "q": q,
        "z_minus": z_minus, "z_plus": z_plus, "b_B": b_B, "b_C": b_C,
        "delay": delay, "mks": mks, "n": n,
    }
    return m


# ============================================================
#  Solution extraction
# ============================================================

_GUROBI_STATUS: dict[int, str] = {
    GRB.OPTIMAL:      "optimal",
    GRB.TIME_LIMIT:   "maxTimeLim",
    GRB.INFEASIBLE:   "infeasible",
    GRB.INF_OR_UNBD:  "infeasible",
    GRB.SUBOPTIMAL:   "feasible",
}


def get_solution(m: gp.Model, raw_data: dict) -> dict:
    """Extract a solution dict after m.optimize() has been called."""
    status_str = _GUROBI_STATUS.get(m.Status, "unknown")

    if m.SolCount == 0:
        return {
            "status":    status_str,
            "objective": None,
            "mip_gap":   None,
            "metrics":   {"makespan": None, "movements": None, "total_delay": None},
            "aircraft":  [],
        }

    data      = m._d
    aircraft  = data["aircraft"]
    positions = data["positions"]
    chains    = data["chains"]
    x         = m._v["x"]
    s         = m._v["s"]
    f         = m._v["f"]
    delay     = m._v["delay"]
    mks       = m._v["mks"]
    n         = m._v["n"]

    aircraft_list: list[dict] = []
    for r in aircraft:
        chosen_pos = next(p for p in positions if x[r, p].X > 0.5)
        chain = chains[r]
        s_r_val = s[chain[0]["id"]].X
        f_r_val = f[chain[-1]["id"]].X
        jobs_out = [
            {"id": j["id"],
             "start":  round(s[j["id"]].X, 4),
             "finish": round(f[j["id"]].X, 4)}
            for j in chain
        ]
        aircraft_list.append({
            "id":       r,
            "position": chosen_pos,
            "start":    round(s_r_val, 4),
            "finish":   round(f_r_val, 4),
            "delay":    round(delay[r].X, 4),
            "jobs":     jobs_out,
        })

    try:
        mip_gap = round(m.MIPGap, 6)
    except Exception:
        mip_gap = None

    return {
        "status":    status_str,
        "objective": round(m.ObjVal, 4),
        "mip_gap":   mip_gap,
        "metrics": {
            "makespan":    round(mks.X, 4),
            "movements":   int(round(n.X)),
            "total_delay": round(sum(delay[r].X for r in aircraft), 4),
        },
        "aircraft": aircraft_list,
    }


# ============================================================
#  __main__ — standalone smoke test
# ============================================================

if __name__ == "__main__":
    import json
    import os
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "input_data"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "output_data"))
    from instance_io           import load_json as load_instance      # noqa: E402
    from check_solution_jobs_v2 import check_solution, print_check     # noqa: E402

    _default = os.path.join(
        os.path.dirname(__file__), "..",
        "data", "instances_202605_02",
        "scn_triangle_tight_P5_R5", "scn_triangle_tight_P5_R5_seed1.json",
    )
    _path     = sys.argv[1] if len(sys.argv) > 1 else _default
    _raw_data = load_instance(_path)

    _data = prepare_data(_raw_data, 0.5, 0.1, 1.0, 10.0)
    _m    = build_model(_data)
    _m.setParam("TimeLimit", 60)
    _m.setParam("MIPGap", 0.0)
    _m.optimize()

    _solution = get_solution(_m, _raw_data)
    print(json.dumps(
        {"status": _solution["status"], "objective": _solution["objective"],
         "metrics": _solution["metrics"]}, indent=2,
    ))

    _report = check_solution(_solution, _raw_data)
    print_check(_report)
