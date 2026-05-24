"""
ConstructiveHeuristic — GRASP-style constructive heuristic for aircraft positioning.

Algorithm (single iteration):
    1. Sort aircrafts by a criterion (e.g. earliest_start, total_duration).
    2. For each aircraft (in biased-random order from the sorted list):
        a. Sort positions by attractiveness (e.g. earliest available time).
        b. Pick a position with biased-random selection.
        c. Insert the aircraft: schedule its jobs sequentially after the
           position becomes free, respecting earliest_start.
    3. Repeat for max_runtime seconds, keeping the best solution found.

Usage
-----
    from solvers.constructive_heuristic import ConstructiveHeuristic
    from aircraft_positioning import Application

    app = Application(solver=ConstructiveHeuristic())
    app.read_data("data/instances/instance.json")
    app.configure_solver(time_limit_s=30, alpha=0.3)
    app.solve()
    app.check_solution()
"""
from __future__ import annotations

import math
import random
import time
from typing import Any


# =============================================================================
#  Public solver class
# =============================================================================

class ConstructiveHeuristic:
    """GRASP constructive heuristic — no external dependencies required."""

    _DEFAULTS: dict = {
        "time_limit_s": 30.0,
        "alpha": 0.3,           # geometric decay: P(rank i) ∝ (1-alpha)^i
        "min_separation": 10.0,
        "weight_makespan": 10.0,
        "weight_delay": 100.0,
        "weight_movements": 1.0,
        "seed": None,
        "log_enabled": False,   # write a .log file alongside the solution JSON
        "n_perturb": 4,         # ILS: number of aircraft removed per perturbation kick
        "ils_ratio": 0.0,       # fraction of iterations that use ILS warm-start (0 = pure GRASP)
        "ls_every":  1,         # run local search every N iterations (1 = every iter)
    }

    def __init__(self) -> None:
        self._params: dict = dict(self._DEFAULTS)
        self._log_lines: list[str] | None = None

    @property
    def name(self) -> str:
        return "constructive"

    def configure_solver(self, **kwargs) -> None:
        for key, value in kwargs.items():
            self._params[key] = value

    def get_config(self) -> dict:
        return dict(self._params)

    def get_log(self) -> list[str] | None:
        """Return log lines from the last solve() call, or None if logging was disabled."""
        return self._log_lines

    def solve(self, instance_data: dict) -> dict:
        rng = random.Random(self._params["seed"])
        time_limit  = self._params["time_limit_s"]
        log_enabled = bool(self._params.get("log_enabled", False))
        t0       = time.perf_counter()
        deadline = t0 + time_limit
        report_interval = max(1.0, time_limit / 10)
        next_report = t0 + report_interval

        best_solution: dict | None = None
        best_obj  = math.inf
        best_log:  list[str] | None = None
        best_iter = 0
        iterations  = 0
        improvements = 0
        iter_rows: list[str] = []   # one summary line per iteration (for the log)

        print(f"  [constructive] starting  alpha={self._params['alpha']}  "
              f"time_limit={time_limit}s")
        print(f"  {'Iter':>8}  {'Time(s)':>8}  {'Best obj':>12}  "
              f"{'Makespan':>10}  {'Delay':>10}  {'Mov':>5}  {'Improv':>7}")
        print(f"  {'-'*70}")

        n_perturb  = self._params.get("n_perturb",  4)    # aircraft removed per ILS kick
        ils_ratio  = self._params.get("ils_ratio",  0.7)  # fraction of iters using ILS warm-start
        # Local search is run only every `ls_every` iterations (plus always on improvements).
        # Setting ls_every=1 reverts to the old behaviour (LS every iteration).
        ls_every   = self._params.get("ls_every",   5)

        while True:
            now = time.perf_counter()
            if now >= deadline:
                break

            iter_log: list[str] | None = [] if log_enabled else None

            # Decide: fresh random build or ILS perturbation of current best
            if (iterations > 0 and best_solution is not None
                    and rng.random() < ils_ratio):
                n_ac_sol = len(best_solution["aircraft"])
                k = max(2, min(n_perturb, n_ac_sol - 1))
                keep = rng.sample(best_solution["aircraft"], n_ac_sol - k)
                warm = {a["id"]: a["position"] for a in keep}
            else:
                warm = None

            sol = _build_solution(instance_data, self._params, rng, iter_log,
                                  warm_assignments=warm)

            # Run local search every ls_every iterations; always run it if this
            # construction beats the current best (to maximise the new candidate).
            raw_obj = _objective(sol, self._params)
            if iterations % ls_every == 0 or raw_obj < best_obj:
                sol = _local_search_reassign(sol, instance_data, self._params, iter_log)

            obj = _objective(sol, self._params)
            iterations += 1
            elapsed = now - t0
            m = sol["metrics"]

            if obj < best_obj:
                best_obj   = obj
                best_solution = sol
                best_log   = iter_log
                best_iter  = iterations
                improvements += 1
                tag = "  *"
                print(f"  {iterations:>8}  {elapsed:>8.2f}  {best_obj:>12.2f}  "
                      f"{m['makespan']:>10.2f}  {m['total_delay']:>10.2f}  "
                      f"{m['movements']:>5}  {improvements:>7}{tag}")
            else:
                tag = ""
                if now >= next_report:
                    bm = best_solution["metrics"]
                    print(f"  {iterations:>8}  {elapsed:>8.2f}  {best_obj:>12.2f}  "
                          f"{bm['makespan']:>10.2f}  {bm['total_delay']:>10.2f}  "
                          f"{bm['movements']:>5}  {improvements:>7}")
                    next_report += report_interval

            if log_enabled:
                iter_rows.append(
                    f"  {iterations:>8}  {elapsed:>8.2f}  {obj:>12.2f}  "
                    f"{m['makespan']:>10.2f}  {m['total_delay']:>10.2f}  "
                    f"{m['movements']:>5}{tag}"
                )

        elapsed_total = time.perf_counter() - t0
        assert best_solution is not None
        print(f"  {'-'*70}")
        print(f"  [constructive] done  iter={iterations}  improvements={improvements}  "
              f"time={elapsed_total:.2f}s  best_obj={best_obj:.2f}")

        best_solution["status"] = f"heuristic ({iterations} iterations)"

        if log_enabled and best_log is not None:
            self._log_lines = _assemble_log(
                instance_data, self._params, iter_rows, best_log, best_iter, best_obj,
            )
        else:
            self._log_lines = None

        return best_solution


