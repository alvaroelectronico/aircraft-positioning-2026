"""Pure interval-set algebra.

A *window set* is a list of closed intervals ``(lo, hi)`` with ``lo <= hi``,
sorted by ``lo`` and pairwise non-overlapping.  ``hi`` may be ``INF``.

No problem semantics live here — see ``access.py`` for that.
"""
from __future__ import annotations

INF = float("inf")


def intersect_windows(a: list[tuple[float, float]],
                      b: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Intersection of two sorted, disjoint window sets."""
    res: list[tuple[float, float]] = []
    i = j = 0
    while i < len(a) and j < len(b):
        lo = max(a[i][0], b[j][0])
        hi = min(a[i][1], b[j][1])
        if lo <= hi:
            res.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return res


def shift_windows(w: list[tuple[float, float]], d: float) -> list[tuple[float, float]]:
    """Translate every interval by ``d`` (use ``-T`` for the exit constraint)."""
    out: list[tuple[float, float]] = []
    for (lo, hi) in w:
        out.append((lo + d, hi + d if hi != INF else INF))
    return out


def clip_nonnegative(w: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Restrict a window set to the non-negative time domain ``[0, INF)``."""
    out: list[tuple[float, float]] = []
    for (lo, hi) in w:
        lo2 = max(0.0, lo)
        if lo2 <= hi:
            out.append((lo2, hi))
    return out


def first_point_at_or_after(w: list[tuple[float, float]], lb: float) -> float | None:
    """Smallest point in ``w`` that is ``>= lb``; ``None`` if none exists."""
    for (lo, hi) in w:
        if hi < lb:
            continue
        return max(lo, lb)
    return None
