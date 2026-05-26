"""
LNSSolver — Large Neighbourhood Search for aircraft positioning.

Algorithm
---------
1. Build an initial solution with the ConstructiveHeuristic (time_limit_s=2).
2. Polish it with a light local search (single-move + 2-opt swap).
3. LNS main loop (until time limit):
   a. DESTROY: pick k aircraft (k ∈ [k_min, k_max]) by worst delay or random.
   b. REPAIR:  try every assignment in positions^k (exhaustive, 5^k combos).
   c. ACCEPT:  keep the best repair if it improves the incumbent (greedy).

Usage
-----
    from solvers.lns_solver import LNSSolver
    from aircraft_positioning import Application

    app = Application(solver=LNSSolver())
    app.read_data("data/instances/instance.json")
    app.configure_solver(time_limit_s=60, k_min=2, k_max=4)
    app.solve()
"""
from __future__ import annotations

import math
import os as _os
import random
import sys as _sys
import time
from itertools import product as _product

# Optional sub-MILP repair — direct gurobipy API (fast, no Pyomo overhead)
_GUROBIPY_AVAILABLE = False
_gp = None
_GRB = None
_gurobi_env = None   # reused across calls to avoid per-call startup cost (~0.5 s)
try:
    import gurobipy as _gp
    from gurobipy import GRB as _GRB
    _gurobi_env = _gp.Env(empty=True)
    _gurobi_env.setParam("OutputFlag", 0)
    _gurobi_env.start()
    _GUROBIPY_AVAILABLE = True
except Exception:
    _gurobi_env = None

# Optional sub-MILP repair — Pyomo fallback (slower, kept for compatibility)
_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", "models"))
try:
    from milp_pyomo import model as _abstract_milp_model, prepare_data as _milp_prepare_data
    from pyomo.environ import SolverFactory as _SolverFactory
    _SUBMILP_AVAILABLE = True
except Exception:
    _SUBMILP_AVAILABLE = False

# ALNS reward constants
_ALNS_STRATEGIES = ["worst", "most_blocking", "cluster"]
_ALNS_REWARD_GLOBAL = 3.0   # new global best found
_ALNS_REWARD_LOCAL  = 1.0   # improved current solution (accepted)
_ALNS_REWARD_NONE   = 0.0   # no improvement
_ALNS_DECAY         = 0.85  # weight decay per iteration

from constructive_heuristic import (
    ConstructiveHeuristic,
    _prepare_aircraft_info,
    _find_best_start,
    _count_movements,
    _objective,
    _build_solution,
)


# =============================================================================
#  Public solver class
# =============================================================================