# =============================================================================
#  Core construction
# =============================================================================

def _build_solution(
    instance: dict,
    params: dict,
    rng: random.Random,
    log: list[str] | None = None,
    warm_assignments: dict[str, str] | None = None,
) -> dict:
    """Build one feasible solution via biased-random greedy insertion.

    Parameters
    ----------
    warm_assignments:
        Optional dict mapping aircraft_id → position for aircraft whose
        position is pre-fixed (ILS perturbation).  These aircraft are
        scheduled first (in earliest_start order) before the GRASP loop
        handles the remaining free aircraft.
    """
    alpha   = params["alpha"]
    min_sep = params["min_separation"]

    aircrafts_raw = instance["aircrafts"]
    jobs_data     = instance["jobs"]
    positions     = instance["hangar"]["positions"]
    blocking_arcs = instance["hangar"]["blocking_arcs"]

    aircraft_info = _prepare_aircraft_info(aircrafts_raw, jobs_data)
    all_ac        = sort_aircrafts(list(aircraft_info.values()))

    pos_free_at: dict[str, float] = {p: 0.0 for p in positions}
    assigned: list[dict] = []
    ac_target: dict[str, float] = {a["id"]: a["target_finish"] for a in aircrafts_raw}
    aircraft_solutions: list[dict] = []

    # ----- ILS warm phase: schedule fixed aircraft first ----------------
    if warm_assignments:
        warm_ids = set(warm_assignments.keys())
        warm_ac  = [a for a in all_ac if a["id"] in warm_ids]
        sorted_ac = [a for a in all_ac if a["id"] not in warm_ids]

        for ac in sorted(warm_ac, key=lambda a: a["earliest_start"]):
            p = warm_assignments[ac["id"]]
            assigned_ids = {x["id"] for x in assigned}
            snapshot = assigned + [
                {"id": x["id"], "position": x["position"],
                 "start": x["start"], "finish": x["finish"]}
                for x in aircraft_solutions if x["id"] not in assigned_ids
            ]
            current_movs = _count_movements(snapshot, blocking_arcs)
            t_s = _find_best_start(
                ac, p, pos_free_at[p], min_sep, blocking_arcs, assigned,
                params, ac_target[ac["id"]], current_movs, log=None,
            )
            t_f   = t_s + ac["total_duration"]
            delay = max(0.0, t_f - ac_target[ac["id"]])
            pos_free_at[p] = t_f
            assigned.append({"id": ac["id"], "position": p,
                              "start": t_s, "finish": t_f})
            t = t_s
            job_schedules = []
            for job in ac["jobs"]:
                job_schedules.append({
                    "id":     job["id"],
                    "start":  round(t, 4),
                    "finish": round(t + job["duration"], 4),
                })
                t += job["duration"]
            aircraft_solutions.append({
                "id":       ac["id"],
                "position": p,
                "start":    round(t_s, 4),
                "finish":   round(t_f, 4),
                "delay":    round(delay, 4),
                "jobs":     job_schedules,
            })
    else:
        sorted_ac = all_ac

    n_ac = len(sorted_ac)

    if log is not None:
        arcs_str = "  ".join(f"{arc['front']}→{arc['rear']}" for arc in blocking_arcs)
        log.append(f"Blocking arcs: {arcs_str or 'none'}")
        if warm_assignments:
            log.append(f"Warm assignments: {len(warm_assignments)} fixed, {n_ac} to insert")
        log.append("")
        log.append("Aircraft initial ranking (target_finish ASC, total_duration ASC):")
        log.append(
            f"  {'Rank':<5}  {'ID':<6}  {'earliest':>9}  {'target':>9}"
            f"  {'duration':>10}"
        )
        log.append(f"  {'-'*46}")
        for i, a in enumerate(sorted_ac):
            log.append(
                f"  [{i:>2}]  {a['id']:<6}  {a['earliest_start']:>9.2f}"
                f"  {a['target_finish']:>9.2f}  {a['total_duration']:>10.2f}"
            )

    w_delay = params.get("weight_delay",    100.0)
    w_make  = params.get("weight_makespan",  10.0)
    w_mov   = params.get("weight_movements",  1.0)
    w_gap   = params.get("weight_gap",       w_make)

    for step in range(n_ac):
        sep = "=" * 72
        if log is not None:
            log.append(f"\n{sep}")
            log.append(f"  STEP {step + 1}/{n_ac}")
            log.append(sep)

        # ---- compute current movement baseline (once per step) ---------
        assigned_ids = {a["id"] for a in assigned}
        snapshot = assigned + [
            {"id": x["id"], "position": x["position"],
             "start": x["start"], "finish": x["finish"]}
            for x in aircraft_solutions if x["id"] not in assigned_ids
        ]
        current_movs = _count_movements(snapshot, blocking_arcs)

        # ---- enumerate ALL (aircraft, position) pairs ------------------
        pairs: list[dict] = []
        for ac_cand in sorted_ac:
            for p in positions:
                t_s = _find_best_start(
                    ac_cand, p, pos_free_at[p], min_sep, blocking_arcs, assigned,
                    params, ac_target[ac_cand["id"]], current_movs, log=None,
                )
                t_f   = t_s + ac_cand["total_duration"]
                delay = max(0.0, t_f - ac_target[ac_cand["id"]])
                test  = assigned + [{"id": ac_cand["id"], "position": p,
                                     "start": t_s, "finish": t_f}]
                movs  = _count_movements(
                    test + [{"id": x["id"], "position": x["position"],
                              "start": x["start"], "finish": x["finish"]}
                             for x in aircraft_solutions
                             if x["id"] not in {a["id"] for a in test}],
                    blocking_arcs,
                )
                # Penalise idle time only after the position has been used at least once.
                # When pos_free_at=0 the position is empty: no gap to penalise.
                gap   = max(0.0, t_s - pos_free_at[p]) if pos_free_at[p] > 1e-9 else 0.0
                score = w_delay * delay + w_make * t_f + w_mov * movs * 2 + w_gap * gap
                pairs.append({
                    "ac": ac_cand, "pos": p,
                    "t_start": t_s, "t_finish": t_f,
                    "delay": delay, "movements": movs, "gap": gap, "score": score,
                })

        pairs.sort(key=lambda e: e["score"])
        pair_weights = _grasp_weights(len(pairs), alpha)

        if log is not None:
            log.append("")
            log.append(f"  Pair evaluation  ({len(pairs)} pairs):")
            log.append(
                f"    {'Rank':<5}  {'ID':<6}  {'Pos':<5}  {'t_start':>8}"
                f"  {'t_finish':>9}  {'delay':>7}  {'gap':>7}  {'blocking':>9}  {'score':>9}"
                f"  {'weight':>8}  {'P(%)':>7}  {'cum(%)':>7}"
            )
            log.append(f"    {'-'*105}")
            total_pw = sum(pair_weights)
            cum_p = 0.0
            for i, (e, w) in enumerate(zip(pairs, pair_weights)):
                p_pct  = 100 * w / total_pw
                cum_p += p_pct
                blocking_flag = f"{e['movements']} mov" if e["movements"] else "none"
                log.append(
                    f"    [{i:>2}]  {e['ac']['id']:<6}  {e['pos']:<5}  {e['t_start']:>8.2f}"
                    f"  {e['t_finish']:>9.2f}  {e['delay']:>7.2f}  {e['gap']:>7.2f}  {blocking_flag:>9}"
                    f"  {e['score']:>9.2f}  {w:>8.4f}  {p_pct:>6.2f}%  {cum_p:>6.2f}%"
                )

        # ---- single GRASP draw over all pairs --------------------------
        selected, pair_draw, pair_rank = _biased_random_select_logged(pairs, pair_weights, rng)

        ac     = selected["ac"]
        pos_id = selected["pos"]
        sorted_ac.remove(ac)

        if log is not None:
            log.append(
                f"    draw={pair_draw:.4f}  →  ({ac['id']}, {pos_id}) (rank {pair_rank}) selected"
            )

        # ---- re-derive start time with log enabled ---------------------
        t_start = _find_best_start(
            ac, pos_id, pos_free_at[pos_id], min_sep, blocking_arcs, assigned,
            params, ac_target[ac["id"]], current_movs, log,
        )

        # ---- schedule jobs ---------------------------------------------
        t = t_start
        job_schedules = []
        for job in ac["jobs"]:
            job_schedules.append({
                "id":     job["id"],
                "start":  round(t, 4),
                "finish": round(t + job["duration"], 4),
            })
            t += job["duration"]

        t_finish = t
        pos_free_at[pos_id] = t_finish
        assigned.append({"id": ac["id"], "position": pos_id,
                         "start": t_start, "finish": t_finish})

        delay = max(0.0, t_finish - ac_target[ac["id"]])
        aircraft_solutions.append({
            "id":       ac["id"],
            "position": pos_id,
            "start":    round(t_start, 4),
            "finish":   round(t_finish, 4),
            "delay":    round(delay, 4),
            "jobs":     job_schedules,
        })

        if log is not None:
            log.append("")
            log.append(
                f"  Assignment: {ac['id']} → {pos_id}"
                f"  [{round(t_start,2):.2f} → {round(t_finish,2):.2f}]"
                f"  delay={round(delay,2):.2f}"
            )
            for j in job_schedules:
                log.append(f"    {j['id']:<10} [{j['start']:.2f} → {j['finish']:.2f}]")

            # current state of all assigned aircraft
            log.append("")
            log.append("  Assigned so far:")
            log.append(
                f"    {'ID':<6}  {'Pos':<5}  {'start':>8}  {'finish':>8}  {'delay':>7}"
            )
            log.append(f"    {'-'*40}")
            for a in aircraft_solutions:
                log.append(
                    f"    {a['id']:<6}  {a['position']:<5}  {a['start']:>8.2f}"
                    f"  {a['finish']:>8.2f}  {a['delay']:>7.2f}"
                )

    makespan    = max((a["finish"] for a in aircraft_solutions), default=0.0)
    total_delay = sum(a["delay"] for a in aircraft_solutions)
    movements   = _count_movements(aircraft_solutions, blocking_arcs)

    if log is not None:
        log.append("")
        log.append("=" * 72)
        log.append(
            f"  Iteration result:  makespan={round(makespan,2):.2f}"
            f"  movements={movements}  delay={round(total_delay,2):.2f}"
        )
        log.append("=" * 72)

    return {
        "status":    "heuristic",
        "objective": 0.0,
        "metrics": {
            "makespan":    round(makespan, 4),
            "movements":   movements,
            "total_delay": round(total_delay, 4),
        },
        "aircraft": aircraft_solutions,
    }


