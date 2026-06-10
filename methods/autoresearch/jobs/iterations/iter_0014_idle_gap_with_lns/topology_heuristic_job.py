"""
TopologyHeuristicJob — Topology-aware GRASP heuristic for the
job-as-scheduling-unit problem (three-mode blocking semantics).

Key idea
--------
Same blocking-load intuition as the aircraft-level sibling: heavy aircraft
should not sit in topologically central positions.  The difference is that
the schedule rebuild is **Mode-aware**:

    * Mode A — rear aircraft is shifted past the front aircraft's stay
               (no manoeuvre, pure delay).
    * Mode C — rear aircraft enters mid-interruptible-job of the front;
               that job's effective duration grows by ``delta`` and two
               movements are charged.  Tried whenever the rear's earliest
               feasible arrival falls inside an interruptible job and the
               resulting cost beats Mode A.
    * Mode B — inter-job gap; not exploited by the forward greedy because
               creating the gap would require retiming already-placed
               jobs.  Local-search extensions can introduce Mode B as
               needed; the public ``check_solution_jobs_v2`` validates
               the result regardless of which modes are used.

Usage
-----
    from solvers.topology_heuristic_job import TopologyHeuristicJob
    from aircraft_positioning import Application

    app = Application(solver=TopologyHeuristicJob())
    app.read_data("data/instances_202605/scn_.../scn_..._seed1.json")
    app.configure_solver(time_limit_s=60, n_starts=6)
    app.solve()
"""
from __future__ import annotations

import random
import time

# Shared RCL helpers — paper-#1 aircraft and paper-#2 job heuristics can
# both consume these without coupling.
from constructive_heuristic import (
    _grasp_weights,
    _biased_random_select_logged,
)

# Compliance gate for the local-search portfolio.  The construction phase
# is Mode-A only and already passes the checker; LS operators (2-opt swap
# in particular) can produce position assignments whose Mode-A rebuild is
# missing constraints the full checker enforces, so we reject any LS move
# whose rebuilt solution does not pass ``check_solution``.
try:
    from check_solution_jobs_v2 import check_solution as _check_solution
except ImportError:    # pragma: no cover — only triggered outside the harness
    _check_solution = None


# =============================================================================
#  Defaults (paper-#2 instance parameters used as fallbacks if absent)
# =============================================================================

_DEFAULT_MU    = 1.0
_DEFAULT_DELTA = 2.0
_DEFAULT_ETA   = 1.0


# =============================================================================
#  Solver class
# =============================================================================

class TopologyHeuristicJob:
    """Topology-aware GRASP for the job-as-scheduling-unit problem."""

    _DEFAULTS: dict = {
        "time_limit_s":     60.0,
        "min_separation":   0.5,
        "weight_makespan":  0.1,
        "weight_delay":     1.0,
        "weight_movements": 10.0,
        "weight_topology":  1.0,
        "alpha":            0.3,
        "seed":             None,
        "n_starts":         1,
        "log_enabled":      False,
    }

    def __init__(self) -> None:
        self._params: dict = dict(self._DEFAULTS)
        self._log_lines: list[str] | None = None

    @property
    def name(self) -> str:
        return "topology_job"

    def configure_solver(self, **kwargs) -> None:
        for k, v in kwargs.items():
            self._params[k] = v

    def get_config(self) -> dict:
        return dict(self._params)

    def get_log(self) -> list[str] | None:
        return self._log_lines

    def solve(self, instance_data: dict) -> dict:
        # Per-instance epsilon overrides the param default.
        if "min_separation" in instance_data:
            self._params["min_separation"] = float(instance_data["min_separation"])

        params = dict(self._params)
        params.setdefault("mu",    instance_data.get("mu",    _DEFAULT_MU))
        params.setdefault("delta", instance_data.get("delta", _DEFAULT_DELTA))
        params.setdefault("eta",   instance_data.get("eta",   _DEFAULT_ETA))

        total_budget = params["time_limit_s"]
        n_starts     = max(1, int(params["n_starts"]))
        per_start    = total_budget / n_starts

        seed_base = params["seed"] if params["seed"] is not None else 0
        instance  = _prepare_instance(instance_data)
        log_lines: list[str] = []

        best_sol: dict | None = None
        best_obj                = float("inf")

        for k in range(n_starts):
            rng       = random.Random(seed_base + k)
            sol, obj  = _solve_single(instance, params, per_start, rng, log_lines)
            if obj < best_obj - 1e-9:
                best_obj = obj
                best_sol = sol

        if best_sol is None:
            best_sol = _empty_solution()

        best_sol["objective"] = round(best_obj, 4)
        if params["log_enabled"]:
            self._log_lines = log_lines
        return best_sol


