"""
Abstract MILP model for aircraft positioning — aircraft-level formulation.

Removes the job concept from the optimisation model: each aircraft is treated
as a single block [s_r, s_r + D_r] where D_r is computed offline as the sum
of its job durations.  The blocking conditions of milp_pyomo.py remain
unchanged since they depend only on aircraft start/finish times.  Job-level
start times are recovered deterministically from s_r by walking the
precedence chain (see get_solution).

Call model.create_instance(prepare_data(raw_data, ...)) to get a concrete
instance, identical to the workflow of milp_pyomo.py.
"""
import json

from pyomo.environ import (
    AbstractModel,
    Binary,
    Constraint,
    NonNegativeReals,
    Objective,
    Param,
    Set,
    Var,
    minimize,
)

# =================================================================
#  Abstract model declaration
# =================================================================
model = AbstractModel()

# --- Base sets ---
model.sAircraft = Set()
model.sPositions = Set()
model.sBlockingArcs = Set(dimen=2)

# --- Parameters ---
model.pDuration = Param(model.sAircraft, within=NonNegativeReals)   # D_r
model.pEarliestStart = Param(model.sAircraft, within=NonNegativeReals)
model.pTargetFinish = Param(model.sAircraft, within=NonNegativeReals)
model.pMinSeparation = Param(within=NonNegativeReals)
# Technical horizon H^{UB}: upper bound on every aircraft start/finish.
model.pHorizonUB = Param(within=NonNegativeReals)
# Big-M constant: H^{UB} + epsilon, so big-M deactivations are tight.
model.pBigM = Param(within=NonNegativeReals)
model.pWeightMakespan = Param(within=NonNegativeReals)
model.pWeightDelay = Param(within=NonNegativeReals)
model.pWeightMovements = Param(within=NonNegativeReals)

# --- Derived sets ---
model.sAircraftPairsOrdered = Set(
    dimen=3,
    initialize=lambda m: [
        (r, rp, p) for r in m.sAircraft for rp in m.sAircraft for p in m.sPositions if r != rp
    ],
)
model.sAircraftPairsUnordered = Set(
    dimen=3,
    initialize=lambda m: [
        (r, rp, p) for r in m.sAircraft for rp in m.sAircraft for p in m.sPositions if r < rp
    ],
)
model.sBlockingTuples = Set(
    dimen=4,
    initialize=lambda m: [
        (r, rp, p, pp)
        for r in m.sAircraft
        for rp in m.sAircraft
        for (p, pp) in m.sBlockingArcs
        if r != rp
    ],
)

# --- Variables ---
# Aircraft start/finish times are bounded above by pHorizonUB = H^{UB};
# this tightens the LP relaxation.  The big-M constant pBigM = H^{UB} +
# epsilon (set in prepare_data) is slightly larger so big-M deactivations
# remain valid.
def _time_bounds(m, r):
    return (0.0, m.pHorizonUB)


model.vAircraftStart = Var(model.sAircraft, domain=NonNegativeReals, bounds=_time_bounds)
model.vAircraftFinish = Var(model.sAircraft, domain=NonNegativeReals, bounds=_time_bounds)
model.vAircraftPosition = Var(model.sAircraft, model.sPositions, domain=Binary)
model.vAircraftOrder = Var(model.sAircraftPairsOrdered, domain=Binary)
model.vAlphaIn = Var(model.sBlockingTuples, domain=Binary)
model.vBetaIn = Var(model.sBlockingTuples, domain=Binary)
model.vUIn = Var(model.sBlockingTuples, domain=Binary)
model.vAlphaOut = Var(model.sBlockingTuples, domain=Binary)
model.vBetaOut = Var(model.sBlockingTuples, domain=Binary)
model.vUOut = Var(model.sBlockingTuples, domain=Binary)
model.vDelay = Var(model.sAircraft, domain=NonNegativeReals)
model.vMakespan = Var(domain=NonNegativeReals)
model.vMovements = Var(domain=NonNegativeReals)


