"""A lean, self-contained BRKGA over random keys (paper #2, theory_assisted).

Biased Random-Key Genetic Algorithm (Goncalves & Resende).  The decoder is
injected, so this module knows nothing about the problem: it only manipulates
key vectors in [0,1) and minimises the objective returned by ``decode_fn``.

Population is partitioned each generation into elite / mutant / crossover:
* elites are copied unchanged,
* mutants are fresh random vectors (diversity),
* the rest are biased crossovers of one elite and one non-elite parent, each
  gene inherited from the elite parent with probability ``rho``.

Termination is wall-clock (``time_limit_s``).  A shake (resample all
non-elites) fires after ``shake_after`` stagnant generations.
"""
from __future__ import annotations

import random
import time


def run_brkga(
    n_keys: int,
    decode_fn,
    *,
    time_limit_s: float,
    seed: int = 0,
    pop_size: int | None = None,
    elite_frac: float = 0.15,
    mutant_frac: float = 0.10,
    rho: float = 0.70,
    shake_after: int = 50,
    warmstarts: list[list[float]] | None = None,
    log: list[str] | None = None,
):
    """Evolve random-key chromosomes; return (best_solution, best_keys).

    ``decode_fn(keys) -> solution_dict`` must return a dict with a numeric
    ``objective`` (lower is better).
    """
    rng = random.Random(seed)
    pop_size = pop_size or max(100, 10 * n_keys)
    n_elite = max(1, int(elite_frac * pop_size))
    n_mutant = max(1, int(mutant_frac * pop_size))

    def random_keys():
        return [rng.random() for _ in range(n_keys)]

    # --- initial population (warm-starts first, then random) ------------
    population: list[list[float]] = []
    for ws in (warmstarts or [])[:pop_size]:
        population.append(list(ws))
    while len(population) < pop_size:
        population.append(random_keys())

    t0 = time.perf_counter()

    def score_pop(keys_list):
        """Decode a population with a wall-clock guard.  Stops once the budget
        is spent (after at least one decode), so a single slow generation on a
        large instance cannot overrun the time limit by a full generation.
        Keys are ordered elites-first by the caller, so an early stop still
        retains the carried-over elites."""
        out = []
        for k in keys_list:
            if out and time.perf_counter() - t0 >= time_limit_s:
                break
            out.append((decode_fn(k)["objective"], k))
        out.sort(key=lambda t: t[0])
        return out

    scored = score_pop(population)
    best_obj, best_keys = scored[0]

    gen = 0
    stagnant = 0
    while time.perf_counter() - t0 < time_limit_s:
        gen += 1
        elites = scored[:n_elite]
        non_elites = scored[n_elite:]

        next_pop: list[list[float]] = [k for _, k in elites]          # carry elites
        for _ in range(n_mutant):                                     # mutants
            next_pop.append(random_keys())
        while len(next_pop) < pop_size:                               # crossover
            _, ep = rng.choice(elites)
            _, np_ = rng.choice(non_elites) if non_elites else rng.choice(elites)
            child = [ep[i] if rng.random() < rho else np_[i] for i in range(n_keys)]
            next_pop.append(child)

        scored = score_pop(next_pop)
        if scored[0][0] + 1e-9 < best_obj:
            best_obj, best_keys = scored[0]
            stagnant = 0
        else:
            stagnant += 1

        if stagnant >= shake_after:                                   # shake
            kept = scored[:n_elite]
            resampled = [(decode_fn(k := random_keys())["objective"], k)
                         for _ in range(pop_size - n_elite)]
            scored = sorted(kept + resampled, key=lambda t: t[0])
            stagnant = 0
            if log is not None:
                log.append(f"gen {gen}: shake (best={best_obj:.4f})")

    best_sol = decode_fn(best_keys)
    if log is not None:
        log.append(f"done: {gen} gens, best={best_obj:.4f}")
    return best_sol, best_keys
