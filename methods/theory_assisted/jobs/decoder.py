"""Chromosome decoder for the theory_assisted BRKGA solver (paper #2).

A chromosome is a vector of random keys of length ``2*|R|``:

    keys[0 : |R|]        assignment keys   -> pi(r) = positions[floor(key*|P|)]
    keys[|R| : 2*|R|]    sequencing keys   -> service order within each position

The decoder turns a chromosome into a full, feasible solution dict (the shape
consumed by ``problems/jobs/checker.py``).  Design (see jobs/notes/design.md):

* Positions are scheduled in **topological order of the blocking DAG**
  (front positions first).  When a rear aircraft is placed, all its fronts are
  already laid out, so its Mode-A/B/C classification is well-defined.
* Each rear aircraft's start time is chosen by a **local-cost scan** over a
  small set of candidate instants; the candidate minimising
  ``W^M*finish + W^D*delay + W^S*movements (+ Mode-C extension estimate)`` wins.
* Access classification reuses the checker's own ``_classify_access`` so the
  decoder agrees with the checker by construction.

Mode C (v2)
-----------
A Mode-C access interrupts an interruptible *front* job, costing +2 movements
and extending that front job by ``delta`` (``kappa`` increments).  Because the
extension shifts the front's tail *after* the front was placed, allowing Mode C
during a single forward pass would create backward cascades.  We avoid this with
a **fixpoint**: each pass lays out every aircraft with the front extensions
``kappa`` held fixed from the previous pass, then recomputes ``kappa`` from the
Mode-C events observed.  When ``kappa`` stops changing the schedule is
self-consistent (front durations match their Mode-C counts, so RQ09 holds).  If
it does not converge within ``max_fixpoint_iters`` passes we fall back to a
Mode-A/B-only pass (``kappa`` empty), which is always consistent.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Import the checker's access classifier — this is problem infrastructure
# (problems/jobs/**), not another solving method, so it is allowed.  Use the
# fully-qualified package path rather than a bare ``import checker``: paper #1
# (problems/aircraft) ships a *different* checker.py, and in the batch runner
# both dirs sit on sys.path, so a bare import would be ambiguous.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from problems.jobs.checker import _classify_access  # noqa: E402

DEFAULT_MU, DEFAULT_DELTA, DEFAULT_ETA = 1.0, 2.0, 1.0
_MAX_CANDIDATES = 80
_MAX_FIXPOINT_ITERS = 8


class DecoderContext:
    """Pre-processed, instance-level data shared across every decode call."""

    def __init__(self, instance: dict, weights: tuple[float, float, float],
                 allow_mode_c: bool = True,
                 max_fixpoint_iters: int = _MAX_FIXPOINT_ITERS):
        self.w_mk, self.w_dly, self.w_mov = weights
        self.allow_mode_c = allow_mode_c
        self.max_fixpoint_iters = max_fixpoint_iters

        self.positions: list[str] = list(instance["hangar"]["positions"])
        self.n_pos = len(self.positions)

        # rear position -> list of front positions blocking it
        self.fronts_of: dict[str, list[str]] = {p: [] for p in self.positions}
        arcs = [(a["front"], a["rear"]) for a in instance["hangar"]["blocking_arcs"]]
        for front, rear in arcs:
            self.fronts_of[rear].append(front)
        self.position_order = self._topo_order(arcs)

        self.aircraft: list[dict] = list(instance["aircrafts"])
        self.aircraft_ids = [a["id"] for a in self.aircraft]
        self.n_air = len(self.aircraft)
        self.E = {a["id"]: a["earliest_start"] for a in self.aircraft}
        self.L = {a["id"]: a["target_finish"] for a in self.aircraft}

        self.job_by_id = {j["id"]: j for j in instance["jobs"]}
        self.chain: dict[str, list[str]] = self._build_chains(instance)
        self.proc_time = {
            r: sum(self.job_by_id[j]["duration"] for j in self.chain[r])
            for r in self.aircraft_ids
        }

        self.eps = instance.get("min_separation", 0.5)
        self.mu = instance.get("mu", DEFAULT_MU)
        self.delta = instance.get("delta", DEFAULT_DELTA)
        self.eta = instance.get("eta", DEFAULT_ETA)

    def _topo_order(self, arcs: list[tuple[str, str]]) -> list[str]:
        """Kahn topological sort of the blocking DAG (fronts before rears)."""
        succ: dict[str, list[str]] = {p: [] for p in self.positions}
        indeg: dict[str, int] = {p: 0 for p in self.positions}
        for front, rear in arcs:
            succ[front].append(rear)
            indeg[rear] += 1
        queue = [p for p in self.positions if indeg[p] == 0]
        order: list[str] = []
        while queue:
            p = queue.pop(0)
            order.append(p)
            for q in succ[p]:
                indeg[q] -= 1
                if indeg[q] == 0:
                    queue.append(q)
        if len(order) != self.n_pos:  # cycle => not a DAG; fall back to listed order
            return list(self.positions)
        return order

    def _build_chains(self, instance: dict) -> dict[str, list[str]]:
        """Reconstruct each aircraft's ordered job chain from precedences."""
        jobs_of: dict[str, list[str]] = {a["id"]: [] for a in self.aircraft}
        for j in instance["jobs"]:
            jobs_of[j["aircraft_id"]].append(j["id"])
        nxt: dict[str, str] = {}
        has_pred: set[str] = set()
        for p in instance["job_precedences"]:
            nxt[p["before"]] = p["after"]
            has_pred.add(p["after"])
        chains: dict[str, list[str]] = {}
        for r, jids in jobs_of.items():
            heads = [j for j in jids if j not in has_pred]
            head = next((j for j in jids if self.job_by_id[j].get("is_first")), None)
            head = head or (heads[0] if heads else jids[0])
            ordered, cur, seen = [], head, set()
            while cur is not None and cur not in seen:
                ordered.append(cur)
                seen.add(cur)
                cur = nxt.get(cur)
            ordered += [j for j in jids if j not in seen]
            chains[r] = ordered
        return chains