# =================================================================
#  Constraint rules
# =================================================================

# -- Assignment and timing --

def fcAssignAircraft(m, r):
    return sum(m.vAircraftPosition[r, p] for p in m.sPositions) == 1


def fcAircraftDuration(m, r):
    return m.vAircraftFinish[r] == m.vAircraftStart[r] + m.pDuration[r]


def fcEarliestStart(m, r):
    return m.vAircraftStart[r] >= m.pEarliestStart[r]


# -- Same-position non-overlap with separation --

def fcSamePositionSep(m, r, rp, p):
    # If r precedes r' at position p (vAircraftOrder[r,r',p] = 1) and both are
    # at p, then start[r'] >= finish[r] + min_separation.
    return m.vAircraftStart[rp] >= (
        m.vAircraftFinish[r]
        + m.pMinSeparation
        - m.pBigM * (1 - m.vAircraftOrder[r, rp, p])
        - m.pBigM * (1 - m.vAircraftPosition[r, p])
        - m.pBigM * (1 - m.vAircraftPosition[rp, p])
    )


def fcOrderConsistencyLB(m, r, rp, p):
    return (
        m.vAircraftOrder[r, rp, p] + m.vAircraftOrder[rp, r, p]
        >= m.vAircraftPosition[r, p] + m.vAircraftPosition[rp, p] - 1
    )


def fcOrderConsistencyUB(m, r, rp, p):
    return m.vAircraftOrder[r, rp, p] + m.vAircraftOrder[rp, r, p] <= 1


# -- Blocking: entry --

def fcAlphaInLB(m, r, rp, p, pp):
    return m.vAircraftStart[rp] >= m.vAircraftStart[r] - m.pBigM * (
        1 - m.vAlphaIn[r, rp, p, pp]
    )


def fcAlphaInUB(m, r, rp, p, pp):
    return m.vAircraftStart[rp] <= (
        m.vAircraftStart[r] + m.pBigM * m.vAlphaIn[r, rp, p, pp]
    )


def fcBetaInUB(m, r, rp, p, pp):
    return m.vAircraftStart[rp] <= m.vAircraftFinish[r] - m.pMinSeparation + m.pBigM * (
        1 - m.vBetaIn[r, rp, p, pp]
    )


def fcBetaInLB(m, r, rp, p, pp):
    # Position-guarded: only binding when r is at p and rp is at pp.
    return m.vAircraftStart[rp] >= m.vAircraftFinish[r] \
        - m.pBigM * m.vBetaIn[r, rp, p, pp] \
        - m.pBigM * (1 - m.vAircraftPosition[r, p]) \
        - m.pBigM * (1 - m.vAircraftPosition[rp, pp])


def fcUInUB1(m, r, rp, p, pp):
    return m.vUIn[r, rp, p, pp] <= m.vAircraftPosition[r, p]


def fcUInUB2(m, r, rp, p, pp):
    return m.vUIn[r, rp, p, pp] <= m.vAircraftPosition[rp, pp]


def fcUInUB3(m, r, rp, p, pp):
    return m.vUIn[r, rp, p, pp] <= m.vAlphaIn[r, rp, p, pp]


def fcUInUB4(m, r, rp, p, pp):
    return m.vUIn[r, rp, p, pp] <= m.vBetaIn[r, rp, p, pp]


def fcUInLB(m, r, rp, p, pp):
    return m.vUIn[r, rp, p, pp] >= (
        m.vAircraftPosition[r, p]
        + m.vAircraftPosition[rp, pp]
        + m.vAlphaIn[r, rp, p, pp]
        + m.vBetaIn[r, rp, p, pp]
        - 3
    )


# -- Blocking: exit --

def fcAlphaOutLB(m, r, rp, p, pp):
    return m.vAircraftFinish[rp] >= m.vAircraftStart[r] - m.pBigM * (
        1 - m.vAlphaOut[r, rp, p, pp]
    )


