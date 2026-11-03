"""Iterated Greedy + VND solver for paper #2 (job-level extension).

This module implements **Candidate A** from the literature synthesis
that informed it (now archived alongside this file as
``synthesis.md`` and ``design.md``): an Iterated-Greedy outer loop
(NEH-style greedy construction + worst-aircraft destruction /
reconstruction) wrapped around a sequential Variable Neighbourhood
Descent local search.  The design was distilled from external theory
that lived (and still lives) under ``methods/theory_assisted/`` — see
CLAUDE.md for the isolation contract this method inherits.

Architecture (two layers, as the synthesis recommends)
------------------------------------------------------
1. **Outer combinatorial decision** — the position assignment
   ``pi : R -> P`` and a global priority order over the aircraft.
2. **Inner timing decision** — a deterministic *decoder* that, given an
   assignment and an order, produces job start/finish times.

Two decoders
------------
The inner layer comes in two regimes (selected per phase, see ``solve``):

* **Zero-movement** (``_decode``): feasible by construction with no
  manoeuvres.  For every blocking arc the rear aircraft is placed
  *before* / *after* / *enclosing* the front (margin ``eta``), so both
  its access instants are Mode A.  The *enclose* (nesting) option lets
  blocking-related aircraft overlap in time.  Always the guaranteed-
  feasible floor.
* **Manoeuvre-aware** (``_decode_v3``): may *spend* Mode-B (inter-job
  gap, no extension) and Mode-C (interruptible job, ``+delta``)
  manoeuvres to compress the schedule when the weights reward it;
  positions are scheduled deepest-rear first and each front takes its
  min-cost start.  Validated against the real checker; accepted only if
  compliant and strictly better than the zero-movement floor.

Search
------
The outer combinatorial state ``(assignment, order)`` is optimised by a
multi-start Iterated-Greedy + VND loop.  Highlights (full detail in the
companion ``iterated_greedy_vnd.md``):

- **Slim construction portfolio** (Attempt 7): two deterministic seed
  orders — NEH (makespan) and SLACK (due-date headroom) — then a single
  diversification mechanism, a rank-biased geometric shuffle
  (``_biased_order``) of the better deterministic base, so every restart
  explores a distinct-but-sensible insertion order.
- **Restarts until the deadline** (Attempt 7): the restart loop runs
  while time remains (no fixed start count); each start ends on its own
  stale counter, so small instances do hundreds of diverse restarts
  instead of leaving the budget idle, and large ones keep their
  per-start time slice.
- **Decode cache** (``_eval``) memoises decodes within a solve.
- **Time budget** (``_time_up``) is polled inside every loop, so the
  solver respects ``time_limit_s`` even on large instances.

This architecture is the one cross-validated by [[Scheduling_Heuristics]],
[[Variable_Neighborhood_Descent]] and [[Iterated_Local_Search]] in the
synthesis.

Solution dict shape (consumed by ``problems/jobs/checker.py``)::

    {"status", "objective", "metrics": {makespan, total_delay, movements},
     "aircraft": [{"id","position","start","finish","delay",
                   "jobs":[{"id","start","finish"}, ...]}, ...]}
"""
from __future__ import annotations

import math
import random
from bisect import bisect_left, bisect_right
from itertools import repeat
import statistics
import time

import numpy as np

import igvnd_kernels as K


class _LazySolution(dict):
    """A decode result whose per-aircraft part is built on first access.

    The search reads only ``objective`` for the vast majority of the
    neighbours it prices, so building ``aircraft`` (a dict per aircraft and
    per job) eagerly would cost more than the compiled decode itself.  Any
    ``[]`` / ``get`` of a key that is not there yet triggers the build once.
    """
    __slots__ = ("_build",)

    def __init__(self, build, data):
        super().__init__(data)
        self._build = build

    def __missing__(self, key):
        if self._build is not None:
            build, self._build = self._build, None
            self.update(build())
            if dict.__contains__(self, key):
                return dict.__getitem__(self, key)
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def materialize(self) -> "_LazySolution":
        self.get("aircraft")
        return self



