"""Greedy/NEH warm-start seed + reverse-encoding.

A single deterministic seed chromosome is injected into the initial BRKGA
population (the rest is random).  No other method is read — not even cached MILP
solutions; the seed is built from scratch.

NEH order: aircraft by descending aggregate time ``T_r``, ties broken by the
tighter slack ``L_r − E_r − T_r``.  Each aircraft is greedily inserted into the
position that minimises the partial objective (it is appended to the end of that
position's current sequence — the cheap first-version insertion).  The resulting
assignment + per-position order is reverse-encoded into a key vector that the
decoder reproduces exactly.
"""
from __future__ import annotations

from brkga.decoder import build_schedule
from brkga.instance import Model
from brkga.state import ScheduleState

_INFEASIBLE_PENALTY = 1e9


def _partial_objective(state: ScheduleState, model: Model,
                       assigned: list[str], weights: dict[str, float]) -> float:
    makespan = max((state.aircraft[r].finish for r in assigned), default=0.0)
    delay = sum(max(0.0, state.aircraft[r].finish - model.target_finish[r])
                for r in assigned)
    return (weights["makespan"] * makespan
            + weights["delay"] * delay
            + weights["movements"] * state.movements
            + _INFEASIBLE_PENALTY * state.infeasible_accesses)


def _neh_order(model: Model) -> list[str]:
    def key(r: str) -> tuple[float, float]:
        slack = model.target_finish[r] - model.earliest_start[r] - model.T[r]
        return (-model.T[r], slack)
    return sorted(model.aircraft_ids, key=key)


def greedy_assignment(model: Model, weights: dict[str, float]
                      ) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Build (pi, seq_order) by NEH-style best-position insertion."""
    pi: dict[str, str] = {}
    seq_order: dict[str, list[str]] = {p: [] for p in model.positions}
    assigned: list[str] = []

    for r in _neh_order(model):
        best_p = None
        best_obj = None
        for p in model.positions:
            seq_order[p].append(r)
            pi[r] = p
            state = build_schedule(pi, seq_order, model)
            obj = _partial_objective(state, model, assigned + [r], weights)
            if best_obj is None or obj < best_obj:
                best_obj = obj
                best_p = p
            seq_order[p].pop()
        pi[r] = best_p
        seq_order[best_p].append(r)
        assigned.append(r)

    return pi, seq_order


def reverse_encode(pi: dict[str, str], seq_order: dict[str, list[str]],
                   model: Model) -> list[float]:
    """Encode an assignment + ordering into keys the decoder reproduces exactly."""
    nR = model.num_aircraft
    nP = model.num_positions
    idx_of = {r: i for i, r in enumerate(model.aircraft_ids)}
    chromo = [0.0] * (2 * nR)

    for r in model.aircraft_ids:
        k = model.pos_index[pi[r]]
        chromo[idx_of[r]] = (k + 0.5) / nP

    for p, order in seq_order.items():
        n = max(len(order), 1)
        for rank, r in enumerate(order):
            chromo[nR + idx_of[r]] = (rank + 0.5) / n

    return chromo


def greedy_seed(model: Model, weights: dict[str, float]) -> list[float]:
    pi, seq_order = greedy_assignment(model, weights)
    return reverse_encode(pi, seq_order, model)