class LNSSolver:
    """Large Neighbourhood Search solver — no external dependencies required."""

    _DEFAULTS: dict = {
        "time_limit_s":     60.0,
        "min_separation":   10.0,
        "weight_makespan":  10.0,
        "weight_delay":     100.0,
        "weight_movements": 1.0,
        "seed":             None,
        "k_min":            2,        # min aircraft destroyed per LNS iteration
        "k_max":            8,        # max aircraft destroyed per LNS iteration
        "k_exact":          4,        # for k ≤ k_exact: exhaustive repair (5^k combos)
                                      # for k >  k_exact: GRASP repair (greedy re-insertion)
        "n_grasp_repair":   12,       # GRASP repair: number of random re-insertions tried
        "destroy":          "alns",    # "worst"|"most_blocking"|"mixed"|"cluster"|"mixed_cluster"|"alns"
        "restart_every":    50,       # restart from new random solution after N no-improve iters
        "repair":           "auto",   # "auto" | "grasp" | "submilp"
        "repair_time_s":    0.2,      # Gurobi budget per sub-MILP repair call (seconds)
        "log_enabled":      False,
    }

    def __init__(self) -> None:
        self._params: dict = dict(self._DEFAULTS)
        self._log_lines: list[str] | None = None

    @property
    def name(self) -> str:
        return "lns"

    def configure_solver(self, **kwargs) -> None:
        for key, value in kwargs.items():
            self._params[key] = value

    def get_config(self) -> dict:
        return dict(self._params)

    def get_log(self) -> list[str] | None:
        return self._log_lines

    # ------------------------------------------------------------------
    def solve(self, instance_data: dict) -> dict:
        # Per-instance epsilon overrides the config fallback.
        if "min_separation" in instance_data:
            self._params["min_separation"] = float(instance_data["min_separation"])
        params      = self._params
        time_limit  = params["time_limit_s"]
        log_enabled = bool(params.get("log_enabled", False))
        rng         = random.Random(params["seed"])

        t0       = time.perf_counter()
        deadline = t0 + time_limit

        positions     = instance_data["hangar"]["positions"]
        blocking_arcs = instance_data["hangar"]["blocking_arcs"]

        report_interval = max(1.0, time_limit / 10)
        next_report = t0 + report_interval

        # ----------------------------------------------------------
        # Step 1: initial solution
        # Priority: warm_solution injected externally (e.g. from TopologyHeuristic)
        # Fallback: fast constructive run capped at init_time seconds
        # ----------------------------------------------------------
        warm_solution = params.get("warm_solution")
        if warm_solution is not None:
            init_sol = warm_solution
            print(f"  [lns] warm start from external solution  obj={_objective(init_sol, params):.2f}")
        else:
            init_time = min(10.0, time_limit * 0.15)
            ch = ConstructiveHeuristic()
            ch.configure_solver(
                time_limit_s     = init_time,
                min_separation   = params["min_separation"],
                weight_makespan  = params["weight_makespan"],
                weight_delay     = params["weight_delay"],
                weight_movements = params["weight_movements"],
                alpha            = 0.7,
                seed             = params["seed"],
                log_enabled      = False,
                ils_ratio        = 0.0,
                ls_every         = 1,
            )
            init_sol = ch.solve(instance_data)
        init_obj_raw = _objective(init_sol, params)
        t_after_init = time.perf_counter()

        # Step 2: bounded local search to polish initial solution.
        # max_passes caps the cost at O(n²·P·cap) rather than unbounded O(n⁴).
        # For R=30 an unbounded LS can consume the entire remaining budget.
        n_ac     = len(instance_data["aircrafts"])
        ls_cap   = max(5, n_ac // 2)
        best_sol = _local_search(init_sol, instance_data, params, max_passes=ls_cap)
        best_obj = _objective(best_sol, params)
        best_assignments = [{"id": a["id"], "position": a["position"]}
                            for a in best_sol["aircraft"]]

        t_after_ls = time.perf_counter()
        print(f"  [lns] constructive init  obj={init_obj_raw:.2f}  t={t_after_init - t0:.2f}s")
        print(f"  [lns] after init LS      obj={best_obj:.2f}  t={t_after_ls - t0:.2f}s  "
              f"budget_remaining={time_limit - (t_after_ls - t0):.1f}s")

        lns_iters   = 0
        improvements = 0
        log_rows: list[str] = []

        # ----------------------------------------------------------
        # Optional: build cached Pyomo concrete instance for sub-MILP repair
        # ----------------------------------------------------------
        repair_strategy = params.get("repair", "auto")
        repair_time_s   = float(params.get("repair_time_s", 0.2))
        _use_gurobi_repair = (
            _GUROBIPY_AVAILABLE and repair_strategy in ("submilp", "auto")
        )
        # Pyomo fallback (only built when gurobipy is NOT available)
        _concrete_cache = None
        _use_submilp    = False
        if not _use_gurobi_repair and _SUBMILP_AVAILABLE and repair_strategy in ("submilp", "auto"):
            try:
                _milp_data = _milp_prepare_data(
                    instance_data,
                    params["min_separation"],
                    params["weight_makespan"],
                    params["weight_delay"],
                    params["weight_movements"],
                )
                _concrete_cache = _abstract_milp_model.create_instance(_milp_data)
                _use_submilp = True
            except Exception as _e:
                print(f"  [lns] Pyomo cache failed ({_e}), falling back to GRASP repair")

        if _use_gurobi_repair:
            print(f"  [lns] sub-MILP repair via gurobipy (repair_time_s={repair_time_s:.2f})")
        elif _use_submilp:
            print(f"  [lns] sub-MILP repair via Pyomo (repair_time_s={repair_time_s:.2f})")

        # Counters for sub-MILP fallback monitoring
        _submilp_calls    = 0
        _submilp_feasible = 0

        # ALNS state — adaptive destroy operator weights
        destroy_strategy = params.get("destroy", "mixed")
        _alns_weights    = {s: 1.0 for s in _ALNS_STRATEGIES}
        _alns_last_strat = _ALNS_STRATEGIES[0]

        print(f"  [lns] initial obj={best_obj:.2f}  positions={positions}")
        print(f"  {'Iter':>8}  {'Time(s)':>8}  {'Best obj':>12}  "
              f"{'Makespan':>10}  {'Delay':>10}  {'Mov':>5}  {'k':>3}  {'Improv':>7}")
        print(f"  {'-'*76}")

        # ----------------------------------------------------------
        # Step 3: LNS main loop
        # ----------------------------------------------------------
        k_min          = int(params.get("k_min", 2))
        k_max          = int(params.get("k_max", 5))
        k_exact        = int(params.get("k_exact", 4))
        n_grasp_repair = int(params.get("n_grasp_repair", 12))
        restart_every  = int(params.get("restart_every", 50))

        # current working solution (may differ from global best after a restart)
        cur_sol         = best_sol
        cur_assignments = best_assignments[:]
        iters_no_improve = 0

        while True:
            now = time.perf_counter()
            if now >= deadline:
                break

            elapsed = now - t0

            # ---- RESTART when stuck ------------------------------------
            if iters_no_improve >= restart_every:
                remaining = deadline - now
                init_time2 = min(3.0, remaining * 0.10)
                if init_time2 > 0.1:
                    ch2 = ConstructiveHeuristic()
                    ch2.configure_solver(
                        time_limit_s=init_time2,
                        min_separation=params["min_separation"],
                        weight_makespan=params["weight_makespan"],
                        weight_delay=params["weight_delay"],
                        weight_movements=params["weight_movements"],
                        alpha=0.7, seed=None, log_enabled=False,
                        ils_ratio=0.0, ls_every=1,
                    )
                    restart_raw = ch2.solve(instance_data)
                    cur_sol = _local_search(restart_raw, instance_data, params, max_passes=ls_cap)
                    cur_assignments = [{"id": a["id"], "position": a["position"]}
                                       for a in cur_sol["aircraft"]]
                    # promote restart solution if it beats the global best
                    restart_obj = _objective(cur_sol, params)
                    if restart_obj < best_obj - 1e-6:
                        best_obj  = restart_obj
                        best_sol  = cur_sol
                        best_assignments = cur_assignments[:]
                iters_no_improve = 0

            k = rng.randint(k_min, k_max)

            # ---- DESTROY -----------------------------------------------
            # ALNS: roulette-select destroy operator using adaptive weights
            if destroy_strategy == "alns":
                _total_w = sum(_alns_weights.values())
                _rv = rng.uniform(0.0, _total_w)
                _cum = 0.0
                _alns_last_strat = _ALNS_STRATEGIES[0]
                for _s in _ALNS_STRATEGIES:
                    _cum += _alns_weights[_s]
                    if _cum >= _rv:
                        _alns_last_strat = _s
                        break
                _effective_destroy = _alns_last_strat
            else:
                _effective_destroy = destroy_strategy

            removed_ids  = _destroy(cur_sol, k, _effective_destroy, rng, blocking_arcs)
            fixed        = [a for a in cur_assignments if a["id"] not in removed_ids]
            removed_list = [a for a in cur_assignments if a["id"] in removed_ids]

            # ---- REPAIR ------------------------------------------------
            repair_best_obj  = math.inf
            repair_best_assg = None

            def _grasp_repair():
                """GRASP repair inline helper — re-inserts removed aircraft."""
                nonlocal repair_best_obj, repair_best_assg
                warm = {a["id"]: a["position"] for a in fixed}
                for _ in range(n_grasp_repair):
                    try:
                        trial_sol = _build_solution(instance_data, params, rng,
                                                    warm_assignments=warm)
                        trial_assg = [{"id": a["id"], "position": a["position"]}
                                      for a in trial_sol["aircraft"]]
                        trial_obj  = _objective(trial_sol, params)
                    except Exception:
                        continue
                    if trial_obj < repair_best_obj:
                        repair_best_obj  = trial_obj
                        repair_best_assg = trial_assg

            if k <= k_exact:
                # Exhaustive: try all positions^k combinations
                for pos_combo in _product(positions, repeat=k):
                    trial_extra = [{"id": removed_list[i]["id"], "position": pos_combo[i]}
                                   for i in range(k)]
                    trial_assg  = fixed + trial_extra
                    try:
                        trial_sol = _rebuild(trial_assg, instance_data, params)
                        trial_obj = _objective(trial_sol, params)
                    except Exception:
                        continue
                    if trial_obj < repair_best_obj:
                        repair_best_obj  = trial_obj
                        repair_best_assg = trial_assg
            elif _use_gurobi_repair:
                # Fast exact repair via direct gurobipy API (no Pyomo overhead)
                _submilp_calls += 1
                submilp_sol = _sub_milp_repair_gurobi(
                    list(removed_ids), cur_sol, instance_data, params, repair_time_s,
                )
                if submilp_sol is not None:
                    _submilp_feasible += 1
                    repair_best_obj  = _objective(submilp_sol, params)
                    repair_best_assg = [{"id": a["id"], "position": a["position"]}
                                        for a in submilp_sol["aircraft"]]
                else:
                    _grasp_repair()
            elif _use_submilp and _concrete_cache is not None:
                # Pyomo fallback
                _submilp_calls += 1
                submilp_sol = _sub_milp_repair(
                    list(removed_ids), cur_sol, instance_data, params,
                    _concrete_cache, repair_time_s,
                )
                if submilp_sol is not None:
                    _submilp_feasible += 1
                    repair_best_obj  = _objective(submilp_sol, params)
                    repair_best_assg = [{"id": a["id"], "position": a["position"]}
                                        for a in submilp_sol["aircraft"]]
                else:
                    _grasp_repair()
            else:
                _grasp_repair()

            lns_iters += 1

            # ---- ACCEPT -----------------------------------------------
            # IMPORTANT: compare the rebuilt schedule quality (not the trial
            # quality) against cur_sol.  trial quality (repair_best_obj) may
            # come from _build_solution which optimises timing; _rebuild uses a
            # greedy scheduler that can produce a different (possibly worse)
            # objective from the same position assignment.  Using trial quality
            # for acceptance but storing rebuild quality in cur_sol would cause
            # cur_sol to degrade silently over many iterations.
            if repair_best_assg is not None:
                repaired_sol = _rebuild(repair_best_assg, instance_data, params)
                repaired_obj = _objective(repaired_sol, params)
                cur_obj      = _objective(cur_sol, params)

                if repaired_obj < cur_obj - 1e-6:
                    cur_sol         = repaired_sol
                    cur_assignments = [{"id": a["id"], "position": a["position"]}
                                       for a in cur_sol["aircraft"]]

                    if repaired_obj < best_obj - 1e-6:
                        # Global best — invest in a convergent local search
                        polished_sol = _local_search(repaired_sol, instance_data, params)
                        polished_obj = _objective(polished_sol, params)
                        cur_sol         = polished_sol
                        cur_assignments = [{"id": a["id"], "position": a["position"]}
                                           for a in cur_sol["aircraft"]]
                        best_obj         = polished_obj
                        best_sol         = polished_sol
                        best_assignments = cur_assignments[:]
                        improvements     += 1
                        iters_no_improve = 0
                        if destroy_strategy == "alns":
                            _alns_weights[_alns_last_strat] = (
                                (1 - _ALNS_DECAY) * _alns_weights[_alns_last_strat]
                                + _ALNS_DECAY * _ALNS_REWARD_GLOBAL
                            )
                        m   = best_sol["metrics"]
                        tag = "  *"
                        print(f"  {lns_iters:>8}  {elapsed:>8.2f}  {best_obj:>12.2f}  "
                              f"{m['makespan']:>10.2f}  {m['total_delay']:>10.2f}  "
                              f"{m['movements']:>5}  {k:>3}  {improvements:>7}{tag}")
                        if log_enabled:
                            log_rows.append(
                                f"  iter={lns_iters}  t={elapsed:.2f}s  k={k}"
                                f"  obj={best_obj:.2f}  makespan={m['makespan']:.2f}"
                                f"  delay={m['total_delay']:.2f}  mov={m['movements']}  *"
                            )
                        next_report = now + report_interval
                    else:
                        iters_no_improve += 1
                        if destroy_strategy == "alns":
                            _alns_weights[_alns_last_strat] = (
                                (1 - _ALNS_DECAY) * _alns_weights[_alns_last_strat]
                                + _ALNS_DECAY * _ALNS_REWARD_LOCAL
                            )
                else:
                    iters_no_improve += 1
                    if destroy_strategy == "alns":
                        _alns_weights[_alns_last_strat] = (
                            (1 - _ALNS_DECAY) * _alns_weights[_alns_last_strat]
                            + _ALNS_DECAY * _ALNS_REWARD_NONE
                        )
            else:
                iters_no_improve += 1
                if destroy_strategy == "alns":
                    _alns_weights[_alns_last_strat] = (
                        (1 - _ALNS_DECAY) * _alns_weights[_alns_last_strat]
                        + _ALNS_DECAY * _ALNS_REWARD_NONE
                    )
                if now >= next_report:
                    m = best_sol["metrics"]
                    print(f"  {lns_iters:>8}  {elapsed:>8.2f}  {best_obj:>12.2f}  "
                          f"{m['makespan']:>10.2f}  {m['total_delay']:>10.2f}  "
                          f"{m['movements']:>5}  {k:>3}  {improvements:>7}")
                    next_report += report_interval

        elapsed_total = time.perf_counter() - t0
        print(f"  {'-'*76}")
        print(f"  [lns] done  iters={lns_iters}  improvements={improvements}"
              f"  time={elapsed_total:.2f}s  best_obj={best_obj:.2f}")
        if _submilp_calls > 0:
            feasible_pct = 100.0 * _submilp_feasible / _submilp_calls
            fallback_n   = _submilp_calls - _submilp_feasible
            print(f"  [lns] sub-MILP calls={_submilp_calls}  feasible={_submilp_feasible}"
                  f" ({feasible_pct:.0f}%)  fallback_grasp={fallback_n}")
            if feasible_pct < 50:
                print(f"  [lns] WARNING: sub-MILP feasibility rate {feasible_pct:.0f}% < 50% — "
                      f"consider reducing k_max or increasing repair_time_s")
        if destroy_strategy == "alns":
            w_str = "  ".join(f"{s}={_alns_weights[s]:.2f}" for s in _ALNS_STRATEGIES)
            print(f"  [lns] ALNS final weights: {w_str}")

        best_sol["status"] = f"lns ({lns_iters} iterations)"

        if log_enabled:
            self._log_lines = _assemble_log(
                instance_data, params, log_rows, best_obj,
                best_sol, lns_iters, improvements,
            )
        else:
            self._log_lines = None

        return best_sol


# =============================================================================
#  LNS helpers
# =============================================================================

def _blocking_score(solution: dict, blocking_arcs: list[dict]) -> dict[str, int]:
    """Return {aircraft_id: count of active blocking arcs it participates in}.

    A blocking arc (front_pos, rear_pos) is active when the aircraft in
    front_pos and the aircraft in rear_pos have overlapping schedules.
    """
    # Group aircraft by position (multiple aircraft may share a position sequentially)
    by_pos: dict[str, list[dict]] = {}
    for a in solution["aircraft"]:
        by_pos.setdefault(a["position"], []).append(a)

    score: dict[str, int] = {a["id"]: 0 for a in solution["aircraft"]}

    for arc in blocking_arcs:
        front_pos = arc["front"]
        rear_pos  = arc["rear"]
        fronts = by_pos.get(front_pos, [])
        rears  = by_pos.get(rear_pos, [])
        for f in fronts:
            for r in rears:
                # Active block: the two aircraft overlap in time
                if f["start"] < r["finish"] and r["start"] < f["finish"]:
                    score[f["id"]] += 1
                    score[r["id"]] += 1
    return score


def _destroy(
    solution: dict,
    k: int,
    strategy: str,
    rng: random.Random,
    blocking_arcs: list[dict] | None = None,
) -> set[str]:
    """Select k aircraft IDs to remove from the current solution.

    Strategies
    ----------
    "worst"         : aircraft with the largest individual delay
    "most_blocking" : aircraft most involved in active blocking arcs
    "mixed"         : "most_blocking" when total_delay ≈ 0, else "worst"
    "random"        : uniform random selection
    "cluster"       : space-time cluster around a bottleneck seed
    "mixed_cluster" : "cluster" when total_delay > 0, else "most_blocking"
    """
    aircraft    = solution["aircraft"]
    total_delay = solution["metrics"]["total_delay"]

    if strategy == "mixed":
        strategy = "most_blocking" if total_delay < 1e-6 else "worst"
    elif strategy == "mixed_cluster":
        strategy = "most_blocking" if total_delay < 1e-6 else "cluster"

    if strategy == "cluster" and blocking_arcs:
        return _cluster_destroy(solution, k, rng, blocking_arcs)

    pool_size = max(k * 2, k + 3)

    if strategy == "worst":
        by_delay  = sorted(aircraft, key=lambda a: a["delay"], reverse=True)
        shuffled  = by_delay[:pool_size]
        rng.shuffle(shuffled)
        chosen = shuffled[:k]

    elif strategy == "most_blocking" and blocking_arcs:
        scores   = _blocking_score(solution, blocking_arcs)
        by_score = sorted(aircraft, key=lambda a: scores.get(a["id"], 0), reverse=True)
        pool     = by_score[:pool_size]
        rng.shuffle(pool)
        chosen   = pool[:k]

    else:
        chosen = rng.sample(aircraft, k)

    return {a["id"] for a in chosen}


def _cluster_destroy(
    solution: dict,
    k: int,
    rng: random.Random,
    blocking_arcs: list[dict],
) -> set[str]:
    """Space-time cluster destroy operator.

    Selects k aircraft that form a real spatio-temporal bottleneck:

    1. SEED — roulette-select one aircraft biased toward high delay and
       high blocking score.
    2. SPATIAL expansion — collect all positions directly connected to the
       seed's position via the blocking-arc graph (both upstream and
       downstream neighbours).
    3. TEMPORAL expansion — find all aircraft in the spatial cluster whose
       stay overlaps with the seed's time window, extended by a margin equal
       to half the average aircraft duration.
    4. RANK & SELECT — within the candidate set, rank by combined delay +
       blocking score and take the top k.  If the cluster is smaller than k,
       fill the remainder with the highest-delay aircraft outside the cluster.
    """
    aircraft      = solution["aircraft"]
    block_scores  = _blocking_score(solution, blocking_arcs)

    # ---- 1. Roulette seed selection -----------------------------------
    # Weight = (delay + 1) * (blocking_score + 1) so every aircraft has
    # a positive weight even when delay = 0 and score = 0.
    weights = [(a["delay"] + 1.0) * (block_scores.get(a["id"], 0) + 1.0)
               for a in aircraft]
    total_w = sum(weights)
    r_val   = rng.uniform(0.0, total_w)
    cumul   = 0.0
    seed    = aircraft[-1]
    for ac, w in zip(aircraft, weights):
        cumul += w
        if cumul >= r_val:
            seed = ac
            break

    # ---- 2. Spatial cluster: direct neighbours in the blocking graph --
    p_seed    = seed["position"]
    spatial   = {p_seed}
    for arc in blocking_arcs:
        if arc["front"] == p_seed:
            spatial.add(arc["rear"])
        if arc["rear"] == p_seed:
            spatial.add(arc["front"])

    # ---- 3. Temporal window ------------------------------------------
    avg_dur    = sum(a["finish"] - a["start"] for a in aircraft) / len(aircraft)
    margin     = avg_dur * 0.5
    t_lo       = seed["start"]  - margin
    t_hi       = seed["finish"] + margin

    candidates = [
        a for a in aircraft
        if a["position"] in spatial
        and a["start"] < t_hi
        and a["finish"] > t_lo
    ]
    # Guarantee seed is always included
    seed_ids = {a["id"] for a in candidates}
    if seed["id"] not in seed_ids:
        candidates.append(seed)

    # ---- 4. Rank candidates by delay + blocking score, take top k -----
    candidates.sort(
        key=lambda a: (a["delay"] + block_scores.get(a["id"], 0)),
        reverse=True,
    )
    chosen = candidates[:k]

    # Fill remainder from worst-delay aircraft outside the cluster
    if len(chosen) < k:
        chosen_ids = {a["id"] for a in chosen}
        extras = sorted(
            [a for a in aircraft if a["id"] not in chosen_ids],
            key=lambda a: a["delay"],
            reverse=True,
        )
        chosen += extras[: k - len(chosen)]

    return {a["id"] for a in chosen}


def _rebuild(
    assignments: list[dict],
    instance: dict,
    params: dict,
    order: list[str] | None = None,
) -> dict:
    """Rebuild a complete solution from a list of {id, position} dicts.

    Aircraft are processed in global earliest_start order by default.
    Pass an explicit *order* list of IDs to override (used by the
    intra-position adjacent-swap operator in local search).
    """
    min_sep       = params["min_separation"]
    blocking_arcs = instance["hangar"]["blocking_arcs"]
    positions     = instance["hangar"]["positions"]

    ac_info   = _prepare_aircraft_info(instance["aircrafts"], instance["jobs"])
    ac_target = {a["id"]: a["target_finish"] for a in instance["aircrafts"]}

    pos_free: dict[str, float] = {p: 0.0 for p in positions}
    scheduled: dict[str, dict] = {}

    # Process in provided order, or fall back to earliest_start order
    if order is None:
        order = sorted(
            [a["id"] for a in assignments],
            key=lambda aid: ac_info[aid]["earliest_start"],
        )
    pos_of = {a["id"]: a["position"] for a in assignments}

    for aid in order:
        ac  = ac_info[aid]
        p   = pos_of[aid]
        assigned_so_far = [
            {"id": s["id"], "position": s["position"],
             "start": s["start"], "finish": s["finish"]}
            for s in scheduled.values()
        ]
        current_movs = _count_movements(assigned_so_far, blocking_arcs)
        t_s = _find_best_start(
            ac, p, pos_free[p], min_sep, blocking_arcs, assigned_so_far,
            params, ac_target[aid], current_movs, log=None,
        )
        t_f   = t_s + ac["total_duration"]
        delay = max(0.0, t_f - ac_target[aid])

        t = t_s
        job_schedules = []
        for job in ac["jobs"]:
            job_schedules.append({
                "id":     job["id"],
                "start":  round(t, 4),
                "finish": round(t + job["duration"], 4),
            })
            t += job["duration"]

        pos_free[p] = t_f
        scheduled[aid] = {
            "id":       aid,
            "position": p,
            "start":    round(t_s, 4),
            "finish":   round(t_f, 4),
            "delay":    round(delay, 4),
            "jobs":     job_schedules,
        }

    aircraft_list = list(scheduled.values())
    makespan    = max(a["finish"] for a in aircraft_list) if aircraft_list else 0.0
    total_delay = sum(a["delay"] for a in aircraft_list)
    movements   = _count_movements(aircraft_list, blocking_arcs)

    return {
        "status":   "lns",
        "objective": 0.0,
        "metrics": {
            "makespan":    round(makespan, 4),
            "movements":   movements,
            "total_delay": round(total_delay, 4),
        },
        "aircraft": aircraft_list,
    }


def _local_search(
    solution: dict,
    instance: dict,
    params: dict,
    max_passes: int = 0,
) -> dict:
    """Light local search: single-move and 2-opt swap operators.

    Runs until no operator finds improvement (local optimum).
    If max_passes > 0, stops after that many non-improving passes.
    """
    positions = instance["hangar"]["positions"]

    assignments = [{"id": a["id"], "position": a["position"]}
                   for a in solution["aircraft"]]
    best_sol = solution
    best_obj = _objective(solution, params)

    passes = 0
    max_iters = max_passes if max_passes > 0 else 10_000
    improved = True
    while improved and passes < max_iters:
        improved = False

        # ---- single-move: reassign one aircraft to a different position ----
        for i, ac_a in enumerate(assignments):
            aid     = ac_a["id"]
            cur_pos = ac_a["position"]
            for new_pos in positions:
                if new_pos == cur_pos:
                    continue
                trial = [a if a["id"] != aid
                         else {"id": aid, "position": new_pos}
                         for a in assignments]
                try:
                    trial_sol = _rebuild(trial, instance, params)
                    trial_obj = _objective(trial_sol, params)
                except Exception:
                    continue
                if trial_obj < best_obj - 1e-6:
                    best_obj    = trial_obj
                    best_sol    = trial_sol
                    assignments = trial
                    improved    = True
                    break
            if improved:
                break

        if improved:
            continue

        # ---- 2-opt: swap positions of two aircraft ----------------------
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
                     "position": pos_j if ki == i else (pos_i if ki == j
                                                        else a["position"])}
                    for ki, a in enumerate(assignments)
                ]
                try:
                    trial_sol = _rebuild(trial, instance, params)
                    trial_obj = _objective(trial_sol, params)
                except Exception:
                    continue
                if trial_obj < best_obj - 1e-6:
                    best_obj    = trial_obj
                    best_sol    = trial_sol
                    assignments = trial
                    improved    = True
                    break
            if improved:
                break

        passes += 1

    return best_sol


