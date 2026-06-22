"""Mixed-chromosome decoder: keys in [0,1)^(2|R|) -> feasible schedule.

Layout (length 2|R|):
  genes [0, |R|)      assignment keys  -> position floor(key * |P|)
  genes [|R|, 2|R|)   sequencing keys  -> order within a position

The decoder is DETERMINISTIC: same chromosome (+ same weights/allow_mode_c)
-> same schedule -> same fitness (required for BRKGA to compare individuals).

Two construction modes, chosen by ``allow_mode_c``:

* **Mode-A only (v0)** — each rear aircraft waits for full front-position
  vacancy (with eta margin) at both its entry and exit instant.  Always
  feasible; movements = 0.  Fast; used as the default fitness and as a
  guaranteed fallback.

* **Mode-A + Mode-C (in-sweep)** — a rear may instead start earlier, letting an
  access instant land inside an *interruptible* front job (Mode C: that job
  gains kappa+1 and extends by delta, the front's later jobs shift).  The choice
  is made greedily per rear and **profile-aware**: Mode C is taken only when the
  weighted delay/makespan it saves the rear exceeds the weighted movement cost
  plus the extra delay the front extension causes.  A separation guard forbids
  interruptions that would push a front into its successor.  Because front
  extensions can still propagate, a Mode-C schedule is **validated by the real
  checker in** :func:`decode`; if anything is non-compliant the decode falls
  back to the always-feasible Mode-A build.
"""
from __future__ import annotations

from brkga.access import count_movements, mode_a_windows_for_position
from brkga.instance import Model
from brkga.state import AircraftState, JobState, ScheduleState
from brkga.windows import (INF, first_point_at_or_after, intersect_windows,
                           shift_windows)

_INFEASIBLE_PENALTY = 1e9
_EPS = 1e-9


# --------------------------------------------------------------------------- #
#  Chromosome -> assignment + ordering
# --------------------------------------------------------------------------- #

def decode_chromosome(chromosome: list[float], model: Model
                      ) -> tuple[dict[str, str], dict[str, list[str]], dict[str, float]]:
    """Return (position assignment pi, per-position order, timing keys per r)."""
    nR = model.num_aircraft
    nP = model.num_positions
    assign = chromosome[:nR]
    seq = chromosome[nR:2 * nR]
    tim = chromosome[2 * nR:3 * nR]

    pi: dict[str, str] = {}
    timing: dict[str, float] = {}
    for idx, r in enumerate(model.aircraft_ids):
        k = int(assign[idx] * nP)
        if k >= nP:
            k = nP - 1
        pi[r] = model.positions[k]
        timing[r] = tim[idx] if idx < len(tim) else 0.0

    buckets: dict[str, list[tuple[float, int, str]]] = {p: [] for p in model.positions}
    for idx, r in enumerate(model.aircraft_ids):
        buckets[pi[r]].append((seq[idx], idx, r))

    seq_order: dict[str, list[str]] = {}
    for p in model.positions:
        seq_order[p] = [r for (_, _, r) in sorted(buckets[p])]
    return pi, seq_order, timing


# --------------------------------------------------------------------------- #
#  Geometry helpers
# --------------------------------------------------------------------------- #

def _place_jobs(model: Model, r: str, start: float) -> tuple[list[JobState], float]:
    """Contiguous job list for aircraft r from *start* (kappa = 0)."""
    jobs: list[JobState] = []
    t = start
    for jid in model.chain[r]:
        d = model.duration[jid]
        jobs.append(JobState(jid, t, t + d, d, model.interruptible[jid], 0))
        t += d
    return jobs, t


def _apply_timing(windows: list[tuple[float, float]], earliest: float,
                  gene: float, cap: float) -> float:
    """Timing-gene placement (chromosome block 3): push the start later than the
    earliest feasible instant by ``gene·cap``, snapping to the next feasible
    window.  ``gene=0`` (the warm-start value) reproduces the earliest start."""
    if cap <= 0.0 or gene <= 0.0:
        return earliest
    target = earliest + gene * cap
    pt = first_point_at_or_after(windows, target)
    return earliest if pt is None else pt


def _mode_a_feasible(p: str, T: float, state: ScheduleState, model: Model
                     ) -> list[tuple[float, float]]:
    access = mode_a_windows_for_position(p, state, model)
    return intersect_windows(access, shift_windows(access, -T))


def _earliest_mode_a(p: str, T: float, lower: float,
                     state: ScheduleState, model: Model) -> float:
    feasible = _mode_a_feasible(p, T, state, model)
    pt = first_point_at_or_after(feasible, lower)
    return lower if pt is None else pt


