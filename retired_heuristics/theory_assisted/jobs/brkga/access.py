"""Access-mode semantics — a faithful mirror of ``problems/jobs/checker.py``.

The decoder must compute movements *exactly* as the checker does, otherwise
RQ07's count-match fails.  ``classify_access`` therefore reproduces
``checker._classify_access`` line-for-line (same ``eta`` margins, same
``TOL``).  ``mode_a_windows_for_position`` builds the *constructive* dual: the
set of access instants that are Mode-A against every front aircraft of a rear
position, used by the decoder's earliest-feasible-start sweep.

Mode A (front vacant) : tau <= s_front - eta   OR   tau >= f_front + eta
Mode B (inter-job gap) : tau in [f_{j_k}, s_{j_{k+1}}]
Mode C (mid interruptible job) : s_j + eta <= tau <= f_j - eta, I_j = 1
otherwise -> infeasible
"""
from __future__ import annotations

from brkga.instance import Model
from brkga.state import ScheduleState
from brkga.windows import INF, clip_nonnegative, intersect_windows

TOL = 1e-4  # identical to checker.TOL


def classify_access(tau: float,
                    r_start: float,
                    r_finish: float,
                    job_intervals: list[tuple[str, float, float]],
                    model: Model) -> str:
    """Return 'A' | 'B' | 'C' | 'infeasible' for one access against one front."""
    eta = model.eta

    if tau <= r_start - eta + TOL:
        return "A"
    if tau >= r_finish + eta - TOL:
        return "A"

    # Mode C candidate: strictly inside some job of the blocker.
    for (jid, j_start, j_finish) in job_intervals:
        if j_start + eta - TOL <= tau <= j_finish - eta + TOL:
            return "C" if model.interruptible.get(jid, False) else "infeasible"

    # Mode B candidate: inside an inter-job gap of the blocker.
    for k in range(len(job_intervals) - 1):
        fk = job_intervals[k][2]
        sk1 = job_intervals[k + 1][1]
        if fk - TOL <= tau <= sk1 + TOL:
            return "B"

    # Boundary touches of the front aircraft's own slot edges -> Mode A.
    if r_start - eta <= tau <= r_start + TOL:
        return "A"
    if r_finish - TOL <= tau <= r_finish + eta:
        return "A"

    return "infeasible"


def mode_a_windows_for_position(p: str, state: ScheduleState, model: Model
                                ) -> list[tuple[float, float]]:
    """Access instants that are Mode-A against *every* front aircraft of ``p``.

    Each front aircraft with aircraft-level stay [s, f] permits Mode-A access in
    ``[0, s - eta] U [f + eta, INF)``.  The position window is the intersection
    over all front aircraft of all front positions of ``p``.
    """
    windows: list[tuple[float, float]] = [(0.0, INF)]
    for q in model.fronts_of.get(p, []):
        for r in state.by_position.get(q, []):
            ac = state.aircraft[r]
            comp: list[tuple[float, float]] = []
            left_hi = ac.start - model.eta
            if left_hi >= 0.0:
                comp.append((0.0, left_hi))
            comp.append((ac.finish + model.eta, INF))
            windows = intersect_windows(windows, comp)
            if not windows:
                break
    return clip_nonnegative(windows)


def count_movements(state: ScheduleState, model: Model) -> tuple[int, int]:
    """Replicate the checker's RQ07 pass: total movements and infeasible count.

    In v0 (contiguous jobs, no Mode C) every access is Mode A, so this returns
    ``(0, 0)``.  Implemented in full so it also serves as a self-check and
    supports Mode-B/C in later milestones.
    """
    movements = 0
    infeasible = 0
    for (p_front, p_rear) in model.arcs:
        fronts = state.by_position.get(p_front, [])
        rears = state.by_position.get(p_rear, [])
        for rf in fronts:
            front = state.aircraft[rf]
            job_intervals = [(j.job_id, j.start, j.finish) for j in front.jobs]
            for rr in rears:
                if rr == rf:
                    continue
                rear = state.aircraft[rr]
                for tau in (rear.start, rear.finish):
                    kind = classify_access(tau, front.start, front.finish,
                                            job_intervals, model)
                    if kind in ("B", "C"):
                        movements += 2
                    elif kind == "infeasible":
                        infeasible += 1
    return movements, infeasible