# =============================================================================
#  Sort & selection helpers
# =============================================================================

def sort_aircrafts(aircrafts: list[dict]) -> list[dict]:
    """Sort aircrafts: urgent (earliest target_finish) first, then by total duration."""
    return sorted(aircrafts, key=lambda a: (a["target_finish"], a["total_duration"]))


def sort_positions(positions: list[str], pos_free_at: dict[str, float]) -> list[str]:
    """Sort positions by earliest available time (least loaded first)."""
    return sorted(positions, key=lambda p: pos_free_at[p])


def _grasp_weights(n: int, alpha: float) -> list[float]:
    """Return geometric weights for n candidates: w_i = (1-alpha)^i."""
    return [(1.0 - alpha) ** i for i in range(n)]


def _biased_random_select_logged(
    sorted_list: list,
    weights: list[float],
    rng: random.Random,
) -> tuple[Any, float, int]:
    """Pick one item using pre-computed geometric weights.

    Returns (selected_item, draw_value, rank).
    """
    total = sum(weights)
    draw  = rng.uniform(0, total)
    cumulative = 0.0
    for rank, (item, w) in enumerate(zip(sorted_list, weights)):
        cumulative += w
        if draw <= cumulative:
            return item, draw, rank
    return sorted_list[-1], draw, len(sorted_list) - 1