def _feasible_bc_windows(p: str, state: ScheduleState, model: Model
                         ) -> list[tuple[float, float]]:
    """Access instants a rear at p can use with Mode-C allowed: Mode-A regions
    (outside each front's stay, eta margin) plus the interiors of *interruptible*
    front jobs.  Built positively to avoid the eta-margin dead zones contiguous
    jobs create.  (No real Mode-B gaps exist in this construction.)"""
    windows: list[tuple[float, float]] = [(0.0, INF)]
    eta = model.eta
    for q in model.fronts_of.get(p, []):
        for fr in state.by_position.get(q, []):
            F = state.aircraft[fr]
            wf: list[tuple[float, float]] = []
            left_hi = F.start - eta
            if left_hi >= 0.0:
                wf.append((0.0, left_hi))
            wf.append((F.finish + eta, INF))
            for j in F.jobs:
                if j.interruptible and (j.finish - eta) > (j.start + eta):
                    wf.append((j.start + eta, j.finish - eta))
            wf.sort()
            windows = intersect_windows(windows, wf)
            if not windows:
                break
    return windows


def _job_at(F: AircraftState, tau: float, eta: float) -> str | None:
    for j in F.jobs:
        if j.start + eta <= tau <= j.finish - eta:
            return j.job_id
    return None


def _apply_interrupt(F: AircraftState, jid: str, model: Model) -> None:
    """kappa += 1 on job jid; extend it by delta; shift F's later jobs."""
    shift = False
    for j in F.jobs:
        if shift:
            j.start += model.delta
            j.finish += model.delta
        elif j.job_id == jid:
            j.kappa += 1
            j.finish += model.delta
            shift = True
    F.start = F.jobs[0].start
    F.finish = F.jobs[-1].finish


def _successor_start(p: str, fr: str, state: ScheduleState) -> float:
    """Start of the aircraft after fr in its position, or +inf if none."""
    order = state.by_position[p]
    i = order.index(fr)
    if i + 1 < len(order):
        return state.aircraft[order[i + 1]].start
    return INF


# --------------------------------------------------------------------------- #
#  Schedule construction
# --------------------------------------------------------------------------- #

def _try_mode_c(state: ScheduleState, r: str, p: str, lower: float, s_a: float,
                model: Model, weights: dict, gene: float = 0.0, cap: float = 0.0
                ) -> float | None:
    """Decide whether rear r should use a Mode-C-assisted earlier start.

    Returns the chosen start (< s_a) and applies the required front
    interruptions in place, or None to keep the Mode-A start.  Profile-aware:
    accepts only when the weighted delay/makespan saved for r outranks the
    weighted movement cost plus the extra delay the front extensions cause.  A
    separation guard rejects interruptions that would collide a front with its
    successor.  The timing gene shifts the Mode-C reference start the same way it
    shifts the Mode-A start, so the A-vs-C comparison stays consistent."""
    T = model.T[r]
    feas = _feasible_bc_windows(p, state, model)
    start_windows = intersect_windows(feas, shift_windows(feas, -T))
    s_c0 = first_point_at_or_after(start_windows, lower)
    if s_c0 is None:
        return None
    s_c = _apply_timing(start_windows, s_c0, gene, cap)
    if s_c >= s_a - _EPS:
        return None

    eta = model.eta
    f_c = s_c + T
    interrupts: list[tuple[str, str]] = []       # (front_aircraft, job)
    extra_front_delay = 0.0
    n_events = 0
    for q in model.fronts_of[p]:
        for fr in state.by_position[q]:
            F = state.aircraft[fr]
            jobints = [(j.job_id, j.start, j.finish) for j in F.jobs]
            from brkga.access import classify_access
            for tau in (s_c, f_c):
                kind = classify_access(tau, F.start, F.finish, jobints, model)
                if kind == "A":
                    continue
                if kind in ("B", "C"):
                    n_events += 1
                    if kind == "C":
                        jid = _job_at(F, tau, eta)
                        if jid is None:
                            return None
                        interrupts.append((fr, jid))
                else:
                    return None  # infeasible (non-interruptible interior)

    # Separation guard + front-delay cost from the (delta-per-interrupt) growth.
    per_front: dict[str, int] = {}
    for (fr, _jid) in interrupts:
        per_front[fr] = per_front.get(fr, 0) + 1
    for fr, k in per_front.items():
        F = state.aircraft[fr]
        new_finish = F.finish + model.delta * k
        if new_finish + model.epsilon > _successor_start(F.position, fr, state) + _EPS:
            return None  # would collide with the front's successor
        old_d = max(0.0, F.finish - model.target_finish[fr])
        new_d = max(0.0, new_finish - model.target_finish[fr])
        extra_front_delay += (new_d - old_d)

    # Benefit (for r) vs cost (movements + front delay).
    delay_a = max(0.0, s_a + T - model.target_finish[r])
    delay_c = max(0.0, f_c - model.target_finish[r])
    benefit = (weights["delay"] * (delay_a - delay_c)
               + weights["makespan"] * (s_a - s_c))
    cost = weights["movements"] * (2 * n_events) + weights["delay"] * extra_front_delay
    if benefit <= cost + _EPS:
        return None

    for (fr, jid) in interrupts:
        _apply_interrupt(state.aircraft[fr], jid, model)
    return s_c


