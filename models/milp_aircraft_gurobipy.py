"""
Native gurobipy MILP for aircraft positioning — aircraft-level formulation.

Drop-in replacement for milp_aircraft_pyomo.py using the gurobipy API
directly, which avoids the Pyomo model-build overhead and is significantly
faster for large instances.

Public API
----------
prepare_data(raw_data, min_sep, w_mks, w_dly, w_mov) -> dict
    Convert instance JSON to a flat data dict.
build_model(data) -> gp.Model
    Construct the gurobipy model (variables + constraints + objective).
    Does NOT call m.optimize(); set solver parameters externally.
get_solution(m, raw_data) -> dict
    Extract the solution dict after m.optimize() has returned.
"""
from __future__ import annotations

import gurobipy as gp
from gurobipy import GRB


# ============================================================
#  Chain helper
# ============================================================

def _sort_job_chain(jobs: list[dict], precedences: list[dict]) -> list[dict]:
    """Return jobs sorted in chain order via the precedence graph."""
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
    while cur:
        chain.append(job_map[cur])
        cur = succ.get(cur)
    seen = {j["id"] for j in chain}
    chain += [job_map[jid] for jid in job_ids if jid not in seen]
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
    """Convert JSON instance data to a flat data dict for build_model.

    Side-effects: caches chain order on raw_data["__ac_chain__"] for
    downstream solution recovery (same contract as milp_aircraft_pyomo).
    Per-instance min_separation in raw_data wins over the argument.
    """
    aircraft_data = raw_data["aircrafts"]
    job_data      = raw_data["jobs"]
    hangar        = raw_data["hangar"]
    precedences   = raw_data.get("job_precedences", [])
    if "min_separation" in raw_data:
        min_separation = float(raw_data["min_separation"])

    aircraft      = [a["id"] for a in aircraft_data]
    positions     = hangar["positions"]
    blocking_arcs = [(arc["front"], arc["rear"]) for arc in hangar["blocking_arcs"]]

    by_ac: dict[str, list[dict]] = {}
    for j in job_data:
        by_ac.setdefault(j["aircraft_id"], []).append(j)
    chains    = {r: _sort_job_chain(by_ac.get(r, []), precedences) for r in aircraft}
    durations = {r: sum(j["duration"] for j in chains[r]) for r in aircraft}

    raw_data["__ac_chain__"] = chains

    n_ac      = len(aircraft)
    max_es    = max((a["earliest_start"] for a in aircraft_data), default=0.0)
    horizon_ub = max_es + sum(durations.values()) + max(0, n_ac - 1) * min_separation
    big_m      = horizon_ub + min_separation

    return {
        "aircraft":         aircraft,
        "positions":        positions,
        "blocking_arcs":    blocking_arcs,
        "durations":        durations,
        "earliest_start":   {a["id"]: a["earliest_start"] for a in aircraft_data},
        "target_finish":    {a["id"]: a["target_finish"]  for a in aircraft_data},
        "min_separation":   min_separation,
        "horizon_ub":       horizon_ub,
        "big_m":            big_m,
        "weight_makespan":  weight_makespan,
        "weight_delay":     weight_delay,
        "weight_movements": weight_movements,
    }


# ============================================================
#  Model construction
# ============================================================