def biased_random_select(sorted_list: list, alpha: float, rng: random.Random) -> Any:
    """Pick one item with geometric probability: P(rank i) ∝ (1-alpha)^i."""
    weights = _grasp_weights(len(sorted_list), alpha)
    item, _, _ = _biased_random_select_logged(sorted_list, weights, rng)
    return item


# =============================================================================
#  Scheduling helpers
# =============================================================================

def _prepare_aircraft_info(aircrafts: list[dict], jobs_data: list[dict]) -> dict:
    """Build a dict with per-aircraft aggregated data needed for sorting and scheduling."""
    ac_jobs: dict[str, list[dict]] = {}
    for job in jobs_data:
        ac_jobs.setdefault(job["aircraft_id"], []).append(job)

    result = {}
    for ac in aircrafts:
        aid = ac["id"]
        jobs = _ordered_jobs(ac_jobs.get(aid, []))
        total_dur = sum(j["duration"] for j in jobs)
        result[aid] = {
            "id": aid,
            "client": ac.get("client", ""),
            "earliest_start": ac["earliest_start"],
            "target_finish": ac["target_finish"],
            "total_duration": total_dur,
            "jobs": jobs,
        }
    return result


def _ordered_jobs(jobs: list[dict]) -> list[dict]:
    """Return jobs sorted by their natural execution order."""
    if not jobs:
        return []
    first  = [j for j in jobs if j.get("is_first")]
    last   = [j for j in jobs if j.get("is_last") and not j.get("is_first")]
    middle = [j for j in jobs if not j.get("is_first") and not j.get("is_last")]
    return first + middle + last