def _sub_milp_repair_gurobi(
    free_ids: list[str],
    current_solution: dict,
    instance_data: dict,
    params: dict,
    repair_time_s: float = 0.2,
) -> dict | None:
    """Compact gurobipy sub-MILP repair — no Pyomo overhead.

    Builds a fresh gurobipy model for the k free aircraft only.
    Fixed aircraft appear as time-window constraints on position occupancy.
    Construction takes milliseconds; viable even for R=30.

    Blocking movements are not penalised in the subproblem objective
    (they are counted from the combined solution after the fact).
    """
    if not _GUROBIPY_AVAILABLE:
        return None

    free_set   = set(free_ids)
    fixed_by_id = {a["id"]: a for a in current_solution["aircraft"]
                   if a["id"] not in free_set}
    positions     = instance_data["hangar"]["positions"]
    blocking_arcs = instance_data["hangar"]["blocking_arcs"]
    min_sep = params["min_separation"]
    w_M     = params.get("weight_makespan", 0.1)
    w_D     = params.get("weight_delay",    1.0)

    ac_info       = _prepare_aircraft_info(instance_data["aircrafts"], instance_data["jobs"])
    target_finish = {a["id"]: a["target_finish"] for a in instance_data["aircrafts"]}

    BIG_M = (max(target_finish.values())
             + sum(j["duration"] for j in instance_data["jobs"]))

    # Fixed aircraft time intervals per position
    pos_fixed: dict[str, list[tuple[float, float]]] = {p: [] for p in positions}
    for f in fixed_by_id.values():
        pos_fixed[f["position"]].append((f["start"], f["finish"]))

    mdl = None
    try:
        mdl = _gp.Model(env=_gurobi_env)  # reuse cached env — no per-call startup cost
        mdl.setParam("TimeLimit",    repair_time_s)
        mdl.setParam("MIPGap",       0.0)
        mdl.setParam("MIPFocus",     1)   # emphasise feasibility

        # --- Decision variables -----------------------------------------
        x    = {(r, p): mdl.addVar(vtype=_GRB.BINARY)
                for r in free_ids for p in positions}
        t_s  = {r: mdl.addVar(lb=ac_info[r]["earliest_start"])  for r in free_ids}
        t_f  = {r: mdl.addVar(lb=0.0)                           for r in free_ids}
        dly  = {r: mdl.addVar(lb=0.0)                           for r in free_ids}
        max_fixed_finish = max((f["finish"] for f in fixed_by_id.values()), default=0.0)
        makespan = mdl.addVar(lb=max_fixed_finish)
        mdl.update()

        # --- Constraints ------------------------------------------------
        for r in free_ids:
            # Each free aircraft assigned to exactly one position
            mdl.addConstr(_gp.quicksum(x[r, p] for p in positions) == 1)
            D = ac_info[r]["total_duration"]
            # Finish time definition
            mdl.addConstr(t_f[r] == t_s[r] + D)
            # Delay
            mdl.addConstr(dly[r] >= t_f[r] - target_finish[r])
            # Makespan
            mdl.addConstr(makespan >= t_f[r])

        # Non-overlap: free aircraft vs fixed aircraft at same position
        for r in free_ids:
            for p in positions:
                for (fs, ff) in pos_fixed[p]:
                    o = mdl.addVar(vtype=_GRB.BINARY)   # 1 → r finishes before f starts
                    mdl.addConstr(
                        t_f[r] + min_sep
                        <= fs + BIG_M * (1 - o) + BIG_M * (1 - x[r, p])
                    )
                    mdl.addConstr(
                        ff + min_sep
                        <= t_s[r] + BIG_M * o + BIG_M * (1 - x[r, p])
                    )

        # Non-overlap: free aircraft vs free aircraft at same position
        free_list = list(free_ids)
        for i in range(len(free_list)):
            for j in range(i + 1, len(free_list)):
                r1, r2 = free_list[i], free_list[j]
                for p in positions:
                    o = mdl.addVar(vtype=_GRB.BINARY)   # 1 → r1 before r2
                    mdl.addConstr(
                        t_f[r1] + min_sep
                        <= t_s[r2]
                        + BIG_M * (1 - o)
                        + BIG_M * (1 - x[r1, p])
                        + BIG_M * (1 - x[r2, p])
                    )
                    mdl.addConstr(
                        t_f[r2] + min_sep
                        <= t_s[r1]
                        + BIG_M * o
                        + BIG_M * (1 - x[r1, p])
                        + BIG_M * (1 - x[r2, p])
                    )

        # --- Objective --------------------------------------------------
        fixed_delay_sum = sum(f["delay"] for f in fixed_by_id.values())
        mdl.setObjective(
            w_M * makespan
            + w_D * (_gp.quicksum(dly[r] for r in free_ids) + fixed_delay_sum),
            _GRB.MINIMIZE,
        )

        mdl.optimize()

        if mdl.SolCount == 0:
            return None

        # --- Extract free aircraft results ------------------------------
        free_part = []
        for r in free_ids:
            p  = next(pp for pp in positions if x[r, pp].X > 0.5)
            ts = round(t_s[r].X, 4)
            tf = round(t_f[r].X, 4)
            d  = round(max(0.0, tf - target_finish[r]), 4)
            t  = ts
            jobs = []
            for job in ac_info[r]["jobs"]:
                jobs.append({"id": job["id"],
                             "start":  round(t, 4),
                             "finish": round(t + job["duration"], 4)})
                t += job["duration"]
            free_part.append({"id": r, "position": p,
                               "start": ts, "finish": tf, "delay": d, "jobs": jobs})

        # --- Combine and recompute metrics ------------------------------
        fixed_part   = [a for a in current_solution["aircraft"]
                        if a["id"] not in free_set]
        all_aircraft = fixed_part + free_part
        mk = max(a["finish"] for a in all_aircraft)
        td = sum(a["delay"]  for a in all_aircraft)
        mv = _count_movements(all_aircraft, blocking_arcs)

        return {
            "status":    "lns_submilp",
            "objective": 0.0,
            "metrics": {
                "makespan":    round(mk, 4),
                "movements":   mv,
                "total_delay": round(td, 4),
            },
            "aircraft": all_aircraft,
        }

    except Exception:
        return None

    finally:
        try:
            if mdl is not None:
                mdl.dispose()
        except Exception:
            pass