def fcAlphaOutUB(m, r, rp, p, pp):
    return m.vAircraftFinish[rp] <= (
        m.vAircraftStart[r] + m.pBigM * m.vAlphaOut[r, rp, p, pp]
    )


def fcBetaOutUB(m, r, rp, p, pp):
    return m.vAircraftFinish[rp] <= m.vAircraftFinish[r] - m.pMinSeparation + m.pBigM * (
        1 - m.vBetaOut[r, rp, p, pp]
    )


def fcBetaOutLB(m, r, rp, p, pp):
    return m.vAircraftFinish[rp] >= m.vAircraftFinish[r] \
        - m.pBigM * m.vBetaOut[r, rp, p, pp] \
        - m.pBigM * (1 - m.vAircraftPosition[r, p]) \
        - m.pBigM * (1 - m.vAircraftPosition[rp, pp])


def fcUOutUB1(m, r, rp, p, pp):
    return m.vUOut[r, rp, p, pp] <= m.vAircraftPosition[r, p]


def fcUOutUB2(m, r, rp, p, pp):
    return m.vUOut[r, rp, p, pp] <= m.vAircraftPosition[rp, pp]


def fcUOutUB3(m, r, rp, p, pp):
    return m.vUOut[r, rp, p, pp] <= m.vAlphaOut[r, rp, p, pp]


def fcUOutUB4(m, r, rp, p, pp):
    return m.vUOut[r, rp, p, pp] <= m.vBetaOut[r, rp, p, pp]


def fcUOutLB(m, r, rp, p, pp):
    return m.vUOut[r, rp, p, pp] >= (
        m.vAircraftPosition[r, p]
        + m.vAircraftPosition[rp, pp]
        + m.vAlphaOut[r, rp, p, pp]
        + m.vBetaOut[r, rp, p, pp]
        - 3
    )


# -- Movements, delays, makespan --

def fcMovements(m):
    return m.vMovements == 2 * sum(
        m.vUIn[idx] + m.vUOut[idx] for idx in m.sBlockingTuples
    )


def fcDelay(m, r):
    return m.vDelay[r] >= m.vAircraftFinish[r] - m.pTargetFinish[r]


def fcMakespan(m, r):
    return m.vMakespan >= m.vAircraftFinish[r]


# =================================================================
#  Activate constraints
# =================================================================
model.cAssignAircraft = Constraint(model.sAircraft, rule=fcAssignAircraft)
model.cAircraftDuration = Constraint(model.sAircraft, rule=fcAircraftDuration)
model.cEarliestStart = Constraint(model.sAircraft, rule=fcEarliestStart)

model.cSamePositionSep = Constraint(model.sAircraftPairsOrdered, rule=fcSamePositionSep)
model.cOrderConsistencyLB = Constraint(model.sAircraftPairsUnordered, rule=fcOrderConsistencyLB)
model.cOrderConsistencyUB = Constraint(model.sAircraftPairsUnordered, rule=fcOrderConsistencyUB)

model.cAlphaInLB = Constraint(model.sBlockingTuples, rule=fcAlphaInLB)
model.cAlphaInUB = Constraint(model.sBlockingTuples, rule=fcAlphaInUB)
model.cBetaInUB = Constraint(model.sBlockingTuples, rule=fcBetaInUB)
model.cBetaInLB = Constraint(model.sBlockingTuples, rule=fcBetaInLB)
model.cUInUB1 = Constraint(model.sBlockingTuples, rule=fcUInUB1)
model.cUInUB2 = Constraint(model.sBlockingTuples, rule=fcUInUB2)
model.cUInUB3 = Constraint(model.sBlockingTuples, rule=fcUInUB3)
model.cUInUB4 = Constraint(model.sBlockingTuples, rule=fcUInUB4)
model.cUInLB = Constraint(model.sBlockingTuples, rule=fcUInLB)

