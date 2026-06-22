"""Self-contained BRKGA evolutionary loop (no external library, no IPR).

Standard BRKGA generation:
  1. carry the elite unchanged,
  2. add fresh random mutants,
  3. fill the rest with biased crossover (elite gene kept with prob rho).

Deterministic given ``seed``.  The time budget is checked once per generation;
the best feasible solution seen (including the initial greedy seed) is always
available as a fallback, so ``solve`` returns something even for a tiny budget.
"""
from __future__ import annotations

import random
import time

from brkga.decoder import decode
from brkga.instance import Model
from brkga.state import ScheduleState
from brkga.warm_start import greedy_seed


def run_brkga(model: Model,
              weights: dict[str, float],
              time_limit_s: float,
              seed: int = 1,
              allow_mode_c: bool = False,
              instance: dict | None = None,
              pop_size: int | None = None,
              elite_frac: float = 0.15,
              mutant_frac: float = 0.10,
              rho: float = 0.7) -> tuple[float, ScheduleState, int]:
    """Run BRKGA; return (best objective, best schedule state, generations).

    When allow_mode_c and an instance are given, fitness uses the Mode-C build
    validated by the real checker (see ``decoder.decode``)."""
    rng = random.Random(seed)
    L = model.chromosome_length
    if pop_size is None:
        pop_size = max(100, 10 * L)          # 10 * 2|R|
    n_elite = max(1, int(elite_frac * pop_size))
    n_mutant = max(1, int(mutant_frac * pop_size))

    def fitness(ch: list[float]) -> float:
        return decode(ch, model, weights, allow_mode_c, instance)[0]

    # Initial population: one greedy seed + random.
    population: list[list[float]] = [greedy_seed(model, weights)]
    while len(population) < pop_size:
        population.append([rng.random() for _ in range(L)])

    scored = sorted(((fitness(ch), ch) for ch in population), key=lambda x: x[0])
    best_fit, best_ch = scored[0]

    t0 = time.perf_counter()
    generations = 0
    while time.perf_counter() - t0 < time_limit_s:
        elite = scored[:n_elite]
        non_elite = scored[n_elite:]

        next_pop: list[list[float]] = [ch for (_, ch) in elite]
        for _ in range(n_mutant):
            next_pop.append([rng.random() for _ in range(L)])
        while len(next_pop) < pop_size:
            e = elite[rng.randrange(len(elite))][1]
            ne = (non_elite[rng.randrange(len(non_elite))][1]
                  if non_elite else elite[rng.randrange(len(elite))][1])
            child = [e[i] if rng.random() < rho else ne[i] for i in range(L)]
            next_pop.append(child)

        scored = sorted(((fitness(ch), ch) for ch in next_pop), key=lambda x: x[0])
        if scored[0][0] < best_fit:
            best_fit, best_ch = scored[0]
        generations += 1

    obj, state = decode(best_ch, model, weights, allow_mode_c, instance)
    return obj, state, generations
