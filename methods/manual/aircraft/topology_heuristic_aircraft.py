"""
TopologyHeuristicAircraft — Topology-aware GRASP heuristic for aircraft positioning.

Key idea
--------
The blocking-arc graph assigns each position a "blocking load" — the number of
positions it can transitively block.  A heavy aircraft (long total duration)
sitting in a high-load position locks out downstream positions for a long time,
multiplying movements and delays.  This solver penalises such assignments so
heavy aircraft gravitate toward low-load positions, reserving high-load
positions for lighter aircraft that vacate them quickly.

Algorithm (single GRASP iteration)
-----------------------------------
1. Pre-compute blocking_load[p] = |reachable positions from p| (transitive).
2. Sort aircraft by total_duration DESCENDING (heaviest choose first).
3. Pair-based GRASP: enumerate all (aircraft, position) pairs, score each
   with standard cost + topology penalty, biased-random select.
4. Light local search (single-move + 2-opt + intra-position operators).
5. Repeat until time limit; keep global best.

Multi-start
-----------
Set n_starts > 1 to divide the time budget into n_starts equal slices and run
a fresh GRASP from a different seed in each slice.  The best solution across
all starts is returned.  This is the recommended mode for production.

Usage
-----
    from solvers.topology_heuristic_aircraft import TopologyHeuristicAircraft
    from aircraft_positioning import Application

    app = Application(solver=TopologyHeuristicAircraft())
    app.read_data("data/instances/instance.json")
    app.configure_solver(time_limit_s=60, weight_topology=1.0, n_starts=6)
    app.solve()
"""
from __future__ import annotations

import random
import time

from constructive_heuristic import (
    _prepare_aircraft_info,
    _find_best_start,
    _count_movements,
    _objective,
    _grasp_weights,
    _biased_random_select_logged,
)
from lns_solver import _rebuild


# =============================================================================
#  Public solver class
# =============================================================================

class TopologyHeuristicAircraft:
    """Topology-aware GRASP heuristic — no external dependencies required."""

    _DEFAULTS: dict = {
        "time_limit_s":     60.0,
        "min_separation":   10.0,
        "weight_makespan":  10.0,
        "weight_delay":     100.0,
        "weight_movements": 1.0,
        "weight_topology":  1.0,   # scales the topology penalty term
        "alpha":            0.3,   # GRASP geometric decay: P(rank i) ∝ (1-alpha)^i
        "seed":             None,
        "n_starts":         1,     # multi-start: divide budget into n_starts slices
        "op_order":         "random",  # LS driver: "random" (RVND) or "fixed" cascade
        "log_enabled":      False,
    }

    def __init__(self) -> None:
        self._params: dict = dict(self._DEFAULTS)
        self._log_lines: list[str] | None = None

    @property
    def name(self) -> str:
        return "topology_aircraft"

    def configure_solver(self, **kwargs) -> None:
        for key, value in kwargs.items():
            self._params[key] = value

    def get_config(self) -> dict:
        return dict(self._params)

    def get_log(self) -> list[str] | None:
        return self._log_lines

    # ------------------------------------------------------------------
    def generate_assignments(
        self,
        instance_data: dict,
        k: int = 5,
        time_per_assign: float = 2.0,
    ) -> list[dict[str, str]]:
        """Return up to *k* diverse position assignments (no LS, GRASP only).

        Each assignment is a dict {aircraft_id: position_id}.
        Duplicates (identical full assignments) are removed.
        """
        params      = self._params
        base_seed   = params["seed"]
        prepared    = _prepare_instance(instance_data)
        assignments: list[dict[str, str]] = []
        seen: set[tuple] = set()

        for i in range(k):
            seed_i = None if base_seed is None else base_seed + i
            deadline = time.perf_counter() + time_per_assign
            sol, _, _, _ = _solve_single(
                instance_data, params, prepared,
                time_per_assign, seed_i, deadline, ls_mode="fast",
            )
            if sol is None:
                continue
            pos_map = {a["id"]: a["position"] for a in sol["aircraft"]}
            key = tuple(sorted(pos_map.items()))
            if key not in seen:
                seen.add(key)
                assignments.append(pos_map)

        return assignments

    # ------------------------------------------------------------------
    def solve(self, instance_data: dict) -> dict:
        # Per-instance epsilon overrides the config fallback.
        if "min_separation" in instance_data:
            self._params["min_separation"] = float(instance_data["min_separation"])
        params      = self._params
        time_limit  = params["time_limit_s"]
        n_starts    = max(1, int(params.get("n_starts", 1)))
        base_seed   = params["seed"]
        log_enabled = bool(params.get("log_enabled", False))

        t0 = time.perf_counter()

        # Pre-compute topology and aircraft data once (shared across all starts)
        prepared = _prepare_instance(instance_data)
        blocking_load = prepared["blocking_load"]

        # Size-adaptive: small instances get the full budget in one start so that
        # the expensive O(n²P) operators (Ops 4–7) have time to complete.
        n_ac = len(instance_data["aircrafts"])
        if n_ac <= 10 and n_starts > 1:
            n_starts = 1

        budget_per_start = time_limit / n_starts
        # Two-speed LS: use only cheap Ops 1–3 when each start is short.
        ls_mode = "fast" if budget_per_start < 20.0 else "full"

        global_best_sol  = None
        global_best_obj  = float("inf")
        all_log_rows: list[str] = []
        total_iters = 0

        for start_idx in range(n_starts):
            # Each start gets its own deterministic seed derived from base_seed
            if base_seed is None:
                seed_i = None   # true random per start
            else:
                seed_i = base_seed + start_idx

            start_t0     = time.perf_counter()
            start_deadline = start_t0 + budget_per_start

            if n_starts > 1:
                elapsed_global = start_t0 - t0
                print(f"\n  [topology] start {start_idx + 1}/{n_starts}"
                      f"  seed={seed_i}  budget={budget_per_start:.1f}s"
                      f"  (elapsed={elapsed_global:.1f}s)")

            sol, obj, iters, log_rows = _solve_single(
                instance_data, params, prepared,
                budget_per_start, seed_i, start_deadline, ls_mode,
            )
            total_iters += iters

            if obj < global_best_obj - 1e-6:
                global_best_obj = obj
                global_best_sol = sol
                if n_starts > 1:
                    m = sol["metrics"]
                    print(f"  [topology] new global best  obj={obj:.2f}"
                          f"  makespan={m['makespan']:.2f}"
                          f"  delay={m['total_delay']:.2f}"
                          f"  mov={m['movements']}  [NEW BEST]")

            if log_enabled:
                all_log_rows.extend(log_rows)

        elapsed_total = time.perf_counter() - t0
        print(f"  [topology] all starts done"
              f"  total_iters={total_iters}  time={elapsed_total:.2f}s"
              f"  best_obj={global_best_obj:.2f}")

        global_best_sol["status"] = f"topology ({total_iters} iterations)"

        if log_enabled:
            self._log_lines = _assemble_log(
                instance_data, params, blocking_load, all_log_rows,
                global_best_obj, global_best_sol, total_iters,
            )
        else:
            self._log_lines = None

        return global_best_sol


