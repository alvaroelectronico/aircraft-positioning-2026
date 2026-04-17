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
    app.read_data("data/instance.json")
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
    }

    def __init__(self) -> None:
        self._params: dict = dict(self._DEFAULTS)

    @property
    def name(self) -> str:
        return "constructive"

    def configure_solver(self, **kwargs) -> None:
        for key, value in kwargs.items():
            self._params[key] = value

    def get_config(self) -> dict:
        return dict(self._params)

    def solve(self, instance_data: dict) -> dict:
        rng = random.Random(self._params["seed"])
        time_limit = self._params["time_limit_s"]
        t0 = time.perf_counter()
        deadline = t0 + time_limit
        report_interval = max(1.0, time_limit / 10)  # print up to 10 updates
        next_report = t0 + report_interval

        best_solution: dict | None = None
        best_obj = math.inf
        iterations = 0
        improvements = 0

        print(f"  [constructive] starting  alpha={self._params['alpha']}  "
              f"time_limit={time_limit}s")
        print(f"  {'Iter':>8}  {'Time(s)':>8}  {'Best obj':>12}  "
              f"{'Makespan':>10}  {'Delay':>10}  {'Mov':>5}  {'Improv':>7}")
        print(f"  {'-'*70}")

        while True:
            now = time.perf_counter()
            if now >= deadline:
                break

            sol = _build_solution(instance_data, self._params, rng)
            obj = _objective(sol, self._params)
            iterations += 1

            if obj < best_obj:
                best_obj = obj
                best_solution = sol
                improvements += 1
                m = sol["metrics"]
                elapsed = now - t0
                print(f"  {iterations:>8}  {elapsed:>8.2f}  {best_obj:>12.2f}  "
                      f"{m['makespan']:>10.2f}  {m['total_delay']:>10.2f}  "
                      f"{m['movements']:>5}  {improvements:>7}  *")

            elif now >= next_report:
                m = best_solution["metrics"]
                elapsed = now - t0
                print(f"  {iterations:>8}  {elapsed:>8.2f}  {best_obj:>12.2f}  "
                      f"{m['makespan']:>10.2f}  {m['total_delay']:>10.2f}  "
                      f"{m['movements']:>5}  {improvements:>7}")
                next_report += report_interval

        elapsed_total = time.perf_counter() - t0
        assert best_solution is not None
        print(f"  {'-'*70}")
        print(f"  [constructive] done  iter={iterations}  improvements={improvements}  "
              f"time={elapsed_total:.2f}s  best_obj={best_obj:.2f}")

        best_solution["status"] = f"heuristic ({iterations} iterations)"
        return best_solution


# =============================================================================
#  Core construction
# =============================================================================

def _build_solution(instance: dict, params: dict, rng: random.Random) -> dict:
    """Build one feasible solution via biased-random greedy insertion."""
    alpha = params["alpha"]
    min_sep = params["min_separation"]

    aircrafts = instance["aircrafts"]
    jobs_data = instance["jobs"]
    positions = instance["hangar"]["positions"]
    blocking_arcs = instance["hangar"]["blocking_arcs"]

    # Pre-compute per-aircraft data
    aircraft_info = _prepare_aircraft_info(aircrafts, jobs_data)

    # Sort aircrafts by criterion, then pick in biased-random order
    sorted_ac = sort_aircrafts(list(aircraft_info.values()))
    assignment: dict[str, str] = {}   # aircraft_id -> position_id
    # Track when each position becomes free
    pos_free_at: dict[str, float] = {p: 0.0 for p in positions}

    for _ in range(len(sorted_ac)):
        ac = biased_random_select(sorted_ac, alpha, rng)
        sorted_ac.remove(ac)

        sorted_pos = sort_positions(positions, pos_free_at)
        pos_id = biased_random_select(sorted_pos, alpha, rng)

        assignment[ac["id"]] = pos_id
        finish = _schedule_finish(ac, pos_free_at[pos_id], min_sep)
        pos_free_at[pos_id] = finish

    return _build_solution_dict(instance, assignment, min_sep)


# =============================================================================
#  Sort & selection helpers
# =============================================================================

def sort_aircrafts(aircrafts: list[dict]) -> list[dict]:
    """Sort aircrafts: urgent (earliest target_finish) first, then by total duration."""
    return sorted(aircrafts, key=lambda a: (a["target_finish"], a["total_duration"]))