model.cAlphaOutLB = Constraint(model.sBlockingTuples, rule=fcAlphaOutLB)
model.cAlphaOutUB = Constraint(model.sBlockingTuples, rule=fcAlphaOutUB)
model.cBetaOutUB = Constraint(model.sBlockingTuples, rule=fcBetaOutUB)
model.cBetaOutLB = Constraint(model.sBlockingTuples, rule=fcBetaOutLB)
model.cUOutUB1 = Constraint(model.sBlockingTuples, rule=fcUOutUB1)
model.cUOutUB2 = Constraint(model.sBlockingTuples, rule=fcUOutUB2)
model.cUOutUB3 = Constraint(model.sBlockingTuples, rule=fcUOutUB3)
model.cUOutUB4 = Constraint(model.sBlockingTuples, rule=fcUOutUB4)
model.cUOutLB = Constraint(model.sBlockingTuples, rule=fcUOutLB)

model.cMovements = Constraint(rule=fcMovements)
model.cDelay = Constraint(model.sAircraft, rule=fcDelay)
model.cMakespan = Constraint(model.sAircraft, rule=fcMakespan)


# =================================================================
#  Objective
# =================================================================
def obj_rule(m):
    return (
        m.pWeightMakespan * m.vMakespan
        + m.pWeightDelay * sum(m.vDelay[r] for r in m.sAircraft)
        + m.pWeightMovements * m.vMovements
    )


model.obj = Objective(rule=obj_rule, sense=minimize)


# =================================================================
#  Data helpers
# =================================================================

def _sort_job_chain(jobs: list[dict], precedences: list[dict]) -> list[dict]:
    """Return *jobs* sorted in chain order via the precedence graph."""
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
    chain = []
    cur = roots[0]
    while cur:
        chain.append(job_map[cur])
        cur = succ.get(cur)
    seen = {j["id"] for j in chain}
    chain += [job_map[jid] for jid in job_ids if jid not in seen]
    return chain


def prepare_data(
    raw_data: dict,
    min_separation: float,
    weight_makespan: float,
    weight_delay: float,
    weight_movements: float,
) -> dict:
    """Convert JSON instance data to the aircraft-level Pyomo data dict.

    The job-level data is consumed only to compute the aggregated duration
    D_r and to cache the chain order for solution recovery.  The cached
    chain is attached to *raw_data* under the key ``__ac_chain__`` so that
    ``get_solution`` can rebuild the job schedule downstream.

    ``min_separation`` is read from ``raw_data['min_separation']`` when
    present (per-instance epsilon); otherwise the argument value is used as
    a fallback.
    """
    aircraft_data = raw_data["aircrafts"]
    job_data = raw_data["jobs"]
    hangar = raw_data["hangar"]
    precedences = raw_data.get("job_precedences", [])
    # Per-instance epsilon wins over the argument fallback.
    if "min_separation" in raw_data:
        min_separation = float(raw_data["min_separation"])

    aircraft = [a["id"] for a in aircraft_data]
    positions = hangar["positions"]
    blocking_arcs = [(arc["front"], arc["rear"]) for arc in hangar["blocking_arcs"]]

    # Group jobs by aircraft and sort each chain
    by_ac: dict[str, list[dict]] = {}
    for j in job_data:
        by_ac.setdefault(j["aircraft_id"], []).append(j)
    chains: dict[str, list[dict]] = {
        r: _sort_job_chain(by_ac.get(r, []), precedences) for r in aircraft
    }
    durations = {r: sum(j["duration"] for j in chains[r]) for r in aircraft}

    # Cache chain order on raw_data for downstream recovery
    raw_data["__ac_chain__"] = chains

    # Technical upper bound H^{UB}: makespan of the worst-case sequential
    # schedule that processes every aircraft on a single position, starting
    # at the latest earliest-start.  Used to bound the time variables.
    # Big-M is set to H^{UB} + epsilon so that constraints with a +epsilon
    # offset (sequencing, beta lower bounds) are fully deactivated when
    # their guard binaries are inactive.
    n_ac = len(aircraft)
    max_es = max((a["earliest_start"] for a in aircraft_data), default=0.0)
    horizon_ub = max_es + sum(durations.values()) + max(0, n_ac - 1) * min_separation
    big_m = horizon_ub + min_separation

    return {
        None: {
            "sAircraft": {None: aircraft},
            "sPositions": {None: positions},
            "sBlockingArcs": {None: blocking_arcs},
            "pDuration": durations,
            "pEarliestStart": {a["id"]: a["earliest_start"] for a in aircraft_data},
            "pTargetFinish":  {a["id"]: a["target_finish"]  for a in aircraft_data},
            "pMinSeparation":   {None: min_separation},
            "pHorizonUB":       {None: horizon_ub},
            "pBigM":            {None: big_m},
            "pWeightMakespan":  {None: weight_makespan},
            "pWeightDelay":     {None: weight_delay},
            "pWeightMovements": {None: weight_movements},
        }
    }