def decode(keys: list[float], ctx: DecoderContext) -> dict:
    """Decode a random-key chromosome into a feasible solution dict.

    Runs the Mode-C fixpoint when enabled; otherwise a single Mode-A/B-only
    pass.  Always returns a checker-consistent schedule."""
    n = ctx.n_air
    assign_keys, seq_keys = keys[:n], keys[n:]
    at_position: dict[str, list[str]] = {p: [] for p in ctx.positions}
    for i, r in enumerate(ctx.aircraft_ids):
        idx = min(int(assign_keys[i] * ctx.n_pos), ctx.n_pos - 1)
        at_position[ctx.positions[idx]].append(r)
    seq_of = {r: seq_keys[i] for i, r in enumerate(ctx.aircraft_ids)}
    for p in ctx.positions:
        at_position[p].sort(key=lambda r: seq_of[r])

    if not ctx.allow_mode_c:
        placed, _ = _decode_pass(ctx, at_position, kappa={}, allow_mode_c=False)
        return _assemble(placed, ctx)

    # Mode-C fixpoint: iterate until the per-job interruption counts stabilise.
    # A separate A/B-only floor pass per decode is deliberately NOT taken: it
    # roughly doubles decode cost and, in a fixed time budget, the lost
    # generations hurt the GA more than the per-chromosome floor helps (measured
    # on the 8 s probe).  The GA's population already explores low-Mode-C
    # chromosomes, so the floor is recovered at the search level, not per decode.
    kappa: dict[tuple[str, str], int] = {}
    for _ in range(ctx.max_fixpoint_iters):
        placed, new_kappa = _decode_pass(ctx, at_position, kappa, allow_mode_c=True)
        if new_kappa == kappa:
            return _assemble(placed, ctx)          # self-consistent fixpoint
        kappa = new_kappa
    # Not converged → Mode-A/B-only pass is always consistent (kappa == {}).
    placed, _ = _decode_pass(ctx, at_position, kappa={}, allow_mode_c=False)
    return _assemble(placed, ctx)