# =============================================================================
#  Instance pre-computation (shared across multi-start runs)
# =============================================================================

def _prepare_instance(instance_data: dict) -> dict:
    """Pre-compute topology and aircraft data once per instance."""
    positions     = instance_data["hangar"]["positions"]
    blocking_arcs = instance_data["hangar"]["blocking_arcs"]
    blocking_load = _compute_blocking_load(positions, blocking_arcs)

    aircraft_info = _prepare_aircraft_info(
        instance_data["aircrafts"], instance_data["jobs"]
    )
    ac_target = {a["id"]: a["target_finish"] for a in instance_data["aircrafts"]}

    for ac in aircraft_info.values():
        ac["slack"] = max(
            0.0, ac["target_finish"] - ac["earliest_start"] - ac["total_duration"]
        )

    all_ac = sorted(aircraft_info.values(),
                    key=lambda a: (a["slack"], -a["total_duration"]))
    avg_slack = (sum(a["slack"] for a in all_ac) / len(all_ac)) if all_ac else 1.0

    return {
        "blocking_load": blocking_load,
        "aircraft_info": aircraft_info,
        "ac_target":     ac_target,
        "all_ac":        all_ac,
        "avg_slack":     avg_slack,
    }


# =============================================================================
#  Single-start solver (one GRASP+kick loop over a fixed budget)
# =============================================================================