def _sub_milp_repair(
    free_ids: list[str],
    current_solution: dict,
    instance_data: dict,
    params: dict,
    concrete,
    repair_time_s: float = 3.0,
) -> dict | None:
    """Fix the non-destroyed aircraft in the Pyomo concrete model and solve for
    the free aircraft exactly with Gurobi.

    Returns the combined solution (fixed + free) or None if Gurobi finds no
    feasible solution within the time budget.  Always leaves *concrete* fully
    unfixed (via a finally block).
    """
    positions     = list(concrete.sPositions)
    blocking_arcs = instance_data["hangar"]["blocking_arcs"]
    free_set      = set(free_ids)

    fixed_ac = {a["id"]: a for a in current_solution["aircraft"]
                if a["id"] not in free_set}

    # Build job → aircraft map from the Pyomo instance
    job_aircraft: dict[str, str] = {}
    for j in concrete.sJobs:
        for r in concrete.sAircraft:
            if concrete.pJobAircraft[j, r] == 1:
                job_aircraft[j] = r
                break

    try:
        # ---- FIX non-free aircraft ----------------------------------------
        for r, a_data in fixed_ac.items():
            p_r = a_data["position"]
            concrete.vAircraftStart[r].fix(a_data["start"])
            concrete.vAircraftFinish[r].fix(a_data["finish"])
            for p in positions:
                concrete.vAircraftPosition[r, p].fix(1 if p == p_r else 0)

            job_lookup = {jd["id"]: jd for jd in a_data["jobs"]}
            for j in concrete.sJobs:
                if job_aircraft.get(j) != r:
                    continue
                jd = job_lookup[j]
                concrete.vStartTime[j].fix(jd["start"])
                concrete.vFinishTime[j].fix(jd["finish"])
                for p in positions:
                    concrete.vJobPosition[j, p].fix(1 if p == p_r else 0)

        # ---- SOLVE --------------------------------------------------------
        solver = _SolverFactory("gurobi")
        solver.options["TimeLimit"]    = repair_time_s
        solver.options["MIPGap"]       = 0.0
        solver.options["LogToConsole"] = 0
        result = solver.solve(concrete, tee=False)

        tc = str(result.solver.termination_condition)
        if tc not in ("optimal", "feasible"):
            return None

        # ---- EXTRACT free aircraft results --------------------------------
        free_part = []
        for r in free_ids:
            p = next(
                (p for p in positions if concrete.vAircraftPosition[r, p]() > 0.5),
                None,
            )
            if p is None:
                return None
            t_s   = round(concrete.vAircraftStart[r](), 4)
            t_f   = round(concrete.vAircraftFinish[r](), 4)
            t_fin = float(concrete.pTargetFinish[r])
            delay = round(max(0.0, t_f - t_fin), 4)
            jobs  = [
                {
                    "id":     j,
                    "start":  round(concrete.vStartTime[j](),  4),
                    "finish": round(concrete.vFinishTime[j](), 4),
                }
                for j in concrete.sJobs
                if job_aircraft.get(j) == r
            ]
            free_part.append({
                "id":       r,
                "position": p,
                "start":    t_s,
                "finish":   t_f,
                "delay":    delay,
                "jobs":     jobs,
            })

        # ---- COMBINE & RECOMPUTE METRICS ----------------------------------
        fixed_part  = [a for a in current_solution["aircraft"] if a["id"] not in free_set]
        all_aircraft = fixed_part + free_part
        makespan     = max(a["finish"] for a in all_aircraft)
        total_delay  = sum(a["delay"]  for a in all_aircraft)
        movements    = _count_movements(all_aircraft, blocking_arcs)

        combined = {
            "status":    "lns_submilp",
            "objective": 0.0,
            "metrics": {
                "makespan":    round(makespan, 4),
                "movements":   movements,
                "total_delay": round(total_delay, 4),
            },
            "aircraft": all_aircraft,
        }
        return combined

    except Exception:
        return None

    finally:
        # Always unfix so the cached instance is clean for the next call
        for r, a_data in fixed_ac.items():
            p_r = a_data["position"]
            concrete.vAircraftStart[r].unfix()
            concrete.vAircraftFinish[r].unfix()
            for p in positions:
                concrete.vAircraftPosition[r, p].unfix()
            for j in concrete.sJobs:
                if job_aircraft.get(j) != r:
                    continue
                concrete.vStartTime[j].unfix()
                concrete.vFinishTime[j].unfix()
                for p in positions:
                    concrete.vJobPosition[j, p].unfix()