def _decode_pass(ctx, at_position, kappa, allow_mode_c):
    """One forward placement pass with front extensions *kappa* held fixed.

    Returns (placed, modeC_counts) where modeC_counts[(aircraft_id, job_id)] is
    the number of Mode-C events that interrupted that front job during the pass.
    """
    placed: dict[str, dict] = {}
    last_finish: dict[str, float] = {}
    gap_uses: dict[tuple[str, int], int] = {}
    modeC_counts: dict[tuple[str, str], int] = {}

    for pos in ctx.position_order:
        front_positions = ctx.fronts_of[pos]
        for r in at_position[pos]:
            earliest = ctx.E[r]
            if pos in last_finish:
                earliest = max(earliest, last_finish[pos] + ctx.eps)
            front_air = [
                placed[fr]
                for fp in front_positions
                for fr in at_position[fp]
                if fr in placed
            ]
            chosen = _place_aircraft(r, earliest, front_air, ctx, gap_uses,
                                     kappa, allow_mode_c)
            chosen["record"]["position"] = pos
            placed[r] = chosen["record"]
            last_finish[pos] = chosen["record"]["finish"]
            for key in chosen["modeB"]:
                gap_uses[key] = gap_uses.get(key, 0) + 1
            for ev in chosen["modeC"]:
                modeC_counts[ev] = modeC_counts.get(ev, 0) + 1

    return placed, modeC_counts


def _proc_eff(r, ctx, kappa):
    """Effective processing time of *r*, including its own Mode-C extensions
    (relevant when *r* is itself a front interrupted by a deeper rear)."""
    ext = sum(kappa.get((r, jid), 0) for jid in ctx.chain[r])
    return ctx.proc_time[r] + ctx.delta * ext


def _place_aircraft(r, earliest, front_air, ctx, gap_uses, kappa, allow_mode_c):
    """Pick the min-local-cost feasible start for aircraft *r*."""
    proc = _proc_eff(r, ctx, kappa)
    cands = _candidate_starts(earliest, proc, front_air, ctx, allow_mode_c)

    best = None
    for s0 in cands:
        ev = _evaluate(s0, proc, front_air, ctx, gap_uses, allow_mode_c)
        if ev is None:
            continue
        finish = s0 + proc
        delay = max(0.0, finish - ctx.L[r])
        # Local cost: own makespan/delay/movements, plus a rough estimate of the
        # downstream cost of each Mode-C extension (the interrupted front finish
        # shifts by delta, potentially adding to makespan and that front's delay).
        modec_pen = len(ev["modeC"]) * (ctx.w_mk + ctx.w_dly) * ctx.delta
        cost = (ctx.w_mk * finish + ctx.w_dly * delay
                + ctx.w_mov * ev["moves"] + modec_pen)
        if best is None or cost < best["cost"]:
            best = {"cost": cost, "s0": s0, "modeB": ev["modeB"], "modeC": ev["modeC"]}

    if best is None:  # safe-late is always Mode A, so this is a guard only
        best = {"s0": _safe_late(earliest, front_air, ctx), "modeB": [], "modeC": []}

    return {"record": _layout(r, best["s0"], ctx, kappa),
            "modeB": best["modeB"], "modeC": best["modeC"]}


def _candidate_starts(earliest, proc, front_air, ctx, allow_mode_c):
    """Bounded set of candidate start times targeting A/B (and, if enabled, C)
    windows, for both the entry (s0) and the exit (s0+proc) access instant."""
    cands = {earliest}
    for f in front_air:
        cands.add(f["finish"] + ctx.eta)                  # entry Mode-A after f
        cands.add(f["start"] - ctx.eta - proc)            # exit Mode-A before f
        ints = f["intervals"]
        for k in range(len(ints) - 1):                    # Mode-B inter-job gaps
            gap_mid = (ints[k][2] + ints[k + 1][1]) / 2.0
            cands.add(gap_mid)                            # entry in gap k
            cands.add(gap_mid - proc)                     # exit in gap k
        if allow_mode_c:                                  # Mode-C job interiors
            for (jid, js, jf) in ints:
                if jf - js <= 2 * ctx.eta:
                    continue                              # too short to host an interior
                if not ctx.job_by_id.get(jid, {}).get("interruptible", False):
                    continue
                mid = (js + jf) / 2.0
                cands.add(mid)                            # entry inside job jid
                cands.add(mid - proc)                     # exit inside job jid
    cands.add(_safe_late(earliest, front_air, ctx))       # guaranteed Mode A
    clamped = sorted({max(earliest, c) for c in cands})
    if len(clamped) > _MAX_CANDIDATES:
        step = len(clamped) / _MAX_CANDIDATES
        clamped = [clamped[int(i * step)] for i in range(_MAX_CANDIDATES)]
    return clamped


