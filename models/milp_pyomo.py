"""
Abstract MILP model for aircraft positioning.
Call model.create_instance(prepare_data(raw_data)) to get a concrete instance.
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
model.sJobs = Set()
model.sAircraft = Set()
model.sPositions = Set()
model.sClients = Set()
model.sBlockingArcs = Set(dimen=2)
model.sPrecedences = Set(dimen=2)

# --- Parameters (declared before derived sets that reference them) ---
model.pDuration = Param(model.sJobs, within=NonNegativeReals)
model.pEarliestStart = Param(model.sAircraft, within=NonNegativeReals)
model.pTargetFinish = Param(model.sAircraft, within=NonNegativeReals)
model.pJobAircraft = Param(model.sJobs, model.sAircraft, within=Binary)
model.pClientAircraft = Param(model.sAircraft, model.sClients, within=Binary)
model.pFirstJob = Param(model.sJobs, model.sAircraft, within=Binary)
model.pLastJob = Param(model.sJobs, model.sAircraft, within=Binary)
model.pMinSeparation = Param(within=NonNegativeReals)
model.pBigM = Param(within=NonNegativeReals)
model.pWeightMakespan = Param(within=NonNegativeReals)
model.pWeightDelay = Param(within=NonNegativeReals)
model.pWeightMovements = Param(within=NonNegativeReals)

# --- Derived sets (rules evaluated at create_instance time) ---
model.sJobPairsOrdered = Set(
    dimen=3,
    initialize=lambda m: [
        (j, jp, p) for j in m.sJobs for jp in m.sJobs for p in m.sPositions if j != jp
    ],
)
model.sJobPairsUnordered = Set(
    dimen=3,
    initialize=lambda m: [
        (j, jp, p) for j in m.sJobs for jp in m.sJobs for p in m.sPositions if j < jp
    ],
)
model.sFirstJobAircraft = Set(
    dimen=2,
    initialize=lambda m: [
        (j, r) for j in m.sJobs for r in m.sAircraft if m.pFirstJob[j, r] == 1
    ],
)
model.sAircraftPairsPosition = Set(
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
model.vStartTime = Var(model.sJobs, domain=NonNegativeReals)
model.vFinishTime = Var(model.sJobs, domain=NonNegativeReals)
model.vAircraftStart = Var(model.sAircraft, domain=NonNegativeReals)
model.vAircraftFinish = Var(model.sAircraft, domain=NonNegativeReals)
model.vJobPosition = Var(model.sJobs, model.sPositions, domain=Binary)
model.vAircraftPosition = Var(model.sAircraft, model.sPositions, domain=Binary)
model.vJobOrder = Var(model.sJobPairsOrdered, domain=Binary)
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


def fcJobPosition(m, j, p):
    # y_jp = x_rp for the unique r with R_jr = 1, expressed as a sum over all r
    return m.vJobPosition[j, p] == sum(
        m.pJobAircraft[j, r] * m.vAircraftPosition[r, p] for r in m.sAircraft
    )


def fcFinishTime(m, j):
    return m.vFinishTime[j] == m.vStartTime[j] + m.pDuration[j]


def fcEarliestStart(m, j, r):
    return m.vStartTime[j] >= m.pEarliestStart[r]


def fcAircraftStart(m, r):
    return m.vAircraftStart[r] == sum(
        m.pFirstJob[j, r] * m.vStartTime[j] for j in m.sJobs
    )


def fcAircraftFinish(m, r):
    return m.vAircraftFinish[r] == sum(
        m.pLastJob[j, r] * m.vFinishTime[j] for j in m.sJobs
    )


# -- Precedences --

def fcPrecedence(m, j, jp):
    return m.vStartTime[jp] >= m.vFinishTime[j]


# -- Non-overlap --

def fcNonOverlapOrder1(m, j, jp, p):
    return m.vStartTime[jp] >= m.vFinishTime[j] - m.pBigM * (
        1
        - m.vJobOrder[j, jp, p]
        + (1 - m.vJobPosition[j, p])
        + (1 - m.vJobPosition[jp, p])
    )


def fcNonOverlapOrder2(m, j, jp, p):
    return m.vStartTime[j] >= m.vFinishTime[jp] - m.pBigM * (
        m.vJobOrder[j, jp, p]
        + (1 - m.vJobPosition[j, p])
        + (1 - m.vJobPosition[jp, p])
    )


def fcNonOverlapConsistencyLB(m, j, jp, p):
    return (
        m.vJobOrder[j, jp, p] + m.vJobOrder[jp, j, p]
        >= m.vJobPosition[j, p] + m.vJobPosition[jp, p] - 1
    )


def fcNonOverlapConsistencyUB(m, j, jp, p):
    return m.vJobOrder[j, jp, p] + m.vJobOrder[jp, j, p] <= 1


def fcNonOverlapAircraft(m, r, rp, p):
    # If both aircraft r and r' are assigned to position p, one must fully precede the other.
    # Enforced via the order variable between their boundary jobs (last of r → first of r', or vice versa).
    return (
        sum(
            m.pLastJob[j, r] * m.pFirstJob[jp, rp] * m.vJobOrder[j, jp, p]
            + m.pLastJob[jp, rp] * m.pFirstJob[j, r] * m.vJobOrder[jp, j, p]
            for j in m.sJobs
            for jp in m.sJobs
            if j != jp
        )
        >= m.vAircraftPosition[r, p] + m.vAircraftPosition[rp, p] - 1
    )


# -- Blocking: entry --

def fcAlphaInLB(m, r, rp, p, pp):
    return m.vAircraftStart[rp] >= m.vAircraftStart[r] - m.pBigM * (
        1 - m.vAlphaIn[r, rp, p, pp]
    )


def fcAlphaInUB(m, r, rp, p, pp):
    # alphaIn=0 is feasible when start[rp] <= start[r] (rp arrives simultaneously or before r).
    # Removing -min_sep ensures simultaneous starts do not force alphaIn=1 (no spurious movement).
    return m.vAircraftStart[rp] <= (
        m.vAircraftStart[r] + m.pBigM * m.vAlphaIn[r, rp, p, pp]
    )


def fcBetaInUB(m, r, rp, p, pp):
    return m.vAircraftStart[rp] <= m.vAircraftFinish[r] - m.pMinSeparation + m.pBigM * (
        1 - m.vBetaIn[r, rp, p, pp]
    )


def fcBetaInLB(m, r, rp, p, pp):
    return m.vAircraftStart[rp] >= m.vAircraftFinish[r] - m.pBigM * m.vBetaIn[r, rp, p, pp]


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
    # alphaOut=0 is feasible when finish[rp] <= start[r] (rp exits simultaneously with r's arrival).
    # Removing -min_sep ensures simultaneous finish/start do not force alphaOut=1.
    return m.vAircraftFinish[rp] <= (
        m.vAircraftStart[r] + m.pBigM * m.vAlphaOut[r, rp, p, pp]
    )


def fcBetaOutUB(m, r, rp, p, pp):
    return m.vAircraftFinish[rp] <= m.vAircraftFinish[r] - m.pMinSeparation + m.pBigM * (
        1 - m.vBetaOut[r, rp, p, pp]
    )


def fcBetaOutLB(m, r, rp, p, pp):
    return m.vAircraftFinish[rp] >= (
        m.vAircraftFinish[r] - m.pBigM * m.vBetaOut[r, rp, p, pp]
    )


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
    return m.vDelay[r] >= sum(
        m.pLastJob[j, r] * (m.vFinishTime[j] - m.pTargetFinish[r]) for j in m.sJobs
    )


def fcMakespan(m, j):
    return m.vMakespan >= m.vFinishTime[j]


# =================================================================
#  Activate constraints
# =================================================================
model.cAssignAircraft = Constraint(model.sAircraft, rule=fcAssignAircraft)
model.cJobPosition = Constraint(model.sJobs, model.sPositions, rule=fcJobPosition)
model.cFinishTime = Constraint(model.sJobs, rule=fcFinishTime)
model.cEarliestStart = Constraint(model.sFirstJobAircraft, rule=fcEarliestStart)
model.cAircraftStart = Constraint(model.sAircraft, rule=fcAircraftStart)
model.cAircraftFinish = Constraint(model.sAircraft, rule=fcAircraftFinish)

model.cPrecedence = Constraint(model.sPrecedences, rule=fcPrecedence)

model.cNonOverlapOrder1 = Constraint(model.sJobPairsOrdered, rule=fcNonOverlapOrder1)
model.cNonOverlapOrder2 = Constraint(model.sJobPairsOrdered, rule=fcNonOverlapOrder2)
model.cNonOverlapConsistencyLB = Constraint(model.sJobPairsUnordered, rule=fcNonOverlapConsistencyLB)
model.cNonOverlapConsistencyUB = Constraint(model.sJobPairsUnordered, rule=fcNonOverlapConsistencyUB)
model.cNonOverlapAircraft = Constraint(model.sAircraftPairsPosition, rule=fcNonOverlapAircraft)

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
model.cMakespan = Constraint(model.sJobs, rule=fcMakespan)


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

def prepare_data(
    raw_data: dict,
    min_separation: float,
    weight_makespan: float,
    weight_delay: float,
    weight_movements: float,
) -> dict:
    """Convert JSON instance data to the Pyomo AbstractModel data dict format."""
    aircraft_data = raw_data["aircrafts"]
    job_data = raw_data["jobs"]
    hangar = raw_data["hangar"]

    jobs = [j["id"] for j in job_data]
    aircraft = [a["id"] for a in aircraft_data]
    positions = hangar["positions"]
    clients = sorted({a["client"] for a in aircraft_data})
    blocking_arcs = [(arc["front"], arc["rear"]) for arc in hangar["blocking_arcs"]]
    precedences = [(p["before"], p["after"]) for p in raw_data["job_precedences"]]

    job_by_id = {j["id"]: j for j in job_data}
    aircraft_by_id = {a["id"]: a for a in aircraft_data}
    big_m = (
        max(aircraft_by_id[r]["target_finish"] for r in aircraft)
        + sum(job_by_id[j]["duration"] for j in jobs)
    )

    return {
        None: {
            "sJobs": {None: jobs},
            "sAircraft": {None: aircraft},
            "sPositions": {None: positions},
            "sClients": {None: clients},
            "sBlockingArcs": {None: blocking_arcs},
            "sPrecedences": {None: precedences},
            "pDuration": {j["id"]: j["duration"] for j in job_data},
            "pEarliestStart": {a["id"]: a["earliest_start"] for a in aircraft_data},
            "pTargetFinish": {a["id"]: a["target_finish"] for a in aircraft_data},
            "pJobAircraft": {
                (j, r): int(job_by_id[j]["aircraft_id"] == r)
                for j in jobs
                for r in aircraft
            },
            "pClientAircraft": {
                (a["id"], c): int(a["client"] == c)
                for a in aircraft_data
                for c in clients
            },
            "pFirstJob": {
                (j, r): int(job_by_id[j]["aircraft_id"] == r and job_by_id[j]["is_first"])
                for j in jobs
                for r in aircraft
            },
            "pLastJob": {
                (j, r): int(job_by_id[j]["aircraft_id"] == r and job_by_id[j]["is_last"])
                for j in jobs
                for r in aircraft
            },
            "pMinSeparation":   {None: min_separation},
            "pBigM":            {None: big_m},
            "pWeightMakespan":  {None: weight_makespan},
            "pWeightDelay":     {None: weight_delay},
            "pWeightMovements": {None: weight_movements},
        }
    }


def get_solution(instance, result) -> dict:
    """Extract solution values from a solved Pyomo instance into a JSON-serialisable dict.

    Schema
    ------
    {
        "status":  str,          # solver termination condition
        "objective": float,
        "metrics": {
            "makespan":     float,
            "movements":    int,
            "total_delay":  float
        },
        "aircraft": [
            {
                "id":       str,
                "position": str,
                "start":    float,
                "finish":   float,
                "delay":    float,
                "jobs": [
                    {"id": str, "start": float, "finish": float}
                ]
            }
        ]
    }
    """
    aircraft_list = []
    for r in instance.sAircraft:
        position = next(
            p for p in instance.sPositions if instance.vAircraftPosition[r, p]() > 0.5
        )
        jobs = [
            {
                "id":     j,
                "start":  round(instance.vStartTime[j](),  4),
                "finish": round(instance.vFinishTime[j](), 4),
            }
            for j in instance.sJobs
            if instance.pJobAircraft[j, r] == 1
        ]
        aircraft_list.append({
            "id":       r,
            "position": position,
            "start":    round(instance.vAircraftStart[r](),  4),
            "finish":   round(instance.vAircraftFinish[r](), 4),
            "delay":    round(instance.vDelay[r](),          2),
            "jobs":     jobs,
        })

    return {
        "status":    str(result.solver.termination_condition),
        "objective": round(instance.obj(), 2),
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

    # TODO: temporary import for debugging — remove once solver pipeline is stable
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "output_data"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "input_data"))
    from load_instance import load_instance      # noqa: E402
    from plot_schedule import plot_schedule      # noqa: E402
    from check_solution import check_solution, print_check  # noqa: E402

    # ---- solver configuration ----
    min_separation  = 10
    weight_makespan  = 10.0
    weight_delay     = 100.0
    weight_movements = 1.0
    # ------------------------------

    instance_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "scn_custom_many_tight_pl10.json"
    )
    raw_data = load_instance(instance_path)

    instance = model.create_instance(
        prepare_data(raw_data, min_separation, weight_makespan, weight_delay, weight_movements)
    )
    solver = SolverFactory("gurobi")
    # NoRelHeurTime: seconds spent on heuristics BEFORE solving the LP relaxation.
    # Gurobi runs primal heuristics aggressively on the original MIP without first
    # solving the root relaxation, which is effective when feasibility matters more
    # than tight bounds.
    solver.options["NoRelHeurTime"] = 10
    solver.options["MIPGap"]        = 10
    result = solver.solve(instance, tee=True)
    solution = get_solution(instance, result)
    print(json.dumps(solution, indent=2))

    report = check_solution(solution, raw_data)
    print_check(report)

    plot_schedule(solution)