def _find_no_block_start(
    ac_info: dict,
    pos_id: str,
    pos_free_at: float,
    min_sep: float,
    blocking_arcs: list[dict],
    assigned: list[dict],
    log: list[str] | None = None,
) -> float:
    """Return the earliest start time ≥ pos_free_at (+ sep) that generates no
    additional blockings with already-assigned aircraft.

    Blocking conditions (strict inequalities, matching _count_movements):
      pos_id is rear  (we are rp): b_s < t < b_f  OR  b_s < t+D < b_f
      pos_id is front (we are r):  t < b_s < t+D  OR  t < b_f < t+D

    Windows considered per conflict:
      Window 2 (front_blockers, departure-only): t = b_f − D  when b_f−D ≤ b_s
      Window 3 (always): t = b_f
      Window b_s (rear_blockees, arrival-only): t = b_s
    """
    D   = ac_info["total_duration"]
    sep = min_sep if pos_free_at > 0 else 0.0
    t   = max(ac_info["earliest_start"], pos_free_at + sep)

    front_blockers: list[dict] = []
    rear_blockees:  list[dict] = []
    for arc in blocking_arcs:
        if arc["rear"] == pos_id:
            front_blockers.extend(a for a in assigned if a["position"] == arc["front"])
        if arc["front"] == pos_id:
            rear_blockees.extend(a for a in assigned if a["position"] == arc["rear"])

    if log is not None and (front_blockers or rear_blockees):
        log.append("")
        log.append(f"  Blocking search  {ac_info['id']} → {pos_id}  (D={D:.2f}):")
        log.append(
            f"    t_initial = max(earliest={ac_info['earliest_start']:.2f},"
            f" free_at+sep={pos_free_at:.2f}+{sep:.2f}) = {t:.2f}"
        )
        if front_blockers:
            log.append("    Front blockers (we are rear):")
            for b in front_blockers:
                log.append(
                    f"      {b['id']} @ {b['position']}"
                    f"  [{b['start']:.2f}, {b['finish']:.2f}]"
                )
        if rear_blockees:
            log.append("    Rear blockees (we are front):")
            for b in rear_blockees:
                log.append(
                    f"      {b['id']} @ {b['position']}"
                    f"  [{b['start']:.2f}, {b['finish']:.2f}]"
                )

    for iteration in range(2 * len(assigned) + 1):
        t_f      = t + D
        delay_to = t

        for b in front_blockers:
            b_s, b_f = b["start"], b["finish"]
            if b_s < t < b_f:
                delay_to = max(delay_to, b_f)
                if log is not None:
                    log.append(
                        f"    iter {iteration+1}: arrival conflict with {b['id']}"
                        f" [{b_s:.2f},{b_f:.2f}]  t={t:.2f} inside → window 3: delay to {b_f:.2f}"
                    )
            elif b_s < t_f < b_f:
                w2 = b_f - D
                if w2 <= b_s and w2 >= t:
                    delay_to = max(delay_to, w2)
                    if log is not None:
                        log.append(
                            f"    iter {iteration+1}: departure conflict with {b['id']}"
                            f" [{b_s:.2f},{b_f:.2f}]  t_f={t_f:.2f} inside"
                            f" → window 2: delay to {w2:.2f}  (b_f-D={w2:.2f} <= b_s={b_s:.2f})"
                        )
                else:
                    delay_to = max(delay_to, b_f)
                    if log is not None:
                        log.append(
                            f"    iter {iteration+1}: departure conflict with {b['id']}"
                            f" [{b_s:.2f},{b_f:.2f}]  t_f={t_f:.2f} inside"
                            f" → window 3: delay to {b_f:.2f}  (w2={w2:.2f} invalid)"
                        )

        for b in rear_blockees:
            b_s, b_f = b["start"], b["finish"]
            if t < b_f < t_f:
                delay_to = max(delay_to, b_f)
                if log is not None:
                    log.append(
                        f"    iter {iteration+1}: rear {b['id']} departs at {b_f:.2f}"
                        f" inside [{t:.2f},{t_f:.2f}] → delay to {b_f:.2f}"
                    )
            elif t < b_s < t_f:
                delay_to = max(delay_to, b_s)
                if log is not None:
                    log.append(
                        f"    iter {iteration+1}: rear {b['id']} arrives at {b_s:.2f}"
                        f" inside [{t:.2f},{t_f:.2f}] → delay to {b_s:.2f}"
                    )

        if delay_to <= t:
            if log is not None and (front_blockers or rear_blockees):
                log.append(f"    → no conflict at t={t:.2f}  t_start={t:.2f}")
            break
        t = delay_to

    return t


