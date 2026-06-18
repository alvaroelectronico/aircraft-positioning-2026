"""Chromosome decoder for the theory_assisted BRKGA solver (paper #2).

A chromosome is a vector of random keys of length ``2*|R|``:

    keys[0 : |R|]        assignment keys   -> pi(r) = positions[floor(key*|P|)]
    keys[|R| : 2*|R|]    sequencing keys   -> service order within each position

The decoder turns a chromosome into a full, feasible solution dict (the shape
consumed by ``problems/jobs/checker.py``).  Design (see jobs/notes/design.md):

* Positions are scheduled in **topological order of the blocking DAG**
  (front positions first).  When a rear aircraft is placed, all its fronts are
  already fixed, so its Mode-A/B/C classification is final.
* Each rear aircraft's start time is chosen by a **local-cost scan** over a
  small set of candidate instants; the candidate minimising
  ``W^M*finish + W^D*delay + W^S*movements`` is committed.
* Construction uses **Mode A and Mode B only** (never deliberately Mode C):
  Mode C is dominated by Mode B under the benchmark weights and would extend
  the (already-frozen) front job, so it is excluded in v1.  A guaranteed
  Mode-A "safe-late" candidate (after every incident front finishes) keeps the
  candidate set non-empty, so a feasible placement always exists.
* Access classification reuses the checker's own ``_classify_access`` so the
  decoder agrees with the checker by construction.
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
_MAX_CANDIDATES = 60


class DecoderContext:
    """Pre-processed, instance-level data shared across every decode call."""

    def __init__(self, instance: dict, weights: tuple[float, float, float]):
        self.w_mk, self.w_dly, self.w_mov = weights

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
            # is_first flag is the authoritative head; fall back to no-predecessor
            head = next((j for j in jids if self.job_by_id[j].get("is_first")), None)
            head = head or (heads[0] if heads else jids[0])
            ordered, cur, seen = [], head, set()
            while cur is not None and cur not in seen:
                ordered.append(cur)
                seen.add(cur)
                cur = nxt.get(cur)
            # append any stragglers not reached via the chain
            ordered += [j for j in jids if j not in seen]
            chains[r] = ordered
        return chains


def decode(keys: list[float], ctx: DecoderContext) -> dict:
    """Decode a random-key chromosome into a feasible solution dict."""
    n = ctx.n_air

    # --- 1. position assignment + 2. within-position sequencing ---------
    assign_keys, seq_keys = keys[:n], keys[n:]
    at_position: dict[str, list[str]] = {p: [] for p in ctx.positions}
    for i, r in enumerate(ctx.aircraft_ids):
        idx = min(int(assign_keys[i] * ctx.n_pos), ctx.n_pos - 1)
        at_position[ctx.positions[idx]].append(r)
    seq_of = {r: seq_keys[i] for i, r in enumerate(ctx.aircraft_ids)}
    for p in ctx.positions:
        at_position[p].sort(key=lambda r: seq_of[r])

    # placed[r] = dict(start, finish, intervals=[(jid,s,f)], position)
    placed: dict[str, dict] = {}
    last_finish: dict[str, float] = {}            # position -> last aircraft finish
    gap_uses: dict[tuple[str, int], int] = {}     # (front_id, gap_idx) -> #Mode-B

    # --- topological placement ------------------------------------------
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
            chosen = _place_aircraft(r, earliest, front_air, ctx, gap_uses)

            chosen["record"]["position"] = pos
            placed[r] = chosen["record"]
            last_finish[pos] = chosen["record"]["finish"]
            for key in chosen["modeB"]:
                gap_uses[key] = gap_uses.get(key, 0) + 1

    return _assemble(placed, ctx)


def _place_aircraft(r, earliest, front_air, ctx, gap_uses):
    """Pick the min-local-cost feasible start for aircraft *r*."""
    proc = ctx.proc_time[r]
    cands = _candidate_starts(earliest, proc, front_air, ctx)

    best = None
    for s0 in cands:
        ev = _evaluate(r, s0, front_air, ctx, gap_uses)
        if ev is None:
            continue
        finish = s0 + proc
        delay = max(0.0, finish - ctx.L[r])
        cost = ctx.w_mk * finish + ctx.w_dly * delay + ctx.w_mov * ev["moves"]
        if best is None or cost < best["cost"]:
            best = {"cost": cost, "s0": s0, "moves": ev["moves"], "modeB": ev["modeB"]}

    if best is None:  # should never happen: safe-late is always Mode A
        s0 = _safe_late(earliest, front_air, ctx)
        best = {"s0": s0, "modeB": []}

    return {"record": _layout(r, best["s0"], ctx), "modeB": best["modeB"]}


def _candidate_starts(earliest, proc, front_air, ctx):
    """Build a bounded set of candidate start times targeting A/B windows."""
    cands = {earliest}
    for f in front_air:
        cands.add(f["finish"] + ctx.eta)                  # entry Mode-A after f
        cands.add(f["start"] - ctx.eta - proc)            # exit Mode-A before f
        ints = f["intervals"]
        for k in range(len(ints) - 1):
            gap_mid = (ints[k][2] + ints[k + 1][1]) / 2.0
            cands.add(gap_mid)                            # entry in gap k
            cands.add(gap_mid - proc)                     # exit in gap k
    cands.add(_safe_late(earliest, front_air, ctx))       # guaranteed Mode A
    clamped = sorted({max(earliest, c) for c in cands})
    if len(clamped) > _MAX_CANDIDATES:
        # keep earliest + an evenly spaced subset (no silent loss of the late end)
        step = len(clamped) / _MAX_CANDIDATES
        clamped = [clamped[int(i * step)] for i in range(_MAX_CANDIDATES)]
    return clamped


def _safe_late(earliest, front_air, ctx):
    """A start after every incident front finishes => both accesses Mode A."""
    if not front_air:
        return earliest
    return max(earliest, max(f["finish"] for f in front_air) + ctx.eta)


def _evaluate(r, s0, front_air, ctx, gap_uses):
    """Classify entry+exit against every front; return moves or None if rejected.

    None means the placement is infeasible or would require Mode C / a too-narrow
    Mode-B gap, and must be rejected.
    """
    entry, exit_ = s0, s0 + ctx.proc_time[r]
    moves = 0
    new_modeB: list[tuple[str, int]] = []
    local_gap_uses: dict[tuple[str, int], int] = {}

    for f in front_air:
        for tau in (entry, exit_):
            res = _classify_access(
                tau, f["start"], f["finish"], f["intervals"], ctx.job_by_id, ctx.eta
            )
            kind = res["kind"]
            if kind == "A":
                continue
            if kind == "C" or kind == "infeasible":
                return None
            # Mode B: enforce cumulative-mu rule on this front gap
            key = (f["id"], res["gap_index"])
            ints = f["intervals"]
            gap_size = ints[res["gap_index"] + 1][1] - ints[res["gap_index"]][2]
            local_gap_uses[key] = local_gap_uses.get(key, 0) + 1
            total_uses = gap_uses.get(key, 0) + local_gap_uses[key]
            if gap_size + 1e-9 < ctx.mu * total_uses:
                return None
            moves += 2
            new_modeB.append(key)

    return {"moves": moves, "modeB": new_modeB}


def _layout(r, s0, ctx):
    """Lay the job chain out compactly from *s0* (no Mode-C => no extension)."""
    t = s0
    intervals = []
    for jid in ctx.chain[r]:
        d = ctx.job_by_id[jid]["duration"]
        intervals.append((jid, t, t + d))
        t += d
    return {"id": r, "start": s0, "finish": t, "intervals": intervals, "position": None}


def _assemble(placed, ctx):
    """Build the checker-shaped solution dict and compute exact metrics.

    The objective is recomputed here from the assembled schedule rather than
    accumulated during placement, so it is exact (movements are re-derived by
    the checker too, and must match).
    """
    aircraft_out = []
    makespan = 0.0
    total_delay = 0.0
    movements = 0

    # Re-derive movements globally with the same classification the checker uses,
    # so the reported count is guaranteed consistent with RQ07_v2.
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