def sort_positions(positions: list[str], pos_free_at: dict[str, float]) -> list[str]:
    """Sort positions by earliest available time (least loaded first)."""
    return sorted(positions, key=lambda p: pos_free_at[p])


def biased_random_select(sorted_list: list, alpha: float, rng: random.Random) -> Any:
    """Pick one item with geometric probability: P(rank i) ∝ (1-alpha)^i.

    Rank 0 (best) has the highest probability. alpha=0 → always pick rank 0;
    alpha→1 → uniform.
    """
    n = len(sorted_list)
    weights = [(1.0 - alpha) ** i for i in range(n)]
    total = sum(weights)
    r = rng.uniform(0, total)
    cumulative = 0.0
    for item, w in zip(sorted_list, weights):
        cumulative += w
        if r <= cumulative:
            return item
    return sorted_list[-1]


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
    """Return jobs sorted by their natural execution order (is_first first, is_last last,
    others by position derived from precedence chain)."""
    if not jobs:
        return []
    # Simple approach: first → middle (by order they appear) → last
    first = [j for j in jobs if j.get("is_first")]
    last = [j for j in jobs if j.get("is_last")]
    middle = [j for j in jobs if not j.get("is_first") and not j.get("is_last")]
    return first + middle + last


def _schedule_finish(ac_info: dict, pos_free_at: float, min_sep: float) -> float:
    """Return the finish time of the last job if aircraft is placed at a position
    that becomes free at pos_free_at. Separation only applied between aircraft."""
    sep = min_sep if pos_free_at > 0 else 0.0
    start = max(ac_info["earliest_start"], pos_free_at + sep)
    return start + ac_info["total_duration"]


# =============================================================================
#  Solution dict builder
# =============================================================================

def _build_solution_dict(instance: dict, assignment: dict[str, str], min_sep: float) -> dict:
    """Build the full solution dict from an aircraft→position assignment."""
    jobs_data = instance["jobs"]
    aircrafts = instance["aircrafts"]
    ac_jobs: dict[str, list[dict]] = {}
    for job in jobs_data:
        ac_jobs.setdefault(job["aircraft_id"], []).append(job)

    ac_earliest: dict[str, float] = {a["id"]: a["earliest_start"] for a in aircrafts}
    ac_target: dict[str, float] = {a["id"]: a["target_finish"] for a in aircrafts}

    # Find when each position is occupied (to detect blocking — simplified: 0 movements)
    pos_free_at: dict[str, float] = {p: 0.0 for p in instance["hangar"]["positions"]}

    aircraft_solutions = []
    for ac in aircrafts:
        aid = ac["id"]
        pos = assignment[aid]
        jobs = _ordered_jobs(ac_jobs.get(aid, []))

        sep = min_sep if pos_free_at[pos] > 0 else 0.0
        ac_start = max(ac_earliest[aid], pos_free_at[pos] + sep)
        t = ac_start
        job_schedules = []
        for job in jobs:
            job_schedules.append({"id": job["id"], "start": round(t, 4), "finish": round(t + job["duration"], 4)})
            t += job["duration"]

        finish = t
        pos_free_at[pos] = finish
        delay = max(0.0, finish - ac_target[aid])

        aircraft_solutions.append({
            "id": aid,
            "position": pos,
            "start": round(ac_start, 4),
            "finish": round(finish, 4),
            "delay": round(delay, 4),
            "jobs": job_schedules,
        })

    makespan = max((a["finish"] for a in aircraft_solutions), default=0.0)
    total_delay = sum(a["delay"] for a in aircraft_solutions)
    movements = _count_movements(aircraft_solutions, instance["hangar"]["blocking_arcs"])

    return {
        "status": "heuristic",
        "objective": 0.0,   # filled after construction
        "metrics": {
            "makespan": round(makespan, 4),
            "movements": movements,
            "total_delay": round(total_delay, 4),
        },
        "aircraft": aircraft_solutions,
    }


def _count_movements(aircraft_solutions: list[dict], blocking_arcs: list[dict]) -> int:
    """Count blocking movements using the same logic as check_solution (RQ07)."""
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
        else os.path.join(_root, "data", "scn_few-tight_seed12_P2_pl5.json")
    )

    _raw = load_instance(_instance_path)
    _solver = ConstructiveHeuristic()
    _solver.configure_solver(time_limit_s=10, alpha=0.3, seed=42)
    _sol = _solver.solve(_raw)

    print(json.dumps(_sol, indent=2))
    _report = check_solution(_sol, _raw)
    print_check(_report)
    plot_schedule(_sol)