def _find_best_start(
    ac_info: dict,
    pos_id: str,
    pos_free_at: float,
    min_sep: float,
    blocking_arcs: list[dict],
    assigned: list[dict],
    params: dict,
    ac_target: float,
    current_movs: int,
    log: list[str] | None = None,
) -> float:
    """Return the start time that minimises local objective cost.

    Compares:
      - t_no_block : delay until no new blockings occur (current behaviour)
      - t_immediate: start as soon as the position is free, accepting blockings

    The option with lower estimated cost wins.
    """
    D     = ac_info["total_duration"]
    sep   = min_sep if pos_free_at > 0 else 0.0
    t_imm = max(ac_info["earliest_start"], pos_free_at + sep)
    t_nob = _find_no_block_start(
        ac_info, pos_id, pos_free_at, min_sep, blocking_arcs, assigned, log=None
    )

    w_delay = params.get("weight_delay",     100.0)
    w_make  = params.get("weight_makespan",   10.0)
    w_mov   = params.get("weight_movements",  1.0)

    def _cost(t_s: float, extra_movs: int) -> float:
        t_f   = t_s + D
        delay = max(0.0, t_f - ac_target)
        return w_delay * delay + w_make * t_f + w_mov * extra_movs * 2

    # Count extra movements if we start at t_imm (may create blockings)
    test_imm = assigned + [{"id": ac_info["id"], "position": pos_id,
                             "start": t_imm, "finish": t_imm + D}]
    movs_imm = _count_movements(test_imm, blocking_arcs) - current_movs
    movs_imm = max(0, movs_imm)

    cost_imm = _cost(t_imm, movs_imm)
    cost_nob = _cost(t_nob, 0)

    if log is not None and abs(t_imm - t_nob) > 1e-6:
        log.append(
            f"  start-time compare  {ac_info['id']} → {pos_id}:"
            f"  t_imm={t_imm:.2f} cost={cost_imm:.2f} ({movs_imm} new movs)"
            f"  vs  t_nob={t_nob:.2f} cost={cost_nob:.2f}"
        )

    return t_imm if cost_imm <= cost_nob else t_nob


