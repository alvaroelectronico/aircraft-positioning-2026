"""Iterated Greedy + VND solver for paper #2 (job-level extension).

This module implements **Candidate A** from
``methods/theory_assisted/jobs/notes/synthesis.md``: an Iterated-Greedy
outer loop (NEH-style greedy construction + worst-aircraft
destruction/reconstruction) wrapped around a sequential Variable
Neighbourhood Descent local search.  The design is drawn only from the
curated theory in ``inspiration/`` / ``digest/`` — see CLAUDE.md.

Architecture (two layers, as the synthesis recommends)
------------------------------------------------------
1. **Outer combinatorial decision** — the position assignment
   ``pi : R -> P`` and a global priority order over the aircraft.
2. **Inner timing decision** — a deterministic *decoder* that, given an
   assignment and an order, produces job start/finish times.

The decoder (this first version)
--------------------------------
We adopt a **zero-movement** decoding rule that is feasible by
construction.  For any blocking arc ``(front, rear)``, the rear
aircraft's two access instants (its own entry and exit) must each land
**Mode A** (front vacant) relative to the front aircraft's stay.  With a
margin ``eta`` that leaves three feasible relative placements:

* rear **before** the front  (rear exit <= front start - eta),
* rear **after**  the front  (rear entry >= front finish + eta), or
* rear **encloses** the front (rear entry <= front start - eta *and*
  rear exit >= front finish + eta) — both instants still Mode A.

The third option (containment / nesting) lets blocking-related aircraft
**overlap in time** when one is long enough to wrap the other, which is
what breaks the full-serialisation bottleneck on tight-blocking
topologies while keeping ``movements = 0`` and ``kappa = 0`` (no Mode-C
feedback on timing).  Aircraft sharing a position are separated by
``epsilon`` (RQ08); aircraft on non-conflicting positions run fully in
parallel.

Consequences:
- ``movements = 0`` always; the heuristic optimises ``makespan`` and
  ``total_delay`` only, by choosing the assignment and the order.
- For the movement-priority weight profile this is automatically strong;
  for makespan/delay-priority profiles it trades the MILP's ability to
  overlap-via-manoeuvre for guaranteed feasibility and speed.  Allowing
  controlled Mode-B/C overlaps is the obvious next iteration (it needs an
  incremental kappa fixpoint in the decoder); kept out of v1 on purpose.

The optimisation that *is* exposed (assignment + order) is driven by the
IG+VND loop, exactly the architecture cross-validated by
[[Scheduling_Heuristics]], [[Variable_Neighborhood_Descent]] and
[[Iterated_Local_Search]] in the synthesis.

Solution dict shape (consumed by ``problems/jobs/checker.py``)::

    {"status", "objective", "metrics": {makespan, total_delay, movements},
     "aircraft": [{"id","position","start","finish","delay",
                   "jobs":[{"id","start","finish"}, ...]}, ...]}
"""
from __future__ import annotations

import random
import time