def get_solution(instance, result, raw_data: dict) -> dict:
    """Extract a job-level solution from the aircraft-level model.

    Job timings are recovered by walking the chain order cached in
    ``raw_data['__ac_chain__']`` from ``prepare_data``.

    Schema is identical to milp_pyomo.get_solution.
    """
    chains: dict[str, list[dict]] = raw_data.get("__ac_chain__", {})

    aircraft_list = []
    for r in instance.sAircraft:
        position = next(
            p for p in instance.sPositions if instance.vAircraftPosition[r, p]() > 0.5
        )
        s_r = round(instance.vAircraftStart[r](), 4)
        f_r = round(instance.vAircraftFinish[r](), 4)

        # Recover job schedule by walking the chain
        jobs = []
        t = s_r
        for j in chains.get(r, []):
            j_start = round(t, 4)
            j_finish = round(t + j["duration"], 4)
            jobs.append({"id": j["id"], "start": j_start, "finish": j_finish})
            t = j_finish

        aircraft_list.append({
            "id":       r,
            "position": position,
            "start":    s_r,
            "finish":   f_r,
            "delay":    round(instance.vDelay[r](), 2),
            "jobs":     jobs,
        })

    obj_val = instance.obj()
    obj_bound = getattr(result.problem, "lower_bound", None)
    if obj_bound is not None and obj_val is not None and abs(obj_val) > 1e-10:
        mip_gap = round(abs(obj_val - obj_bound) / abs(obj_val), 6)
    else:
        mip_gap = None

    return {
        "status":    str(result.solver.termination_condition),
        "objective": round(obj_val, 2),
        "mip_gap":   mip_gap,
        "metrics": {
            "makespan":    round(instance.vMakespan(),   2),
            "movements":   int(round(instance.vMovements())),
            "total_delay": round(sum(instance.vDelay[r]() for r in instance.sAircraft), 2),
        },
        "aircraft": aircraft_list,
    }


if __name__ == "__main__":
    import os
    import sys
    from pyomo.environ import SolverFactory

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "output_data"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "input_data"))
    from instance_io import load_json as load_instance      # noqa: E402
    from check_solution import check_solution, print_check  # noqa: E402

    min_separation = 1.0
    weight_makespan = 0.1
    weight_delay = 1.0
    weight_movements = 10.0

    instance_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(
            os.path.dirname(__file__), "..",
            "data", "instances_202605", "scn_easy_loose_P5_R4",
            "scn_easy_loose_P5_R4_seed1.json",
        )
    )
    raw_data = load_instance(instance_path)

    instance = model.create_instance(
        prepare_data(raw_data, min_separation, weight_makespan, weight_delay, weight_movements)
    )
    solver = SolverFactory("gurobi")
    solver.options["TimeLimit"] = 60
    solver.options["MIPGap"] = 0.0
    result = solver.solve(instance, tee=True)
    solution = get_solution(instance, result, raw_data)
    print(json.dumps(solution, indent=2))

    report = check_solution(solution, raw_data)
    print_check(report)