def build_schedule(pi: dict[str, str], seq_order: dict[str, list[str]],
                   model: Model, weights: dict | None = None,
                   allow_mode_c: bool = False,
                   timing: dict[str, float] | None = None,
                   cap: float = 0.0) -> ScheduleState:
    """Construct a schedule.  Mode-A only unless allow_mode_c and weights given.
    ``timing`` (per-aircraft keys in [0,1)) + ``cap`` push starts later than the
    earliest feasible instant (timing-gene block); ``timing=None`` ⇒ earliest."""
    state = ScheduleState(by_position={p: [] for p in model.positions})

    for p in model.topo_positions:
        last_finish: float | None = None
        has_fronts = bool(model.fronts_of.get(p))
        for r in seq_order[p]:
            lower = model.earliest_start[r]
            if last_finish is not None:
                lower = max(lower, last_finish + model.epsilon)

            gene = timing.get(r, 0.0) if timing else 0.0
            feas_a = _mode_a_feasible(p, model.T[r], state, model)
            s_a0 = first_point_at_or_after(feas_a, lower)
            s_a0 = lower if s_a0 is None else s_a0
            s_a = _apply_timing(feas_a, s_a0, gene, cap)
            start = s_a
            if allow_mode_c and weights is not None and has_fronts:
                s_c = _try_mode_c(state, r, p, lower, s_a, model, weights, gene, cap)
                if s_c is not None:
                    start = s_c

            jobs, finish = _place_jobs(model, r, start)
            state.aircraft[r] = AircraftState(r, p, start, finish, jobs)
            state.by_position[p].append(r)
            last_finish = finish

    movements, infeasible = count_movements(state, model)
    state.movements = movements
    state.infeasible_accesses = infeasible
    return state


# --------------------------------------------------------------------------- #
#  Objective and solution dict
# --------------------------------------------------------------------------- #

def compute_objective(state: ScheduleState, model: Model, weights: dict) -> float:
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
                     weights: dict, status: str) -> dict:
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


# --------------------------------------------------------------------------- #
#  Full decode (with optional Mode-C + real-checker validation)
# --------------------------------------------------------------------------- #

def decode(chromosome: list[float], model: Model, weights: dict,
           allow_mode_c: bool = False, instance: dict | None = None,
           cap: float = 0.0) -> tuple[float, ScheduleState]:
    """chromosome -> (objective, schedule state).

    Mode-A path is purely analytic (movements = 0, validated mirror).  When
    allow_mode_c and an instance is given, the Mode-C build is validated by the
    real checker: if compliant, its checker-inferred movement count is used;
    otherwise the decode falls back to the guaranteed-feasible Mode-A build.
    ``cap`` (with the chromosome's timing block) enables timing-gene placement."""
    pi, seq_order, timing = decode_chromosome(chromosome, model)

    if not (allow_mode_c and instance is not None):
        state = build_schedule(pi, seq_order, model, timing=timing, cap=cap)
        return compute_objective(state, model, weights), state

    state = build_schedule(pi, seq_order, model, weights=weights,
                           allow_mode_c=True, timing=timing, cap=cap)
    # If the greedy applied no interruption, the schedule is Mode-A-equivalent
    # (movements = 0) and already feasible by construction — skip the checker so
    # profiles that never use Mode C (e.g. wMOV) keep the full generation count.
    if state.movements == 0 and state.infeasible_accesses == 0:
        return compute_objective(state, model, weights), state

    from checker import check_solution  # problems/jobs/ (allowed)
    sol = to_solution_dict(state, model, weights, "decode")
    report = check_solution(sol, instance)
    rq = report["requirements"]
    rq07 = rq["RQ07"]
    feasible = (
        not rq07["infeasibilities"]
        and not rq07["gap_violations"]
        and all(info["pass"] for k, info in rq.items() if k != "RQ07")
    )
    if feasible:
        state.movements = rq07["movements_count"]
        state.infeasible_accesses = 0
        return compute_objective(state, model, weights), state

    # Propagation broke something: fall back to the always-feasible Mode-A build
    # (timing-gene placement preserved; Mode-A is feasible for any start choice).
    state = build_schedule(pi, seq_order, model, timing=timing, cap=cap)
    return compute_objective(state, model, weights), state