def _local_search_reassign(
    solution: dict,
    instance: dict,
    params: dict,
    log: list[str] | None = None,
) -> dict:
    """Improve *solution* by trying to move each aircraft to a better position.

    For each aircraft, tries placing it in every other position (appended at the
    end of that position's queue) and keeps the move if the total objective
    improves.  Repeats until a full pass produces no improvement.
    """
    min_sep    = params["min_separation"]
    blocking_arcs = instance["hangar"]["blocking_arcs"]
    positions  = instance["hangar"]["positions"]
    aircrafts  = {a["id"]: a for a in instance["aircrafts"]}
    jobs_data  = {j["id"]: j for j in instance["jobs"]}

    # Flatten aircraft info from _prepare_aircraft_info format
    ac_info_map = _prepare_aircraft_info(instance["aircrafts"], instance["jobs"])

    def _rebuild_from_assignments(
        assignments: list[dict],
        custom_order: list[str] | None = None,
    ) -> dict:
        """Given list of {id, position}, rebuild a full solution in position order.

        Parameters
        ----------
        custom_order:
            Optional explicit processing order (list of aircraft IDs). When
            provided, aircraft are scheduled in this sequence instead of being
            sorted by earliest_start. Useful for trying different intra-position
            orderings in local search.
        """
        from collections import defaultdict
        pos_queue: dict[str, list] = defaultdict(list)
        for a in assignments:
            pos_queue[a["position"]].append(a["id"])

        pos_free: dict[str, float] = {p: 0.0 for p in positions}
        ac_target: dict[str, float] = {aid: ac["target_finish"] for aid, ac in ac_info_map.items()}

        scheduled: dict[str, dict] = {}
        if custom_order is not None:
            queue_order = custom_order
        else:
            queue_order = sorted(
                [aid for aids in pos_queue.values() for aid in aids],
                key=lambda aid: ac_info_map[aid]["earliest_start"],
            )
        for aid in queue_order:
            ac = ac_info_map[aid]
            p  = next(a["position"] for a in assignments if a["id"] == aid)
            assigned_so_far = [
                {"id": s["id"], "position": s["position"],
                 "start": s["start"], "finish": s["finish"]}
                for s in scheduled.values()
            ]
            t_s = _find_best_start(
                ac, p, pos_free[p], min_sep, blocking_arcs, assigned_so_far,
                params, ac_target[aid],
                _count_movements(assigned_so_far, blocking_arcs),
                log=None,
            )
            t_f   = t_s + ac["total_duration"]
            delay = max(0.0, t_f - ac_target[aid])
            t = t_s
            job_schedules = []
            for job in ac["jobs"]:
                job_schedules.append({"id": job["id"],
                                      "start": round(t, 4),
                                      "finish": round(t + job["duration"], 4)})
                t += job["duration"]
            pos_free[p] = t_f
            scheduled[aid] = {"id": aid, "position": p,
                               "start": round(t_s, 4), "finish": round(t_f, 4),
                               "delay": round(delay, 4), "jobs": job_schedules}

        aircraft_list = list(scheduled.values())
        makespan    = max(a["finish"] for a in aircraft_list) if aircraft_list else 0.0
        total_delay = sum(a["delay"] for a in aircraft_list)
        movements   = _count_movements(aircraft_list, blocking_arcs)
        return {
            "status":    solution["status"],
            "objective": 0.0,
            "metrics":   {"makespan": round(makespan, 4),
                          "movements": movements,
                          "total_delay": round(total_delay, 4)},
            "aircraft":  aircraft_list,
        }

    best_sol = solution
    best_obj = _objective(solution, params)
    assignments = [{"id": a["id"], "position": a["position"]} for a in solution["aircraft"]]

    if log is not None:
        log.append("")
        log.append("=" * 72)
        log.append(f"  Local search start  obj={best_obj:.2f}")
        log.append("=" * 72)

    improved = True
    while improved:
        improved = False
        for i, ac_assign in enumerate(assignments):
            aid      = ac_assign["id"]
            cur_pos  = ac_assign["position"]
            for new_pos in positions:
                if new_pos == cur_pos:
                    continue
                trial = [a if a["id"] != aid else {"id": aid, "position": new_pos}
                         for a in assignments]
                try:
                    trial_sol = _rebuild_from_assignments(trial)
                    trial_obj = _objective(trial_sol, params)
                except Exception:
                    continue
                if trial_obj < best_obj - 1e-6:
                    if log is not None:
                        log.append(
                            f"  LS move: {aid}  {cur_pos} → {new_pos}"
                            f"  obj {best_obj:.2f} → {trial_obj:.2f}"
                        )
                    best_obj  = trial_obj
                    best_sol  = trial_sol
                    assignments = trial
                    improved  = True
                    break
            if improved:
                break

        if improved:
            continue   # restart while with single-move before trying 2-opt

        # ---- 2-opt: swap positions of two aircraft ---------------------
        for i in range(len(assignments)):
            for j in range(i + 1, len(assignments)):
                pos_i = assignments[i]["position"]
                pos_j = assignments[j]["position"]
                if pos_i == pos_j:
                    continue
                aid_i = assignments[i]["id"]
                aid_j = assignments[j]["id"]
                trial = [
                    {"id": a["id"],
                     "position": pos_j if k == i else (pos_i if k == j else a["position"])}
                    for k, a in enumerate(assignments)
                ]
                try:
                    trial_sol = _rebuild_from_assignments(trial)
                    trial_obj = _objective(trial_sol, params)
                except Exception:
                    continue
                if trial_obj < best_obj - 1e-6:
                    if log is not None:
                        log.append(
                            f"  LS 2-opt swap: {aid_i} {pos_i}<->{pos_j} {aid_j}"
                            f"  obj {best_obj:.2f} -> {trial_obj:.2f}"
                        )
                    best_obj    = trial_obj
                    best_sol    = trial_sol
                    assignments = trial
                    improved    = True
                    break
            if improved:
                break

        if improved:
            continue   # restart while before trying intra-position reordering

        # ---- intra-position adjacent-swap operator ---------------------
        # For each position with ≥2 aircraft, try swapping every pair of
        # adjacent aircraft in the processing order.  O(n) swaps per position
        # instead of O(n!) — fast enough to keep ILS iterations light.
        default_order = sorted(
            [a["id"] for a in assignments],
            key=lambda aid: ac_info_map[aid]["earliest_start"],
        )
        for pos in positions:
            pos_aids = [aid for aid in default_order
                        if any(a["id"] == aid and a["position"] == pos for a in assignments)]
            if len(pos_aids) < 2:
                continue
            pos_aids_set = set(pos_aids)
            for swap_i in range(len(pos_aids) - 1):
                swapped = pos_aids[:]
                swapped[swap_i], swapped[swap_i + 1] = swapped[swap_i + 1], swapped[swap_i]
                swap_iter = iter(swapped)
                custom = [next(swap_iter) if aid in pos_aids_set else aid
                          for aid in default_order]
                try:
                    trial_sol = _rebuild_from_assignments(assignments, custom_order=custom)
                    trial_obj = _objective(trial_sol, params)
                except Exception:
                    continue
                if trial_obj < best_obj - 1e-6:
                    if log is not None:
                        log.append(
                            f"  LS adj-swap {pos}[{swap_i}↔{swap_i+1}]: "
                            f"{pos_aids[swap_i]}<->{pos_aids[swap_i+1]}"
                            f"  obj {best_obj:.2f} -> {trial_obj:.2f}"
                        )
                    best_obj    = trial_obj
                    best_sol    = trial_sol
                    assignments = [{"id": a["id"], "position": a["position"]}
                                   for a in trial_sol["aircraft"]]
                    improved    = True
                    break
            if improved:
                break

    if log is not None:
        log.append(f"  Local search end    obj={best_obj:.2f}")

    return best_sol