def _solve_single(
    instance_data: dict,
    params: dict,
    prepared: dict,
    time_limit: float,
    seed: int | None,
    deadline: float,
    ls_mode: str = "full",
) -> tuple[dict, float, int, list[str]]:
    """Run the topology GRASP loop for *time_limit* seconds.

    Returns (best_sol, best_obj, iters, log_rows).
    """
    rng = random.Random(seed)

    blocking_load = prepared["blocking_load"]
    all_ac        = prepared["all_ac"]
    ac_target     = prepared["ac_target"]
    avg_slack     = prepared["avg_slack"]

    w_delay  = params["weight_delay"]
    w_make   = params["weight_makespan"]
    w_mov    = params["weight_movements"]
    w_topo   = params["weight_topology"]
    alpha    = params["alpha"]
    min_sep  = params["min_separation"]

    n_ac        = len(all_ac)
    _kick_ratio = params.get("kick_interval_ratio", 0.125)
    kick_interval_s = (float("inf") if _kick_ratio <= 0
                       else max(5.0, time_limit * _kick_ratio))
    last_kick_t = time.perf_counter()

    best_sol  = None
    best_obj  = float("inf")
    iters     = 0
    log_rows: list[str] = []

    t0_single = time.perf_counter()
    report_interval = max(1.0, time_limit / 10)
    next_report = t0_single + report_interval

    print(f"  [topology] blocking_load={blocking_load}  avg_slack={avg_slack:.2f}")
    print(f"  {'Iter':>6}  {'Time(s)':>8}  {'Best obj':>12}  "
          f"{'Makespan':>10}  {'Delay':>10}  {'Mov':>5}")
    print(f"  {'-'*60}")

    while True:
        now = time.perf_counter()
        if now >= deadline:
            break

        _noise_ratio = params.get("noise_scale_ratio", 0.005)
        noise_scale  = _noise_ratio * avg_slack if avg_slack > 0 else _noise_ratio
        all_ac_iter  = sorted(
            all_ac,
            key=lambda a: (a["slack"] + rng.gauss(0, noise_scale), -a["total_duration"]),
        )

        do_kick = (best_sol is not None and now - last_kick_t >= kick_interval_s)
        if do_kick:
            k = rng.randint(max(2, n_ac // 5), max(3, n_ac // 3))
            k = min(k, n_ac - 1)
            by_worst    = sorted(best_sol["aircraft"],
                                 key=lambda a: (-a["delay"], -a["finish"]))
            pool        = by_worst[:max(k * 2, k + 3)]
            rng.shuffle(pool)
            removed_ids  = {a["id"] for a in pool[:k]}
            pos_of_fixed = {x["id"]: x["position"]
                            for x in best_sol["aircraft"]
                            if x["id"] not in removed_ids}
            warm_ac = [a for a in all_ac_iter if a["id"] not in removed_ids]
            free_ac = [a for a in all_ac_iter if a["id"] in removed_ids]
            sol = _build_topology_solution_warm(
                instance_data, params, rng,
                warm_ac, free_ac, pos_of_fixed, ac_target, blocking_load,
                avg_slack, w_delay, w_make, w_mov, 0.0, alpha, min_sep,
            )
            last_kick_t = now
        else:
            sol = _build_topology_solution(
                instance_data, params, rng,
                all_ac_iter, ac_target, blocking_load,
                avg_slack, w_delay, w_make, w_mov, w_topo, alpha, min_sep,
            )

        max_passes = max(5, n_ac)
        sol = _light_local_search(sol, instance_data, params, max_passes, rng,
                                  deadline=deadline, ls_mode=ls_mode,
                                  op_order=params.get("op_order", "random"))
        obj = _objective(sol, params)
        iters += 1

        if obj < best_obj - 1e-6:
            best_obj = obj
            best_sol = sol
            m        = best_sol["metrics"]
            elapsed  = now - t0_single
            print(f"  {iters:>6}  {elapsed:>8.2f}  {best_obj:>12.2f}  "
                  f"{m['makespan']:>10.2f}  {m['total_delay']:>10.2f}  "
                  f"{m['movements']:>5}  *")
            if params.get("log_enabled"):
                log_rows.append(
                    f"  iter={iters}  t={elapsed:.2f}s"
                    f"  obj={best_obj:.2f}  makespan={m['makespan']:.2f}"
                    f"  delay={m['total_delay']:.2f}  mov={m['movements']}  *"
                )
            next_report = now + report_interval
        elif now >= next_report and best_sol is not None:
            m = best_sol["metrics"]
            elapsed = now - t0_single
            print(f"  {iters:>6}  {elapsed:>8.2f}  {best_obj:>12.2f}  "
                  f"{m['makespan']:>10.2f}  {m['total_delay']:>10.2f}  "
                  f"{m['movements']:>5}")
            next_report += report_interval

    elapsed_s = time.perf_counter() - t0_single
    print(f"  {'-'*60}")
    print(f"  [topology] done  iters={iters}  time={elapsed_s:.2f}s"
          f"  best_obj={best_obj:.2f}")

    return best_sol, best_obj, iters, log_rows


# =============================================================================
#  Core construction
# =============================================================================

def _build_topology_solution(
    instance: dict,
    params: dict,
    rng: random.Random,
    all_ac: list[dict],
    ac_target: dict[str, float],
    blocking_load: dict[str, int],
    avg_slack: float,
    w_delay: float,
    w_make: float,
    w_mov: float,
    w_topo: float,
    alpha: float,
    min_sep: float,
) -> dict:
    """Build one feasible solution with topology-aware position scoring."""
    positions     = instance["hangar"]["positions"]
    blocking_arcs = instance["hangar"]["blocking_arcs"]

    pos_free_at: dict[str, float] = {p: 0.0 for p in positions}
    assigned:    list[dict]       = []
    ac_solutions: list[dict]      = []

    for ac in all_ac:
        snapshot_ids = {a["id"] for a in assigned}
        current_movs = _count_movements(
            assigned + [
                {"id": x["id"], "position": x["position"],
                 "start": x["start"], "finish": x["finish"]}
                for x in ac_solutions if x["id"] not in snapshot_ids
            ],
            blocking_arcs,
        )

        urgency_factor = 1.0 / (1.0 + ac["slack"] / avg_slack) if avg_slack > 0 else 1.0

        pos_options: list[dict] = []
        for p in positions:
            t_s = _find_best_start(
                ac, p, pos_free_at[p], min_sep, blocking_arcs, assigned,
                params, ac_target[ac["id"]], current_movs, log=None,
            )
            t_f   = t_s + ac["total_duration"]
            delay = max(0.0, t_f - ac_target[ac["id"]])

            trial = assigned + [{"id": ac["id"], "position": p,
                                 "start": t_s, "finish": t_f}]
            movs  = _count_movements(
                trial + [
                    {"id": x["id"], "position": x["position"],
                     "start": x["start"], "finish": x["finish"]}
                    for x in ac_solutions
                    if x["id"] not in {a["id"] for a in trial}
                ],
                blocking_arcs,
            )

            topo_penalty = w_topo * urgency_factor * blocking_load[p] * w_delay
            score = w_delay * delay + w_make * t_f + w_mov * movs * 2 + topo_penalty

            pos_options.append({
                "pos": p, "t_start": t_s, "t_finish": t_f,
                "score": score, "delay": delay, "movements": movs,
            })

        pos_options.sort(key=lambda e: e["score"])
        effective_alpha = alpha + urgency_factor * (1.0 - alpha)
        weights  = _grasp_weights(len(pos_options), effective_alpha)
        selected, _, _ = _biased_random_select_logged(pos_options, weights, rng)

        pos_id = selected["pos"]
        t_s    = selected["t_start"]
        t_f    = selected["t_finish"]

        pos_free_at[pos_id] = t_f
        assigned.append({"id": ac["id"], "position": pos_id,
                         "start": t_s, "finish": t_f})

        delay = max(0.0, t_f - ac_target[ac["id"]])
        t = t_s
        job_schedules = []
        for job in ac["jobs"]:
            job_schedules.append({
                "id":     job["id"],
                "start":  round(t, 4),
                "finish": round(t + job["duration"], 4),
            })
            t += job["duration"]

        ac_solutions.append({
            "id":       ac["id"],
            "position": pos_id,
            "start":    round(t_s, 4),
            "finish":   round(t_f, 4),
            "delay":    round(delay, 4),
            "jobs":     job_schedules,
        })

    makespan    = max((a["finish"] for a in ac_solutions), default=0.0)
    total_delay = sum(a["delay"]  for a in ac_solutions)
    movements   = _count_movements(ac_solutions, blocking_arcs)

    return {
        "status":    "topology",
        "objective": 0.0,
        "metrics": {
            "makespan":    round(makespan, 4),
            "movements":   movements,
            "total_delay": round(total_delay, 4),
        },
        "aircraft": ac_solutions,
    }


# =============================================================================
#  Topology helpers
# =============================================================================

def _build_topology_solution_warm(
    instance: dict,
    params: dict,
    rng: random.Random,
    warm_ac: list[dict],
    free_ac: list[dict],
    pos_of_fixed: dict[str, str],
    ac_target: dict[str, float],
    blocking_load: dict[str, int],
    avg_slack: float,
    w_delay: float,
    w_make: float,
    w_mov: float,
    w_topo: float,
    alpha: float,
    min_sep: float,
) -> dict:
    """LNS repair: schedule warm_ac at their fixed positions first, then
    use topology-aware GRASP to re-insert free_ac.
    """
    positions     = instance["hangar"]["positions"]
    blocking_arcs = instance["hangar"]["blocking_arcs"]

    pos_free_at: dict[str, float] = {p: 0.0 for p in positions}
    assigned:    list[dict]       = []
    ac_solutions: list[dict]      = []

    for ac in sorted(warm_ac, key=lambda a: (a["slack"], -a["total_duration"])):
        p = pos_of_fixed[ac["id"]]
        snapshot_ids = {a["id"] for a in assigned}
        current_movs = _count_movements(
            assigned + [{"id": x["id"], "position": x["position"],
                         "start": x["start"], "finish": x["finish"]}
                        for x in ac_solutions if x["id"] not in snapshot_ids],
            blocking_arcs,
        )
        t_s = _find_best_start(
            ac, p, pos_free_at[p], min_sep, blocking_arcs, assigned,
            params, ac_target[ac["id"]], current_movs, log=None,
        )
        t_f   = t_s + ac["total_duration"]
        delay = max(0.0, t_f - ac_target[ac["id"]])
        pos_free_at[p] = t_f
        assigned.append({"id": ac["id"], "position": p, "start": t_s, "finish": t_f})
        t = t_s
        jobs = []
        for job in ac["jobs"]:
            jobs.append({"id": job["id"], "start": round(t, 4),
                         "finish": round(t + job["duration"], 4)})
            t += job["duration"]
        ac_solutions.append({"id": ac["id"], "position": p, "start": round(t_s, 4),
                              "finish": round(t_f, 4), "delay": round(delay, 4),
                              "jobs": jobs})

    for ac in sorted(free_ac, key=lambda a: (a["slack"], -a["total_duration"])):
        snapshot_ids = {a["id"] for a in assigned}
        current_movs = _count_movements(
            assigned + [{"id": x["id"], "position": x["position"],
                         "start": x["start"], "finish": x["finish"]}
                        for x in ac_solutions if x["id"] not in snapshot_ids],
            blocking_arcs,
        )
        urgency_factor  = 1.0 / (1.0 + ac["slack"] / avg_slack) if avg_slack > 0 else 1.0
        effective_alpha = alpha + urgency_factor * (1.0 - alpha)

        pos_options: list[dict] = []
        for p in positions:
            t_s = _find_best_start(
                ac, p, pos_free_at[p], min_sep, blocking_arcs, assigned,
                params, ac_target[ac["id"]], current_movs, log=None,
            )
            t_f   = t_s + ac["total_duration"]
            delay = max(0.0, t_f - ac_target[ac["id"]])
            trial = assigned + [{"id": ac["id"], "position": p, "start": t_s, "finish": t_f}]
            movs  = _count_movements(
                trial + [{"id": x["id"], "position": x["position"],
                          "start": x["start"], "finish": x["finish"]}
                         for x in ac_solutions
                         if x["id"] not in {a["id"] for a in trial}],
                blocking_arcs,
            )
            topo_penalty = w_topo * urgency_factor * blocking_load[p] * w_delay
            score = w_delay * delay + w_make * t_f + w_mov * movs * 2 + topo_penalty
            pos_options.append({"pos": p, "t_start": t_s, "t_finish": t_f,
                                 "score": score, "delay": delay, "movements": movs})

        pos_options.sort(key=lambda e: e["score"])
        weights  = _grasp_weights(len(pos_options), effective_alpha)
        selected, _, _ = _biased_random_select_logged(pos_options, weights, rng)

        p   = selected["pos"]
        t_s = selected["t_start"]
        t_f = selected["t_finish"]
        pos_free_at[p] = t_f
        assigned.append({"id": ac["id"], "position": p, "start": t_s, "finish": t_f})
        delay = max(0.0, t_f - ac_target[ac["id"]])
        t = t_s
        jobs = []
        for job in ac["jobs"]:
            jobs.append({"id": job["id"], "start": round(t, 4),
                         "finish": round(t + job["duration"], 4)})
            t += job["duration"]
        ac_solutions.append({"id": ac["id"], "position": p, "start": round(t_s, 4),
                              "finish": round(t_f, 4), "delay": round(delay, 4),
                              "jobs": jobs})

    makespan    = max((a["finish"] for a in ac_solutions), default=0.0)
    total_delay = sum(a["delay"]  for a in ac_solutions)
    movements   = _count_movements(ac_solutions, blocking_arcs)
    return {
        "status": "topology", "objective": 0.0,
        "metrics": {"makespan": round(makespan, 4), "movements": movements,
                    "total_delay": round(total_delay, 4)},
        "aircraft": ac_solutions,
    }
# =============================================================================
#  Local search — state, neighbourhoods, and the descent driver
# =============================================================================

class _LSState:
    """The search trajectory point.

    Invariant: ``_rebuild(assignments, instance, params, order=order)``
    reproduces ``sol`` -- and therefore ``obj`` -- exactly.  Every operator
    goes through :func:`_accept`, so the invariant cannot drift.
    """

    __slots__ = ("assignments", "order", "sol", "obj")

    def __init__(self, solution: dict, params: dict) -> None:
        self.assignments = [{"id": a["id"], "position": a["position"]}
                            for a in solution["aircraft"]]
        # The constructor schedules in its own aircraft order; handing that
        # order to _rebuild reproduces the incoming objective exactly.
        self.order = [a["id"] for a in solution["aircraft"]]
        self.sol   = solution
        self.obj   = _objective(solution, params)


def _accept(st: _LSState, ctx: dict, assignments: list[dict],
            order: list[str]) -> bool:
    """Evaluate a candidate; adopt it only if it strictly improves."""
    sol = _rebuild(assignments, ctx["instance"], ctx["params"], order=order)
    obj = _objective(sol, ctx["params"])
    if obj >= st.obj - 1e-6:
        return False
    st.obj         = obj
    st.sol         = sol
    st.assignments = [{"id": a["id"], "position": a["position"]}
                      for a in sol["aircraft"]]
    st.order       = list(order)
    return True


def _splice(block_order: list[str], block_ids: set[str],
            base_order: list[str]) -> list[str]:
    """Substitute *block_order* into the slots *block_ids* occupy in *base_order*."""
    it = iter(block_order)
    return [next(it) if aid in block_ids else aid for aid in base_order]


def _blocks(st: _LSState, ctx: dict,
            min_size: int = 2) -> list[tuple[list[str], set[str]]]:
    """Per-position aircraft blocks in current order, with a shuffled scan order."""
    pos_of = {a["id"]: a["position"] for a in st.assignments}
    out = []
    for pos in ctx["positions"]:
        aids = [aid for aid in st.order if pos_of[aid] == pos]
        if len(aids) >= min_size:
            out.append((aids, set(aids)))
    ctx["rng"].shuffle(out)
    return out


def _expired(ctx: dict) -> bool:
    return time.perf_counter() >= ctx["deadline"]


# --- N1 ----------------------------------------------------------------------
def _op_single_move(st: _LSState, ctx: dict) -> bool:
    """Move one aircraft to a different position."""
    rng = ctx["rng"]
    indices = list(range(len(st.assignments)))
    rng.shuffle(indices)
    for i in indices:
        if _expired(ctx):
            return False
        aid     = st.assignments[i]["id"]
        cur_pos = st.assignments[i]["position"]
        cands   = [p for p in ctx["positions"] if p != cur_pos]
        rng.shuffle(cands)
        for new_pos in cands:
            trial = [a if a["id"] != aid else {"id": aid, "position": new_pos}
                     for a in st.assignments]
            if _accept(st, ctx, trial, st.order):
                return True
    return False


# --- N2 ----------------------------------------------------------------------
def _op_two_opt(st: _LSState, ctx: dict) -> bool:
    """Swap the positions of two aircraft that sit in different positions."""
    n = len(st.assignments)
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)
             if st.assignments[i]["position"] != st.assignments[j]["position"]]
    ctx["rng"].shuffle(pairs)
    for i, j in pairs:
        if _expired(ctx):
            return False
        pos_i = st.assignments[i]["position"]
        pos_j = st.assignments[j]["position"]
        trial = [{"id": a["id"],
                  "position": pos_j if k == i else (pos_i if k == j else a["position"])}
                 for k, a in enumerate(st.assignments)]
        if _accept(st, ctx, trial, st.order):
            return True
    return False


