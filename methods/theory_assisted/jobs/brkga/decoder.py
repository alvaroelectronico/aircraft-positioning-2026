"""Mixed-chromosome decoder: keys in [0,1)^(2|R|) -> feasible schedule.

Layout (length 2|R|):
  genes [0, |R|)      assignment keys  -> position floor(key * |P|)
  genes [|R|, 2|R|)   sequencing keys  -> order within a position

The decoder is DETERMINISTIC: same chromosome -> same schedule -> same fitness
(a hard requirement for BRKGA to compare individuals meaningfully).

v0 schedules each aircraft's jobs contiguously (kappa = 0).  Because there are
no inter-job gaps, the only feasible access mode is Mode A: a rear aircraft can
enter/leave only when every front position is vacant (with margin ``eta``) at
both its entry and its exit instant.  The earliest-feasible-start sweep finds
that instant via interval-set algebra; positions are visited in topological
order so a rear position's fronts are already fixed when it is scheduled.
"""
from __future__ import annotations

from brkga.access import count_movements, mode_a_windows_for_position
from brkga.instance import Model
from brkga.state import AircraftState, JobState, ScheduleState
from brkga.windows import first_point_at_or_after, intersect_windows, shift_windows

# Objective penalty applied per infeasible access (v0 should never incur one).
_INFEASIBLE_PENALTY = 1e9


def decode_chromosome(chromosome: list[float], model: Model
                      ) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Return (position assignment pi, per-position aircraft order)."""
    nR = model.num_aircraft
    nP = model.num_positions
    assign = chromosome[:nR]
    seq = chromosome[nR:2 * nR]

    pi: dict[str, str] = {}
    for idx, r in enumerate(model.aircraft_ids):
        k = int(assign[idx] * nP)
        if k >= nP:
            k = nP - 1
        pi[r] = model.positions[k]

    buckets: dict[str, list[tuple[float, int, str]]] = {p: [] for p in model.positions}
    for idx, r in enumerate(model.aircraft_ids):
        buckets[pi[r]].append((seq[idx], idx, r))

    seq_order: dict[str, list[str]] = {}
    for p in model.positions:
        seq_order[p] = [r for (_, _, r) in sorted(buckets[p])]
    return pi, seq_order


def _earliest_start(p: str, T: float, lower: float,
                    state: ScheduleState, model: Model) -> float:
    """Smallest start >= lower with both entry and exit Mode-A in position p."""
    access = mode_a_windows_for_position(p, state, model)
    feasible = intersect_windows(access, shift_windows(access, -T))
    pt = first_point_at_or_after(feasible, lower)
    if pt is None:
        # The tail [max_front_finish + eta, INF) is always Mode-A, so this is a
        # safety net only; place the aircraft after everything seen so far.
        return lower
    return pt


def build_schedule(pi: dict[str, str], seq_order: dict[str, list[str]],
                   model: Model, allow_mode_c: bool = False) -> ScheduleState:
    """Construct the v0 schedule (contiguous jobs, Mode-A only)."""
    state = ScheduleState(by_position={p: [] for p in model.positions})

    for p in model.topo_positions:
        last_finish: float | None = None
        for r in seq_order[p]:
            lower = model.earliest_start[r]
            if last_finish is not None:
                lower = max(lower, last_finish + model.epsilon)

            start = _earliest_start(p, model.T[r], lower, state, model)

            jobs: list[JobState] = []
            t = start
            for jid in model.chain[r]:
                d = model.duration[jid]
                jobs.append(JobState(jid, t, t + d, d, model.interruptible[jid], 0))
                t += d

            state.aircraft[r] = AircraftState(r, p, start, t, jobs)
            state.by_position[p].append(r)
            last_finish = t

    movements, infeasible = count_movements(state, model)
    state.movements = movements
    state.infeasible_accesses = infeasible
    return state


def compute_objective(state: ScheduleState, model: Model, weights: dict[str, float]) -> float:
    makespan = max((ac.finish for ac in state.aircraft.values()), default=0.0)
    total_delay = sum(
        max(0.0, state.aircraft[r].finish - model.target_finish[r])
        for r in model.aircraft_ids
    )
    obj = (weights["makespan"] * makespan
           + weights["delay"] * total_delay
           + weights["movements"] * state.movements)
    return obj + _INFEASIBLE_PENALTY * state.infeasible_accesses


def to_solution_dict(state: ScheduleState, model: Model,
                     weights: dict[str, float], status: str) -> dict:
    aircraft = []
    for r in model.aircraft_ids:
        ac = state.aircraft[r]
        delay = max(0.0, ac.finish - model.target_finish[r])
        aircraft.append({
            "id": r,
            "position": ac.position,
            "start": ac.start,
            "finish": ac.finish,
            "delay": delay,
            "jobs": [{"id": j.job_id, "start": j.start, "finish": j.finish} for j in ac.jobs],
        })
    makespan = max((ac.finish for ac in state.aircraft.values()), default=0.0)
    total_delay = sum(a["delay"] for a in aircraft)
    return {
        "status": status,
        "objective": compute_objective(state, model, weights),
        "metrics": {
            "makespan": makespan,
            "total_delay": total_delay,
            "movements": state.movements,
        },
        "aircraft": aircraft,
    }


def decode(chromosome: list[float], model: Model, weights: dict[str, float],
           allow_mode_c: bool = False) -> tuple[float, ScheduleState]:
    """Full decode: chromosome -> (objective, schedule state)."""
    pi, seq_order = decode_chromosome(chromosome, model)
    state = build_schedule(pi, seq_order, model, allow_mode_c=allow_mode_c)
    return compute_objective(state, model, weights), state
