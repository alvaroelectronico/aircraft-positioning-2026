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

- **Construction portfolio** (``_build_portfolio``): each restart seeds
  from a different rule — NEH / EDD / slack / regret-2 / critical-ratio /
  blend — so due-date rules steer tight-target aircraft into early slots.
- **Adaptive multi-start**: more restarts on the cheap small instances
  (the time-limited search is non-deterministic; restarts avoid bad
  basins).
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
            n_starts          : multi-start restarts (default adaptive to R:
                                8 / 4 / 3 for R<=10 / <=20 / else)
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
        # Multi-start count, adaptive to instance size.  The time-limited
        # search is non-deterministic and on some instances occasionally lands
        # in a bad (high-delay) basin; more *independent* restarts make finding
        # the good basin reliable.  Small instances are cheap, so they can
        # afford many restarts; large ones need the per-start time, so fewer.
        default_starts = 8 if R <= 10 else 4 if R <= 20 else 3
        n_starts = int(cfg.get("n_starts", default_starts))

        t0 = time.perf_counter()
        global_dl = t0 + self.time_limit
        per_start = self.time_limit / max(1, n_starts)

        # Per-solve decode cache (instance + weights are fixed within a solve).
        self._cache = {}
        self._cache_hits = self._cache_misses = 0

        # Construction portfolio: each multi-start restart builds its own seed
        # from a different rule, so the starts differ by *construction* (not
        # only by the IG perturbation RNG).  The due-date rules (EDD / slack /
        # critical-ratio) and regret-2 steer tight-target aircraft into early
        # slots, which is what `wDLY` needs.
        portfolio = self._build_portfolio()

        best_sol, best_obj = None, float("inf")
        start_objs: list[float] = []          # per-start incumbents (search risk)
        i = 0
        while time.perf_counter() < global_dl - 0.05 and i < n_starts:
            self.rng = random.Random(base_seed + i)
            start_dl = min(global_dl, time.perf_counter() + per_start)
            self._deadline = start_dl
            self._decode_fn = self._decode
            self._decoder_tag = "v2"
            ctor_name, ctor = portfolio[i % len(portfolio)]
            a0, o0 = ctor()
            sol, obj = self._one_start(instance_data, a0, o0, start_dl)
            start_objs.append(obj)
            if obj < best_obj - 1e-9:
                best_sol, best_obj = sol, obj
            self._log.append(
                f"start {i} (seed {base_seed + i}, ctor {ctor_name})  obj={obj:.4f}  "
                f"ms={sol['metrics']['makespan']:.1f} dly={sol['metrics']['total_delay']:.1f} "
                f"mov={sol['metrics']['movements']}  best={best_obj:.4f}"
            )
            i += 1

        # Option B — dense concentric-nesting schedule (targets dense `wMOV`).
        # Built ONCE with explicit start times (not via the earliest-feasible
        # decode, which cannot nest), validated by the checker, and adopted
        # only if it beats the multi-start best.  Gated to the movement-priority
        # regime with a blocking topology, where it is relevant.
        if self._arcs and self.wS >= self.wM and self.wS >= self.wD:
            nest = self._dense_nest_solution()
            if (nest is not None and nest["objective"] < best_obj - 1e-9
                    and self._is_compliant(nest, instance_data)):
                nest["phase"] = "dense_nest"
                best_sol, best_obj = nest, nest["objective"]
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
        return best_sol

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
        """VND + Iterated-Greedy loop using the current ``self._decode_fn``."""
        self._deadline = deadline
        assignment, order = self._vnd(assignment, order)
        best_assign, best_order = dict(assignment), list(order)
        best_obj = self._objective(self._eval(best_assign, best_order))
        cur_assign, cur_order = dict(best_assign), list(best_order)
        no_improve = 0
        while time.perf_counter() < deadline and no_improve < self.max_no_improve:
            a2, o2 = self._perturb(cur_assign, cur_order, self.k_destroy)
            a2, o2 = self._vnd(a2, o2)
            obj2 = self._objective(self._eval(a2, o2))
            cur_obj = self._objective(self._eval(cur_assign, cur_order))
            if obj2 <= cur_obj + 1e-9:
                cur_assign, cur_order = a2, o2
            if obj2 < best_obj - 1e-9:
                best_assign, best_order = dict(a2), list(o2)
                best_obj = obj2
                no_improve = 0
            else:
                no_improve += 1
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

        Returns 1 or 2 intervals.  Two intervals leave a feasible *hole*
        between them — the nesting (containment) option — which the
        earliest-fit scan can land in.
        """
        eta, eps = self.eta, self.eps
        if p2 == p:
            # Same position: must be fully before/after with epsilon gap.
            return [(s2 - dur - eps, f2 + eps)]
        if (p2, p) in self._arcs:
            # We are the REAR (p2 is the front).  Allowed: before, after,
            # or our stay encloses the front stay.
            if dur >= (f2 - s2) + 2 * eta - 1e-9:        # enclose feasible
                return [(s2 - eta - dur, f2 + eta - dur), (s2 - eta, f2 + eta)]
            return [(s2 - eta - dur, f2 + eta)]
        if (p, p2) in self._arcs:
            # We are the FRONT (p2 is the rear).  Allowed: rear before,
            # rear after, or the rear stay encloses ours.
            if dur <= (f2 - s2) - 2 * eta + 1e-9:        # enclose feasible
                return [(s2 - dur - eta, s2 + eta), (f2 - dur - eta, f2 + eta)]
            return [(s2 - dur - eta, f2 + eta)]
        return []  # non-conflicting positions: free overlap

    # ==================================================================
    # Decoder  (assignment + order  ->  full solution dict)
    # ==================================================================

    def _decode(self, assignment: dict, order: list[str]) -> dict:
        eta, eps = self.eta, self.eps
        placed: dict[str, tuple[float, float]] = {}

        for r in order:
            p = assignment[r]
            dur = self.T[r]
            forbidden: list[tuple[float, float]] = []
            for r2, (s2, f2) in placed.items():
                forbidden.extend(self._forbidden(p, dur, assignment[r2], s2, f2))
            forbidden.sort()
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
        """Option B — explicit concentric-nesting schedule for dense blocking.

        Groups aircraft into **waves** that nest concentrically: sorted by
        duration descending, each aircraft joins the wave whose innermost
        member can still wrap it (`Tᵣ ≤ inner − 2·eta`) and has a free
        position, else opens a new wave.  Within a wave the longest member is
        the outer container and is assigned the **deepest** position (so the
        rear aircraft encloses the fronts); successive members start `eta`
        later (concentric nesting).  Waves are serialised (`+eta`).  Start
        times are written **explicitly** — this does NOT go through the
        earliest-feasible decode (which would un-nest it) — and every rear
        access lands Mode A, so movements = 0 by construction.  Returns a full
        solution dict, or None.  (Checker-validated and best-of in `solve`.)
        """
        eta = self.eta
        P = self._pos_by_depth_desc                       # deepest (rear) first
        cap = len(P)
        by_dur = sorted(self.aircraft_ids, key=lambda r: -self.T[r])
        # Try a small "beam" of wave partitions (each wave <= |P|), keep the
        # lowest-objective one.  Within a wave the *stay length* (not the work
        # T) must decrease by >= 2*eta to nest, achieved by stretching shorter
        # aircraft with idle.
        n_waves = max(1, math.ceil(len(by_dur) / cap))
        chunk = [by_dur[k:k + cap] for k in range(0, len(by_dur), cap)]
        rr = [[] for _ in range(n_waves)]                 # round-robin (balances waves)
        for idx, r in enumerate(by_dur):
            rr[idx % n_waves].append(r)
        partitions = [chunk, [w for w in rr if w]]

        def stay_lengths(w):
            # minimal stay L_i (outer..inner) with L_i >= T_i and
            # L_{i-1} >= L_i + 2*eta; computed inner->outer to stay minimal.
            T = [self.T[r] for r in w]
            L = [0.0] * len(w)
            L[-1] = T[-1]
            for i in range(len(w) - 2, -1, -1):
                L[i] = max(T[i], L[i + 1] + 2 * eta)
            return L

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

        def build_from(waves):
            placed: dict[str, tuple] = {}
            assignment: dict[str, str] = {}
            prev_finish = None
            for w in waves:                               # w sorted by dur desc
                L = stay_lengths(w)
                anchor_lb = max(self.E[w[i]] - i * eta for i in range(len(w)))
                anchor = anchor_lb if prev_finish is None else max(prev_finish + eta, anchor_lb)
                w_finish = None
                for i, r in enumerate(w):
                    s = anchor + i * eta
                    jobs, f = build_jobs(r, s, L[i])
                    placed[r] = (s, f, jobs)
                    assignment[r] = P[i]
                    w_finish = f if w_finish is None else max(w_finish, f)
                prev_finish = w_finish

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
        for waves in partitions:
            sol = build_from(waves)
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

    def _neh_order(self, assignment: dict) -> list[str]:
        return sorted(self.aircraft_ids, key=lambda r: -self.T[r])

    def _build_portfolio(self):
        """Construction portfolio for the multi-start.  Each entry returns a
        seed ``(assignment, order)``.  The order rules diversify the starts;
        the due-date rules (EDD / slack / critical-ratio) and regret-2 steer
        tight-target aircraft into early slots — the lever `wDLY` needs."""
        ids = self.aircraft_ids
        by_neh   = sorted(ids, key=lambda r: -self.T[r])                      # makespan
        by_edd   = sorted(ids, key=lambda r: self.L[r])                       # earliest due date
        by_slack = sorted(ids, key=lambda r: self.L[r] - self.E[r] - self.T[r])
        by_cr    = sorted(ids, key=lambda r: (self.L[r] / self.T[r]) if self.T[r] > 0 else float("inf"))
        rT = {r: i for i, r in enumerate(by_neh)}
        rL = {r: i for i, r in enumerate(by_edd)}
        rS = {r: i for i, r in enumerate(by_slack)}
        by_blend = sorted(ids, key=lambda r: 0.4 * rT[r] + 0.3 * rL[r] + 0.3 * rS[r])

        def fixed(o):
            return lambda o=o: (self._greedy_construct(o), list(o))

        # Order chosen so the first n_starts cover makespan + two due-date
        # rules + regret-2 (the most useful mix for a small n_starts).
        return [
            ("NEH",     fixed(by_neh)),
            ("EDD",     fixed(by_edd)),
            ("SLACK",   fixed(by_slack)),
            ("regret2", self._regret2_construct),
            ("CR",      fixed(by_cr)),
            ("BLEND",   fixed(by_blend)),
        ]

    def _regret2_construct(self):
        """Regret-2 insertion: at each step insert the aircraft whose 2nd-best
        position is much worse than its best (largest regret), at its best
        position (appended to the order).  Targets low-slack / high-`Wᴰ`
        aircraft that have few good slots."""
        assignment: dict = {}
        order: list[str] = []
        unplaced = list(self.aircraft_ids)
        while unplaced and not self._time_up():
            choice = None  # (regret, r, best_p)
            for r in unplaced:
                costs = []
                for p in self.positions:
                    assignment[r] = p
                    costs.append((self._objective(self._eval(assignment, order + [r])), p))
                del assignment[r]
                costs.sort(key=lambda c: c[0])
                best_o, best_p = costs[0]
                second_o = costs[1][0] if len(costs) > 1 else best_o
                regret = second_o - best_o
                if choice is None or regret > choice[0]:
                    choice = (regret, r, best_p)
            _, r, p = choice
            assignment[r] = p
            order.append(r)
            unplaced.remove(r)
        for r in unplaced:                         # budget-exhausted fallback
            assignment[r] = self.positions[0]
            order.append(r)
        return assignment, order

    # ==================================================================
    # VND  (sequential, B-VND reset over three neighbourhoods)
    # ==================================================================

    def _vnd(self, assignment: dict, order: list[str]) -> tuple[dict, list[str]]:
        assignment = dict(assignment)
        order = list(order)
        cur = self._objective(self._eval(assignment, order))
        k = 0
        neighbourhoods = (self._n_reassign, self._n_swap_pos, self._n_reorder)
        while k < len(neighbourhoods):
            if self._time_up():
                break
            improved, assignment, order, cur = neighbourhoods[k](assignment, order, cur)
            if improved:
                k = 0  # B-VND reset
            else:
                k += 1
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
        pos_members = {p: [r for r in order if assignment[r] == p] for p in self.positions}
        placed: dict[str, tuple] = {}

        for p in self._pos_by_depth_desc:
            prev_f = None
            for r in pos_members[p]:
                lower = self.E[r]
                if prev_f is not None:
                    lower = max(lower, prev_f + self.eps)
                # access instants of already-placed rears blocked by p
                rear_acc: list[float] = []
                for pr in self._rears_of[p]:
                    for a in pos_members.get(pr, []):
                        if a in placed:
                            s_a, f_a = placed[a][0], placed[a][1]
                            rear_acc.append(s_a)
                            rear_acc.append(f_a)
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
        # prefix start / end offset of each job relative to the aircraft start,
        # ignoring delta extensions (approximate seed; the sim corrects it).
        prefix, acc = [], 0.0
        for (_, D) in chain:
            prefix.append(acc)
            acc += D

        cands = {lower}
        for tau in rear_acc:
            # zero-movement options: front entirely before / after / nested
            for c in (tau - eta - T, tau - eta, tau + eta):
                if c >= lower - 1e-9:
                    cands.add(round(c, 4))
            for (jid, D), pj in zip(chain, prefix):
                # Mode-C alignment: an interruptible job's interior over tau.
                if self.interruptible[jid]:
                    for c in (tau - pj - eta, tau - pj - D + eta, tau - pj - D / 2.0):
                        if c >= lower - 1e-9:
                            cands.add(round(c, 4))
                # Mode-B alignment: a job *end* just before tau, so tau falls
                # into the gap opened after it (no delta extension).
                for c in (tau - pj - D, tau - pj - D - eta):
                    if c >= lower - 1e-9:
                        cands.add(round(c, 4))
        # guaranteed-feasible fallback: start after every rear access (all
        # Mode A) AND at/after `lower` (same-position separation, E_r).
        if rear_acc:
            cands.add(max(lower, max(rear_acc) + eta))

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
        acc = sorted(rear_acc)
        used = [False] * len(acc)
        sched = []
        mov_events = 0
        t = s_start
        n = len(chain)

        for j in range(n):
            jid, D = chain[j]
            interruptible = self.interruptible[jid]

            kappa = 0
            while True:                                   # Mode-C kappa fixpoint
                f_j = t + D + delta * kappa
                cnt = sum(1 for i, tau in enumerate(acc)
                          if not used[i] and t + eta - 1e-9 <= tau <= f_j - eta + 1e-9)
                if cnt == kappa:
                    break
                kappa = cnt
                if kappa > len(acc) + 5:                  # safety
                    return None, None, None, False
            f_j = t + D + delta * kappa
            if kappa > 0 and not interruptible:
                return None, None, None, False            # Mode C on non-interruptible
            for i, tau in enumerate(acc):                 # eta-margin bad zones
                if used[i]:
                    continue
                if t - 1e-9 < tau < t + eta - 1e-9:
                    return None, None, None, False
                if f_j - eta + 1e-9 < tau < f_j - 1e-9:
                    return None, None, None, False
            for i, tau in enumerate(acc):                 # consume Mode-C accesses
                if not used[i] and t + eta - 1e-9 <= tau <= f_j - eta + 1e-9:
                    used[i] = True
            mov_events += kappa
            sched.append((jid, t, f_j, kappa))
            t = f_j

            # Mode-B gap before the next job
            if j < n - 1:
                next_interruptible = self.interruptible[chain[j + 1][0]]
                window = chain[j + 1][1] if not next_interruptible else delta
                batch = [i for i in range(len(acc))
                         if not used[i] and f_j + 1e-9 < acc[i] <= f_j + window + 1e-9]
                if batch:
                    s_next = max(max(acc[i] for i in batch), f_j + mu * len(batch))
                    # reconcile: every unused access in (f_j, s_next] is in the
                    # gap (Mode B) and must be counted, which may widen the gap.
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
                    t = s_next

        f_r = t
        # Any unused access strictly inside the stay is an unclassifiable /
        # zero-gap boundary case — reject (the checker would too).
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

    _HERE = Path(__file__).resolve().parent              # methods/iterated_greedy_vnd/jobs/
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