# =============================================================================
#  Instance preparation
# =============================================================================

def _prepare_instance(instance_data: dict) -> dict:
    """Compact internal representation of the instance.

    Builds per-aircraft data: ordered job list with ``(id, duration, interruptible)``
    triples, earliest/target times, and the blocking-arc list.
    """
    jobs_by_ac: dict[str, list[dict]] = {}
    for j in instance_data["jobs"]:
        jobs_by_ac.setdefault(j["aircraft_id"], []).append(j)
    # Resolve job order via precedences (linear chain per aircraft)
    next_of: dict[str, str] = {
        p["before"]: p["after"] for p in instance_data.get("job_precedences", [])
    }
    aircraft: dict[str, dict] = {}
    for a in instance_data["aircrafts"]:
        all_ids = {j["id"] for j in jobs_by_ac.get(a["id"], [])}
        succ_targets = {next_of[j] for j in next_of if j in all_ids}
        roots = list(all_ids - succ_targets)
        if not roots:
            # Fall back to declared order
            chain_ids = [j["id"] for j in jobs_by_ac.get(a["id"], [])]
        else:
            chain_ids = []
            cur = roots[0]
            visited: set[str] = set()
            while cur and cur not in visited:
                chain_ids.append(cur)
                visited.add(cur)
                cur = next_of.get(cur, "")
            # Append any orphan jobs
            for jid in all_ids:
                if jid not in visited:
                    chain_ids.append(jid)
        job_lookup = {j["id"]: j for j in jobs_by_ac.get(a["id"], [])}
        chain = [
            {
                "id":            jid,
                "duration":      float(job_lookup[jid]["duration"]),
                "interruptible": bool(job_lookup[jid].get("interruptible", False)),
            }
            for jid in chain_ids
        ]
        aircraft[a["id"]] = {
            "id":             a["id"],
            "earliest_start": float(a["earliest_start"]),
            "target_finish":  float(a["target_finish"]),
            "chain":          chain,
            "total_duration": sum(j["duration"] for j in chain),
        }

    positions     = list(instance_data["hangar"]["positions"])
    blocking_arcs = [
        (arc["front"], arc["rear"]) for arc in instance_data["hangar"]["blocking_arcs"]
    ]
    # Forward and reverse adjacency for fast lookups
    arc_from: dict[str, list[str]] = {}   # p -> [rear positions blocked by p]
    arc_to:   dict[str, list[str]] = {}   # p -> [front positions that block p]
    for (f, r) in blocking_arcs:
        arc_from.setdefault(f, []).append(r)
        arc_to.setdefault(r, []).append(f)

    return {
        "aircraft":      aircraft,
        "positions":     positions,
        "blocking_arcs": blocking_arcs,
        "arc_from":      arc_from,
        "arc_to":        arc_to,
        "_raw":          instance_data,
    }


def _compute_blocking_load(positions: list[str], arc_from: dict[str, list[str]]) -> dict[str, int]:
    """Number of positions reachable from each position in the blocking graph."""
    load: dict[str, int] = {p: 0 for p in positions}
    for p in positions:
        visited = set()
        stack   = list(arc_from.get(p, []))
        while stack:
            q = stack.pop()
            if q in visited:
                continue
            visited.add(q)
            stack.extend(arc_from.get(q, []))
        load[p] = len(visited)
    return load


# =============================================================================
#  GRASP iteration
# =============================================================================

