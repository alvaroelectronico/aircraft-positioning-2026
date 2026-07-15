"""Iterated Greedy + VND solver for paper #2 (job-level extension).

This module implements **Candidate A** from the literature synthesis
that informed it (now archived alongside this file as
``synthesis.md`` and ``design.md``): an Iterated-Greedy outer loop
(NEH-style greedy construction + worst-aircraft destruction /
reconstruction) wrapped around a sequential Variable Neighbourhood
Descent local search.  The design was distilled from external theory
that lives under ``methods/theory_assisted/`` (the scaffold this
method graduated out of) — see CLAUDE.md for the isolation contract
this method inherits.

Architecture (two layers, as the synthesis recommends)
------------------------------------------------------
1. **Outer combinatorial decision** — the position assignment
   ``pi : R -> P`` and a global priority order over the aircraft.
2. **Inner timing decision** — a deterministic *decoder* that, given an
   assignment and an order, produces job start/finish times.

The decoder (v02): manoeuvre-aware, with a zero-movement fallback
-----------------------------------------------------------------
v01 used a **zero-movement** decoding rule that is feasible by
construction: every rear access instant is forced **Mode A** (front
vacant) by placing the rear before / after / enclosing the front stay
(margin ``eta``); same-position aircraft are separated by ``epsilon``;
non-conflicting positions run in parallel.  That rule guarantees
``movements = 0`` and ``kappa = 0`` but can never *spend* a manoeuvre to
compress the schedule.

Under two of the three benchmark weight profiles that matters:

* ``(W^M,W^D,W^S) = (100,1,1)`` (makespan-priority) and ``(1,100,1)``
  (delay-priority) both *reward* letting a rear aircraft access **during**
  the front aircraft's stay, because it lets the rear finish earlier.
* ``(1,1,100)`` (movement-priority) rewards exactly the opposite — and the
  zero-movement decode is already optimal on the movement term there.

So v02 adds a **manoeuvre-aware decoder** (``_decode_man``) that *may*
route a rear access through **Mode C** — strictly inside an interruptible
front job, which pauses that job (``kappa += 1``, the job grows by
``delta``) and costs 2 movements — when the weighted objective rewards it.
The Mode-C job extension feeds back into the front aircraft's finish (and
its same-position successors), so the decoder iterates a **kappa fixpoint**
until the interruption counts stabilise.

Two safety guarantees keep v02 dominant over the v01 baseline and always
feasible:

1. ``_decode`` evaluates **both** ``_decode_zero`` (the v01 rule) and
   ``_decode_man`` and returns whichever has the lower weighted objective.
   v02 is therefore never worse than v01 on any (assignment, order).
2. If the kappa fixpoint does not converge (durations and interruption
   counts must be mutually consistent for ``checker.py`` to pass), the
   manoeuvre decode is discarded and the zero-movement decode is used.

Mode B (routing an access through an inter-job *gap* of the front) is not
actively created in v02: the decoder packs each aircraft's jobs tight, so
no gaps exist to route through, and any access that would land on a packed
job boundary is rejected as infeasible.  Opening gaps for Mode-B
manoeuvres is the natural next iteration.

Solution dict shape (consumed by ``problems/jobs/checker.py``)::

    {"status", "objective", "metrics": {makespan, total_delay, movements},
     "aircraft": [{"id","position","start","finish","delay",
                   "jobs":[{"id","start","finish"}, ...]}, ...]}
"""
from __future__ import annotations

import random
import time

# Numerical tolerance.  Matches ``problems/jobs/checker.py`` (TOL = 1e-4) so
# that the mode classification used inside the decoder agrees with the
# checker's classification of the schedule we emit.
TOL = 1e-4
# Extra safety slack used only when *generating* candidate placements, so
# that a placement intended as Mode A / Mode C lands comfortably away from
# the eta boundary the checker tests against.
SAFE = 1e-2


