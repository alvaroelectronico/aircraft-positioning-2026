"""Internal model: normalise a paper-#2 instance JSON for the decoder.

Everything the decoder needs in fixed, reproducible order:

* ``positions`` in hangar order, ``aircraft_ids`` in instance order (so the
  chromosome gene order is stable run-to-run).
* the blocking-arc topology: ``fronts_of[p]`` and a ``topo_positions`` order
  in which every front position precedes the rear positions it blocks.
* per-aircraft job chain (from ``job_precedences`` / ``is_first``), durations,
  interruptibility, aggregate time ``T[r]``.
* the scalar parameters with their paper-#2 defaults:
  ``epsilon = min_separation`` (REQUIRED key), ``mu``, ``delta``, ``eta``.

Note ``epsilon`` and ``eta`` are *distinct*: ``epsilon`` is the same-position
separation (RQ08); ``eta`` is the granularity that defines the access-mode
margins in RQ07 (see ``access.py``).
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

DEFAULT_MU = 1.0
DEFAULT_DELTA = 2.0
DEFAULT_ETA = 1.0
DEFAULT_EPSILON = 0.5


@dataclass
class Model:
    positions: list[str]
    pos_index: dict[str, int]
    arcs: list[tuple[str, str]]
    fronts_of: dict[str, list[str]]
    topo_positions: list[str]

    aircraft_ids: list[str]
    earliest_start: dict[str, float]
    target_finish: dict[str, float]

    chain: dict[str, list[str]]          # aircraft_id -> ordered job ids
    duration: dict[str, float]           # job_id -> nominal duration D_j
    interruptible: dict[str, bool]       # job_id -> I_j
    T: dict[str, float]                  # aircraft_id -> sum of durations

    epsilon: float
    mu: float
    delta: float
    eta: float

    @property
    def num_positions(self) -> int:
        return len(self.positions)

    @property
    def num_aircraft(self) -> int:
        return len(self.aircraft_ids)

    @property
    def chromosome_length(self) -> int:
        return 2 * self.num_aircraft


def _build_chain(aircraft_id: str, jobs: list[dict], precedences: list[dict]) -> list[str]:
    """Reconstruct the linear job chain of one aircraft from precedences."""
    ids = {j["id"] for j in jobs}
    succ: dict[str, str] = {}
    has_pred: set[str] = set()
    for p in precedences:
        if p["before"] in ids and p["after"] in ids:
            succ[p["before"]] = p["after"]
            has_pred.add(p["after"])

    firsts = [j["id"] for j in jobs if j.get("is_first")]
    if not firsts:
        firsts = [jid for jid in ids if jid not in has_pred]
    # Deterministic head if data is odd: smallest id.
    head = sorted(firsts)[0]

    chain = [head]
    seen = {head}
    cur = head
    while cur in succ and succ[cur] not in seen:
        cur = succ[cur]
        chain.append(cur)
        seen.add(cur)

    # Append any stragglers (defensive; well-formed instances are linear).
    for jid in sorted(ids - seen):
        chain.append(jid)
    return chain


def _topo_positions(positions: list[str], arcs: list[tuple[str, str]]) -> list[str]:
    """Kahn topological order; ties broken by hangar position order."""
    indeg = {p: 0 for p in positions}
    adj: dict[str, list[str]] = {p: [] for p in positions}
    seen_edges = set()
    for (f, r) in arcs:
        if (f, r) in seen_edges:
            continue
        seen_edges.add((f, r))
        adj[f].append(r)
        indeg[r] += 1

    order_index = {p: i for i, p in enumerate(positions)}
    queue = deque(sorted([p for p in positions if indeg[p] == 0], key=lambda p: order_index[p]))
    topo: list[str] = []
    while queue:
        n = queue.popleft()
        topo.append(n)
        for m in sorted(adj[n], key=lambda p: order_index[p]):
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if len(topo) != len(positions):  # cycle (should not happen: arcs form a DAG)
        remaining = [p for p in positions if p not in topo]
        topo.extend(remaining)
    return topo


def build_model(instance: dict) -> Model:
    positions = list(instance["hangar"]["positions"])
    pos_index = {p: i for i, p in enumerate(positions)}
    arcs = [(a["front"], a["rear"]) for a in instance["hangar"]["blocking_arcs"]]

    fronts_of: dict[str, list[str]] = {p: [] for p in positions}
    for (f, r) in arcs:
        if f not in fronts_of[r]:
            fronts_of[r].append(f)

    topo_positions = _topo_positions(positions, arcs)

    aircraft_ids = [a["id"] for a in instance["aircrafts"]]
    earliest_start = {a["id"]: float(a["earliest_start"]) for a in instance["aircrafts"]}
    target_finish = {a["id"]: float(a["target_finish"]) for a in instance["aircrafts"]}

    jobs_by_air: dict[str, list[dict]] = defaultdict(list)
    duration: dict[str, float] = {}
    interruptible: dict[str, bool] = {}
    for j in instance["jobs"]:
        jobs_by_air[j["aircraft_id"]].append(j)
        duration[j["id"]] = float(j["duration"])
        interruptible[j["id"]] = bool(j.get("interruptible", False))

    precedences = instance["job_precedences"]
    chain: dict[str, list[str]] = {}
    T: dict[str, float] = {}
    for r in aircraft_ids:
        chain[r] = _build_chain(r, jobs_by_air[r], precedences)
        T[r] = sum(duration[jid] for jid in chain[r])

    return Model(
        positions=positions,
        pos_index=pos_index,
        arcs=arcs,
        fronts_of=fronts_of,
        topo_positions=topo_positions,
        aircraft_ids=aircraft_ids,
        earliest_start=earliest_start,
        target_finish=target_finish,
        chain=chain,
        duration=duration,
        interruptible=interruptible,
        T=T,
        epsilon=float(instance.get("min_separation", DEFAULT_EPSILON)),
        mu=float(instance.get("mu", DEFAULT_MU)),
        delta=float(instance.get("delta", DEFAULT_DELTA)),
        eta=float(instance.get("eta", DEFAULT_ETA)),
    )