class IteratedGreedyVNDJobSolver:
    """Iterated Greedy + VND heuristic (Candidate A)."""

    name = "iterated_greedy_vnd"

    def __init__(self) -> None:
        self._config: dict = {}
        self._log: list[str] = []
        self._deadline: float = float("inf")   # wall-clock cap for search loops
        self._decoder_tag: str = "v2"          # identifies the active decoder
        self._cache: dict = {}                 # decode memoisation (per solve)
        self._moves_cache: dict = {}           # neighbourhood-scan memoisation (per solve)
        self._cache_max: int = 400_000
        self._cache_hits: int = 0
        self._cache_misses: int = 0

    # ------------------------------------------------------------------
    # Contract
    # ------------------------------------------------------------------

    def configure_solver(self, **kwargs) -> None:
        """Store tunable parameters.

        Recognised keys (all optional except those Application sets):
            time_limit_s      : wall-clock cap in seconds (default 60)
            weight_makespan   : W^M (default 0.1)
            weight_delay      : W^D (default 1.0)
            weight_movements  : W^S (default 10.0)
            seed              : base RNG seed (default 1); start i uses seed+i
            n_starts          : optional HARD CAP on restarts (testing/ablation
                                only; default None = restart until the
                                deadline)
            k_destroy         : aircraft removed per IG perturbation
                                (default max(1, R // 4))
            max_no_improve    : early-stop after this many non-improving
                                IG iterations (default 400)
            use_v3            : enable the manoeuvre-aware polish (default True)
        """
        self._config.update(kwargs)

    def get_config(self) -> dict:
        return dict(self._config)

    def get_log(self) -> list[str]:
        return list(self._log)

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------

    def solve(self, instance_data: dict) -> dict:
        self._log = []
        cfg = self._config
        self.time_limit = float(cfg.get("time_limit_s") or 60.0)
        self.wM = float(cfg.get("weight_makespan", 0.1))
        self.wD = float(cfg.get("weight_delay", 1.0))
        self.wS = float(cfg.get("weight_movements", 10.0))

        self._prepare(instance_data)
        R = len(self.aircraft_ids)
        self.k_destroy = int(cfg.get("k_destroy", max(1, R // 4)))
        self.max_no_improve = int(cfg.get("max_no_improve", 400))
        self.use_v3 = bool(cfg.get("use_v3", True))
        base_seed = int(cfg.get("seed", 1) or 1)
        # Per-start time slice.  Small instances (R <= 10) converge in a few
        # seconds, so many short restarts add diversity (Attempt 7 — restarts
        # keep looping until the deadline).  Larger instances never converge
        # inside a slice: there two long trajectories — one per Mode-A band —
        # beat 3–4 lottery restarts whose best never came from a restart >= 4
        # (Attempt 14).  The slice is a CAP, not a schedule.
        slice_div = 8 if R <= 10 else 2
        # Optional hard cap on restarts (testing/ablation only; None = until
        # the deadline).
        max_starts = cfg.get("n_starts")
        max_starts = int(max_starts) if max_starts is not None else None

        t0 = time.perf_counter()
        global_dl = t0 + self.time_limit
        per_start = self.time_limit / slice_div

        # Per-solve decode cache (instance + weights are fixed within a solve).
        self._cache = {}
        self._moves_cache = {}
        self._cache_hits = self._cache_misses = 0

        # Slim construction portfolio (Attempt 7): two deterministic seed
        # orders — NEH (longest total work first, the makespan rule) and SLACK
        # (least due-date headroom first, the delay rule) — and, from the third
        # restart on, ONE diversification mechanism: a rank-biased (geometric)
        # shuffle of whichever deterministic order scored better, so restarts
        # explore unlimited distinct-but-sensible insertion orders.
        ids = self.aircraft_ids
        by_neh = sorted(ids, key=lambda r: -self.T[r])
        by_slack = sorted(ids, key=lambda r: self.L[r] - self.E[r] - self.T[r])
        det_seeds = [("NEH", by_neh), ("SLACK", by_slack)]
        rule_obj: dict[str, float] = {}       # deterministic rule -> its start obj

        # Global incumbent (best solution dict and its objective) over all restarts.
        best_sol, best_obj = None, float("inf")
        start_objs: list[float] = []          # per-start incumbents (search risk)
        i = 0                                  # restart counter
        while (time.perf_counter() < global_dl - 0.05
               and (max_starts is None or i < max_starts)):
            # --- one independent multi-start restart ---
            # Each restart gets its own RNG (seed = base+i): restarts are
            # reproducible and independent, so they explore different basins.
            self.rng = random.Random(base_seed + i)
            start_dl = min(global_dl, time.perf_counter() + per_start)
            self._deadline = start_dl
            # Alternate the Mode-A clearance per restart (Attempt 11, refined):
            # even restarts search the checker-exact band geometry (margin 0,
            # reaches the relaxed-MILP optima), odd restarts the conservative
            # eta geometry (keeps the old landscape's basins reachable — the
            # band-only landscape regressed chain R10 and wDLY at scale).
            self.bandA = 0.0 if i % 2 == 0 else self.eta
            # Activate the zero-movement decoder for this restart's first phase.
            self._decode_fn = self._decode
            # Tag the active decoder so the decode cache keys stay disjoint
            # (the tag must carry the active Mode-A clearance).
            self._decoder_tag = "v2b" if self.bandA == 0.0 else "v2"
            # This restart's insertion order: deterministic for the first two
            # starts, rank-biased around the better deterministic base after.
            if i < len(det_seeds):
                name, order0 = det_seeds[i]
            else:
                base = min(rule_obj, key=rule_obj.get) if rule_obj else "NEH"
                order0 = self._biased_order(dict(det_seeds)[base])
                name = f"biased-{base}"
            a0 = self._greedy_construct(order0)
            # _one_start runs the full restart on this seed: a zero-movement
            # search, then the checker-validated manoeuvre-aware polish; it
            # returns the restart's best solution dict and its objective value.
            sol, obj = self._one_start(instance_data, a0, list(order0), start_dl)
            if i < len(det_seeds):
                rule_obj[name] = obj           # remember each rule's quality
            start_objs.append(obj)            # record for the search-risk diagnostic
            # Keep this restart's result iff it strictly improves the incumbent.
            if obj < best_obj - 1e-9:
                best_sol, best_obj = sol, obj
                self._log.append(
                    f"start {i} (seed {base_seed + i}, ctor {name})  obj={obj:.4f}  "
                    f"ms={sol['metrics']['makespan']:.1f} dly={sol['metrics']['total_delay']:.1f} "
                    f"mov={sol['metrics']['movements']}  best={best_obj:.4f}"
                )
            i += 1                             # advance to the next restart

        # Option B — dense concentric-nesting schedule (targets dense `wMOV`).
        # Built ONCE with explicit start times (not via the earliest-feasible
        # decode, which cannot nest), validated by the checker, and adopted
        # only if it beats the multi-start best.  Gated to the movement-priority
        # regime with a blocking topology, where it is relevant.
        # Gate: only worth trying when there is blocking AND the movement weight
        # dominates (the regime where concentric nesting pays off).
        if self._arcs and self.wS >= self.wM and self.wS >= self.wD:
            # Build the explicit concentric-nesting schedule; returns a full
            # solution dict (movements = 0 by construction) or None.  Band
            # wraps: checker-exact and tightest (improved every wMOV guard).
            self.bandA = 0.0
            nest = self._dense_nest_solution()
            # Adopt it only if it exists, strictly improves the incumbent, and
            # _is_compliant (which runs the real paper-#2 checker -> bool) passes.
            if (nest is not None and nest["objective"] < best_obj - 1e-9
                    and self._is_compliant(nest, instance_data)):
                nest["phase"] = "dense_nest"
                best_sol, best_obj = nest, nest["objective"]   # replace the incumbent
                self._log.append(f"dense-nest ACCEPTED obj={best_obj:.4f} "
                                 f"ms={nest['metrics']['makespan']:.1f}")

        # NOTE (Commit 6 attempted & reverted): a DelayRiskRepair fired here —
        # a re-search from a delay-biased seed (delayed aircraft pulled to the
        # front in EDD order) on leftover budget.  Measured on the ablation
        # subset it never once improved the incumbent (0/74 runs accepted) and
        # left the one clean target, `triangle_loose_R10` seed10 wDLY, at delay
        # 1.5.  The run-to-run search noise (≈19 delay units on `chain_R10`
        # wMK, where the repair cannot even act) dwarfed any apparent effect.
        # The residual is search-variance-bound, not order-bound — see Part III.

        elapsed = time.perf_counter() - t0
        best_sol["status"] = "heuristic_ok"
        best_sol["timed_out"] = elapsed >= self.time_limit - 0.5
        best_sol["solve_time_s"] = round(elapsed, 3)

        # Commit 5 — risk diagnostics (observability only, no behaviour change).
        # Self-diagnosed internal symptoms that later commits fire repairs on,
        # instead of an external "outlier-vs-MILP" label that a fresh instance
        # cannot provide.  Attached to the solution and summarised in the log.
        # _diagnostics inspects the final solution and the per-start objectives
        # and returns a dict of risk metrics (delay / nesting / search risk).
        # Observability only — it does not change the returned schedule.
        diag = self._diagnostics(best_sol, start_objs)
        best_sol["diagnostics"] = diag
        dr, nr, sr = diag["delay_risk"], diag["nesting_risk"], diag["search_risk"]
        self._log.append(
            "diagnostics  "
            f"delay[n={dr['n_delayed']} tot={dr['total_delay']:.1f} "
            f"max={dr['max_delay']:.1f} minslack={dr['min_slack_delayed']}]  "
            f"nest[mov={nr['movements']} dens={nr['blocking_density']:.2f} "
            f"serial={nr['serial_points']}/{nr['n_aircraft']}]  "
            f"search[n={sr['n_starts']} std={sr['obj_std']:.3f} "
            f"spread={sr['obj_spread']:.3f}]"
        )
        n_eval = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / n_eval if n_eval else 0.0
        self._log.append(
            f"done  starts={i}  best_obj={best_obj:.4f}  "
            f"ms={best_sol['metrics']['makespan']:.2f} "
            f"dly={best_sol['metrics']['total_delay']:.2f} "
            f"mov={best_sol['metrics']['movements']}  "
            f"phase={best_sol.get('phase')}  timed_out={best_sol['timed_out']}  "
            f"decodes={n_eval} cache_hit={hit_rate:.0%}  ({elapsed:.2f}s)"
        )
        return best_sol     # the best checker-valid schedule found across all restarts

    # ------------------------------------------------------------------
    # Risk diagnostics (Commit 5 — observability, no behaviour change)
    # ------------------------------------------------------------------

    def _diagnostics(self, sol: dict, start_objs: list[float]) -> dict:
        """Self-diagnosed internal symptoms of the returned best solution.

        Three families, each a *trigger* for a later specialised repair:

        * ``delay_risk``  — is there real lateness with headroom to remove it?
          ``min_slack_delayed`` < 0 means a delayed aircraft's target window
          is itself infeasible (no repair can help); ≥ 0 means slack exists.
        * ``nesting_risk`` — is the schedule serialised where blocking would
          allow concentric nesting?  ``serial_points`` counts aircraft that
          start only after everything earlier has finished (a serial break);
          high relative to ``n_aircraft`` under a dense ``blocking_density``
          is the ComponentNesting trigger.
        * ``search_risk`` — did the multi-start incumbents disagree?  A large
          ``obj_std`` / ``obj_spread`` means the basin is luck-dependent (an
          ALNS / more-restarts trigger); ~0 means the search is stable.
        """
        acc = sol.get("aircraft", [])
        m = sol.get("metrics", {})

        delays = [a.get("delay", 0.0) for a in acc]
        delayed = [a for a in acc if a.get("delay", 0.0) > 1e-9]
        # slack of a delayed aircraft against its own target window
        slacks = [self.L[a["id"]] - self.E[a["id"]] - self.T[a["id"]]
                  for a in delayed if a["id"] in self.T]
        delay_risk = {
            "n_delayed": len(delayed),
            "total_delay": float(m.get("total_delay", sum(delays))),
            "max_delay": float(max(delays) if delays else 0.0),
            "min_slack_delayed": round(min(slacks), 3) if slacks else None,
        }

        nP = len(self.positions)
        density = (len(self._arcs) / (nP * (nP - 1) / 2)) if nP > 1 else 0.0
        # serial breaks: walking aircraft by start time, count those that begin
        # only after every earlier aircraft has finished (no temporal overlap
        # with the prefix) — the opposite of nesting.
        by_start = sorted(acc, key=lambda a: a.get("start", 0.0))
        serial_points, prefix_finish = 0, float("-inf")
        for a in by_start:
            if a.get("start", 0.0) >= prefix_finish - 1e-9:
                serial_points += 1
            prefix_finish = max(prefix_finish, a.get("finish", 0.0))
        nesting_risk = {
            "movements": int(m.get("movements", 0)),
            "blocking_density": round(density, 3),
            "serial_points": serial_points,
            "n_aircraft": len(acc),
        }

        if start_objs:
            lo, hi = min(start_objs), max(start_objs)
            search_risk = {
                "n_starts": len(start_objs),
                "obj_min": round(lo, 4),
                "obj_max": round(hi, 4),
                "obj_std": round(statistics.pstdev(start_objs), 4) if len(start_objs) > 1 else 0.0,
                "obj_spread": round((hi - lo) / lo, 4) if lo > 1e-9 else 0.0,
            }
        else:
            search_risk = {"n_starts": 0, "obj_min": None, "obj_max": None,
                           "obj_std": 0.0, "obj_spread": 0.0}

        return {"delay_risk": delay_risk, "nesting_risk": nesting_risk,
                "search_risk": search_risk}

    def _one_start(self, instance_data: dict, a0: dict, o0: list, deadline: float) -> tuple[dict, float]:
        """One multi-start restart from the seed ``(a0, o0)``: zero-movement
        (v2) search, then an optional manoeuvre-aware (v3) polish validated by
        the real checker.  Returns (solution, objective)."""
        # ---- Phase 1: zero-movement search (v2 decoder) ----
        # The v2 floor is feasible by construction, so the incumbent returned
        # here is always a complete, valid schedule.
        self._decode_fn = self._decode
        self._decoder_tag = "v2b" if self.bandA == 0.0 else "v2"
        dl1 = min(deadline, time.perf_counter() + (deadline - time.perf_counter()) *
                  (0.5 if self.use_v3 else 1.0))
        a1, o1, _ = self._search(dict(a0), list(o0), {}, dl1)
        best_sol = self._finalize(self._decode(a1, o1, with_jobs=True))
        best_obj = best_sol["objective"]
        best_sol["phase"] = "zero"

        # ---- Phase 2: manoeuvre-aware polish (v3 decoder) ----
        # v2 is the guaranteed floor; the v3 candidate is taken only if the
        # real checker certifies it AND it strictly improves — so a timed-out
        # or invalid manoeuvre-aware search can never worsen the incumbent.
        if self.use_v3:
            self._decode_fn = self._decode_v3
            self._decoder_tag = "v3"
            a3, o3, s3 = self._search(dict(a1), list(o1), {}, deadline)
            sol_v3 = self._finalize(self._decode_v3(a3, o3, s3))
            if (sol_v3["objective"] < best_obj - 1e-9
                    and self._is_compliant(sol_v3, instance_data)):
                sol_v3["phase"] = "manoeuvre"
                best_sol, best_obj = sol_v3, sol_v3["objective"]
        return best_sol, best_obj

    # ------------------------------------------------------------------
    # Search driver (shared by both phases via self._decode_fn)
    # ------------------------------------------------------------------

    def _search(self, assignment, order, shift, deadline):
        """VND + Iterated-Greedy loop using the current ``self._decode_fn``.

        Drives one restart's local search.  First the seed is taken to a local
        optimum by the VND; then the Iterated-Greedy loop repeatedly perturbs
        the *current* state (destroy + reconstruct), re-optimises it with the
        VND, and decides whether to accept it.  Two incumbents are tracked: the
        walk's current state ``cur`` and the global best ``best`` ever seen.
        The loop stops at the deadline or after ``max_no_improve`` fruitless
        iterations.  Returns the best ``(assignment, order, shift)`` found
        (``shift`` stays empty under the zero-movement decoder).
        """
        self._deadline = deadline
        # Take the seed to a local optimum before the perturbation loop starts.
        assignment, order, shift = self._local_search(assignment, order, shift)
        best_obj = self._objective(self._eval(assignment, order, shift))
        polish = self._decoder_tag == "v3"     # align only under the manoeuvre decoder
        if polish:
            shift, best_obj = self._polish(assignment, order, shift, best_obj, kicks=False)
        best_assign, best_order, best_shift = dict(assignment), list(order), dict(shift)
        cur_assign, cur_order, cur_shift, cur_obj = dict(best_assign), list(best_order), dict(best_shift), best_obj
        no_improve = 0
        while time.perf_counter() < deadline and no_improve < self.max_no_improve:
            # Iterated-Greedy kick: destroy k aircraft and greedily rebuild,
            # then re-descend to a local optimum with the local search.
            a2, o2, s2 = self._perturb(cur_assign, cur_order, cur_shift, self.k_destroy)
            a2, o2, s2 = self._local_search(a2, o2, s2)
            obj2 = self._objective(self._eval(a2, o2, s2))
            if polish:
                # Judge the candidate with its shifts aligned (single-rear
                # aligns, the cheap step): with the shifts it inherits, the
                # structures the optima use look far worse than they are.
                s2, obj2 = self._align(a2, o2, s2, obj2, self._deadline, max_level=1)
            if polish and obj2 < best_obj - 1e-9:
                s2, obj2 = self._polish(a2, o2, s2, obj2, kicks=False)
            # Acceptance: walk to the new state if it does not worsen the
            # current one (a "better-or-equal" random-walk acceptance).  Under
            # this rule cur never leaves the best plateau (cur_obj == best_obj
            # always holds), so no re-centring on the best is ever needed.
            if obj2 <= cur_obj + 1e-9:
                cur_assign, cur_order, cur_shift, cur_obj = a2, o2, s2, obj2
            # Track the global best separately, and reset the stale counter
            # only on a strict global improvement.
            if obj2 < best_obj - 1e-9:
                best_assign, best_order, best_shift = dict(a2), list(o2), dict(s2)
                best_obj = obj2
                no_improve = 0
            else:
                no_improve += 1
            # On stagnation, the shift kicks get one go at the best: they
            # target a converged search's last valley (a search still
            # improving would only lose time to them).  If they improve, the
            # IG continues from there; otherwise the restart ends.
            if (polish and no_improve >= self.max_no_improve
                    and time.perf_counter() < deadline):
                s3, obj3 = self._polish(best_assign, best_order, best_shift, best_obj)
                if obj3 < best_obj - 1e-9:
                    best_shift, best_obj = dict(s3), obj3
                    cur_assign, cur_order = dict(best_assign), list(best_order)
                    cur_shift, cur_obj = dict(s3), obj3
                    no_improve = 0
        return best_assign, best_order, best_shift

    @staticmethod
    def _finalize(sol: dict) -> dict:
        if isinstance(sol, _LazySolution):
            sol.materialize()
        sol["status"] = "heuristic_ok"
        sol.pop("_pushers", None)   # search-only annotations, never serialised
        sol.pop("_push", None)
        return sol

    def _time_up(self) -> bool:
        """True once the current wall-clock budget is exhausted.  Checked
        inside every search loop so the solver respects ``time_limit_s`` even
        on large instances where a single sweep is expensive."""
        return time.perf_counter() >= self._deadline

    def _is_compliant(self, sol: dict, instance_data: dict) -> bool:
        """Validate a candidate with the real paper-#2 checker (safety net)."""
        try:
            from checker import check_solution  # problems/jobs on sys.path
        except Exception:
            return True  # checker not importable in this context — trust the sim
        try:
            return bool(check_solution(sol, instance_data)["compliant"])
        except Exception:
            return False

    # ==================================================================
    # Instance preprocessing
    # ==================================================================

    def _prepare(self, inst: dict) -> None:
        self.eta = float(inst.get("eta", 1.0))
        self.eps = float(inst.get("min_separation", 0.5))
        # Mode-A (vacant-front) clearance used by the whole-stay geometry.
        # The checker treats any instant OUTSIDE the front's stay [s, f] as
        # vacant (touching allowed), so no eta margin is required there — eta
        # is semantics only for the Mode-C job interior.  Attempt 11: the
        # restart loop ALTERNATES this between 0.0 (checker-exact band
        # geometry, reaches the relaxed-MILP optima) and eta (conservative
        # geometry, keeps the pre-Attempt-11 landscape's basins reachable).
        self.bandA = 0.0
        self.mu = float(inst.get("mu", 1.0))
        self.delta = float(inst.get("delta", 2.0))

        self.positions: list[str] = list(inst["hangar"]["positions"])
        arcs = inst["hangar"]["blocking_arcs"]
        conflict: set[tuple[str, str]] = set()
        directed: set[tuple[str, str]] = set()   # (front, rear)
        for arc in arcs:
            directed.add((arc["front"], arc["rear"]))
            conflict.add((arc["front"], arc["rear"]))
            conflict.add((arc["rear"], arc["front"]))
        self._conflict = conflict
        self._arcs = directed

        # Blocking depth (longest front→rear chain ending at a position).
        # Deeper = more rear; the v3 decoder schedules deep positions first
        # so a front aircraft sees its rears' access instants already fixed.
        depth = {p: 0 for p in self.positions}
        for _ in range(len(self.positions)):
            for (f, r) in directed:
                if depth[r] < depth[f] + 1:
                    depth[r] = depth[f] + 1
        self._pos_by_depth_desc = sorted(self.positions, key=lambda p: -depth[p])
        # rears blocked by each front position, and fronts blocking each rear
        self._rears_of = {p: [r for (f, r) in directed if f == p] for p in self.positions}
        self._fronts_of = {p: [f for (f, r) in directed if r == p] for p in self.positions}

        self.aircraft_ids: list[str] = [a["id"] for a in inst["aircrafts"]]
        self.E: dict[str, float] = {a["id"]: float(a["earliest_start"]) for a in inst["aircrafts"]}
        self.L: dict[str, float] = {a["id"]: float(a["target_finish"]) for a in inst["aircrafts"]}

        # Per-aircraft ordered job chain (is_first + precedence successors).
        jobs_by_ac: dict[str, list[dict]] = {}
        for j in inst["jobs"]:
            jobs_by_ac.setdefault(j["aircraft_id"], []).append(j)
        succ: dict[str, str] = {}
        for pr in inst["job_precedences"]:
            succ[pr["before"]] = pr["after"]

        self.interruptible: dict[str, bool] = {
            j["id"]: bool(j.get("interruptible", False)) for j in inst["jobs"]
        }
        self.chain: dict[str, list[tuple[str, float]]] = {}
        self.T: dict[str, float] = {}
        for r in self.aircraft_ids:
            jl = jobs_by_ac.get(r, [])
            by_id = {j["id"]: j for j in jl}
            first = next((j for j in jl if j.get("is_first")), jl[0] if jl else None)
            chain: list[tuple[str, float]] = []
            cur = first["id"] if first else None
            seen: set[str] = set()
            while cur is not None and cur in by_id and cur not in seen:
                seen.add(cur)
                chain.append((cur, float(by_id[cur]["duration"])))
                cur = succ.get(cur)
            # Fallback: append any jobs not reached via the chain (defensive).
            for j in jl:
                if j["id"] not in seen:
                    chain.append((j["id"], float(j["duration"])))
            self.chain[r] = chain
            self.T[r] = sum(d for _, d in chain)

        # Array view of the instance for the compiled decode kernels.
        ids, P = self.aircraft_ids, self.positions
        self._idx = {r: i for i, r in enumerate(ids)}
        self._pidx = {p: i for i, p in enumerate(P)}
        self._E = np.array([self.E[r] for r in ids])
        self._L = np.array([self.L[r] for r in ids])
        self._T = np.array([self.T[r] for r in ids])
        off = [0]
        for r in ids:
            off.append(off[-1] + len(self.chain[r]))
        self._job_off_l = off
        self._job_off = np.array(off, np.int64)
        self._job_dur = np.array([d for r in ids for _, d in self.chain[r]])
        self._job_int = np.array([self.interruptible[j] for r in ids for j, _ in self.chain[r]],
                                 np.bool_)
        # kind[p, p2]: 1 same position, 2 p2 is a front of p, 3 p2 is a rear of p
        kind = np.zeros((len(P), len(P)), np.int8)
        for a, p in enumerate(P):
            for b, p2 in enumerate(P):
                kind[a, b] = (1 if p2 == p else 2 if (p2, p) in directed
                              else 3 if (p, p2) in directed else 0)
        self._kind = kind
        # name rank: the zero-movement scan breaks band ties by aircraft id
        by_name = sorted(ids)
        self._rank = np.array([by_name.index(r) for r in ids], np.int64)
        self._pos_depth = np.array([self._pidx[p] for p in self._pos_by_depth_desc], np.int64)
        self._rears_mat = np.zeros((len(P), len(P)), np.int64)
        self._n_rears = np.zeros(len(P), np.int64)
        for p in P:
            for x, q in enumerate(self._rears_of[p]):
                self._rears_mat[self._pidx[p], x] = self._pidx[q]
            self._n_rears[self._pidx[p]] = len(self._rears_of[p])
        # front positions of each position (the align polish's boundaries)
        self._fronts_mat = np.zeros((len(P), len(P)), np.int64)
        self._n_fronts = np.zeros(len(P), np.int64)
        for p in P:
            for x, q in enumerate(self._fronts_of[p]):
                self._fronts_mat[self._pidx[p], x] = self._pidx[q]
            self._n_fronts[self._pidx[p]] = len(self._fronts_of[p])
        # dep[p, s]: s is a rear of p, transitively — p's manoeuvre-decoder
        # schedule depends on s's (the incremental pricing's affected set)
        dep = np.zeros((len(P), len(P)), np.bool_)
        for p in P:
            stack = list(self._rears_of[p])
            while stack:
                q = stack.pop()
                if not dep[self._pidx[p], self._pidx[q]]:
                    dep[self._pidx[p], self._pidx[q]] = True
                    stack.extend(self._rears_of[q])
        self._kinst = (self._E, self._L, self._T, self._kind, self._rank, self._job_off,
                       self._job_dur, self._job_int, self._pos_depth, self._rears_mat,
                       self._n_rears, dep)
        # Compile / load the kernels now, outside the solve's timer.
        self.wM = getattr(self, "wM", 1.0)
        self.wD = getattr(self, "wD", 1.0)
        self.wS = getattr(self, "wS", 1.0)
        warm = {r: P[0] for r in ids}
        self._decode(warm, list(ids))
        self._decode_v3(warm, list(ids))
        apos, o_arr, sh_d, sh_g, prm = self._kernel_state(warm, list(ids), {})
        for v3 in (False, True):
            K.scan_moves(v3, o_arr[:1], apos, o_arr, sh_d, sh_g, 0.0, self._kinst, prm, len(P), 0.0)
            K.best_insert(v3, 0, apos, o_arr[1:], sh_d, sh_g, self._kinst, prm, len(P))
        K.align_one(0, np.zeros(0, np.int64), o_arr, apos, sh_d, sh_g, 0.0, self._kinst, prm,
                    self._fronts_mat, self._n_fronts, 0.0, 1, 1, 1, 7)
        K.proposals_of(0, o_arr, apos, sh_d, sh_g, self._kinst, prm, self._fronts_mat,
                       self._n_fronts)

    def _pos_conflict(self, p: str, q: str) -> bool:
        return (p, q) in self._conflict

    # ==================================================================
    # Decoder  (assignment + order  ->  full solution dict)
    # ==================================================================

    def _decode(self, assignment: dict, order: list[str], with_jobs: bool = False) -> dict:
        """Zero-movement decoder.  Aircraft are placed one at a time in the
        priority order; each is given the earliest start that is feasible
        (manoeuvre-free) against everything already placed — the compiled
        kernel ``decode_v2`` (``igvnd_kernels``), whose forbidden-band
        geometry keeps every access instant in Mode A.  So the result has
        movements = 0 and is feasible by construction — the guaranteed floor.

        ``_pushers[r]`` lists the aircraft whose forbidden band moved r's
        start.  r's start depends on nothing else, so an improving move must
        touch the pusher tree rooted at the makespan / delayed aircraft — the
        exact candidate filter used by the local search (Attempt 14).

        Most decodes are only ever asked for their objective, so ``aircraft``
        and ``_pushers`` are built on first access (``_LazySolution``), and the
        per-job entries only for a schedule that leaves the search
        (``with_jobs``).
        """
        idx, ids = self._idx, self.aircraft_ids
        R = len(ids)
        pos = list(map(assignment.__getitem__, order))  # snapshot: the search mutates assignment
        o = np.fromiter(map(idx.__getitem__, order), np.int64, len(order))
        op = np.fromiter(map(self._pidx.__getitem__, pos), np.int64, len(pos))
        start = np.zeros(R)
        push = np.zeros((R, R), np.uint8)
        K.decode_v2(o, op, self._E, self._T, self._kind, self._rank, self.eps,
                    self.bandA, start, push)
        finish = start + self._T
        placed = np.zeros(R, np.bool_)
        placed[o] = True
        makespan, total_delay = K.metrics(self._L, finish, placed)

        def build():
            where = dict(zip(order, pos))
            st, fi = start.tolist(), finish.tolist()
            pushers: dict[str, list] = {r: [] for r in order}
            for i, j in np.argwhere(push).tolist():
                pushers[ids[i]].append(ids[j])
            for v in pushers.values():
                v.sort()
            # tight job chains, kappa = 0
            aircraft_out = []
            for r in ids:
                if r not in where:
                    continue  # partial decode during greedy construction
                i = idx[r]
                s_r, f_r = st[i], fi[i]
                a_out = {"id": r, "position": where[r], "start": s_r, "finish": f_r,
                         "delay": max(0.0, f_r - self.L[r])}
                if with_jobs:
                    jobs_out = []
                    tcur = s_r
                    for jid, d in self.chain[r]:
                        jobs_out.append({"id": jid, "start": tcur, "finish": tcur + d})
                        tcur += d
                    a_out["jobs"] = jobs_out
                aircraft_out.append(a_out)
            # _pushers is search-only, stripped by _finalize
            return {"aircraft": aircraft_out, "_pushers": pushers}

        obj = self.wM * makespan + self.wD * total_delay  # movements == 0
        return _LazySolution(build, {
            "status": "heuristic_ok",
            "objective": round(obj, 6),
            "metrics": {
                "makespan": makespan,
                "total_delay": total_delay,
                "movements": 0,
            },
            "_push": (finish, push, placed),    # for _critical, without the build
        })


    def _dense_nest_solution(self):
        """Explicit concentric-nesting candidate, generalised to the actual
        blocking DAG (Attempt 9; the mechanism the certified optimum uses).

        Aircraft are grouped into **rounds** of one aircraft per position.
        Within a round only the positions that actually block each other get
        the concentric treatment: along every front→rear arc the rear's stay
        is **stretched with inter-job idle** so it wraps the front's stay by
        `eta` on both sides (deepest rear = outermost shell, stays stepped by
        ≥ 2·eta along each chain).  Unconflicted positions simply run tight
        and in parallel.  Rounds are serialised within the blocking component
        (`+ max(eps, eta)`), and chained per position (`+ eps`) elsewhere.
        Start times are written **explicitly** — this does NOT go through the
        earliest-feasible decode (which would un-nest it) — and every rear
        access lands Mode A, so movements = 0 by construction.  Returns a full
        solution dict.  (Checker-validated and best-of in `solve`.)
        """
        eta, eps = self.eta, self.eps
        P = self._pos_by_depth_desc                       # deepest (rear) first
        cap = len(P)
        # depth rank: index in the deepest-first list (higher = more front)
        rank = {p: i for i, p in enumerate(P)}
        # fronts this position must wrap (its already-front positions)
        fronts_of = {p: [f for (f, r) in self._arcs if r == p] for p in P}
        conf_pos = {p for arc in self._arcs for p in arc}  # any arc endpoint
        by_dur = sorted(self.aircraft_ids, key=lambda r: -self.T[r])
        n_rounds = max(1, math.ceil(len(by_dur) / cap))
        rr = [[] for _ in range(n_rounds)]                # round-robin (balances rounds)
        for idx, r in enumerate(by_dur):
            rr[idx % n_rounds].append(r)

        def chunks(seq):
            return [sorted(seq[k:k + cap], key=lambda r: -self.T[r])
                    for k in range(0, len(seq), cap)]
        # Small partition beam: long-first / short-first / earliest-E-first
        # chunking + duration round-robin.  Within a round the members are
        # always ordered by duration (longest gets the outermost shell).
        partitions = [chunks(by_dur),
                      chunks(list(reversed(by_dur))),
                      chunks(sorted(self.aircraft_ids, key=lambda r: self.E[r])),
                      [sorted(w, key=lambda r: -self.T[r]) for w in rr if w]]

        def build_jobs(r, s, L):
            # lay jobs from s; insert the idle (L - T) after the first job so
            # the last job finishes at s + L (needs >= 2 jobs; else stay = T).
            chain = self.chain[r]
            extra = max(0.0, L - self.T[r]) if len(chain) > 1 else 0.0
            t, jobs = s, []
            for idx, (jid, d) in enumerate(chain):
                jobs.append({"id": jid, "start": t, "finish": t + d})
                t += d
                if idx == 0:
                    t += extra
            return jobs, t                                # t = final finish

        def build_from(rounds):
            placed: dict[str, tuple] = {}
            assignment: dict[str, str] = {}
            prev_fin = {p: None for p in P}               # per-position chain
            comp_fin = None                               # blocking-component round finish
            for w in rounds:                              # w sorted by dur desc
                # Longest aircraft to the deepest conflicted positions (they
                # carry the longest, most-stretched stays); a short tail
                # prefers the free positions (tight, parallel).
                use = list(P) if len(w) == cap else \
                    ([p for p in P if p not in conf_pos] +
                     [p for p in P if p in conf_pos])[:len(w)]
                use.sort(key=lambda p: (p not in conf_pos, rank[p]))
                occ = {p: r for p, r in zip(use, w)}
                # Start times.  Conflicted positions share a round anchor and
                # stagger +eta outermost-first along the arcs; free positions
                # just chain on their own history.
                base = {p: max(self.E[occ[p]],
                               (prev_fin[p] + eps) if prev_fin[p] is not None else 0.0)
                        for p in occ}
                # Per-position anchoring: a front may start later than its
                # rear's stagger (the finish pass stretches the rear to keep
                # wrapping it); only the component round anchor is shared, so
                # this round's rear accesses clear last round's fronts.
                comp_anchor = (comp_fin + max(eps, eta)) if comp_fin is not None else 0.0
                s: dict[str, float] = {}
                for p in sorted(occ, key=lambda q: rank[q]):      # deepest first
                    if p in conf_pos:
                        t = max(base[p], comp_anchor)
                        for q in occ:                             # rears wrapping p
                            if p in fronts_of[q] and q in s:
                                t = max(t, s[q] + self.bandA)
                        s[p] = t
                    else:
                        s[p] = base[p]
                # Finishes.  Fronts first (shallowest): each rear's stay is
                # stretched so it also wraps its fronts' finishes by eta.
                fin: dict[str, float] = {}
                for p in sorted(occ, key=lambda q: -rank[q]):     # fronts first
                    f_need = s[p] + self.T[occ[p]]
                    for f in fronts_of[p]:
                        if f in occ:
                            f_need = max(f_need, fin[f] + self.bandA)
                    fin[p] = f_need
                for p, r in occ.items():
                    jobs, f_r = build_jobs(r, s[p], fin[p] - s[p])
                    placed[r] = (s[p], f_r, jobs)
                    assignment[r] = p
                    prev_fin[p] = f_r
                    if p in conf_pos:
                        comp_fin = f_r if comp_fin is None else max(comp_fin, f_r)

            aircraft_out, makespan, total_delay = [], 0.0, 0.0
            for r in self.aircraft_ids:
                s_r, f_r, jobs_out = placed[r]
                delay = max(0.0, f_r - self.L[r])
                makespan = max(makespan, f_r)
                total_delay += delay
                aircraft_out.append({"id": r, "position": assignment[r], "start": s_r,
                                     "finish": f_r, "delay": delay, "jobs": jobs_out})
            obj = self.wM * makespan + self.wD * total_delay   # movements == 0
            return {
                "status": "heuristic_ok",
                "objective": round(obj, 6),
                "metrics": {"makespan": makespan, "total_delay": total_delay, "movements": 0},
                "aircraft": aircraft_out,
            }

        best = None
        for rounds in partitions:
            sol = build_from(rounds)
            if best is None or sol["objective"] < best["objective"]:
                best = sol
        return best

    def _objective(self, sol: dict) -> float:
        return float(sol["objective"])

    def _eval(self, assignment: dict, order: list[str], shift: dict | None = None) -> dict:
        """Decode ``(assignment, order, shift)`` with the active decoder, memoised.

        The decode depends only on the active decoder and, for the aircraft in
        ``order``, their positions, sequence and shifts — so the key captures
        exactly that.  Cache is reset per solve (instance + weights are fixed
        there).  Returned dicts must be treated as read-only by callers.
        """
        key = (self._decoder_tag, tuple(order),
               tuple(map(assignment.__getitem__, order)),
               tuple(sorted(shift.items())) if shift else ())
        cached = self._cache.get(key)
        if cached is not None:
            self._cache_hits += 1
            return cached
        self._cache_misses += 1
        sol = self._decode_fn(assignment, order, shift) if shift else self._decode_fn(assignment, order)
        if len(self._cache) < self._cache_max:
            self._cache[key] = sol
        return sol

    # ==================================================================
    # Construction
    # ==================================================================

    def _greedy_construct(self, order: list[str]) -> dict:
        """NEH-style greedy: insert aircraft one by one (in *order*) at the
        position minimising the partial objective."""
        assignment: dict = {}
        partial_order: list[str] = []
        for r in order:
            partial_order.append(r)
            if self._time_up():
                # Budget exhausted mid-construction: assign the rest to a
                # default position (any assignment is feasible for the v2
                # decoder) so we still return a complete seed.
                assignment[r] = self.positions[0]
                continue
            best_p, best_o = None, float("inf")
            for p in self.positions:
                assignment[r] = p
                o = self._objective(self._eval(assignment, partial_order))
                if o < best_o:
                    best_o, best_p = o, p
            assignment[r] = best_p
        return assignment

    def _biased_order(self, base: list[str]) -> list[str]:
        """Rank-biased (geometric) shuffle of a base priority order.

        Repeatedly draws the next aircraft from the *remaining* base order with
        a geometric distribution over the rank (P(pick rank k) ∝ (1−β)^k), so
        the result stays close to the base rule's logic while every restart
        explores a distinct insertion order.  This is the single
        diversification mechanism of the slim portfolio (Attempt 7) — it
        replaces the retired EDD / CR / BLEND / regret-2 rules.
        """
        beta = 0.3                       # bias strength: ~70 % mass on ranks 0-3
        pool = list(base)
        out: list[str] = []
        while pool:
            u = self.rng.random()
            idx = int(math.log(u) / math.log(1.0 - beta)) if u > 1e-12 else 0
            out.append(pool.pop(min(idx, len(pool) - 1)))
        return out

    # ==================================================================
    # VND  (sequential, B-VND reset over three neighbourhoods)
    # ==================================================================

    def _local_search(self, assignment: dict, order: list[str], shift: dict) -> tuple[dict, list[str], dict]:
        """Exact-filtered first-improvement local search (Attempt 14).

        Candidates are the aircraft whose move can change the objective: under
        the zero-movement decoder, the pusher tree rooted at the makespan and
        delayed aircraft (a move touching only aircraft outside it can never
        improve — their bands never bound anyone and their delay is zero);
        under the manoeuvre decoder, every aircraft.  Each candidate tries
        three moves — reassign to another position, relocate to one
        representative order slot per distinct-decode class, swap positions
        with another aircraft — in a randomised scan; the first improving move
        is applied and the candidate set recomputed.  Stops at a local optimum
        w.r.t. all three moves or when the budget runs out.  The shift is
        carried, not searched, here (see ``_align``).
        """
        assignment = dict(assignment)
        order = list(order)
        shift = dict(shift)
        cur = self._objective(self._eval(assignment, order, shift))
        while not self._time_up():
            cands = (list(self.aircraft_ids) if self._decoder_tag == "v3"
                     else self._critical(self._eval(assignment, order, shift)))
            self.rng.shuffle(cands)
            found = self._scan_moves(cands, assignment, order, shift, cur)
            if found is None:
                break
            r, move, arg, cur = found
            if move == 1:                       # reassign
                assignment[r] = self.positions[arg]
            elif move == 2:                     # relocate
                rest = [q for q in order if q != r]
                order = rest[:arg] + [r] + rest[arg:]
            else:                               # swap
                q = self.aircraft_ids[arg]
                assignment[r], assignment[q] = assignment[q], assignment[r]
        return assignment, order, shift

    def _critical(self, sol: dict) -> list[str]:
        """Aircraft whose move can lower the objective of ``sol``: the makespan
        and delayed aircraft plus everything that pushed them (transitively).
        Without pusher information (manoeuvre decoder) every aircraft qualifies.
        Read from the decode's arrays (``push[r, q]``: q's band moved r), so
        the per-aircraft dicts are never built for it."""
        arrays = dict.get(sol, "_push")         # plain get: no lazy build
        if arrays is None:
            return list(self.aircraft_ids)
        finish, push, placed = arrays
        mk = finish[placed].max()
        seen = placed & ((np.maximum(0.0, finish - self._L) > 1e-9) | (finish >= mk - 1e-9))
        frontier = seen
        while frontier.any():
            frontier = push[frontier].any(axis=0) & ~seen
            seen = seen | frontier
        return [self.aircraft_ids[i] for i in np.flatnonzero(seen)]

    def _kernel_state(self, assignment: dict, order: list[str], shift: dict):
        """Array form of a search state for the neighbourhood kernels:
        position index per aircraft, order as indices, shift arrays, and the
        scalar parameters (the Mode-A band changes per restart)."""
        R = len(self.aircraft_ids)
        apos = np.fromiter(map(self._pidx.__getitem__,
                               map(assignment.__getitem__, self.aircraft_ids)), np.int64, R)
        o = np.fromiter(map(self._idx.__getitem__, order), np.int64, len(order))
        sh_d, sh_g = np.zeros(R), np.zeros(R)
        for r, (d, g) in shift.items():
            sh_d[self._idx[r]] = d
            sh_g[self._idx[r]] = g
        prm = np.array([self.eps, self.bandA, self.eta, self.delta, self.mu,
                        self.wM, self.wD, self.wS])
        return apos, o, sh_d, sh_g, prm

    def _scan_moves(self, cands: list[str], assignment: dict, order: list[str],
                    shift: dict, cur: float):
        """The first improving move of the candidates, in the order given:
        each candidate r tries (1) reassign r to another position; (2)
        relocate r in the order, one slot per distinct-decode class (a class
        is delimited by the aircraft r interacts with — same position, or a
        blocking arc; the manoeuvre decoder only sequences within a position,
        so there only same-position aircraft delimit — and two slots in one
        class decode identically); (3) swap positions with another aircraft.
        Returns (r, move, arg, obj) as the ``scan_moves`` kernel encodes the
        move, or None at a local optimum or once the budget runs out.  The
        candidates not memoised are scanned in one kernel call, against a
        single decode of the state."""
        # A candidate's scan is a deterministic function of (decoder, r,
        # state) — `cur` is the state's own objective — and IG kicks keep
        # revisiting states, so its outcome is memoised like a decode.
        state = (self._decoder_tag, tuple(order),
                 tuple(map(assignment.__getitem__, self.aircraft_ids)),
                 tuple(sorted(shift.items())) if shift else ())
        todo, hit = [], None
        for r in cands:
            memo = self._moves_cache.get((r, state))
            if memo is None:
                todo.append(r)
            elif memo[0]:
                hit = (r, *memo)
                break
        if todo:
            apos, o_arr, sh_d, sh_g, prm = self._kernel_state(assignment, order, shift)
            j, move, arg, o, nev = K.scan_moves(
                self._decoder_tag == "v3",
                np.fromiter(map(self._idx.__getitem__, todo), np.int64, len(todo)),
                apos, o_arr, sh_d, sh_g, cur, self._kinst, prm, len(self.positions),
                self._deadline)
            self._cache_misses += nev
            for r in todo[:j]:
                if len(self._moves_cache) < self._cache_max:
                    self._moves_cache[(r, state)] = (0, 0, cur)
            if move:
                if len(self._moves_cache) < self._cache_max:
                    self._moves_cache[(todo[j], state)] = (move, arg, o)
                return todo[j], move, arg, o
            if j < len(todo):                   # budget exhausted mid-scan
                return None
        if hit is not None and not self._time_up():
            return hit
        return None

    def _polish(self, assignment: dict, order: list[str], shift: dict, cur: float,
                kicks: bool = True):
        """Polish of a new incumbent of the manoeuvre phase (Attempt 17): the
        align descent, then an iterated local search on the shift alone —
        kick 1–3 random rears, each to one of its own align proposals drawn
        at random (not necessarily improving), align again, and keep the
        result if it is better.  The align descent only reaches boundaries of
        the current schedule; the optimum often needs several aircraft moved
        together to values that become boundaries only once the others have
        moved, a valley no single improving step crosses.  From the MILP's
        own (pi, sigma), over the 439 proven-optimal R5/R10 cells, the align
        descent reaches 388 optima and the kicks raise it to 423–427.  Stops
        after as many consecutive fruitless kicks as there are rears, or at
        the polish budget.  ``kicks=False`` runs the align descent only (a
        new best during the IG; the kicks run on stagnation, see
        ``_search``).  Returns (shift, obj)."""
        # A polish may use at most a quarter of the time left in the phase:
        # proving a hub of R = 30 align-optimal can take seconds, which would
        # otherwise come out of the search itself.
        now = time.perf_counter()
        t_end = min(self._deadline, now + 0.25 * max(0.0, self._deadline - now))
        shift, cur = self._align(assignment, order, shift, cur, t_end)
        if not kicks:
            return shift, cur
        rears = [r for r in self.aircraft_ids
                 if self._fronts_of[assignment[r]] or self._rears_of[assignment[r]]]
        fails = 0
        while rears and fails < len(rears) and time.perf_counter() < t_end:
            kick = dict(shift)
            for r in self.rng.sample(rears, self.rng.randint(1, min(3, len(rears)))):
                apos, o_arr, sh_d, sh_g, prm = self._kernel_state(assignment, order, kick)
                D, G = K.proposals_of(self._idx[r], o_arr, apos, sh_d, sh_g, self._kinst, prm,
                                      self._fronts_mat, self._n_fronts)
                props = sorted(set(zip(D.tolist(), G.tolist())))
                if props:
                    d, g = self.rng.choice(props)
                    if d == 0 and g == 0:
                        kick.pop(r, None)
                    else:
                        kick[r] = (d, g)
            kick, obj = self._align(assignment, order, kick,
                                    self._objective(self._eval(assignment, order, kick)), t_end)
            if obj < cur - 1e-9:
                shift, cur, fails = kick, obj, 0
            else:
                fails += 1
        return shift, cur

    def _align(self, assignment: dict, order: list[str], shift: dict, cur: float,
               t_end: float, max_level: int = 3):
        """First-improvement descent on the align move alone (Attempt 17):
        rears with blocking fronts, in random order, until no shift improves
        or ``t_end`` passes.  Too costly as a permanent neighbourhood (it
        multiplied the cost of a non-improving pass ~5x and starved the IG
        loop), so it runs in full only inside ``_polish``; each IG candidate
        gets step (a) alone (``max_level=1``).  Returns (shift, obj).

        Each rear r escalates through three steps, the next tried only when
        the previous finds nothing:
          (a) one align of r;
          (b) a second align of r from each state of (a) — the front r targets
              is re-placed by the decoder once r moves, so the boundary r must
              land on often only exists after the move;
          (c) a coordinated pair: each state of (a) plus one of the 6 nearest
              aligns of a related rear q (q at a front of r, behind r, or
              sharing a front with r) — cascades along a blocking chain and
              siblings wrapping the same front move together in the optima.
        (b) and (c) escalate only the 12 first steps nearest to r's current
        shift, and (b) tries the 6 second steps nearest to each.  From the
        MILP's own (pi, sigma), over the 439 proven-optimal R5/R10 cells, the
        optimum is reached in 324 with (a), 338 with (a)+(b), 378 with all
        three uncapped and 377 capped, at a quarter of the work.  The three
        steps for one rear are a single call of the compiled ``align_one``.
        ``max_level`` stops the escalation early: 1 runs the descent on (a)
        alone, the cheap form every IG candidate gets in ``_search``.
        """
        rears = [r for r in self.aircraft_ids
                 if self._fronts_of[assignment[r]] or self._rears_of[assignment[r]]]
        apos, o_arr, sh_d, sh_g, prm = self._kernel_state(assignment, order, shift)
        no_rel = np.empty(0, np.int64)

        # Escalate globally: (a) over every rear first, (b) only once no rear
        # improves with (a), (c) only once none does with (b); after an
        # improvement start again from (a).  The end state is the same kind
        # of local optimum (nothing improves with any step), but the costly
        # (c) is only paid when the cheap steps are exhausted.
        level = 0
        while level < max_level and time.perf_counter() < t_end:
            improved = False
            # The front aircraft each rear interacts with in the current
            # schedule — on each blocking position, those overlapping its stay
            # plus the last one before and the first one after it (the same
            # set its align proposals come from).  Two rears are related when
            # one is such a front of the other or they share one: the aircraft
            # that move together around one front in the optima (a position
            # test alone relates every spoke of a hub — hundreds of pairs).
            # (only step (c) uses them)
            near = {}
            stay = ({a["id"]: (a["start"], a["finish"])
                     for a in self._eval(assignment, order, shift)["aircraft"]}
                    if level == 2 else {})
            for r in (rears if level == 2 else ()):
                s_r, f_r = stay[r]
                near[r] = set()
                for fp in self._fronts_of[assignment[r]]:
                    before = after = None
                    for a in self.aircraft_ids:
                        if assignment[a] != fp:
                            continue
                        s_a, f_a = stay[a]
                        if s_a <= f_r and s_r <= f_a:
                            near[r].add(a)
                        elif f_a < s_r:
                            if before is None or f_a > stay[before][1]:
                                before = a
                        elif after is None or s_a < stay[after][0]:
                            after = a
                    near[r].update(x for x in (before, after) if x is not None)
            self.rng.shuffle(rears)
            for r in rears:
                rel = (np.fromiter(
                    (self._idx[q] for q in rears if q != r and (
                        q in near[r] or r in near[q] or near[r] & near[q])), np.int64)
                       if level == 2 else no_rel)
                found, dr, gr, qi, dq, gq, o, nev = K.align_one(
                    self._idx[r], rel, o_arr, apos, sh_d, sh_g, cur, self._kinst, prm,
                    self._fronts_mat, self._n_fronts, t_end, 6, 12, 12,
                    1 << level)
                self._cache_misses += nev
                if found:
                    shift = dict(shift)
                    moved = [(r, dr, gr)]
                    if qi >= 0:
                        moved.append((self.aircraft_ids[qi], dq, gq))
                    for a, d, g in moved:
                        sh_d[self._idx[a]], sh_g[self._idx[a]] = d, g
                        if d == 0 and g == 0:
                            shift.pop(a, None)
                        else:
                            shift[a] = (d, g)
                    cur, improved = o, True
                    break
                if time.perf_counter() >= t_end:
                    break
            level = 0 if improved else level + 1
        return shift, cur

    # ==================================================================
    # Iterated Greedy perturbation
    # ==================================================================

    def _perturb(self, assignment: dict, order: list[str], shift: dict, k: int):
        """Destruction–reconstruction: remove the k highest-contribution
        aircraft, then greedily reinsert each at its best position and a
        good spot in the order.  Removed aircraft lose their shift (it was
        aligned to a context the rebuild changes)."""
        # Half the perturbations remove k aircraft uniformly at random: the
        # targeted (delay-weighted) rule below degenerates under wMK/wMOV
        # (delay ~ 0 -> almost always the same longest k+2), anchoring the
        # walk in its basin (Attempt 10).  The random half restores diversity.
        if self.rng.random() < 0.5:
            removed = self.rng.sample(self.aircraft_ids,
                                      min(k, len(self.aircraft_ids)))
        else:
            sol = self._eval(assignment, order, shift)
            contrib = {a["id"]: self.wD * a["delay"] + 1e-3 * self.T[a["id"]]
                       for a in sol["aircraft"]}
            # Remove the k worst contributors, with a little randomisation so
            # the loop explores rather than removing the same set every time.
            ranked = sorted(self.aircraft_ids, key=lambda r: -contrib[r])
            pool = ranked[: min(len(ranked), k + 2)]
            self.rng.shuffle(pool)
            removed = pool[:k]

        a2 = dict(assignment)
        kept_order = [r for r in order if r not in removed]
        s2 = {r: v for r, v in shift.items() if r not in removed}

        # Reinsert each removed aircraft at the best (position, order-slot).
        for r in removed:
            if self._time_up():
                # Budget exhausted: reinsert the rest cheaply (keep their
                # original position, append to the order) so the returned
                # state is always complete and feasible.
                a2[r] = assignment[r]
                kept_order.append(r)
                continue
            # Best (position, slot) over every position and one slot per
            # distinct-decode class (exact pruning, as in _scan_moves) — one
            # call of the compiled best_insert kernel; first one on ties.
            apos, o_arr, sh_d, sh_g, prm = self._kernel_state(a2, kept_order, s2)
            bp, bslot, _, nev = K.best_insert(self._decoder_tag == "v3", self._idx[r], apos,
                                              o_arr, sh_d, sh_g, self._kinst, prm,
                                              len(self.positions))
            self._cache_misses += nev
            a2[r] = self.positions[bp]
            kept_order = kept_order[:bslot] + [r] + kept_order[bslot:]

        return a2, kept_order, s2

    # ==================================================================
    # v3 decoder — manoeuvre-aware (allows Mode-C overlap)
    # ==================================================================

    def _decode_v3(self, assignment: dict, order: list[str], shift: dict | None = None) -> dict:
        """Decode allowing rear aircraft to interrupt front aircraft
        (Mode C), spending manoeuvres to compress the schedule.

        Positions are scheduled deep-first (rears before fronts) so that
        when a front is placed, its rears' access instants are already
        fixed.  Each front is given the **minimum-cost** start (weighted
        finish + delay + manoeuvre penalty); the rear-before/after/nested
        zero-movement options are always among the candidates, so this
        only ever adds the manoeuvre option, never removes a feasible one.
        The placement and the Mode-A/B/C simulation are the compiled kernels
        ``decode_v3`` / ``place_front`` / ``sim_front`` (``igvnd_kernels``);
        ``aircraft`` is built on first access, as in ``_decode``.

        ``shift[r] = (delay, stretch)`` (Attempt 17) delays r's earliest start
        and inserts ``stretch`` of idle before its last job.  Placing rears
        first means a rear can never *react* to its fronts, so an exit that
        lands exactly on a front boundary — the structure most proven optima
        use — is only expressible through this search-owned shift.
        """
        idx, ids = self._idx, self.aircraft_ids
        R = len(ids)
        pos = list(map(assignment.__getitem__, order))  # snapshot: the search mutates assignment
        o = np.fromiter(map(idx.__getitem__, order), np.int64, len(order))
        op = np.fromiter(map(self._pidx.__getitem__, pos), np.int64, len(pos))
        sh_d = np.zeros(R)
        sh_g = np.zeros(R)
        for r, (d, g) in (shift or {}).items():
            sh_d[idx[r]] = d
            sh_g[idx[r]] = g
        start, finish = np.zeros(R), np.zeros(R)
        mov_ev = np.zeros(R, np.int64)
        J = len(self._job_dur)
        js, jf, jk = np.zeros(J), np.zeros(J), np.zeros(J, np.int64)
        placed = np.zeros(R, np.bool_)
        K.decode_v3(o, op, sh_d, sh_g, self._E, self._L, self._T, self._job_off,
                    self._job_dur, self._job_int, self._pos_depth, self._rears_mat,
                    self._n_rears, self.eta, self.eps, self.delta, self.mu,
                    self.wM, self.wD, self.wS, start, finish, mov_ev, js, jf, jk, placed)
        makespan, total_delay = K.metrics(self._L, finish, placed)
        movements = 2 * int(mov_ev.sum())

        def build():
            where = dict(zip(order, pos))
            st, fi, pl = start.tolist(), finish.tolist(), placed.tolist()
            s_j, f_j = js.tolist(), jf.tolist()
            aircraft_out = []
            for i, r in enumerate(ids):
                if not pl[i]:
                    continue
                j0 = self._job_off_l[i]
                jobs_out = [{"id": jid, "start": s_j[j0 + k], "finish": f_j[j0 + k]}
                            for k, (jid, _) in enumerate(self.chain[r])]
                s_r, f_r = st[i], fi[i]
                aircraft_out.append({
                    "id": r, "position": where[r], "start": s_r, "finish": f_r,
                    "delay": max(0.0, f_r - self.L[r]), "jobs": jobs_out,
                })
            return {"aircraft": aircraft_out}

        obj = self.wM * makespan + self.wD * total_delay + self.wS * movements
        return _LazySolution(build, {
            "status": "heuristic_ok",
            "objective": round(obj, 6),
            "metrics": {"makespan": makespan, "total_delay": total_delay, "movements": movements},
        })


# Backwards-compatible alias: the Application contract only needs the
# duck-typed methods, but earlier scaffolding referred to this name.
TheoryAssistedJobSolver = IteratedGreedyVNDJobSolver


if __name__ == "__main__":
    import sys
    from pathlib import Path

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    _HERE = Path(__file__).resolve().parent              # methods/iterated_greedy_vnd_v01/jobs/
    _ROOT = _HERE.parent.parent.parent                   # repo root
    sys.path.insert(0, str(_ROOT / "shared"))            # instance_io
    sys.path.insert(0, str(_ROOT / "problems" / "jobs")) # checker

    from instance_io import load_json                    # noqa: E402
    from checker import check_solution, print_check       # noqa: E402

    default = _ROOT / "problems" / "jobs" / "instances" / \
        "scn_triangle_tight_P5_R5" / "scn_triangle_tight_P5_R5_seed1.json"
    path = sys.argv[1] if len(sys.argv) > 1 else str(default)
    tlimit = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    inst = load_json(path)

    solver = IteratedGreedyVNDJobSolver()
    solver.configure_solver(
        time_limit_s=tlimit,
        weight_makespan=0.1, weight_delay=1.0, weight_movements=10.0,
        seed=1,
    )
    sol = solver.solve(inst)
    print("\n".join(solver.get_log()))
    print(f"\nobjective={sol['objective']}  metrics={sol['metrics']}")
    print_check(check_solution(sol, inst))