def _count_movements(aircraft_solutions: list[dict], blocking_arcs: list[dict]) -> int:
    """Count blocking movements using strict inequality conditions."""
    pos_of: dict[str, str] = {a["id"]: a["position"] for a in aircraft_solutions}
    interval_of: dict[str, tuple[float, float]] = {
        a["id"]: (a["start"], a["finish"]) for a in aircraft_solutions
    }
    total = 0
    for arc in blocking_arcs:
        front, rear = arc["front"], arc["rear"]
        blockers = [aid for aid, p in pos_of.items() if p == front]
        blockees = [aid for aid, p in pos_of.items() if p == rear]
        for r in blockers:
            r_start, r_finish = interval_of[r]
            for rp in blockees:
                rp_start, rp_finish = interval_of[rp]
                if r_start < rp_start < r_finish:
                    total += 2
                if r_start < rp_finish < r_finish:
                    total += 2
    return total


# =============================================================================
#  Log assembly
# =============================================================================

def _assemble_log(
    instance: dict,
    params: dict,
    iter_rows: list[str],
    best_construction: list[str],
    best_iter: int,
    best_obj: float,
) -> list[str]:
    """Assemble the full log: header, iteration summary, best construction detail."""
    instance_name = instance.get("name", "unknown")
    W = 72

    lines: list[str] = []
    lines.append("=" * W)
    lines.append(f"  ConstructiveHeuristic — {instance_name}")
    lines.append("=" * W)
    lines.append(
        f"  alpha={params['alpha']}  time_limit={params['time_limit_s']}s"
        f"  seed={params['seed']}  min_sep={params['min_separation']}"
    )
    lines.append(
        f"  weights: makespan={params['weight_makespan']}  "
        f"delay={params['weight_delay']}  movements={params['weight_movements']}"
    )
    lines.append("")

    # instance summary
    aircrafts = instance["aircrafts"]
    positions = instance["hangar"]["positions"]
    arcs      = instance["hangar"]["blocking_arcs"]
    lines.append(
        f"  Instance: {len(aircrafts)} aircraft  {len(positions)} positions"
        f"  {len(arcs)} blocking arcs"
    )
    arcs_str = "  ".join(f"{a['front']}→{a['rear']}" for a in arcs)
    lines.append(f"  Blocking arcs: {arcs_str or 'none'}")

    lines.append(f"\n{'─'*W}")
    lines.append(f"  Best construction detail  (iter {best_iter}  obj={best_obj:.4f})")
    lines.append(f"{'─'*W}")
    lines.extend(best_construction)

    lines.append(f"\n{'─'*W}")
    lines.append("  Iteration history")
    lines.append(f"{'─'*W}")
    lines.append(
        f"  {'Iter':>8}  {'Time(s)':>8}  {'Obj':>12}  "
        f"{'Makespan':>10}  {'Delay':>10}  {'Mov':>5}"
    )
    lines.append(f"  {'-'*60}")
    lines.extend(iter_rows)
    lines.append(f"  {'-'*60}")

    return lines


# =============================================================================
#  Objective
# =============================================================================

def _objective(solution: dict, params: dict) -> float:
    m = solution["metrics"]
    obj = (
        params["weight_makespan"] * m["makespan"]
        + params["weight_delay"] * m["total_delay"]
        + params["weight_movements"] * m["movements"]
    )
    solution["objective"] = round(obj, 4)
    return obj


# =============================================================================
#  __main__ — standalone debugging
# =============================================================================

if __name__ == "__main__":
    import json
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "input_data"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "output_data"))
    from instance_io import load_json as load_instance       # noqa: E402
    from check_solution import check_solution, print_check  # noqa: E402
    from plot_schedule import plot_schedule                  # noqa: E402

    _root = os.path.join(os.path.dirname(__file__), "..")
    _instance_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(_root, "data", "instances", "scn_few-tight_seed12_P2_pl5.json")
    )

    _raw = load_instance(_instance_path)
    _solver = ConstructiveHeuristic()
    _solver.configure_solver(time_limit_s=10, alpha=0.3, seed=42)
    _sol = _solver.solve(_raw)

    print(json.dumps(_sol, indent=2))
    _report = check_solution(_sol, _raw)
    print_check(_report)
    plot_schedule(_sol)