# --- N3 ----------------------------------------------------------------------
def _op_intra_adjacent_swap(st: _LSState, ctx: dict) -> bool:
    """Swap a consecutive pair within one position's block."""
    for aids, ids in _blocks(st, ctx):
        if _expired(ctx):
            return False
        slots = list(range(len(aids) - 1))
        ctx["rng"].shuffle(slots)
        for k in slots:
            swapped = aids[:]
            swapped[k], swapped[k + 1] = swapped[k + 1], swapped[k]
            if _accept(st, ctx, st.assignments, _splice(swapped, ids, st.order)):
                return True
    return False


# --- N4 ----------------------------------------------------------------------
def _op_intra_insert(st: _LSState, ctx: dict) -> bool:
    """Move one aircraft to a different slot inside its own position block."""
    for aids, ids in _blocks(st, ctx):
        if _expired(ctx):
            return False
        moves = [(s, d) for s in range(len(aids)) for d in range(len(aids)) if s != d]
        ctx["rng"].shuffle(moves)
        for src, dst in moves:
            reordered = aids[:]
            reordered.insert(dst, reordered.pop(src))
            if _accept(st, ctx, st.assignments, _splice(reordered, ids, st.order)):
                return True
    return False


# --- N5 ----------------------------------------------------------------------
def _op_intra_swap(st: _LSState, ctx: dict) -> bool:
    """Swap two non-adjacent aircraft inside one position block (N3 covers pairs)."""
    for aids, ids in _blocks(st, ctx, min_size=3):
        if _expired(ctx):
            return False
        pairs = [(i, j) for i in range(len(aids)) for j in range(i + 2, len(aids))]
        ctx["rng"].shuffle(pairs)
        for i, j in pairs:
            swapped = aids[:]
            swapped[i], swapped[j] = swapped[j], swapped[i]
            if _accept(st, ctx, st.assignments, _splice(swapped, ids, st.order)):
                return True
    return False