def build_model(data: dict) -> gp.Model:
    """Build the aircraft-level MILP as a gurobipy Model.

    The model is returned un-solved.  Set solver parameters
    (TimeLimit, MIPGap, …) on the returned object and call m.optimize().

    Attributes stored on the returned model:
        m._d  — the data dict (same reference as the *data* argument)
        m._v  — dict of variable collections keyed by name
    """
    ac   = data["aircraft"]
    pos  = data["positions"]
    arcs = data["blocking_arcs"]
    D    = data["durations"]
    E    = data["earliest_start"]
    L    = data["target_finish"]
    eps  = data["min_separation"]
    H    = data["horizon_ub"]
    M    = data["big_m"]
    wM   = data["weight_makespan"]
    wD   = data["weight_delay"]
    wS   = data["weight_movements"]

    # Derived index lists
    ordered   = [(r, rp, p)       for r in ac for rp in ac for p in pos   if r != rp]
    unordered = [(r, rp, p)       for r in ac for rp in ac for p in pos   if r  < rp]
    bt        = [(r, rp, p, pp)   for r in ac for rp in ac for (p, pp) in arcs if r != rp]

    m = gp.Model()

    # ----------------------------------------------------------
    # Variables
    # ----------------------------------------------------------
    s    = m.addVars(ac,        lb=0.0, ub=H,            name="s")
    f    = m.addVars(ac,        lb=0.0, ub=H,            name="f")
    x    = m.addVars(ac, pos,   vtype=GRB.BINARY,        name="x")
    o    = m.addVars(ordered,   vtype=GRB.BINARY,        name="o")
    ain  = m.addVars(bt,        vtype=GRB.BINARY,        name="ain")
    bin_ = m.addVars(bt,        vtype=GRB.BINARY,        name="bin")
    uin  = m.addVars(bt,        vtype=GRB.BINARY,        name="uin")
    aout = m.addVars(bt,        vtype=GRB.BINARY,        name="aout")
    bout = m.addVars(bt,        vtype=GRB.BINARY,        name="bout")
    uout = m.addVars(bt,        vtype=GRB.BINARY,        name="uout")
    dly  = m.addVars(ac,        lb=0.0,                  name="dly")
    mks  = m.addVar(            lb=0.0,                  name="mks")
    mov  = m.addVar(            lb=0.0,                  name="mov")

    # ----------------------------------------------------------
    # Constraints — assignment & timing
    # ----------------------------------------------------------
    m.addConstrs((gp.quicksum(x[r, p] for p in pos) == 1  for r in ac),  name="assign")
    m.addConstrs((f[r] == s[r] + D[r]                      for r in ac),  name="duration")
    m.addConstrs((s[r] >= E[r]                              for r in ac),  name="earliest")

    # ----------------------------------------------------------
    # Same-position non-overlap with separation
    # ----------------------------------------------------------
    m.addConstrs(
        (s[rp] >= f[r] + eps
         - M * (1 - o[r, rp, p])
         - M * (1 - x[r, p])
         - M * (1 - x[rp, p])
         for r, rp, p in ordered),
        name="sep",
    )
    m.addConstrs(
        (o[r, rp, p] + o[rp, r, p] >= x[r, p] + x[rp, p] - 1
         for r, rp, p in unordered),
        name="ordLB",
    )
    m.addConstrs(
        (o[r, rp, p] + o[rp, r, p] <= 1
         for r, rp, p in unordered),
        name="ordUB",
    )

    # ----------------------------------------------------------
    # Blocking — entry
    # ----------------------------------------------------------
    m.addConstrs(
        (s[rp] >= s[r] - M * (1 - ain[r, rp, p, pp])
         for r, rp, p, pp in bt),
        name="aInLB",
    )
    m.addConstrs(
        (s[rp] <= s[r] + M * ain[r, rp, p, pp]
         for r, rp, p, pp in bt),
        name="aInUB",
    )
    m.addConstrs(
        (s[rp] <= f[r] - eps + M * (1 - bin_[r, rp, p, pp])
         for r, rp, p, pp in bt),
        name="bInUB",
    )
    m.addConstrs(
        (s[rp] >= f[r]
         - M * bin_[r, rp, p, pp]
         - M * (1 - x[r, p])
         - M * (1 - x[rp, pp])
         for r, rp, p, pp in bt),
        name="bInLB",
    )
    m.addConstrs((uin[r, rp, p, pp] <= x[r, p]            for r, rp, p, pp in bt), name="uInUB1")
    m.addConstrs((uin[r, rp, p, pp] <= x[rp, pp]          for r, rp, p, pp in bt), name="uInUB2")
    m.addConstrs((uin[r, rp, p, pp] <= ain[r, rp, p, pp]  for r, rp, p, pp in bt), name="uInUB3")
    m.addConstrs((uin[r, rp, p, pp] <= bin_[r, rp, p, pp] for r, rp, p, pp in bt), name="uInUB4")
    m.addConstrs(
        (uin[r, rp, p, pp] >= x[r, p] + x[rp, pp] + ain[r, rp, p, pp] + bin_[r, rp, p, pp] - 3
         for r, rp, p, pp in bt),
        name="uInLB",
    )

    # ----------------------------------------------------------
    # Blocking — exit
    # ----------------------------------------------------------
    m.addConstrs(
        (f[rp] >= s[r] - M * (1 - aout[r, rp, p, pp])
         for r, rp, p, pp in bt),
        name="aOutLB",
    )
    m.addConstrs(
        (f[rp] <= s[r] + M * aout[r, rp, p, pp]
         for r, rp, p, pp in bt),
        name="aOutUB",
    )
    m.addConstrs(
        (f[rp] <= f[r] - eps + M * (1 - bout[r, rp, p, pp])
         for r, rp, p, pp in bt),
        name="bOutUB",
    )
    m.addConstrs(
        (f[rp] >= f[r]
         - M * bout[r, rp, p, pp]
         - M * (1 - x[r, p])
         - M * (1 - x[rp, pp])
         for r, rp, p, pp in bt),
        name="bOutLB",
    )
    m.addConstrs((uout[r, rp, p, pp] <= x[r, p]             for r, rp, p, pp in bt), name="uOutUB1")
    m.addConstrs((uout[r, rp, p, pp] <= x[rp, pp]           for r, rp, p, pp in bt), name="uOutUB2")
    m.addConstrs((uout[r, rp, p, pp] <= aout[r, rp, p, pp]  for r, rp, p, pp in bt), name="uOutUB3")
    m.addConstrs((uout[r, rp, p, pp] <= bout[r, rp, p, pp]  for r, rp, p, pp in bt), name="uOutUB4")
    m.addConstrs(
        (uout[r, rp, p, pp] >= x[r, p] + x[rp, pp] + aout[r, rp, p, pp] + bout[r, rp, p, pp] - 3
         for r, rp, p, pp in bt),
        name="uOutLB",
    )

    # ----------------------------------------------------------
    # Movements, delay, makespan
    # ----------------------------------------------------------
    if bt:
        m.addConstr(
            mov == 2 * gp.quicksum(uin[idx] + uout[idx] for idx in bt),
            name="movements",
        )
    else:
        m.addConstr(mov == 0, name="movements")

    m.addConstrs((dly[r] >= f[r] - L[r]  for r in ac), name="delay")
    m.addConstrs((mks >= f[r]             for r in ac), name="makespan")

    # ----------------------------------------------------------
    # Objective
    # ----------------------------------------------------------
    m.setObjective(
        wM * mks + wD * gp.quicksum(dly[r] for r in ac) + wS * mov,
        GRB.MINIMIZE,
    )

    m._d = data
    m._v = {
        "s": s, "f": f, "x": x, "o": o,
        "ain": ain, "bin_": bin_, "uin": uin,
        "aout": aout, "bout": bout, "uout": uout,
        "dly": dly, "mks": mks, "mov": mov,
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
    """Extract the solution dict after m.optimize() has been called.

    Returns a dict with the same schema as milp_aircraft_pyomo.get_solution.
    If Gurobi found no feasible solution (SolCount == 0), the objective and
    metrics are None and aircraft is an empty list.
    """
    status_str = _GUROBI_STATUS.get(m.Status, "unknown")

    if m.SolCount == 0:
        return {
            "status":    status_str,
            "objective": None,
            "mip_gap":   None,
            "metrics":   {"makespan": None, "movements": None, "total_delay": None},
            "aircraft":  [],
        }

    chains = raw_data.get("__ac_chain__", {})
    ac   = m._d["aircraft"]
    pos  = m._d["positions"]
    s    = m._v["s"]
    f    = m._v["f"]
    x    = m._v["x"]
    dly  = m._v["dly"]
    mks  = m._v["mks"]
    mov  = m._v["mov"]

    aircraft_list = []
    for r in ac:
        position = next(p for p in pos if x[r, p].X > 0.5)
        s_r = round(s[r].X, 4)
        f_r = round(f[r].X, 4)

        jobs: list[dict] = []
        t = s_r
        for j in chains.get(r, []):
            j_start  = round(t, 4)
            j_finish = round(t + j["duration"], 4)
            jobs.append({"id": j["id"], "start": j_start, "finish": j_finish})
            t = j_finish

        aircraft_list.append({
            "id":       r,
            "position": position,
            "start":    s_r,
            "finish":   f_r,
            "delay":    round(dly[r].X, 2),
            "jobs":     jobs,
        })

    obj_val = round(m.ObjVal, 2)
    try:
        mip_gap = round(m.MIPGap, 6)
    except AttributeError:
        mip_gap = None

    return {
        "status":    status_str,
        "objective": obj_val,
        "mip_gap":   mip_gap,
        "metrics": {
            "makespan":    round(mks.X, 2),
            "movements":   int(round(mov.X)),
            "total_delay": round(sum(dly[r].X for r in ac), 2),
        },
        "aircraft": aircraft_list,
    }


# ============================================================
#  __main__ — standalone smoke-test
# ============================================================

if __name__ == "__main__":
    import json
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "input_data"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "output_data"))
    from instance_io import load_json as load_instance      # noqa: E402
    from check_solution import check_solution, print_check  # noqa: E402

    _default = os.path.join(
        os.path.dirname(__file__), "..",
        "data", "instances_202605", "scn_easy_loose_P5_R4",
        "scn_easy_loose_P5_R4_seed1.json",
    )
    _path     = sys.argv[1] if len(sys.argv) > 1 else _default
    _raw_data = load_instance(_path)

    _data = prepare_data(_raw_data, 0.5, 0.1, 1.0, 10.0)
    _m    = build_model(_data)
    _m.setParam("TimeLimit", 60)
    _m.setParam("MIPGap", 0.0)
    _m.optimize()

    _solution = get_solution(_m, _raw_data)
    print(json.dumps(_solution, indent=2))

    _report = check_solution(_solution, _raw_data)
    print_check(_report)
