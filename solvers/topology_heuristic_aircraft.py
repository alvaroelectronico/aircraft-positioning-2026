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
                                  deadline=deadline, ls_mode=ls_mode)
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


def _light_local_search(
    solution: dict,
    instance: dict,
    params: dict,
    max_passes: int,
    rng: random.Random,
    deadline: float = float("inf"),
    ls_mode: str = "full",
) -> dict:
    """Bounded local search with seven operators in priority order.

    Operators (first-improvement, restart from Op 1 on any improvement):
      1. Single-move:            move one aircraft to a different position
      2. 2-opt swap:             swap positions of two aircraft
      3. Adjacent intra-swap:    swap consecutive pair within a position
      4. Intra-position insert:  move aircraft to another slot in same position
      5. Non-adjacent intra-swap: swap any two aircraft within a position
      6. EDD repair:             reorder whole position block by EDD/slack/ratio
      7. Delay-block insert:     relocate highest-delay aircraft more aggressively

    The deadline parameter stops the search early if a time limit is active.
    max_passes bounds total outer restarts when no operator finds improvement.
    """
    positions   = instance["hangar"]["positions"]
    assignments = [{"id": a["id"], "position": a["position"]}
                   for a in solution["aircraft"]]
    best_sol = solution
    best_obj = _objective(solution, params)

    # Pre-build aircraft info for EDD/slack ordering (target_finish, slack)
    ac_meta: dict[str, dict] = {}
    for ac in instance["aircrafts"]:
        ac_meta[ac["id"]] = {
            "earliest_start": ac.get("earliest_start", 0.0),
            "target_finish":  ac.get("target_finish", float("inf")),
        }
    for ac in instance.get("jobs", []):
        pass  # jobs don't carry target_finish directly

    def _get_order(assgn: list[dict]) -> list[str]:
        return sorted([a["id"] for a in assgn],
                      key=lambda aid: ac_meta[aid]["earliest_start"])

    for _ in range(max_passes):
        if time.perf_counter() >= deadline:
            break
        improved = False

        # ---- Op 1: single-move ------------------------------------------
        indices = list(range(len(assignments)))
        rng.shuffle(indices)
        for i in indices:
            if time.perf_counter() >= deadline:
                break
            aid     = assignments[i]["id"]
            cur_pos = assignments[i]["position"]
            pos_candidates = [p for p in positions if p != cur_pos]
            rng.shuffle(pos_candidates)
            for new_pos in pos_candidates:
                trial = [a if a["id"] != aid
                         else {"id": aid, "position": new_pos}
                         for a in assignments]
                trial_sol = _rebuild(trial, instance, params)
                trial_obj = _objective(trial_sol, params)
                if trial_obj < best_obj - 1e-6:
                    best_obj    = trial_obj
                    best_sol    = trial_sol
                    assignments = [{"id": a["id"], "position": a["position"]}
                                   for a in trial_sol["aircraft"]]
                    improved    = True
                    break
            if improved:
                break

        if not improved:
            # ---- Op 2: 2-opt swap ----------------------------------------
            pairs = [(i, j) for i in range(len(assignments))
                     for j in range(i + 1, len(assignments))
                     if assignments[i]["position"] != assignments[j]["position"]]
            rng.shuffle(pairs)
            for i, j in pairs:
                if time.perf_counter() >= deadline:
                    break
                pos_i = assignments[i]["position"]
                pos_j = assignments[j]["position"]
                trial = [
                    {"id": a["id"],
                     "position": pos_j if ki == i else (pos_i if ki == j else a["position"])}
                    for ki, a in enumerate(assignments)
                ]
                trial_sol = _rebuild(trial, instance, params)
                trial_obj = _objective(trial_sol, params)
                if trial_obj < best_obj - 1e-6:
                    best_obj    = trial_obj
                    best_sol    = trial_sol
                    assignments = [{"id": a["id"], "position": a["position"]}
                                   for a in trial_sol["aircraft"]]
                    improved    = True
                    break

        if not improved:
            # ---- Op 3: adjacent intra-position swap ----------------------
            default_order = _get_order(assignments)
            pos_of = {a["id"]: a["position"] for a in assignments}
            for pos in positions:
                if time.perf_counter() >= deadline:
                    break
                pos_aids = [aid for aid in default_order if pos_of[aid] == pos]
                if len(pos_aids) < 2:
                    continue
                pos_aids_set = set(pos_aids)
                for swap_i in range(len(pos_aids) - 1):
                    swapped = pos_aids[:]
                    swapped[swap_i], swapped[swap_i + 1] = (
                        swapped[swap_i + 1], swapped[swap_i]
                    )
                    swap_iter    = iter(swapped)
                    custom_order = [next(swap_iter) if aid in pos_aids_set else aid
                                    for aid in default_order]
                    trial_sol = _rebuild(assignments, instance, params,
                                         order=custom_order)
                    trial_obj = _objective(trial_sol, params)
                    if trial_obj < best_obj - 1e-6:
                        best_obj    = trial_obj
                        best_sol    = trial_sol
                        assignments = [{"id": a["id"], "position": a["position"]}
                                       for a in trial_sol["aircraft"]]
                        improved    = True
                        break
                if improved:
                    break

        if not improved and ls_mode == "full":
            # ---- Op 4: intra-position insertion --------------------------
            # Move one aircraft to a different slot index within the same position.
            default_order = _get_order(assignments)
            pos_of = {a["id"]: a["position"] for a in assignments}
            for pos in positions:
                if time.perf_counter() >= deadline:
                    break
                pos_aids = [aid for aid in default_order if pos_of[aid] == pos]
                if len(pos_aids) < 2:
                    continue
                pos_aids_set = set(pos_aids)
                for src in range(len(pos_aids)):
                    for dst in range(len(pos_aids)):
                        if src == dst:
                            continue
                        reordered = pos_aids[:]
                        item = reordered.pop(src)
                        reordered.insert(dst, item)
                        ins_iter     = iter(reordered)
                        custom_order = [next(ins_iter) if aid in pos_aids_set else aid
                                        for aid in default_order]
                        trial_sol = _rebuild(assignments, instance, params,
                                              order=custom_order)
                        trial_obj = _objective(trial_sol, params)
                        if trial_obj < best_obj - 1e-6:
                            best_obj    = trial_obj
                            best_sol    = trial_sol
                            assignments = [{"id": a["id"], "position": a["position"]}
                                           for a in trial_sol["aircraft"]]
                            improved    = True
                            break
                    if improved:
                        break
                if improved:
                    break

        if not improved and ls_mode == "full":
            # ---- Op 5: non-adjacent intra-position swap ------------------
            default_order = _get_order(assignments)
            pos_of = {a["id"]: a["position"] for a in assignments}
            for pos in positions:
                if time.perf_counter() >= deadline:
                    break
                pos_aids = [aid for aid in default_order if pos_of[aid] == pos]
                if len(pos_aids) < 3:
                    continue  # adjacent swap (Op 3) already covers pairs
                pos_aids_set = set(pos_aids)
                for i in range(len(pos_aids)):
                    for j in range(i + 2, len(pos_aids)):  # skip adjacent (Op 3)
                        swapped = pos_aids[:]
                        swapped[i], swapped[j] = swapped[j], swapped[i]
                        sw_iter      = iter(swapped)
                        custom_order = [next(sw_iter) if aid in pos_aids_set else aid
                                        for aid in default_order]
                        trial_sol = _rebuild(assignments, instance, params,
                                              order=custom_order)
                        trial_obj = _objective(trial_sol, params)
                        if trial_obj < best_obj - 1e-6:
                            best_obj    = trial_obj
                            best_sol    = trial_sol
                            assignments = [{"id": a["id"], "position": a["position"]}
                                           for a in trial_sol["aircraft"]]
                            improved    = True
                            break
                    if improved:
                        break
                if improved:
                    break

        if not improved and ls_mode == "full":
            # ---- Op 6: EDD repair per position ---------------------------
            # Try three full reorderings of each position block:
            # EDD (target_finish ASC), slack ASC, delay_ratio DESC.
            default_order = _get_order(assignments)
            pos_of = {a["id"]: a["position"] for a in assignments}
            # Gather per-aircraft delay from current best solution
            delay_of = {a["id"]: a.get("delay", 0.0) for a in best_sol["aircraft"]}
            dur_of   = {}
            for ac in instance["aircrafts"]:
                total_dur = sum(j["duration"] for j in instance["jobs"]
                                if j["aircraft_id"] == ac["id"])
                dur_of[ac["id"]] = total_dur if total_dur > 0 else 1.0

            for pos in positions:
                if time.perf_counter() >= deadline:
                    break
                pos_aids = [aid for aid in default_order if pos_of[aid] == pos]
                if len(pos_aids) < 2:
                    continue
                pos_aids_set = set(pos_aids)

                orderings = [
                    sorted(pos_aids, key=lambda aid: ac_meta[aid]["target_finish"]),
                    sorted(pos_aids, key=lambda aid:
                           ac_meta[aid]["target_finish"] - ac_meta[aid]["earliest_start"]),
                    sorted(pos_aids, key=lambda aid:
                           -(delay_of.get(aid, 0.0) / dur_of.get(aid, 1.0))),
                ]
                for reordered in orderings:
                    if reordered == pos_aids:
                        continue
                    edd_iter     = iter(reordered)
                    custom_order = [next(edd_iter) if aid in pos_aids_set else aid
                                    for aid in default_order]
                    trial_sol = _rebuild(assignments, instance, params,
                                          order=custom_order)
                    trial_obj = _objective(trial_sol, params)
                    if trial_obj < best_obj - 1e-6:
                        best_obj    = trial_obj
                        best_sol    = trial_sol
                        assignments = [{"id": a["id"], "position": a["position"]}
                                       for a in trial_sol["aircraft"]]
                        improved    = True
                        break
                if improved:
                    break

        if not improved and ls_mode == "full":
            # ---- Op 7: delay-block insertion -----------------------------
            # Take K highest-delay aircraft; for each, try all positions in
            # its own block AND all single-move targets (cross-position).
            # More aggressive than Op 1 because it combines intra + inter.
            n_ac = len(assignments)
            k    = max(2, n_ac // 10)
            delay_ranked = sorted(best_sol["aircraft"],
                                  key=lambda a: -a.get("delay", 0.0))
            target_ids   = {a["id"] for a in delay_ranked[:k]}

            default_order = _get_order(assignments)
            pos_of = {a["id"]: a["position"] for a in assignments}

            for aid in [a["id"] for a in delay_ranked[:k]]:
                if time.perf_counter() >= deadline:
                    break
                cur_pos  = pos_of[aid]
                pos_aids = [x for x in default_order if pos_of[x] == cur_pos]
                pos_aids_set = set(pos_aids)

                # Intra-position: try all insertion slots
                src_idx = pos_aids.index(aid)
                for dst in range(len(pos_aids)):
                    if dst == src_idx:
                        continue
                    reordered = pos_aids[:]
                    reordered.pop(src_idx)
                    reordered.insert(dst, aid)
                    ins_iter     = iter(reordered)
                    custom_order = [next(ins_iter) if x in pos_aids_set else x
                                    for x in default_order]
                    trial_sol = _rebuild(assignments, instance, params,
                                          order=custom_order)
                    trial_obj = _objective(trial_sol, params)
                    if trial_obj < best_obj - 1e-6:
                        best_obj    = trial_obj
                        best_sol    = trial_sol
                        assignments = [{"id": a["id"], "position": a["position"]}
                                       for a in trial_sol["aircraft"]]
                        improved    = True
                        break

                if not improved:
                    # Cross-position: try moving to a different position entirely
                    for new_pos in [p for p in positions if p != cur_pos]:
                        trial = [a if a["id"] != aid
                                 else {"id": aid, "position": new_pos}
                                 for a in assignments]
                        trial_sol = _rebuild(trial, instance, params)
                        trial_obj = _objective(trial_sol, params)
                        if trial_obj < best_obj - 1e-6:
                            best_obj    = trial_obj
                            best_sol    = trial_sol
                            assignments = [{"id": a["id"], "position": a["position"]}
                                           for a in trial_sol["aircraft"]]
                            improved    = True
                            break

                if improved:
                    break

        if not improved:
            break

    return best_sol


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