# --- N6 ----------------------------------------------------------------------
def _op_edd_repair(st: _LSState, ctx: dict) -> bool:
    """Reorder a whole position block by EDD / slack / delay-ratio."""
    meta     = ctx["ac_meta"]
    dur_of   = ctx["dur_of"]
    delay_of = {a["id"]: a.get("delay", 0.0) for a in st.sol["aircraft"]}
    for aids, ids in _blocks(st, ctx):
        if _expired(ctx):
            return False
        orderings = [
            sorted(aids, key=lambda a: meta[a]["target_finish"]),
            sorted(aids, key=lambda a: (meta[a]["target_finish"]
                                        - meta[a]["earliest_start"])),
            sorted(aids, key=lambda a: -(delay_of.get(a, 0.0) / dur_of.get(a, 1.0))),
        ]
        ctx["rng"].shuffle(orderings)
        for reordered in orderings:
            if reordered == aids:
                continue
            if _accept(st, ctx, st.assignments, _splice(reordered, ids, st.order)):
                return True
    return False


# --- N7 ----------------------------------------------------------------------
def _op_delay_block(st: _LSState, ctx: dict) -> bool:
    """Relocate the K highest-delay aircraft: every intra slot AND every position."""
    rng    = ctx["rng"]
    k      = max(2, len(st.assignments) // 10)
    ranked = sorted(st.sol["aircraft"], key=lambda a: -a.get("delay", 0.0))[:k]
    pos_of = {a["id"]: a["position"] for a in st.assignments}

    for ac in ranked:
        if _expired(ctx):
            return False
        aid     = ac["id"]
        cur_pos = pos_of[aid]
        aids    = [x for x in st.order if pos_of[x] == cur_pos]
        ids     = set(aids)

        # intra-position: every insertion slot
        src   = aids.index(aid)
        slots = [d for d in range(len(aids)) if d != src]
        rng.shuffle(slots)
        for dst in slots:
            reordered = aids[:]
            reordered.pop(src)
            reordered.insert(dst, aid)
            if _accept(st, ctx, st.assignments, _splice(reordered, ids, st.order)):
                return True

        # cross-position
        cands = [p for p in ctx["positions"] if p != cur_pos]
        rng.shuffle(cands)
        for new_pos in cands:
            trial = [a if a["id"] != aid else {"id": aid, "position": new_pos}
                     for a in st.assignments]
            if _accept(st, ctx, trial, st.order):
                return True
    return False


_OPS_CHEAP = (_op_single_move, _op_two_opt, _op_intra_adjacent_swap)
_OPS_FULL  = (_op_intra_insert, _op_intra_swap, _op_edd_repair, _op_delay_block)


def _light_local_search(
    solution: dict,
    instance: dict,
    params: dict,
    max_passes: int,
    rng: random.Random,
    deadline: float = float("inf"),
    ls_mode: str = "full",
    op_order: str = "random",
) -> dict:
    """First-improvement descent over seven neighbourhoods.

    Neighbourhoods
      N1. Single-move             move one aircraft to a different position
      N2. 2-opt swap              swap the positions of two aircraft
      N3. Adjacent intra-swap     swap a consecutive pair within a position
      N4. Intra-position insert   move an aircraft to another slot, same position
      N5. Non-adjacent intra-swap swap two aircraft within a position
      N6. EDD repair              reorder a position block by EDD/slack/ratio
      N7. Delay-block insert      relocate the highest-delay aircraft

    ``ls_mode="fast"`` exposes only the three cheap neighbourhoods (N1-N3);
    ``"full"`` exposes all seven.

    ``op_order`` selects the driver:

    - ``"random"`` -- RVND.  Neighbourhoods are drawn in a fresh random
      order; an improvement re-arms the whole set, a failure retires that
      one, and the descent ends once every neighbourhood has failed in a
      row.  The scan order *inside* each neighbourhood is shuffled too, so
      a descent is not biased towards low-numbered positions or slots.
    - ``"fixed"`` -- the historical cascade: try N1, then N2, ... and
      restart from N1 on any improvement.

    Both drivers stop at ``deadline``; ``max_passes`` bounds improving
    rounds.  The natural stop is the local optimum.
    """
    st  = _LSState(solution, params)
    ctx = {
        "instance":  instance,
        "params":    params,
        "positions": instance["hangar"]["positions"],
        "rng":       rng,
        "deadline":  deadline,
        "ac_meta":   {ac["id"]: {"earliest_start": ac.get("earliest_start", 0.0),
                                 "target_finish":  ac.get("target_finish", float("inf"))}
                      for ac in instance["aircrafts"]},
    }
    dur_of: dict[str, float] = {}
    for ac in instance["aircrafts"]:
        total = sum(j["duration"] for j in instance["jobs"]
                    if j["aircraft_id"] == ac["id"])
        dur_of[ac["id"]] = total if total > 0 else 1.0
    ctx["dur_of"] = dur_of

    ops = list(_OPS_CHEAP) + (list(_OPS_FULL) if ls_mode == "full" else [])

    if op_order == "random":
        pending = ops[:]
        rng.shuffle(pending)
        rounds = 0
        while pending and rounds < max_passes and not _expired(ctx):
            if pending[-1](st, ctx):
                rounds += 1
                pending = ops[:]          # re-arm every neighbourhood
                rng.shuffle(pending)
            else:
                pending.pop()             # retire this neighbourhood
    else:
        for _ in range(max_passes):
            if _expired(ctx):
                break
            if not any(op(st, ctx) for op in ops):
                break

    return st.sol


def _prepare_ac_earliest(instance: dict, aid: str) -> float:
    """Return earliest_start for aircraft *aid* (used for intra-pos ordering)."""
    for ac in instance["aircrafts"]:
        if ac["id"] == aid:
            return ac.get("earliest_start", 0.0)
    return 0.0


def _compute_blocking_load(
    positions: list[str],
    blocking_arcs: list[dict],
) -> dict[str, int]:
    """Return {position: number of positions reachable transitively from it}."""
    adj: dict[str, set[str]] = {p: set() for p in positions}
    for arc in blocking_arcs:
        adj[arc["front"]].add(arc["rear"])

    result: dict[str, int] = {}
    for start in positions:
        visited: set[str] = set()
        stack = list(adj[start])
        while stack:
            node = stack.pop()
            if node not in visited:
                visited.add(node)
                stack.extend(adj[node] - visited)
        result[start] = len(visited)
    return result


# =============================================================================
#  Log assembly
# =============================================================================

def _assemble_log(
    instance: dict,
    params: dict,
    blocking_load: dict[str, int],
    log_rows: list[str],
    best_obj: float,
    best_sol: dict,
    total_iters: int,
) -> list[str]:
    lines: list[str] = []
    sep = "=" * 72

    lines.append(sep)
    lines.append("  Topology-Aware Heuristic — run summary")
    lines.append(sep)
    lines.append(f"  Instance aircraft : {len(instance['aircrafts'])}")
    lines.append(f"  Positions         : {instance['hangar']['positions']}")
    lines.append(f"  Blocking load     : "
                 + "  ".join(f"{p}={v}" for p, v in sorted(blocking_load.items())))
    lines.append("")
    lines.append("  Parameters:")
    for k, v in params.items():
        lines.append(f"    {k}: {v}")
    lines.append("")
    lines.append(sep)
    lines.append(f"  Iterations: {total_iters}")
    lines.append(f"  Best objective: {best_obj:.4f}")
    m = best_sol["metrics"]
    lines.append(f"  Makespan: {m['makespan']:.4f}   "
                 f"Delay: {m['total_delay']:.4f}   "
                 f"Movements: {m['movements']}")
    lines.append(sep)
    lines.append("")
    lines.append("  Improvement log:")
    lines.extend(log_rows)
    lines.append("")
    lines.append(sep)
    lines.append("  Best solution — aircraft assignments:")
    lines.append(f"  {'ID':<6}  {'Pos':<5}  {'load':>4}  {'duration':>9}"
                 f"  {'start':>8}  {'finish':>8}  {'delay':>7}")
    lines.append(f"  {'-'*56}")
    aircraft_info = _prepare_aircraft_info(instance["aircrafts"], instance["jobs"])
    for a in sorted(best_sol["aircraft"], key=lambda x: x["start"]):
        dur  = aircraft_info[a["id"]]["total_duration"]
        load = blocking_load.get(a["position"], 0)
        lines.append(
            f"  {a['id']:<6}  {a['position']:<5}  {load:>4}  {dur:>9.2f}"
            f"  {a['start']:>8.2f}  {a['finish']:>8.2f}  {a['delay']:>7.2f}"
        )
    lines.append(sep)

    return lines