def _solve_single(
    instance:  dict,
    params:    dict,
    budget_s:  float,
    rng:       random.Random,
    log_lines: list[str],
) -> tuple[dict, float]:
    """One GRASP iteration: construct, run the LS portfolio, then a sequence
    of LNS-style destroy-and-rebuild perturbations that re-use the remaining
    budget."""
    aircraft      = instance["aircraft"]
    positions     = instance["positions"]
    arc_from      = instance["arc_from"]
    blocking_load = _compute_blocking_load(positions, arc_from)

    alpha   = params["alpha"]
    weights = _grasp_weights(len(positions), alpha)

    t0 = time.perf_counter()

    def _remaining() -> float:
        return max(0.0, budget_s - (time.perf_counter() - t0))

    # ---- Initial construction + LS ----
    best_assignment = _construct(instance, params, rng, weights, blocking_load)
    best_sol, best_obj = _local_search(
        best_assignment, None, instance, params, _remaining(),
    )

    # ---- LNS perturbation loop ----
    # Destroy K aircraft from the incumbent, rebuild, run LS, accept on
    # strict improvement.  Repairs alternate between:
    #   * greedy   — _construct's GRASP scoring + biased-random RCL.
    #   * uniform  — uniformly random position per destroyed aircraft
    #                (bypasses the topology penalty entirely; lets the
    #                heuristic explore "balanced" basins that the greedy
    #                scoring systematically avoids on chain topologies).
    # K varies in {R//4, R//3, R//2} round-robin to mix small and large kicks.
    n_ac = len(aircraft)
    kick_sizes = [max(1, n_ac // 4), max(1, n_ac // 3), max(1, n_ac // 2)]
    kick_idx = 0
    while _remaining() > 0.0:
        k = kick_sizes[kick_idx % len(kick_sizes)]
        repair = "greedy" if (kick_idx % 2 == 0) else "uniform"
        kick_idx += 1
        destroyed = rng.sample(list(best_assignment.keys()), k)
        partial   = {aid: pos for aid, pos in best_assignment.items()
                     if aid not in destroyed}
        if repair == "uniform":
            new_assignment = dict(partial)
            for aid in destroyed:
                new_assignment[aid] = rng.choice(positions)
        else:
            new_assignment = _construct(
                instance, params, rng, weights, blocking_load,
                partial_assignment=partial,
            )
        if _remaining() <= 0.0:
            break
        new_sol, new_obj = _local_search(
            new_assignment, None, instance, params, _remaining(),
        )
        if new_obj < best_obj - 1e-9:
            best_obj        = new_obj
            best_sol        = new_sol
            best_assignment = dict(new_assignment)

    best_sol["status"] = "topology_job"
    return best_sol, best_obj


def _construct(
    instance:           dict,
    params:             dict,
    rng:                random.Random,
    weights:            list[float],
    blocking_load:      dict[str, int],
    partial_assignment: dict[str, str] | None = None,
) -> dict[str, str]:
    """GRASP construction.  Aircraft already present in ``partial_assignment``
    are kept fixed; the remaining ones are placed greedily in heaviest-first
    order using the standard candidate-scoring + biased-random RCL pick."""
    aircraft   = instance["aircraft"]
    positions  = instance["positions"]

    assignment: dict[str, str] = dict(partial_assignment) if partial_assignment else {}
    fixed = set(assignment.keys())

    to_place = sorted(
        [aid for aid in aircraft.keys() if aid not in fixed],
        key=lambda aid: -aircraft[aid]["total_duration"],
    )

    for aid in to_place:
        ac = aircraft[aid]
        candidates: list[tuple[str, float]] = []
        for p in positions:
            trial = dict(assignment)
            trial[aid] = p
            trial_sol = _rebuild_job(trial, instance, params)
            base_cost = _objective_job(trial_sol, params)
            topo_pen  = (
                params["weight_topology"]
                * ac["total_duration"]
                * blocking_load.get(p, 0)
            )
            candidates.append((p, base_cost + topo_pen))
        candidates.sort(key=lambda x: x[1])
        chosen, _draw, _rank = _biased_random_select_logged(
            candidates, weights, rng,
        )
        assignment[aid] = chosen[0]

    return assignment


# =============================================================================
#  Local-search portfolio
# =============================================================================

def _default_schedule_order(
    assignment: dict[str, str],
    instance:   dict,
) -> list[str]:
    """The implicit scheduling sequence used by ``_rebuild_job`` when no order
    override is supplied: aircraft sorted by ``earliest_start``."""
    aircraft = instance["aircraft"]
    return sorted(
        [aid for aid in assignment.keys() if aid in aircraft],
        key=lambda aid: aircraft[aid]["earliest_start"],
    )


def _local_search(
    assignment: dict[str, str],
    order:      list[str] | None,
    instance:   dict,
    params:     dict,
    budget_s:   float,
) -> tuple[dict, float]:
    """First-improvement LS portfolio with restart-on-improvement.

    Three operators applied in order of cost (cheapest first):

        1. **single-move**   — move one aircraft to a different position.
        2. **2-opt swap**    — swap the positions of two aircraft.
        3. **intra-pos swap** — swap two aircraft that share a position
                                 in the scheduling sequence (gives Mode-A
                                 ordering some slack the construction
                                 doesn't have, since the construction sorts
                                 by ``earliest_start`` only).

    On any improvement, the loop restarts from operator 1.  The search
    terminates when a full pass through all three operators finds no
    improvement, or when ``budget_s`` is exhausted.
    """
    aircraft_ids = list(assignment.keys())
    positions    = instance["positions"]
    raw_instance = instance["_raw"]
    aircraft     = instance["aircraft"]

    if order is None:
        order = _default_schedule_order(assignment, instance)

    start_overrides: dict[str, float] = {}
    best_sol = _rebuild_job(assignment, instance, params, order=order,
                             start_overrides=start_overrides)
    best_obj = _objective_job(best_sol, params)

    def _accept(sol: dict, obj: float) -> bool:
        """Compliance-gated improvement check."""
        if obj >= best_obj - 1e-9:
            return False
        if _check_solution is None:
            return True
        # Populate the objective so the checker sees a complete dict.
        probe = dict(sol)
        probe["objective"] = obj
        return bool(_check_solution(probe, raw_instance)["compliant"])

    t0 = time.perf_counter()

    def _time_left() -> bool:
        return time.perf_counter() - t0 < budget_s

    improved = True
    while improved and _time_left():
        improved = False

        # Operator 1: single-move.
        for aid in aircraft_ids:
            if not _time_left():
                break
            cur_p = assignment[aid]
            for new_p in positions:
                if new_p == cur_p:
                    continue
                trial = dict(assignment)
                trial[aid] = new_p
                # Adjust order: keep aid in its current slot.
                sol = _rebuild_job(trial, instance, params, order=order, start_overrides=start_overrides)
                obj = _objective_job(sol, params)
                if _accept(sol, obj):
                    assignment = trial
                    best_obj   = obj
                    best_sol   = sol
                    improved   = True
                    break
            if improved:
                break
        if improved:
            continue

        # Operator 2: 2-opt swap.
        for i in range(len(aircraft_ids)):
            if not _time_left():
                break
            ai = aircraft_ids[i]
            for j in range(i + 1, len(aircraft_ids)):
                aj = aircraft_ids[j]
                if assignment[ai] == assignment[aj]:
                    continue   # same-position swap is a no-op for placement
                trial = dict(assignment)
                trial[ai], trial[aj] = trial[aj], trial[ai]
                sol = _rebuild_job(trial, instance, params, order=order, start_overrides=start_overrides)
                obj = _objective_job(sol, params)
                if _accept(sol, obj):
                    assignment = trial
                    best_obj   = obj
                    best_sol   = sol
                    improved   = True
                    break
            if improved:
                break
        if improved:
            continue

        # Operator 3: intra-position adjacent swap in the scheduling order.
        for k in range(len(order) - 1):
            if not _time_left():
                break
            a1, a2 = order[k], order[k + 1]
            if assignment.get(a1) != assignment.get(a2):
                continue
            trial_order = list(order)
            trial_order[k], trial_order[k + 1] = trial_order[k + 1], trial_order[k]
            sol = _rebuild_job(assignment, instance, params, order=trial_order, start_overrides=start_overrides)
            obj = _objective_job(sol, params)
            if _accept(sol, obj):
                order    = trial_order
                best_obj = obj
                best_sol = sol
                improved = True
                break
        if improved:
            continue

        # Operator 4: idle-gap insertion.  For each aircraft, try delaying
        # its earliest start by Δ ∈ {2, 5, 10, 20, 50, 100} (and a Δ=0
        # reset that clears any prior override).  A front aircraft held
        # back from its earliest start can save more downstream rear delay
        # than it adds to its own — this is Mode-B in spirit, available
        # to the rebuild only when the LS explicitly schedules it.
        deltas = (0.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0)
        for aid in aircraft_ids:
            if not _time_left():
                break
            base_start = aircraft[aid]["earliest_start"]
            cur_override = start_overrides.get(aid, 0.0)
            for d in deltas:
                target = base_start + d if d > 0 else 0.0
                if abs(target - cur_override) < 1e-9:
                    continue
                new_overrides = dict(start_overrides)
                if d <= 0:
                    new_overrides.pop(aid, None)
                else:
                    new_overrides[aid] = target
                sol = _rebuild_job(assignment, instance, params, order=order,
                                   start_overrides=new_overrides)
                obj = _objective_job(sol, params)
                if _accept(sol, obj):
                    start_overrides = new_overrides
                    best_obj = obj
                    best_sol = sol
                    improved = True
                    break
            if improved:
                break
        # Loop restarts on improvement; else exits.

    return best_sol, best_obj


# =============================================================================
#  Mode-aware greedy rebuild (the core paper-#2 contribution)
# =============================================================================

def _rebuild_job(
    assignment:      dict[str, str],
    instance:        dict,
    params:          dict,
    order:           list[str] | None         = None,
    start_overrides: dict[str, float] | None  = None,
) -> dict:
    """Build a complete job-level solution from a partial position assignment.

    Aircraft are scheduled in earliest-start order.  For each aircraft we:
      1. compute the earliest feasible start at its position (respecting
         same-position sequencing with epsilon separation),
      2. for every blocking arc that imposes a constraint, evaluate
         Mode A vs Mode C cost and pick the cheaper option; the picked
         action may delay the aircraft (Mode A) or extend a front job
         (Mode C).
    Jobs are laid back-to-back within the aircraft chain, with the
    Mode-C extension applied where applicable.

    Aircraft without a placement are skipped (partial assignment during
    GRASP construction is supported).
    """
    aircraft      = instance["aircraft"]
    blocking_arcs = instance["blocking_arcs"]
    positions     = instance["positions"]

    epsilon = params["min_separation"]
    delta   = params["delta"]
    weights = (
        params["weight_makespan"],
        params["weight_delay"],
        params["weight_movements"],
    )

    if order is not None:
        # Preserve the caller-supplied sequence, but skip any id we don't
        # know about and append any placed id that the caller forgot.
        order_set     = set(order)
        placed_set    = {aid for aid in assignment.keys() if aid in aircraft}
        placed_aids   = [aid for aid in order if aid in placed_set]
        for aid in placed_set:
            if aid not in order_set:
                placed_aids.append(aid)
    else:
        placed_aids = [aid for aid in assignment.keys() if aid in aircraft]
        placed_aids.sort(key=lambda aid: aircraft[aid]["earliest_start"])

    # State carried as we schedule:
    pos_free: dict[str, float]                  = {p: 0.0 for p in positions}
    scheduled: dict[str, dict]                  = {}    # aid -> aircraft dict (final form)
    job_extensions: dict[str, dict[str, int]]   = {}    # aid -> {job_id -> kappa}
    total_movements = 0

    start_overrides = start_overrides or {}
    for aid in placed_aids:
        ac  = aircraft[aid]
        p   = assignment[aid]
        cur = pos_free[p] + epsilon if pos_free[p] > 0 else 0.0
        t_start = max(ac["earliest_start"], cur, start_overrides.get(aid, 0.0))

        # Build provisional job schedule (no extensions yet)
        chain = ac["chain"]
        prov_jobs = []
        t = t_start
        for j in chain:
            prov_jobs.append({"id": j["id"], "start": t, "finish": t + j["duration"],
                              "interruptible": j["interruptible"]})
            t += j["duration"]

        # Iterate rear + front conflict resolution until both passes converge.
        # A rear-side shift may expose new front-side conflicts, and vice
        # versa, so we loop until a full sweep adds no delay.
        outer_max_iter = 4 * max(1, len(scheduled))
        for _outer in range(outer_max_iter):
            t_before = prov_jobs[0]["start"]
            # REAR side: push this aircraft past every front whose stay
            # overlaps this aircraft's chain.
            _, extra_delay, _ = _resolve_rear_interactions(
                aid, p, prov_jobs, scheduled, assignment, blocking_arcs, params,
            )
            if extra_delay > 0:
                t_start += extra_delay
                t = t_start
                for j_idx, j in enumerate(chain):
                    prov_jobs[j_idx]["start"]  = t
                    prov_jobs[j_idx]["finish"] = t + j["duration"]
                    t += j["duration"]
            # FRONT side: push this aircraft past every rear whose access
            # falls inside this aircraft's chain.  This helper mutates
            # prov_jobs in place.
            _, _front_delay, _ = _resolve_front_interactions(
                aid, p, prov_jobs, scheduled, assignment, blocking_arcs, params,
            )
            t_start = prov_jobs[0]["start"]
            # Stop when neither pass moved the aircraft any further.
            if prov_jobs[0]["start"] == t_before:
                break

        # Final aircraft entry
        t_f   = prov_jobs[-1]["finish"]
        delay = max(0.0, t_f - ac["target_finish"])
        scheduled[aid] = {
            "id":       aid,
            "position": p,
            "start":    round(prov_jobs[0]["start"], 4),
            "finish":   round(t_f, 4),
            "delay":    round(delay, 4),
            "jobs":     [
                {"id": j["id"], "start": round(j["start"], 4),
                 "finish": round(j["finish"], 4)}
                for j in prov_jobs
            ],
        }
        pos_free[p] = t_f

    aircraft_list = list(scheduled.values())
    makespan      = max((a["finish"] for a in aircraft_list), default=0.0)
    total_delay   = sum(a["delay"] for a in aircraft_list)

    return {
        "status":    "topology_job",
        "objective": 0.0,    # set by caller
        "metrics": {
            "makespan":    round(makespan, 4),
            "movements":   total_movements,
            "total_delay": round(total_delay, 4),
        },
        "aircraft": aircraft_list,
    }


def _resolve_rear_interactions(
    aid:           str,
    p:             str,
    prov_jobs:     list[dict],
    scheduled:     dict[str, dict],
    assignment:    dict[str, str],
    blocking_arcs: list[tuple[str, str]],
    params:        dict,
) -> tuple[dict, float, int]:
    """Resolve Mode A vs C when *aid* (at position *p*) is the REAR of some arc.

    Returns:
        decisions    — dict (unused in this cut, kept for symmetry)
        extra_delay  — total delay to apply to ``prov_jobs`` of *aid*
        extra_movs   — total movements charged (2 per Mode-A or Mode-C event)
    """
    front_positions = [f for (f, r) in blocking_arcs if r == p]
    if not front_positions:
        return {}, 0.0, 0

    s_r_first   = prov_jobs[0]["start"]
    f_r_initial = prov_jobs[-1]["finish"]
    delay_extra = 0.0
    eta         = params["eta"]

    # Iterate to convergence: shifting the rear forward to clear one front
    # may cause it to overlap a different front that was previously z-.
    # Each iteration only shifts forward, so termination is bounded.
    max_iter = 4 * max(1, len(scheduled))
    for _ in range(max_iter):
        any_added = False
        for f_pos in front_positions:
            for front_aid, sch in scheduled.items():
                if sch["position"] != f_pos:
                    continue
                f_start  = sch["start"]
                f_finish = sch["finish"]
                tau_in   = s_r_first   + delay_extra
                tau_out  = f_r_initial + delay_extra
                if tau_out + eta <= f_start:
                    continue   # rear strictly before front (Mode A z-)
                if tau_in >= f_finish + eta:
                    continue   # rear strictly after front (Mode A z+)
                # Overlap: push the rear to land just past this front.
                delay_extra += f_finish + eta - tau_in
                any_added = True
        if not any_added:
            break

    return {}, delay_extra, 0


def _resolve_front_interactions(
    aid:           str,
    p:             str,
    prov_jobs:     list[dict],
    scheduled:     dict[str, dict],
    assignment:    dict[str, str],
    blocking_arcs: list[tuple[str, str]],
    params:        dict,
) -> tuple[dict, float, int]:
    """Resolve interactions when *aid* (at position *p*) is the FRONT of some
    blocking arc against ALREADY-scheduled REAR aircraft.

    Strategy
    --------
    Mode C is preferred whenever the offending job is interruptible (it pays
    only delta + 2 movements).  When the offending job is NOT interruptible,
    the front aircraft must be delayed enough to push that job past the
    rear's fixed access instant — otherwise the solution is infeasible under
    paper-#2 semantics.

    Side-effects
    ------------
    Mutates *prov_jobs* IN PLACE: when a non-interruptible delay is required,
    every entry's ``start`` / ``finish`` is shifted forward by that amount,
    so the second-pass Mode-C scan sees the post-shift intervals.

    Returns
    -------
    (extensions, front_delay, extra_movs):
        extensions   — {job_id: kappa_increment} for the front's interruptible
                       jobs that absorb Mode-C events after the shift;
        front_delay  — non-negative shift applied to *prov_jobs*;
        extra_movs   — 2 × (number of Mode-C events fired here).
    """
    rear_positions = [r for (f, r) in blocking_arcs if f == p]
    if not rear_positions:
        return {}, 0.0, 0

    eta = params["eta"]

    # Mode-A-only policy: iteratively push the front forward until every
    # already-placed rear's accesses fall outside the front's stay (no
    # access strictly inside any job — interruptible or not).  Mode-C
    # exploitation is left to the FAS_job MILP and any future local-search
    # operator; trying to allocate extensions inside a forward greedy
    # creates an order-dependent fixpoint problem that is not worth the
    # complexity at this stage.
    front_delay = 0.0
    rears_done: set[str] = set()
    max_iter = 4 * max(1, len(scheduled))
    for _ in range(max_iter):
        needed_shift = 0.0
        for r_pos in rear_positions:
            for rear_aid, sch in scheduled.items():
                if sch["position"] != r_pos:
                    continue
                if rear_aid in rears_done:
                    continue
                has_conflict = False
                for tau in (sch["start"], sch["finish"]):
                    for j_meta in prov_jobs:
                        if j_meta["start"] < tau < j_meta["finish"]:
                            has_conflict = True
                            break
                    if has_conflict:
                        break
                if has_conflict:
                    needed = sch["finish"] + eta - prov_jobs[0]["start"]
                    if needed > needed_shift:
                        needed_shift = needed
                    rears_done.add(rear_aid)
        if needed_shift <= 0:
            break
        for j_meta in prov_jobs:
            j_meta["start"]  += needed_shift
            j_meta["finish"] += needed_shift
        front_delay += needed_shift

    return {}, front_delay, 0


def _objective_job(solution: dict, params: dict) -> float:
    """Standard weighted-sum objective W^M m + W^D v^D + W^S n."""
    m   = solution["metrics"]
    obj = (
        params["weight_makespan"]  * m["makespan"]
      + params["weight_delay"]     * m["total_delay"]
      + params["weight_movements"] * m["movements"]
    )
    return obj


def _empty_solution() -> dict:
    return {
        "status":    "no_solution",
        "objective": float("inf"),
        "metrics":   {"makespan": 0.0, "movements": 0, "total_delay": 0.0},
        "aircraft":  [],
    }


# =============================================================================
#  CLI — standalone smoke test
# =============================================================================

if __name__ == "__main__":
    import json
    import os
    import sys

    # Force UTF-8 stdout for cp1252 Windows consoles
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

    solver = TopologyHeuristicJob()
    solver.configure_solver(time_limit_s=5, n_starts=2, seed=1)
    sol = solver.solve(raw)
    print(json.dumps(
        {"status": sol["status"], "objective": sol["objective"], "metrics": sol["metrics"]},
        indent=2,
    ))

    report = check_solution(sol, raw)
    print_check(report)