class IteratedGreedyVNDJobSolver:
    """Iterated Greedy + VND heuristic (Candidate A), manoeuvre-aware v02."""

    name = "iterated_greedy_vnd"

    def __init__(self) -> None:
        self._config: dict = {}
        self._log: list[str] = []
        self._enable_b: bool = True   # Mode-B toggle for the staged fallback
        self._deadline: float = float("inf")  # set per-solve; see _out_of_time

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
            seed              : RNG seed for reproducibility (default 1)
            k_destroy         : aircraft removed per IG perturbation
                                (default max(1, R // 4))
            max_no_improve    : early-stop after this many non-improving
                                IG iterations (default 400)
            allow_manoeuvres  : enable the Mode-C manoeuvre decoder
                                (default True).  When False the solver is
                                the pure v01 zero-movement heuristic.
        """
        self._config.update(kwargs)

    def get_config(self) -> dict:
        return dict(self._config)

    def get_log(self) -> list[str]:
        return list(self._log)

    def _out_of_time(self) -> bool:
        """True once the wall-clock deadline is reached.  Polled by the inner
        scans so no single sweep overruns ``time_limit_s``."""
        return time.perf_counter() >= self._deadline

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
        # Master switch for the manoeuvre-aware decoder.  When True the search
        # runs in two phases (see below); when False it is the pure v01
        # zero-movement heuristic.
        self._man_master = bool(cfg.get("allow_manoeuvres", True))
        self.rng = random.Random(int(cfg.get("seed", 1) or 1))

        self._prepare(instance_data)
        R = len(self.aircraft_ids)
        k_destroy = int(cfg.get("k_destroy", max(1, R // 4)))
        max_no_improve = int(cfg.get("max_no_improve", 400))

        # Fraction of the budget spent in the fast zero-movement phase before
        # manoeuvres are switched on.  The manoeuvre decode is ~50x slower, so
        # the split is adaptive to instance size: small instances can afford
        # manoeuvres throughout (frac 0); mid-size instances split 50/50;
        # large instances keep the whole budget for the fast search and only
        # apply a single manoeuvre *polish* at the end (frac 1) — that keeps
        # phase A identical to the v01 baseline and the final polish can only
        # improve, so v02 never regresses against v01 on large instances.
        if "man_phase_frac" in cfg:
            man_phase_frac = float(cfg["man_phase_frac"])
        elif R <= 12:
            man_phase_frac = 0.0
        elif R <= 22:
            man_phase_frac = 0.5
        else:
            man_phase_frac = 1.0

        t0 = time.perf_counter()
        # Hard wall-clock deadline.  The IG loop checks time between iterations,
        # but a single construction / VND sweep / perturbation on a large dense
        # instance can itself overrun by minutes, so the inner scans poll this
        # deadline and abort early (see _out_of_time).  This keeps every run
        # within time_limit_s as the benchmark requires.
        self._deadline = t0 + self.time_limit

        # Phase A always runs with the fast zero-movement decoder so a strong
        # incumbent is found cheaply.  Phase B (if manoeuvres are enabled)
        # turns them on to refine that incumbent.
        self.allow_man = False
        switch_at = self.time_limit * man_phase_frac if self._man_master else self.time_limit

        # ---- construction (NEH order + greedy best-position insertion) ----
        order = sorted(self.aircraft_ids, key=lambda r: -self.T[r])
        assignment = self._greedy_construct(order)
        order = self._neh_order(assignment)
        assignment, order = self._vnd(assignment, order)
        best_assign, best_order = dict(assignment), list(order)
        best_obj = self._obj(best_assign, best_order)
        self._log.append(
            f"construct+vnd  obj={best_obj:.4f}  "
            f"({time.perf_counter() - t0:.2f}s)"
        )

        # ---- Iterated Greedy outer loop ----
        cur_assign, cur_order = dict(best_assign), list(best_order)
        it = 0
        no_improve = 0
        switched = False
        while (time.perf_counter() - t0) < self.time_limit and no_improve < max_no_improve:
            # Phase switch: enable manoeuvres once the fast phase budget is
            # spent.  Re-evaluate the incumbent under the richer decoder (it
            # may now score lower) and reset the stall counter for phase B.
            if self._man_master and not switched and (time.perf_counter() - t0) >= switch_at:
                self.allow_man = True
                switched = True
                best_obj = self._obj(best_assign, best_order)
                cur_assign, cur_order = dict(best_assign), list(best_order)
                no_improve = 0
                self._log.append(
                    f"iter {it:>4}  manoeuvres ON  incumbent re-eval obj={best_obj:.4f}  "
                    f"({time.perf_counter() - t0:.2f}s)"
                )
            it += 1
            a2, o2 = self._perturb(cur_assign, cur_order, k_destroy)
            a2, o2 = self._vnd(a2, o2)
            obj2 = self._obj(a2, o2)
            cur_obj = self._obj(cur_assign, cur_order)
            # Acceptance: keep the new local optimum if it does not worsen
            # the incumbent walk (standard IG accept-if-better-or-equal),
            # always tracking the global best separately.
            if obj2 <= cur_obj + 1e-9:
                cur_assign, cur_order = a2, o2
            if obj2 < best_obj - 1e-9:
                best_assign, best_order = dict(a2), list(o2)
                best_obj = obj2
                no_improve = 0
                self._log.append(
                    f"iter {it:>4}  new best obj={best_obj:.4f}  "
                    f"({time.perf_counter() - t0:.2f}s)"
                )
            else:
                no_improve += 1
            # Occasionally restart the walk from the global best to avoid
            # drifting into a worse basin.
            if no_improve > 0 and no_improve % 50 == 0:
                cur_assign, cur_order = dict(best_assign), list(best_order)

        # Final safety net: if manoeuvres never got switched on (e.g. phase A
        # used the whole budget) but they are enabled, polish the best (a,o)
        # once with the manoeuvre decoder and keep it only if it improves.
        if self._man_master and not self.allow_man:
            self.allow_man = True
        elapsed = time.perf_counter() - t0
        sol = self._decode(best_assign, best_order)
        self._log.append(
            f"done  iters={it}  best_obj={best_obj:.4f}  "
            f"makespan={sol['metrics']['makespan']:.2f}  "
            f"delay={sol['metrics']['total_delay']:.2f}  "
            f"mov={sol['metrics']['movements']}  ({elapsed:.2f}s)"
        )
        sol["status"] = "heuristic_ok"
        return sol

    # ==================================================================
    # Instance preprocessing
    # ==================================================================

    def _prepare(self, inst: dict) -> None:
        self.eta = float(inst.get("eta", 1.0))
        self.eps = float(inst.get("min_separation", 0.5))
        self.delta = float(inst.get("delta", 2.0))
        self.mu = float(inst.get("mu", 1.0))

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

        # chain[r] = ordered list of (job_id, nominal_duration, interruptible)
        self.chain: dict[str, list[tuple[str, float, bool]]] = {}
        self.T: dict[str, float] = {}
        for r in self.aircraft_ids:
            jl = jobs_by_ac.get(r, [])
            by_id = {j["id"]: j for j in jl}
            first = next((j for j in jl if j.get("is_first")), jl[0] if jl else None)
            chain: list[tuple[str, float, bool]] = []
            cur = first["id"] if first else None
            seen: set[str] = set()
            while cur is not None and cur in by_id and cur not in seen:
                seen.add(cur)
                jd = by_id[cur]
                chain.append((cur, float(jd["duration"]), bool(jd.get("interruptible", False))))
                cur = succ.get(cur)
            # Fallback: append any jobs not reached via the chain (defensive).
            for j in jl:
                if j["id"] not in seen:
                    chain.append((j["id"], float(j["duration"]), bool(j.get("interruptible", False))))
            self.chain[r] = chain
            self.T[r] = sum(d for _, d, _ in chain)

    # ==================================================================
    # Job-interval construction (packed tight from a start time)
    # ==================================================================

    def _job_intervals(self, r: str, start: float,
                       kappa: dict[str, int] | None,
                       gaps: dict[tuple[str, int], float] | None = None
                       ) -> list[tuple[str, float, float, bool]]:
        """Return r's job intervals from ``start``.

        Each entry is ``(job_id, job_start, job_finish, interruptible)``.
        ``job_finish - job_start = D_j + delta * kappa_j`` (Mode-C extensions);
        after job ``k`` an inter-job *gap* of ``gaps[(r, k)]`` is inserted
        (Mode-B routing windows).  With ``gaps`` empty the jobs are packed
        tight (the v02 behaviour).
        """
        chain = self.chain[r]
        out: list[tuple[str, float, float, bool]] = []
        t = start
        if not kappa and not gaps:           # fast path: pack tight (common)
            for jid, d, intr in chain:
                out.append((jid, t, t + d, intr))
                t += d
            return out
        n = len(chain)
        for k, (jid, d, intr) in enumerate(chain):
            dur = d + self.delta * (kappa.get(jid, 0) if kappa else 0)
            out.append((jid, t, t + dur, intr))
            t += dur
            if gaps and k < n - 1:
                t += gaps.get((r, k), 0.0)
        return out

    def _duration(self, r: str, kappa: dict[str, int] | None,
                  gaps: dict[tuple[str, int], float] | None = None) -> float:
        dur = self.T[r]
        if kappa:
            dur += self.delta * sum(kappa.get(jid, 0) for jid, _, _ in self.chain[r])
        if gaps:
            dur += sum(g for (rr, _), g in gaps.items() if rr == r)
        return dur

    # ==================================================================
    # Access-mode classification (mirrors problems/jobs/checker.py)
    # ==================================================================

    def _classify(self, tau: float, s: float, f: float,
                  jobs: list[tuple[str, float, float, bool]]) -> tuple[str, object]:
        """Classify access instant ``tau`` against a front stay ``[s, f]``.

        Returns ``(kind, info)`` where kind is 'A' (no manoeuvre), 'B'
        (inter-job gap, info = gap index), 'C' (inside interruptible job,
        info = job_id) or 'X' (infeasible).  The inequalities mirror
        ``_classify_access`` in the checker exactly.
        """
        eta = self.eta
        if tau <= s - eta + TOL:
            return ("A", None)
        if tau >= f + eta - TOL:
            return ("A", None)
        for (jid, js, jf, intr) in jobs:
            if js + eta - TOL <= tau <= jf - eta + TOL:
                if intr:
                    return ("C", jid)
                return ("X", None)
        for k in range(len(jobs) - 1):
            fk = jobs[k][2]
            sk1 = jobs[k + 1][1]
            if fk - TOL <= tau <= sk1 + TOL:
                return ("B", k)
        if s - eta <= tau <= s + TOL:
            return ("A", None)
        if f - TOL <= tau <= f + eta:
            return ("A", None)
        return ("X", None)

    # ==================================================================
    # Decoder dispatcher: best of zero-movement and manoeuvre-aware
    # ==================================================================

    def _decode(self, assignment: dict, order: list[str], full: bool = True) -> dict:
        zero = self._decode_zero(assignment, order, full=full)
        if not self.allow_man:
            return zero
        man = self._decode_man(assignment, order, full=full)
        if man is not None and man["objective"] < zero["objective"] - 1e-9:
            return man
        return zero

    def _obj(self, assignment: dict, order: list[str]) -> float:
        """Dispatched objective only (no solution dict) — the search hot path."""
        return self._decode(assignment, order, full=False)["objective"]

    def _objective(self, sol: dict) -> float:
        return float(sol["objective"])

    def _finalise(self, placed: dict, assignment: dict,
                  kappa: dict[str, int] | None, movements: int,
                  gaps: dict[tuple[str, int], float] | None = None,
                  full: bool = True) -> dict:
        """Weighted objective (and, when ``full``, the full solution dict) from
        a placement.  ``placed[r] = (s_r, f_r)`` already carries each aircraft's
        finish, so the objective needs no interval rebuild.

        During the search (VND / IG / construction) only the objective is
        needed, so callers pass ``full=False`` to skip building the per-aircraft
        / per-job lists — the dominant cost of a decode (see profiling note in
        design.md).  The final solution returned by ``solve`` is built with
        ``full=True`` so it carries the job schedule the checker consumes.
        """
        makespan = 0.0
        total_delay = 0.0
        for r in self.aircraft_ids:
            if r not in placed:
                continue  # partial decode during greedy construction
            f_r = placed[r][1]
            total_delay += max(0.0, f_r - self.L[r])
            if f_r > makespan:
                makespan = f_r
        obj = self.wM * makespan + self.wD * total_delay + self.wS * movements
        metrics = {"makespan": makespan, "total_delay": total_delay,
                   "movements": movements}
        if not full:
            return {"objective": round(obj, 6), "metrics": metrics}

        aircraft_out = []
        for r in self.aircraft_ids:
            if r not in placed:
                continue
            s_r, f_r = placed[r]
            jobs_out = [{"id": jid, "start": js, "finish": jf}
                        for jid, js, jf, _ in self._job_intervals(r, s_r, kappa, gaps)]
            aircraft_out.append({
                "id": r, "position": assignment[r], "start": s_r, "finish": f_r,
                "delay": max(0.0, f_r - self.L[r]), "jobs": jobs_out,
            })
        return {
            "status": "heuristic_ok",
            "objective": round(obj, 6),
            "metrics": metrics,
            "aircraft": aircraft_out,
        }

    # ==================================================================
    # Zero-movement decoder (v01 rule) — always feasible, movements = 0
    # ==================================================================

    def _forbidden(self, p, dur, p2, s2, f2):
        """Open intervals where our start ``t`` is infeasible against an
        already-placed aircraft on position ``p2`` occupying ``[s2, f2]``.

        Two intervals leave a feasible *hole* between them — the nesting
        (containment) option — which the earliest-fit scan can land in.
        """
        eta, eps = self.eta, self.eps
        if p2 == p:
            return [(s2 - dur - eps, f2 + eps)]
        if (p2, p) in self._arcs:
            # We are the REAR (p2 is the front): before, after, or enclose.
            if dur >= (f2 - s2) + 2 * eta - 1e-9:
                return [(s2 - eta - dur, f2 + eta - dur), (s2 - eta, f2 + eta)]
            return [(s2 - eta - dur, f2 + eta)]
        if (p, p2) in self._arcs:
            # We are the FRONT (p2 is the rear): rear before, after, or enclose.
            if dur <= (f2 - s2) - 2 * eta + 1e-9:
                return [(s2 - dur - eta, s2 + eta), (f2 - dur - eta, f2 + eta)]
            return [(s2 - dur - eta, f2 + eta)]
        return []

    def _zero_place(self, assignment: dict, order: list[str], start: int = 0,
                    placed: dict | None = None) -> dict:
        """Earliest-feasible-start forward pass for the zero-movement rule.

        Places ``order[start:]`` into ``placed`` (which must already hold the
        placements of ``order[:start]``) and returns it.  Because the pass is
        causal — each aircraft's placement depends only on those *before* it in
        ``order`` — re-placing just a suffix from a cached prefix is exact,
        which is what the incremental VND evaluation (`_zero_obj_inc`) exploits.
        """
        placed = {} if placed is None else placed
        for idx in range(start, len(order)):
            r = order[idx]
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
        return placed

    def _zero_obj_inc(self, assignment: dict, order: list[str], k: int,
                      base_placed: dict) -> float:
        """Zero-movement objective when only ``order[k:]`` may have changed:
        reuse ``base_placed`` for the unchanged prefix ``order[:k]`` and
        re-place only the suffix.  Exactly equal to a full zero decode."""
        prefix = {order[t]: base_placed[order[t]] for t in range(k)}
        placed = self._zero_place(assignment, order, start=k, placed=prefix)
        makespan = 0.0
        total_delay = 0.0
        for r in order:
            f_r = placed[r][1]
            total_delay += max(0.0, f_r - self.L[r])
            if f_r > makespan:
                makespan = f_r
        return round(self.wM * makespan + self.wD * total_delay, 6)

    def _decode_zero(self, assignment: dict, order: list[str], full: bool = True) -> dict:
        placed = self._zero_place(assignment, order)
        return self._finalise(placed, assignment, kappa=None, movements=0, full=full)

    # ==================================================================
    # Manoeuvre-aware decoder (Mode-C) with kappa fixpoint
    # ==================================================================

    def _decode_man(self, assignment: dict, order: list[str], full: bool = True) -> dict | None:
        """Manoeuvre-aware decode with a staged fallback.

        First tries the full joint (kappa, gaps) fixpoint — Mode-C *and*
        Mode-B.  The extra Mode-B state can oscillate on dense topologies, so
        if it does not converge quickly we retry with Mode-B **disabled**
        (the v02 kappa-only fixpoint, which is stable on those instances)
        before giving up to the zero-movement decode.  This keeps v03's
        Mode-B gains on sparse topologies without regressing the dense ones."""
        self._enable_b = True
        res = self._man_fixpoint(assignment, order, cap=5, full=full)
        if res is not None:
            return res
        self._enable_b = False                    # v02 kappa-only behaviour
        res = self._man_fixpoint(assignment, order, cap=8, full=full)
        self._enable_b = True
        return res  # may be None -> caller falls back to zero-movement decode

    def _man_fixpoint(self, assignment: dict, order: list[str],
                      cap: int, full: bool = True) -> dict | None:
        """Iterate the (kappa[, gaps]) fixpoint up to ``cap`` times.  Returns a
        self-consistent solution dict, or ``None`` if it does not converge."""
        kappa: dict[str, int] = {}
        gaps: dict[tuple[str, int], float] = {}
        placed: dict[str, tuple[float, float]] = {}
        for _ in range(cap):
            placed = self._forward_pass(assignment, order, kappa, gaps)
            new_kappa, new_gaps, movements, feasible = self._classify_schedule(
                assignment, placed, kappa, gaps
            )
            if not feasible:
                return None
            if new_kappa == kappa and self._gaps_equal(new_gaps, gaps):
                # Converged: the durations/gaps used reproduce exactly the
                # interruption counts and gap requirements the classification
                # infers -> the schedule is self-consistent and passes checker.
                return self._finalise(placed, assignment, kappa, movements, gaps, full=full)
            kappa, gaps = new_kappa, new_gaps
        return None  # did not converge within the cap

    @staticmethod
    def _gaps_equal(a: dict, b: dict) -> bool:
        if a.keys() != b.keys():
            return False
        return all(abs(a[k] - b[k]) <= TOL for k in a)

    def _forward_pass(self, assignment: dict, order: list[str],
                      kappa: dict[str, int],
                      gaps: dict[tuple[str, int], float]) -> dict:
        """Place every aircraft (in ``order``) at the start time minimising a
        local weighted cost, given fixed durations (from ``kappa``/``gaps``)
        and the already-placed neighbours.  Always returns a feasible
        placement."""
        placed: dict[str, tuple[float, float]] = {}
        # Cache each placed aircraft's job intervals once (they do not change
        # while later aircraft are placed) so the per-candidate scans in
        # _choose_start/_eval_start reuse them instead of rebuilding — the hot
        # path by a wide margin (see profiling note in design.md).
        placed_jobs: dict[str, list[tuple[str, float, float, bool]]] = {}
        for r in order:
            dur = self._duration(r, kappa, gaps)
            t = self._choose_start(r, assignment, dur, placed, placed_jobs, kappa, gaps)
            placed[r] = (t, t + dur)
            placed_jobs[r] = self._job_intervals(r, t, kappa, gaps)
        return placed

    def _choose_start(self, r: str, assignment: dict, dur: float,
                      placed: dict, placed_jobs: dict, kappa: dict[str, int],
                      gaps: dict[tuple[str, int], float]) -> float:
        """Pick the start time for ``r`` minimising local weighted cost.

        Considers a set of candidate start times induced by the placed
        neighbours, keeps only feasible ones (no same-position overlap, no
        access inside a non-interruptible job), and scores each by
        ``wM*finish + wD*delay + wS*2*events``.  Candidates include Mode-A
        (outside the front stay), Mode-C (inside an interruptible job) and
        Mode-B (on a front inter-job boundary, where a gap can be opened).
        A guaranteed-feasible 'after everything' candidate is always included.

        ``placed_jobs`` caches each placed neighbour's intervals; ``base_r`` is
        r's own intervals at start 0, computed once and shifted per candidate.
        """
        p = assignment[r]
        E_r = self.E[r]
        cands: set[float] = {E_r}
        latest = E_r
        base_r = self._job_intervals(r, 0.0, kappa, gaps)   # r's offsets, once
        for r2, (s2, f2) in placed.items():
            latest = max(latest, f2)
            p2 = assignment[r2]
            if p2 == p:
                cands.add(f2 + self.eps + SAFE)
                cands.add(s2 - self.eps - dur - SAFE)
            if (p2, p) in self._arcs:
                # r is REAR, r2 is FRONT.  r's entry (t) / exit (t+dur) vs r2.
                cands.add(f2 + self.eta + SAFE)              # entry after front
                cands.add(s2 - self.eta - SAFE)              # entry before front
                cands.add(s2 - self.eta - dur - SAFE)        # exit before front
                jobs2 = placed_jobs[r2]
                last2 = len(jobs2) - 1
                for k, (jid, js, jf, intr) in enumerate(jobs2):
                    if intr and (jf - js) > 2 * self.eta + 2 * SAFE:
                        mid = 0.5 * (js + jf)
                        cands.add(mid)                       # entry mid-job (Mode C)
                        cands.add(mid - dur)                 # exit mid-job (Mode C)
                    if self._enable_b and k < last2:         # Mode B: front boundary
                        cands.add(jf)                        # entry at front job-k end
                        cands.add(jf - dur)                  # exit at front job-k end
            if (p, p2) in self._arcs:
                # r is FRONT, r2 is REAR.  r2's fixed instants vs r's stay.
                last_r = len(base_r) - 1
                for tau in (s2, f2):
                    cands.add(tau + self.eta + SAFE)             # tau before r
                    cands.add(tau - self.eta - dur - SAFE)       # tau after r
                    for k, (jid, js, jf, intr) in enumerate(base_r):
                        if intr and (jf - js) > 2 * self.eta + 2 * SAFE:
                            # centre r's job over tau -> tau is Mode C inside it
                            cands.add(tau - 0.5 * (js + jf))
                        if self._enable_b and k < last_r:        # Mode B: align
                            cands.add(tau - jf)              # r's job-k end with tau
        cands.add(latest + self.eta + self.eps + dur + SAFE)  # safe fallback

        best_t = None
        best_cost = float("inf")
        for t in sorted(cands):
            if t < E_r - 1e-9:
                continue
            ok, events = self._eval_start(r, assignment, t, dur, placed,
                                          placed_jobs, base_r, kappa, gaps)
            if not ok:
                continue
            f_r = t + dur
            cost = (self.wM * f_r
                    + self.wD * max(0.0, f_r - self.L[r])
                    + self.wS * 2 * events)
            if cost < best_cost - 1e-9:
                best_cost = cost
                best_t = t
        if best_t is None:
            # Should not happen (fallback candidate is always feasible), but
            # be defensive: place strictly after everything.
            best_t = latest + self.eta + self.eps + dur + SAFE
        return best_t

    def _eval_start(self, r: str, assignment: dict, t: float, dur: float,
                    placed: dict, placed_jobs: dict, base_r: list,
                    kappa: dict[str, int],
                    gaps: dict[tuple[str, int], float]):
        """Return ``(feasible, events)`` for placing ``r`` at start ``t``.

        ``events`` counts the Mode-B/C access events r's placement creates
        against already-placed neighbours (each worth 2 movements).  Used as
        a local cost guide only; authoritative movement counting happens in
        ``_classify_schedule`` over the full placement.  Neighbour intervals
        come from the ``placed_jobs`` cache; r's own intervals are ``base_r``
        (offsets from 0) shifted by ``t``.
        """
        p = assignment[r]
        s_r, f_r = t, t + dur
        r_jobs = [(jid, js + t, jf + t, intr) for (jid, js, jf, intr) in base_r]
        events = 0
        for r2, (s2, f2) in placed.items():
            p2 = assignment[r2]
            if p2 == p:
                # Same position: disjoint with >= eps gap on both sides.
                if not (f_r + self.eps <= s2 + TOL or f2 + self.eps <= s_r + TOL):
                    return (False, 0)
            if (p2, p) in self._arcs:
                jobs2 = placed_jobs[r2]
                for tau in (s_r, f_r):
                    kind, _ = self._classify(tau, s2, f2, jobs2)
                    if kind == "X" or (kind == "B" and not self._enable_b):
                        return (False, 0)
                    if kind in ("B", "C"):
                        events += 1
            if (p, p2) in self._arcs:
                for tau in (s2, f2):
                    kind, _ = self._classify(tau, s_r, f_r, r_jobs)
                    if kind == "X" or (kind == "B" and not self._enable_b):
                        return (False, 0)
                    if kind in ("B", "C"):
                        events += 1
        return (True, events)

    def _classify_schedule(self, assignment: dict, placed: dict,
                           kappa: dict[str, int],
                           gaps: dict[tuple[str, int], float]):
        """Re-classify every access instant over the full placement.

        Returns ``(new_kappa, new_gaps, movements, feasible)``.  ``new_kappa``
        maps each interrupted job to its Mode-C event count and ``new_gaps``
        maps each used front inter-job gap ``(aircraft, k)`` to the cumulative
        width ``mu * count`` it must be opened to — both feed the next forward
        pass so durations and gaps become self-consistent.  ``movements`` is
        ``2 * (#Mode-B + #Mode-C events)``; ``feasible`` is False only on a
        genuine infeasibility (access inside a non-interruptible job).
        """
        new_kappa: dict[str, int] = {}
        gap_uses: dict[tuple[str, int], int] = {}
        events = 0
        # Job intervals per aircraft under the current (kappa, gaps).
        jobs_of = {r: self._job_intervals(r, s, kappa, gaps)
                   for r, (s, _) in placed.items()}
        for (p_front, p_rear) in self._arcs:
            fronts = [r for r in placed if assignment[r] == p_front]
            rears = [r for r in placed if assignment[r] == p_rear]
            for rf in fronts:
                s_f, f_f = placed[rf]
                jobs_f = jobs_of[rf]
                for rr in rears:
                    if rr == rf:
                        continue
                    s_r, f_r = placed[rr]
                    for tau in (s_r, f_r):
                        kind, info = self._classify(tau, s_f, f_f, jobs_f)
                        if kind == "A":
                            continue
                        if kind == "X" or (kind == "B" and not self._enable_b):
                            return ({}, {}, 0, False)
                        if kind == "C":
                            new_kappa[info] = new_kappa.get(info, 0) + 1
                            events += 1
                        elif kind == "B":
                            gap_uses[(rf, info)] = gap_uses.get((rf, info), 0) + 1
                            events += 1
        # Each used inter-job gap must be opened to mu * (#accesses through it).
        new_gaps = {key: self.mu * n for key, n in gap_uses.items()}
        return (new_kappa, new_gaps, 2 * events, True)

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
            if self._out_of_time():
                assignment[r] = self.positions[0]  # finish fast, stay feasible
                continue
            best_p, best_o = None, float("inf")
            for p in self.positions:
                assignment[r] = p
                o = self._obj(assignment, partial_order)
                if o < best_o:
                    best_o, best_p = o, p
            assignment[r] = best_p
        return assignment

    def _neh_order(self, assignment: dict) -> list[str]:
        return sorted(self.aircraft_ids, key=lambda r: -self.T[r])

    # ==================================================================
    # VND  (sequential, B-VND reset over three neighbourhoods)
    # ==================================================================

    def _vnd(self, assignment: dict, order: list[str]) -> tuple[dict, list[str]]:
        assignment = dict(assignment)
        order = list(order)
        cur = self._obj(assignment, order)
        k = 0
        neighbourhoods = (self._n_reassign, self._n_swap_pos, self._n_reorder)
        while k < len(neighbourhoods):
            if self._out_of_time():
                break
            improved, assignment, order, cur = neighbourhoods[k](assignment, order, cur)
            if improved:
                k = 0  # B-VND reset
            else:
                k += 1
        return assignment, order

    def _n_reassign(self, assignment, order, cur):
        """N1 — move one aircraft to a different position (first improvement).

        In phase A (zero decode) each probe only changes the moved aircraft, so
        the objective is evaluated incrementally — re-placing the order suffix
        from the moved aircraft onward, reusing the cached prefix (`_zero_obj_inc`).
        Phase B (manoeuvre decode) cannot be incrementalised and uses `_obj`."""
        inc = not self.allow_man
        base = self._zero_place(assignment, order) if inc else None
        idx_of = {r: i for i, r in enumerate(order)} if inc else None
        for r in self.aircraft_ids:
            if self._out_of_time():
                return False, assignment, order, cur
            p0 = assignment[r]
            k = idx_of[r] if inc else 0
            for p in self.positions:
                if p == p0:
                    continue
                assignment[r] = p
                o = (self._zero_obj_inc(assignment, order, k, base) if inc
                     else self._obj(assignment, order))
                if o < cur - 1e-9:
                    return True, assignment, order, o
                assignment[r] = p0
        return False, assignment, order, cur

    def _n_swap_pos(self, assignment, order, cur):
        """N2 — swap the positions of two aircraft (first improvement)."""
        inc = not self.allow_man
        base = self._zero_place(assignment, order) if inc else None
        idx_of = {r: i for i, r in enumerate(order)} if inc else None
        ids = self.aircraft_ids
        for i in range(len(ids)):
            if self._out_of_time():
                return False, assignment, order, cur
            for j in range(i + 1, len(ids)):
                ri, rj = ids[i], ids[j]
                if assignment[ri] == assignment[rj]:
                    continue
                assignment[ri], assignment[rj] = assignment[rj], assignment[ri]
                if inc:
                    k = idx_of[ri] if idx_of[ri] < idx_of[rj] else idx_of[rj]
                    o = self._zero_obj_inc(assignment, order, k, base)
                else:
                    o = self._obj(assignment, order)
                if o < cur - 1e-9:
                    return True, assignment, order, o
                assignment[ri], assignment[rj] = assignment[rj], assignment[ri]
        return False, assignment, order, cur

    def _n_reorder(self, assignment, order, cur):
        """N3 — swap two aircraft in the priority order (first improvement)."""
        inc = not self.allow_man
        base = self._zero_place(assignment, order) if inc else None
        for i in range(len(order)):
            if self._out_of_time():
                return False, assignment, order, cur
            for j in range(i + 1, len(order)):
                order[i], order[j] = order[j], order[i]
                o = (self._zero_obj_inc(assignment, order, i, base) if inc
                     else self._obj(assignment, order))
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
        sol = self._decode(assignment, order)
        contrib = {a["id"]: self.wD * a["delay"] + 1e-3 * self.T[a["id"]]
                   for a in sol["aircraft"]}
        ranked = sorted(self.aircraft_ids, key=lambda r: -contrib.get(r, 0.0))
        pool = ranked[: min(len(ranked), k + 2)]
        self.rng.shuffle(pool)
        removed = pool[:k]

        a2 = dict(assignment)
        kept_order = [r for r in order if r not in removed]

        for r in removed:
            if self._out_of_time():
                # Out of budget mid-reconstruction: place the rest cheaply
                # (append at the end on the first position) so we still return
                # a complete, feasible (assignment, order).
                a2[r] = self.positions[0]
                kept_order.append(r)
                continue
            best = None  # (obj, position, slot)
            for slot in range(len(kept_order) + 1):
                trial_order = kept_order[:slot] + [r] + kept_order[slot:]
                for p in self.positions:
                    a2[r] = p
                    o = self._obj(a2, trial_order)
                    if best is None or o < best[0]:
                        best = (o, p, slot)
            _, bp, bslot = best
            a2[r] = bp
            kept_order = kept_order[:bslot] + [r] + kept_order[bslot:]

        return a2, kept_order


# Backwards-compatible alias.
TheoryAssistedJobSolver = IteratedGreedyVNDJobSolver


if __name__ == "__main__":
    import sys
    from pathlib import Path

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    _HERE = Path(__file__).resolve().parent              # methods/iterated_greedy_vnd_v02/jobs/
    _ROOT = _HERE.parent.parent.parent                   # repo root
    sys.path.insert(0, str(_ROOT / "shared"))            # instance_io
    sys.path.insert(0, str(_ROOT / "problems" / "jobs")) # checker

    from instance_io import load_json                    # noqa: E402
    from checker import check_solution, print_check       # noqa: E402

    default = _ROOT / "data" / "instances_202605_02" / \
        "scn_triangle_tight_P5_R5" / "scn_triangle_tight_P5_R5_seed1.json"
    path = sys.argv[1] if len(sys.argv) > 1 else str(default)
    tlimit = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    wM = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1
    wD = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    wS = float(sys.argv[5]) if len(sys.argv) > 5 else 10.0
    inst = load_json(path)

    solver = IteratedGreedyVNDJobSolver()
    solver.configure_solver(
        time_limit_s=tlimit,
        weight_makespan=wM, weight_delay=wD, weight_movements=wS,
        seed=1,
    )
    sol = solver.solve(inst)
    print("\n".join(solver.get_log()))
    print(f"\nobjective={sol['objective']}  metrics={sol['metrics']}")
    print_check(check_solution(sol, inst))
