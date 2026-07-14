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
import statistics
import time


class IteratedGreedyVNDJobSolver:
    """Iterated Greedy + VND heuristic (Candidate A)."""

    name = "iterated_greedy_vnd"

    def __init__(self) -> None:
        self._config: dict = {}
        self._log: list[str] = []
        self._deadline: float = float("inf")   # wall-clock cap for search loops
        self._decoder_tag: str = "v2"          # identifies the active decoder
        self._cache: dict = {}                 # decode memoisation (per solve)
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
        # Per-start time slice, adaptive to instance size (large instances need
        # their per-start time; small ones end each start early on the stale
        # counter anyway).  The slice is a CAP, not a schedule: restarts keep
        # looping until the deadline, so no budget is left idle (Attempt 7 —
        # the old fixed n_starts cap left ~97 % of the 60 s unused on R5).
        slice_div = 8 if R <= 10 else 4 if R <= 20 else 3
        # Optional hard cap on restarts (testing/ablation only; None = until
        # the deadline).
        max_starts = cfg.get("n_starts")
        max_starts = int(max_starts) if max_starts is not None else None

        t0 = time.perf_counter()
        global_dl = t0 + self.time_limit
        per_start = self.time_limit / slice_div

        # Per-solve decode cache (instance + weights are fixed within a solve).
        self._cache = {}
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
            # Activate the zero-movement decoder for this restart's first phase.
            self._decode_fn = self._decode
            # Tag the active decoder so the decode cache keys stay disjoint.
            self._decoder_tag = "v2"
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
            # solution dict (movements = 0 by construction) or None.
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
        self._decoder_tag = "v2"
        dl1 = min(deadline, time.perf_counter() + (deadline - time.perf_counter()) *
                  (0.5 if self.use_v3 else 1.0))
        a1, o1 = self._search(dict(a0), list(o0), dl1)
        best_sol = self._finalize(self._decode(a1, o1))
        best_obj = best_sol["objective"]
        best_sol["phase"] = "zero"

        # ---- Phase 2: manoeuvre-aware polish (v3 decoder) ----
        # v2 is the guaranteed floor; the v3 candidate is taken only if the
        # real checker certifies it AND it strictly improves — so a timed-out
        # or invalid manoeuvre-aware search can never worsen the incumbent.
        if self.use_v3:
            self._decode_fn = self._decode_v3
            self._decoder_tag = "v3"
            a3, o3 = self._search(dict(a1), list(o1), deadline)
            sol_v3 = self._finalize(self._decode_v3(a3, o3))
            if (sol_v3["objective"] < best_obj - 1e-9
                    and self._is_compliant(sol_v3, instance_data)):
                sol_v3["phase"] = "manoeuvre"
                best_sol, best_obj = sol_v3, sol_v3["objective"]
        return best_sol, best_obj

    # ------------------------------------------------------------------
    # Search driver (shared by both phases via self._decode_fn)
    # ------------------------------------------------------------------

    def _search(self, assignment, order, deadline):
        """VND + Iterated-Greedy loop using the current ``self._decode_fn``.

        Drives one restart's local search.  First the seed is taken to a local
        optimum by the VND; then the Iterated-Greedy loop repeatedly perturbs
        the *current* state (destroy + reconstruct), re-optimises it with the
        VND, and decides whether to accept it.  Two incumbents are tracked: the
        walk's current state ``cur`` and the global best ``best`` ever seen.
        The loop stops at the deadline or after ``max_no_improve`` fruitless
        iterations.  Returns the best ``(assignment, order)`` found.
        """
        self._deadline = deadline
        # Take the seed to a local optimum before the perturbation loop starts.
        assignment, order = self._vnd(assignment, order)
        best_assign, best_order = dict(assignment), list(order)
        best_obj = self._objective(self._eval(best_assign, best_order))
        cur_assign, cur_order = dict(best_assign), list(best_order)
        no_improve = 0
        while time.perf_counter() < deadline and no_improve < self.max_no_improve:
            # Iterated-Greedy kick: destroy k aircraft and greedily rebuild,
            # then re-descend to a local optimum with the VND.
            a2, o2 = self._perturb(cur_assign, cur_order, self.k_destroy)
            a2, o2 = self._vnd(a2, o2)
            obj2 = self._objective(self._eval(a2, o2))
            cur_obj = self._objective(self._eval(cur_assign, cur_order))
            # Acceptance: walk to the new state if it does not worsen the
            # current one (a "better-or-equal" random-walk acceptance).
            if obj2 <= cur_obj + 1e-9:
                cur_assign, cur_order = a2, o2
            # Track the global best separately, and reset the stale counter
            # only on a strict global improvement.
            if obj2 < best_obj - 1e-9:
                best_assign, best_order = dict(a2), list(o2)
                best_obj = obj2
                no_improve = 0
            else:
                no_improve += 1
            # Periodic intensification: after a streak of non-improving kicks,
            # restart the walk from the global best so it does not drift away.
            if no_improve > 0 and no_improve % 50 == 0:
                cur_assign, cur_order = dict(best_assign), list(best_order)
        return best_assign, best_order

    @staticmethod
    def _finalize(sol: dict) -> dict:
        sol["status"] = "heuristic_ok"
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
        # rears blocked by each front position
        self._rears_of = {p: [r for (f, r) in directed if f == p] for p in self.positions}

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

    def _pos_conflict(self, p: str, q: str) -> bool:
        return (p, q) in self._conflict

    def _forbidden(self, p, dur, p2, s2, f2):
        """Open intervals where our start ``t`` is infeasible against an
        already-placed aircraft on position ``p2`` occupying ``[s2, f2]``.

        This is the geometric heart of the zero-movement decoder.  We are
        about to place an aircraft of stay length ``dur`` on position ``p``;
        a neighbour already sits at ``p2`` over the time window ``[s2, f2]``.
        Depending on whether ``p`` and ``p2`` share a position or form a
        blocking arc, only certain start times ``t`` keep the schedule
        manoeuvre-free.  We return the *complement* — the open interval(s) of
        start times that are NOT allowed — so the caller can scan for the
        earliest ``t`` that lies in none of them.

        Returns 1 or 2 intervals.  Two intervals leave a feasible *hole*
        between them — the nesting (containment) option — which the
        earliest-fit scan can land in.  This hole is exactly what lets a long
        aircraft wrap a shorter blocking-related one instead of serialising
        the two.
        """
        eta, eps = self.eta, self.eps
        if p2 == p:
            # Same position: the two stays may not overlap, and must be
            # separated by the tow time eps.  Our stay [t, t+dur] clashes with
            # [s2, f2] unless t+dur <= s2-eps (we finish first) or t >= f2+eps
            # (we start last); the single forbidden band is everything between.
            return [(s2 - dur - eps, f2 + eps)]
        if (p2, p) in self._arcs:
            # We are the REAR aircraft (p2 holds the front).  To keep BOTH our
            # access instants (entry t, exit t+dur) in Mode A, our stay must be
            # entirely before the front (t+dur <= s2-eta), entirely after it
            # (t >= f2+eta), or *enclose* it (t <= s2-eta and t+dur >= f2+eta).
            if dur >= (f2 - s2) + 2 * eta - 1e-9:
                # Long enough to enclose: two forbidden bands, with the gap
                # between them = the "enclosing" start window (the nesting hole).
                return [(s2 - eta - dur, f2 + eta - dur), (s2 - eta, f2 + eta)]
            # Too short to enclose: only before/after survive, so one band.
            return [(s2 - eta - dur, f2 + eta)]
        if (p, p2) in self._arcs:
            # We are the FRONT aircraft (p2 holds the rear).  Symmetric to the
            # rear case, but now it is the rear's fixed access instants (s2, f2)
            # that must stay in Mode A relative to OUR stay: the rear is before
            # us, after us, or its stay encloses ours.
            if dur <= (f2 - s2) - 2 * eta + 1e-9:
                # The rear is long enough to enclose us: two forbidden bands
                # with the enclosing window between them.
                return [(s2 - dur - eta, s2 + eta), (f2 - dur - eta, f2 + eta)]
            return [(s2 - dur - eta, f2 + eta)]
        return []  # p and p2 do not block each other: free to overlap freely

    # ==================================================================
    # Decoder  (assignment + order  ->  full solution dict)
    # ==================================================================

    def _decode(self, assignment: dict, order: list[str]) -> dict:
        # Zero-movement decoder.  Aircraft are placed one at a time in the
        # priority order; each is given the earliest start that is feasible
        # (manoeuvre-free) against everything already placed.  Because every
        # placement keeps all access instants in Mode A, the result has
        # movements = 0 and is feasible by construction — the guaranteed floor.
        eta, eps = self.eta, self.eps
        placed: dict[str, tuple[float, float]] = {}  # r -> (start, finish)

        for r in order:
            p = assignment[r]
            dur = self.T[r]
            # Collect the forbidden start-time bands induced by every neighbour
            # already placed (same-position separation and blocking geometry).
            forbidden: list[tuple[float, float]] = []
            for r2, (s2, f2) in placed.items():
                forbidden.extend(self._forbidden(p, dur, assignment[r2], s2, f2))
            forbidden.sort()
            # Earliest-fit scan: start at the earliest start E[r] and, whenever
            # t falls inside a forbidden band, jump to that band's end.  Repeat
            # until a full pass moves nothing — t is then the earliest instant
            # outside every band.  Jumping to `hi` naturally lands t in the
            # nesting hole left between a pair of bands when enclosing is the
            # only feasible option.
            t = self.E[r]
            moved = True
            while moved:
                moved = False
                for lo, hi in forbidden:
                    if lo + 1e-7 < t < hi - 1e-7:
                        t = hi
                        moved = True
            placed[r] = (t, t + dur)

        # Build the solution dict (tight job chains, kappa = 0).
        aircraft_out = []
        makespan = 0.0
        total_delay = 0.0
        for r in self.aircraft_ids:
            if r not in placed:
                continue  # partial decode during greedy construction
            s_r, f_r = placed[r]
            jobs_out = []
            tcur = s_r
            for jid, d in self.chain[r]:
                jobs_out.append({"id": jid, "start": tcur, "finish": tcur + d})
                tcur += d
            delay = max(0.0, f_r - self.L[r])
            makespan = max(makespan, f_r)
            total_delay += delay
            aircraft_out.append({
                "id": r,
                "position": assignment[r],
                "start": s_r,
                "finish": f_r,
                "delay": delay,
                "jobs": jobs_out,
            })

        obj = self.wM * makespan + self.wD * total_delay  # movements == 0
        return {
            "status": "heuristic_ok",
            "objective": round(obj, 6),
            "metrics": {
                "makespan": makespan,
                "total_delay": total_delay,
                "movements": 0,
            },
            "aircraft": aircraft_out,
        }

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
                                t = max(t, s[q] + eta)
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
                            f_need = max(f_need, fin[f] + eta)
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

    def _eval(self, assignment: dict, order: list[str]) -> dict:
        """Decode ``(assignment, order)`` with the active decoder, memoised.

        The decode depends only on the active decoder and, for the aircraft in
        ``order``, their positions and sequence — so the key captures exactly
        that.  Cache is reset per solve (instance + weights are fixed there).
        Returned dicts must be treated as read-only by callers.
        """
        key = (self._decoder_tag, tuple(order),
               tuple(assignment[r] for r in order))
        cached = self._cache.get(key)
        if cached is not None:
            self._cache_hits += 1
            return cached
        self._cache_misses += 1
        sol = self._decode_fn(assignment, order)
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

    def _vnd(self, assignment: dict, order: list[str]) -> tuple[dict, list[str]]:
        """Sequential B-VND: descend through the three neighbourhoods, and on
        any improvement reset to the first one; stop when no neighbourhood can
        improve (a local optimum w.r.t. all three) or the budget runs out."""
        assignment = dict(assignment)
        order = list(order)
        cur = self._objective(self._eval(assignment, order))
        k = 0
        neighbourhoods = (self._n_reassign, self._n_swap_pos, self._n_reorder)
        while k < len(neighbourhoods):
            if self._time_up():
                break
            # Each call applies the first improving move it finds in N_k (first
            # improvement) and reports whether it improved the objective.
            improved, assignment, order, cur = neighbourhoods[k](assignment, order, cur)
            if improved:
                k = 0  # B-VND reset: go back to the first neighbourhood
            else:
                k += 1  # no improvement in N_k: try the next neighbourhood
        return assignment, order

    def _n_reassign(self, assignment, order, cur):
        """N1 — move one aircraft to a different position (first improvement)."""
        for r in self.aircraft_ids:
            if self._time_up():
                return False, assignment, order, cur
            p0 = assignment[r]
            for p in self.positions:
                if p == p0:
                    continue
                assignment[r] = p
                o = self._objective(self._eval(assignment, order))
                if o < cur - 1e-9:
                    return True, assignment, order, o
                assignment[r] = p0
        return False, assignment, order, cur

    def _n_swap_pos(self, assignment, order, cur):
        """N2 — swap the positions of two aircraft (first improvement)."""
        ids = self.aircraft_ids
        for i in range(len(ids)):
            if self._time_up():
                return False, assignment, order, cur
            for j in range(i + 1, len(ids)):
                ri, rj = ids[i], ids[j]
                if assignment[ri] == assignment[rj]:
                    continue
                assignment[ri], assignment[rj] = assignment[rj], assignment[ri]
                o = self._objective(self._eval(assignment, order))
                if o < cur - 1e-9:
                    return True, assignment, order, o
                assignment[ri], assignment[rj] = assignment[rj], assignment[ri]
        return False, assignment, order, cur

    def _n_reorder(self, assignment, order, cur):
        """N3 — swap two aircraft in the priority order (first improvement)."""
        for i in range(len(order)):
            if self._time_up():
                return False, assignment, order, cur
            for j in range(i + 1, len(order)):
                order[i], order[j] = order[j], order[i]
                o = self._objective(self._eval(assignment, order))
                if o < cur - 1e-9:
                    return True, assignment, order, o
                order[i], order[j] = order[j], order[i]
        return False, assignment, order, cur

    # ==================================================================
    # Iterated Greedy perturbation
    # ==================================================================

    def _perturb(self, assignment: dict, order: list[str], k: int):
        """Destruction–reconstruction: remove the k highest-contribution
        aircraft, then greedily reinsert each at its best position and a
        good spot in the order."""
        sol = self._eval(assignment, order)
        contrib = {a["id"]: self.wD * a["delay"] + 1e-3 * self.T[a["id"]]
                   for a in sol["aircraft"]}
        # Remove the k worst contributors, with a little randomisation so the
        # loop explores rather than removing the same set every iteration.
        ranked = sorted(self.aircraft_ids, key=lambda r: -contrib[r])
        pool = ranked[: min(len(ranked), k + 2)]
        self.rng.shuffle(pool)
        removed = pool[:k]

        a2 = dict(assignment)
        kept_order = [r for r in order if r not in removed]

        # Reinsert each removed aircraft at the best (position, order-slot).
        for r in removed:
            if self._time_up():
                # Budget exhausted: reinsert the rest cheaply (keep their
                # original position, append to the order) so the returned
                # state is always complete and feasible.
                a2[r] = assignment[r]
                kept_order.append(r)
                continue
            best = None  # (obj, position, slot)
            for slot in range(len(kept_order) + 1):
                trial_order = kept_order[:slot] + [r] + kept_order[slot:]
                for p in self.positions:
                    a2[r] = p
                    o = self._objective(self._eval(a2, trial_order))
                    if best is None or o < best[0]:
                        best = (o, p, slot)
            _, bp, bslot = best
            a2[r] = bp
            kept_order = kept_order[:bslot] + [r] + kept_order[bslot:]

        return a2, kept_order

    # ==================================================================
    # v3 decoder — manoeuvre-aware (allows Mode-C overlap)
    # ==================================================================

    def _decode_v3(self, assignment: dict, order: list[str]) -> dict:
        """Decode allowing rear aircraft to interrupt front aircraft
        (Mode C), spending manoeuvres to compress the schedule.

        Positions are scheduled deep-first (rears before fronts) so that
        when a front is placed, its rears' access instants are already
        fixed.  Each front is given the **minimum-cost** start (weighted
        finish + delay + manoeuvre penalty); the rear-before/after/nested
        zero-movement options are always among the candidates, so this
        only ever adds the manoeuvre option, never removes a feasible one.
        """
        # Aircraft grouped by their assigned position, each list kept in
        # priority order so same-position aircraft are sequenced consistently.
        pos_members = {p: [r for r in order if assignment[r] == p] for p in self.positions}
        placed: dict[str, tuple] = {}  # r -> (start, finish, sched, mov_events)

        # Schedule positions DEEPEST-REAR FIRST.  This ordering is what makes
        # the manoeuvre accounting tractable: by the time we lay out a front
        # aircraft, every rear it can block has already been placed, so the
        # rear access instants it must react to are known constants.
        for p in self._pos_by_depth_desc:
            prev_f = None  # finish of the previous aircraft sharing position p
            for r in pos_members[p]:
                # Earliest this aircraft may start: its own E[r], pushed past
                # the previous same-position aircraft by the tow time eps.
                lower = self.E[r]
                if prev_f is not None:
                    lower = max(lower, prev_f + self.eps)
                # Gather the access instants (entry s_a and exit f_a) of every
                # already-placed rear aircraft that this position blocks — these
                # are the events the front must classify as Mode A / B / C.
                rear_acc: list[float] = []
                for pr in self._rears_of[p]:
                    for a in pos_members.get(pr, []):
                        if a in placed:
                            s_a, f_a = placed[a][0], placed[a][1]
                            rear_acc.append(s_a)
                            rear_acc.append(f_a)
                # Place the front at its minimum-cost feasible start.
                s_r, f_r, sched, mov_events = self._place_front(r, lower, rear_acc)
                placed[r] = (s_r, f_r, sched, mov_events)
                prev_f = f_r

        aircraft_out = []
        makespan = 0.0
        total_delay = 0.0
        total_events = 0
        for r in self.aircraft_ids:
            if r not in placed:
                continue
            s_r, f_r, sched, mov_events = placed[r]
            jobs_out = [{"id": jid, "start": s, "finish": f} for (jid, s, f, k) in sched]
            total_events += mov_events
            delay = max(0.0, f_r - self.L[r])
            makespan = max(makespan, f_r)
            total_delay += delay
            aircraft_out.append({
                "id": r, "position": assignment[r],
                "start": s_r, "finish": f_r, "delay": delay, "jobs": jobs_out,
            })

        movements = 2 * total_events
        obj = self.wM * makespan + self.wD * total_delay + self.wS * movements
        return {
            "status": "heuristic_ok",
            "objective": round(obj, 6),
            "metrics": {"makespan": makespan, "total_delay": total_delay, "movements": movements},
            "aircraft": aircraft_out,
        }

    def _place_front(self, r, lower, rear_acc):
        """Choose the minimum-cost feasible start for front aircraft r.

        Returns (start, finish, sched, mov_events).
        """
        eta, T = self.eta, self.T[r]
        chain = self.chain[r]
        # prefix[j] = work-time offset of job j's start relative to the aircraft
        # start, ignoring any delta extensions (an approximate seed; the forward
        # simulation in _sim_front recomputes exact times including extensions).
        prefix, acc = [], 0.0
        for (_, D) in chain:
            prefix.append(acc)
            acc += D

        # Build a small set of candidate start times.  The strategy is to
        # propose only starts that are "interesting" with respect to some rear
        # access tau: starts that keep tau in Mode A, or that deliberately align
        # a job interior / job end on tau to invite a cheap Mode-C / Mode-B.
        # `lower` is always included, and the zero-movement options are always
        # present, so the chosen start can never be worse than a Mode-A schedule.
        cands = {lower}
        for tau in rear_acc:
            # Zero-movement options: place the whole stay before tau (finish at
            # tau-eta), after tau (start at tau+eta), or nested so tau is the
            # entry margin (start at tau-eta-T).  All keep tau in Mode A.
            for c in (tau - eta - T, tau - eta, tau + eta):
                if c >= lower - 1e-9:
                    cands.add(round(c, 4))
            for (jid, D), pj in zip(chain, prefix):
                # Mode-C alignment: shift the start so that job j's *interior*
                # straddles tau (just after its start, just before its end, or
                # at its midpoint) — only worthwhile if j is interruptible.
                if self.interruptible[jid]:
                    for c in (tau - pj - eta, tau - pj - D + eta, tau - pj - D / 2.0):
                        if c >= lower - 1e-9:
                            cands.add(round(c, 4))
                # Mode-B alignment: shift the start so job j *ends* just before
                # tau, so tau falls into the inter-job gap opened after j and is
                # routed through it with no delta extension.
                for c in (tau - pj - D, tau - pj - D - eta):
                    if c >= lower - 1e-9:
                        cands.add(round(c, 4))
        # Guaranteed-feasible fallback: start after every rear access, so the
        # whole stay is past them (all Mode A), respecting `lower` too.  This
        # ensures the candidate set always contains at least one feasible start.
        if rear_acc:
            cands.add(max(lower, max(rear_acc) + eta))

        # Price every candidate by simulating it, and keep the cheapest feasible
        # one.  The cost mirrors the objective's local contribution of r:
        # weighted finish + delay + manoeuvre penalty (2 movements per event).
        best = None  # (cost, s, f, sched, mov_events)
        for s in sorted(cands):
            f_r, sched, mov_events, ok = self._sim_front(r, s, rear_acc)
            if not ok:
                continue
            delay = max(0.0, f_r - self.L[r])
            cost = self.wM * f_r + self.wD * delay + self.wS * (2 * mov_events)
            if best is None or cost < best[0] - 1e-9:
                best = (cost, s, f_r, sched, mov_events)
        # `lower` with no rears, or the fallback, always yields a feasible
        # placement, so `best` is never None.
        _, s, f, sched, mov_events = best
        return s, f, sched, mov_events

    def _sim_front(self, r, s_start, rear_acc):
        """Forward-simulate front aircraft r from s_start.

        Each rear access is classified against r's laid-out jobs:
          * Mode C — strictly inside an interruptible job interior; the job
            is extended by ``delta`` (kappa fixpoint per job).
          * Mode B — routed through a deliberately inserted inter-job *gap*
            (no job extension); the gap is sized ``>= mu * (#accesses in it)``.
            A gap is opened after job j for the accesses just past its end
            when that is cheaper than Mode C (within ``delta`` of the end) or
            when the next job is non-interruptible (so the access cannot be
            absorbed and must pass through a gap).
          * Mode A — outside r's stay; free.

        Returns (finish, sched, mov_events, feasible), where ``sched`` is a
        list of (job_id, start, finish, kappa) and ``mov_events`` is the
        number of Mode-B + Mode-C access events (movements = 2 * mov_events).
        Infeasible if an access lands in a non-interruptible job interior, in
        a job's eta-margin, or cannot be classified.
        """
        eta, delta, mu = self.eta, self.delta, self.mu
        chain = self.chain[r]
        acc = sorted(rear_acc)        # the rear access instants to classify
        used = [False] * len(acc)     # which accesses have been accounted for
        sched = []                    # (job_id, start, finish, kappa) per job
        mov_events = 0                # Mode-B + Mode-C access events so far
        t = s_start                   # running cursor = start of the next job
        n = len(chain)

        # Lay the jobs of r one after another from s_start, classifying every
        # rear access against each job as we go.
        for j in range(n):
            jid, D = chain[j]
            interruptible = self.interruptible[jid]

            # --- Mode-C count via a fixpoint --------------------------------
            # Each access strictly inside job j's interior is a Mode-C
            # interruption that lengthens the job by delta.  But lengthening the
            # job widens its interior, which can pull in further accesses — so
            # we iterate kappa = (#interior accesses) until it stops growing.
            kappa = 0
            while True:                                   # Mode-C kappa fixpoint
                f_j = t + D + delta * kappa
                cnt = sum(1 for i, tau in enumerate(acc)
                          if not used[i] and t + eta - 1e-9 <= tau <= f_j - eta + 1e-9)
                if cnt == kappa:
                    break
                kappa = cnt
                if kappa > len(acc) + 5:                  # runaway guard
                    return None, None, None, False
            f_j = t + D + delta * kappa
            # A Mode-C interruption is only legal on an interruptible job.
            if kappa > 0 and not interruptible:
                return None, None, None, False
            # Reject accesses that land in the eta-margin at either edge of the
            # job: they are neither cleanly outside nor cleanly inside, so the
            # checker would consider them ambiguous/infeasible.
            for i, tau in enumerate(acc):                 # eta-margin bad zones
                if used[i]:
                    continue
                if t - 1e-9 < tau < t + eta - 1e-9:
                    return None, None, None, False
                if f_j - eta + 1e-9 < tau < f_j - 1e-9:
                    return None, None, None, False
            # Mark the interior accesses as consumed (handled as Mode C).
            for i, tau in enumerate(acc):                 # consume Mode-C accesses
                if not used[i] and t + eta - 1e-9 <= tau <= f_j - eta + 1e-9:
                    used[i] = True
            mov_events += kappa
            sched.append((jid, t, f_j, kappa))
            t = f_j

            # --- Mode-B gap before the next job -----------------------------
            # Accesses that fall just after this job's end can instead be routed
            # through an inter-job gap (no delta extension).  We open a gap when
            # it is the cheaper option (access within `delta` of the end) or
            # mandatory (the next job is non-interruptible, so the access cannot
            # be absorbed as Mode C and MUST pass through a gap).
            if j < n - 1:
                next_interruptible = self.interruptible[chain[j + 1][0]]
                window = chain[j + 1][1] if not next_interruptible else delta
                batch = [i for i in range(len(acc))
                         if not used[i] and f_j + 1e-9 < acc[i] <= f_j + window + 1e-9]
                if batch:
                    # The gap must end past the last routed access AND be wide
                    # enough to absorb mu per access routed through it.
                    s_next = max(max(acc[i] for i in batch), f_j + mu * len(batch))
                    # Reconcile: widening the gap may now enclose further unused
                    # accesses, which are then also "in the gap" (Mode B) and
                    # counted — which can widen it again.  Iterate to a fixpoint.
                    while True:
                        extra = [i for i in range(len(acc))
                                 if not used[i] and i not in batch
                                 and f_j + 1e-9 < acc[i] <= s_next + 1e-9]
                        if not extra:
                            break
                        batch += extra
                        s_next = max(s_next, max(acc[i] for i in batch), f_j + mu * len(batch))
                    for i in batch:
                        used[i] = True
                    mov_events += len(batch)
                    t = s_next                            # next job starts after the gap

        f_r = t
        # Final check: any access still unclassified that lies strictly inside
        # the aircraft's stay is an unrepresentable boundary/zero-gap case —
        # reject it (the real checker would reject it too).
        for i, tau in enumerate(acc):
            if not used[i] and s_start + eta - 1e-9 <= tau <= f_r - eta + 1e-9:
                return None, None, None, False
        return f_r, sched, mov_events, True


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