def _assemble_log(
    instance: dict,
    params: dict,
    log_rows: list[str],
    best_obj: float,
    best_sol: dict,
    total_iters: int,
    improvements: int,
) -> list[str]:
    """Assemble the full log content for the LNS run."""
    lines: list[str] = []
    sep = "=" * 72

    lines.append(sep)
    lines.append("  LNS solver — run summary")
    lines.append(sep)
    lines.append(f"  Instance aircraft : {len(instance['aircrafts'])}")
    lines.append(f"  Positions         : {instance['hangar']['positions']}")
    lines.append(f"  Blocking arcs     : "
                 + "  ".join(f"{a['front']}->{a['rear']}"
                             for a in instance["hangar"]["blocking_arcs"]))
    lines.append("")
    lines.append("  Parameters:")
    for k, v in params.items():
        lines.append(f"    {k}: {v}")
    lines.append("")
    lines.append(sep)
    lines.append(f"  Iterations: {total_iters}   Improvements: {improvements}")
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
    lines.append(f"  {'ID':<6}  {'Pos':<5}  {'start':>8}  {'finish':>8}  {'delay':>7}")
    lines.append(f"  {'-'*42}")
    for a in sorted(best_sol["aircraft"], key=lambda x: x["start"]):
        lines.append(f"  {a['id']:<6}  {a['position']:<5}  "
                     f"{a['start']:>8.2f}  {a['finish']:>8.2f}  {a['delay']:>7.2f}")
    lines.append(sep)

    return lines
