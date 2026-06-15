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
        self.rng = random.Random(int(cfg.get("seed", 1) or 1))

        self._prepare(instance_data)
        R = len(self.aircraft_ids)
        k_destroy = int(cfg.get("k_destroy", max(1, R // 4)))
        max_no_improve = int(cfg.get("max_no_improve", 400))

        t0 = time.perf_counter()

        # ---- construction (NEH order + greedy best-position insertion) ----
        order = sorted(self.aircraft_ids, key=lambda r: -self.T[r])
        assignment = self._greedy_construct(order)
        order = self._neh_order(assignment)
        assignment, order = self._vnd(assignment, order)
        best_assign, best_order = dict(assignment), list(order)
        best_obj = self._objective(self._decode(best_assign, best_order))
        self._log.append(
            f"construct+vnd  obj={best_obj:.4f}  "
            f"({time.perf_counter() - t0:.2f}s)"
        )

        # ---- Iterated Greedy outer loop ----
        cur_assign, cur_order = dict(best_assign), list(best_order)
        it = 0
        no_improve = 0
        while (time.perf_counter() - t0) < self.time_limit and no_improve < max_no_improve:
            it += 1
            a2, o2 = self._perturb(cur_assign, cur_order, k_destroy)
            a2, o2 = self._vnd(a2, o2)
            obj2 = self._objective(self._decode(a2, o2))
            cur_obj = self._objective(self._decode(cur_assign, cur_order))
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
        cur = self._objective(self._decode(assignment, order))
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
                o = self._objective(self._decode(assignment, order))
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
                o = self._objective(self._decode(assignment, order))
                if o < cur - 1e-9:
                    return True, assignment, order, o
                assignment[ri], assignment[rj] = assignment[rj], assignment[ri]
        return False, assignment, order, cur

    def _n_reorder(self, assignment, order, cur):
        """N3 — swap two aircraft in the priority order (first improvement)."""
        for i in range(len(order)):
            for j in range(i + 1, len(order)):
                order[i], order[j] = order[j], order[i]
                o = self._objective(self._decode(assignment, order))
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
                    o = self._objective(self._decode(a2, trial_order))
                    if best is None or o < best[0]:
                        best = (o, p, slot)
            _, bp, bslot = best
            a2[r] = bp
            kept_order = kept_order[:bslot] + [r] + kept_order[bslot:]

        return a2, kept_order


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