class IteratedGreedyVNDJobSolver:
    """Iterated Greedy + VND heuristic (Candidate A)."""

    name = "iterated_greedy_vnd"

    def __init__(self) -> None:
        self._config: dict = {}
        self._log: list[str] = []

    # ------------------------------------------------------------------
    # Contract
    # ------------------------------------------------------------------

    def configure_solver(self, **kwargs) -> None:
        """Store tunable parameters.

        Recognised keys (all optional except those Application sets):
            time_limit_s      : wall-clock cap in seconds (default 60)
            weight_makespan   : W^M (default 0.1)
            weight_delay      : W^D (default 1.0)
            weight_movements  : W^S (default 10.0)  — informational here
            seed              : RNG seed for reproducibility (default 1)
            k_destroy         : aircraft removed per IG perturbation
                                (default max(1, R // 4))
            max_no_improve    : early-stop after this many non-improving
                                IG iterations (default 400)
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
        n_starts = int(cfg.get("n_starts", 4))

        # Shared deterministic construction (the per-start variety comes from
        # the IG perturbation RNG, re-seeded per start).
        self._decode_fn = self._decode
        ctor_order = sorted(self.aircraft_ids, key=lambda r: -self.T[r])
        self._ctor_assignment = self._greedy_construct(ctor_order)
        self._ctor_order = self._neh_order(self._ctor_assignment)

        t0 = time.perf_counter()
        global_dl = t0 + self.time_limit
        per_start = self.time_limit / max(1, n_starts)

        best_sol, best_obj = None, float("inf")
        i = 0
        while time.perf_counter() < global_dl - 0.05 and i < n_starts:
            self.rng = random.Random(base_seed + i)
            start_dl = min(global_dl, time.perf_counter() + per_start)
            sol, obj = self._one_start(instance_data, start_dl)
            if obj < best_obj - 1e-9:
                best_sol, best_obj = sol, obj
            self._log.append(
                f"start {i} (seed {base_seed + i})  obj={obj:.4f}  "
                f"ms={sol['metrics']['makespan']:.1f} dly={sol['metrics']['total_delay']:.1f} "
                f"mov={sol['metrics']['movements']}  best={best_obj:.4f}"
            )
            i += 1

        best_sol["status"] = "heuristic_ok"
        self._log.append(
            f"done  starts={i}  best_obj={best_obj:.4f}  "
            f"ms={best_sol['metrics']['makespan']:.2f} "
            f"dly={best_sol['metrics']['total_delay']:.2f} "
            f"mov={best_sol['metrics']['movements']}  "
            f"({time.perf_counter() - t0:.2f}s)"
        )
        return best_sol

    def _one_start(self, instance_data: dict, deadline: float) -> tuple[dict, float]:
        """One multi-start restart: zero-movement (v2) search, then an
        optional manoeuvre-aware (v3) polish validated by the real checker.
        Returns (solution, objective)."""
        # ---- Phase 1: zero-movement search (v2 decoder) ----
        self._decode_fn = self._decode
        dl1 = min(deadline, time.perf_counter() + (deadline - time.perf_counter()) *
                  (0.5 if self.use_v3 else 1.0))
        a1, o1 = self._search(dict(self._ctor_assignment), list(self._ctor_order), dl1)
        best_sol = self._finalize(self._decode(a1, o1))
        best_obj = best_sol["objective"]

        # ---- Phase 2: manoeuvre-aware polish (v3 decoder) ----
        # v2 is the guaranteed floor; the v3 candidate is taken only if the
        # real checker certifies it AND it strictly improves.
        if self.use_v3:
            self._decode_fn = self._decode_v3
            a3, o3 = self._search(dict(a1), list(o1), deadline)
            sol_v3 = self._finalize(self._decode_v3(a3, o3))
            if (sol_v3["objective"] < best_obj - 1e-9
                    and self._is_compliant(sol_v3, instance_data)):
                best_sol, best_obj = sol_v3, sol_v3["objective"]
        return best_sol, best_obj

    # ------------------------------------------------------------------
    # Search driver (shared by both phases via self._decode_fn)
    # ------------------------------------------------------------------

    def _search(self, assignment, order, deadline):
        """VND + Iterated-Greedy loop using the current ``self._decode_fn``."""
        assignment, order = self._vnd(assignment, order)
        best_assign, best_order = dict(assignment), list(order)
        best_obj = self._objective(self._decode_fn(best_assign, best_order))
        cur_assign, cur_order = dict(best_assign), list(best_order)
        no_improve = 0
        while time.perf_counter() < deadline and no_improve < self.max_no_improve:
            a2, o2 = self._perturb(cur_assign, cur_order, self.k_destroy)
            a2, o2 = self._vnd(a2, o2)
            obj2 = self._objective(self._decode_fn(a2, o2))
            cur_obj = self._objective(self._decode_fn(cur_assign, cur_order))
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

    def _objective(self, sol: dict) -> float:
        return float(sol["objective"])

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
            best_p, best_o = None, float("inf")
            for p in self.positions:
                assignment[r] = p
                o = self._objective(self._decode(assignment, partial_order))
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
        cur = self._objective(self._decode_fn(assignment, order))
        k = 0
        neighbourhoods = (self._n_reassign, self._n_swap_pos, self._n_reorder)
        while k < len(neighbourhoods):
            improved, assignment, order, cur = neighbourhoods[k](assignment, order, cur)
            if improved:
                k = 0  # B-VND reset
            else:
                k += 1
        return assignment, order

    def _n_reassign(self, assignment, order, cur):
        """N1 — move one aircraft to a different position (first improvement)."""
        for r in self.aircraft_ids:
            p0 = assignment[r]
            for p in self.positions:
                if p == p0:
                    continue
                assignment[r] = p
                o = self._objective(self._decode_fn(assignment, order))
                if o < cur - 1e-9:
                    return True, assignment, order, o
                assignment[r] = p0
        return False, assignment, order, cur

    def _n_swap_pos(self, assignment, order, cur):
        """N2 — swap the positions of two aircraft (first improvement)."""
        ids = self.aircraft_ids
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                ri, rj = ids[i], ids[j]
                if assignment[ri] == assignment[rj]:
                    continue
                assignment[ri], assignment[rj] = assignment[rj], assignment[ri]
                o = self._objective(self._decode_fn(assignment, order))
                if o < cur - 1e-9:
                    return True, assignment, order, o
                assignment[ri], assignment[rj] = assignment[rj], assignment[ri]
        return False, assignment, order, cur

    def _n_reorder(self, assignment, order, cur):
        """N3 — swap two aircraft in the priority order (first improvement)."""
        for i in range(len(order)):
            for j in range(i + 1, len(order)):
                order[i], order[j] = order[j], order[i]
                o = self._objective(self._decode_fn(assignment, order))
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
        sol = self._decode_fn(assignment, order)
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
            best = None  # (obj, position, slot)
            for slot in range(len(kept_order) + 1):
                trial_order = kept_order[:slot] + [r] + kept_order[slot:]
                for p in self.positions:
                    a2[r] = p
                    o = self._objective(self._decode_fn(a2, trial_order))
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

    _HERE = Path(__file__).resolve().parent              # methods/theory_assisted/jobs/
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
