"""GRASP Restricted Candidate List (RCL) helpers.

These three primitives are the only stateful sampling building block
shared across the constructive heuristic, the topology heuristic, and
any other method that wants biased-random selection from a sorted
candidate list.  They were originally inlined in the legacy
``constructive_heuristic.py`` file; extracting them here keeps the RCL
math in one place and lets new methods import it without pulling in any
manual heuristic implementation.

API:

    weights = _grasp_weights(n, alpha)
        Geometric weights for ``n`` candidates: ``w_i = (1 - alpha)^i``.

    item, draw, rank = _biased_random_select_logged(sorted_list, weights, rng)
        Pick one item from ``sorted_list`` (already sorted best-first)
        using the pre-computed ``weights``.  Returns the picked item,
        the random draw value (for reproducibility logging), and its
        rank in ``sorted_list``.

    item = biased_random_select(sorted_list, alpha, rng)
        Convenience wrapper that builds ``weights`` from ``alpha`` and
        calls the logged primitive, discarding the draw/rank.

Note: the underscore-prefixed names are kept because the legacy code
already imports them under those names; renaming them is a future
clean-up step.
"""
from __future__ import annotations

import random
from typing import Any


def _grasp_weights(n: int, alpha: float) -> list[float]:
    """Return geometric weights for n candidates: w_i = (1 - alpha)^i."""
    return [(1.0 - alpha) ** i for i in range(n)]


def _biased_random_select_logged(
    sorted_list: list,
    weights:     list[float],
    rng:         random.Random,
) -> tuple[Any, float, int]:
    """Pick one item using pre-computed geometric weights.

    Returns (selected_item, draw_value, rank).
    """
    total = sum(weights)
    draw  = rng.uniform(0, total)
    cumulative = 0.0
    for rank, (item, w) in enumerate(zip(sorted_list, weights)):
        cumulative += w
        if draw <= cumulative:
            return item, draw, rank
    return sorted_list[-1], draw, len(sorted_list) - 1


def biased_random_select(sorted_list: list, alpha: float, rng: random.Random) -> Any:
    """Pick one item with geometric probability: P(rank i) ∝ (1 - alpha)^i."""
    weights = _grasp_weights(len(sorted_list), alpha)
    item, _, _ = _biased_random_select_logged(sorted_list, weights, rng)
    return item