def _safe_late(earliest, front_air, ctx):
    """A start after every incident front finishes => both accesses Mode A."""
    if not front_air:
        return earliest
    return max(earliest, max(f["finish"] for f in front_air) + ctx.eta)


def _evaluate(s0, proc, front_air, ctx, gap_uses, allow_mode_c):
    """Classify entry+exit against every front; return event lists or None.

    None ⇒ infeasible (access inside a non-interruptible job, a too-narrow
    Mode-B gap, or — when Mode C is disabled — any Mode-C access).
    """
    entry, exit_ = s0, s0 + proc
    moves = 0
    new_modeB: list[tuple[str, int]] = []
    new_modeC: list[tuple[str, str]] = []
    local_gap_uses: dict[tuple[str, int], int] = {}

    for f in front_air:
        for tau in (entry, exit_):
            res = _classify_access(
                tau, f["start"], f["finish"], f["intervals"], ctx.job_by_id, ctx.eta
            )
            kind = res["kind"]
            if kind == "A":
                continue
            if kind == "infeasible":
                return None
            if kind == "C":
                if not allow_mode_c:
                    return None
                moves += 2
                new_modeC.append((f["id"], res["job_id"]))
                continue
            # Mode B: enforce the cumulative-mu rule on this front gap
            key = (f["id"], res["gap_index"])
            ints = f["intervals"]
            gap_size = ints[res["gap_index"] + 1][1] - ints[res["gap_index"]][2]
            local_gap_uses[key] = local_gap_uses.get(key, 0) + 1
            total_uses = gap_uses.get(key, 0) + local_gap_uses[key]
            if gap_size + 1e-9 < ctx.mu * total_uses:
                return None
            moves += 2
            new_modeB.append(key)

    return {"moves": moves, "modeB": new_modeB, "modeC": new_modeC}


def _layout(r, s0, ctx, kappa):
    """Lay the job chain out compactly from *s0*, applying each job's Mode-C
    extension ``delta * kappa[(r, jid)]`` (0 for jobs never interrupted)."""
    t = s0
    intervals = []
    for jid in ctx.chain[r]:
        d = ctx.job_by_id[jid]["duration"] + ctx.delta * kappa.get((r, jid), 0)
        intervals.append((jid, t, t + d))
        t += d
    return {"id": r, "start": s0, "finish": t, "intervals": intervals, "position": None}


def _assemble(placed, ctx):
    """Build the checker-shaped solution dict and compute exact metrics.

    Movements are re-derived globally with the checker's own classifier, so the
    reported count is guaranteed consistent with RQ07_v2 (and, at a fixpoint,
    with the kappa baked into the job durations → RQ09).
    """
    aircraft_out = []
    makespan = 0.0
    total_delay = 0.0
    movements = 0

    at_position: dict[str, list[str]] = {p: [] for p in ctx.positions}
    for r, rec in placed.items():
        at_position[rec["position"]].append(r)
    for rear_pos, fronts in ctx.fronts_of.items():
        for rp in at_position[rear_pos]:
            rec = placed[rp]
            for fp in fronts:
                for fr in at_position[fp]:
                    if fr == rp:
                        continue
                    f = placed[fr]
                    for tau in (rec["start"], rec["finish"]):
                        res = _classify_access(
                            tau, f["start"], f["finish"], f["intervals"],
                            ctx.job_by_id, ctx.eta,
                        )
                        if res["kind"] in ("B", "C"):
                            movements += 2

    for r in ctx.aircraft_ids:
        rec = placed[r]
        delay = max(0.0, rec["finish"] - ctx.L[r])
        total_delay += delay
        makespan = max(makespan, rec["finish"])
        aircraft_out.append({
            "id": r,
            "position": rec["position"],
            "start": rec["start"],
            "finish": rec["finish"],
            "delay": delay,
            "jobs": [
                {"id": jid, "start": s, "finish": fin}
                for (jid, s, fin) in rec["intervals"]
            ],
        })

    objective = ctx.w_mk * makespan + ctx.w_dly * total_delay + ctx.w_mov * movements
    return {
        "status": "heuristic",
        "objective": objective,
        "metrics": {
            "makespan": makespan,
            "total_delay": total_delay,
            "movements": movements,
        },
        "aircraft": aircraft_out,
    }
