# iter_0008_balance_plus_3cycle — balance scoring + 3-cycle position swap

## Hypothesis

MILP's chain_R10 solution distributes aircraft 2-per-position, while our
heuristic clusters (3, 1, 1, 2, 3) at positions P1..P5 — the topology
penalty pushes heavy aircraft to P5 (zero blocking_load) and lighter
aircraft to P1, leaving the middle empty.  Two changes to break the
basin:

1. **Balance scoring** in construction — alternate "topology" and
   "balance" across multi-starts; balance penalises stacking with
   `weight × duration × (count + 1)²`.
2. **3-cycle position swap** as LS Op 4 — for every ordered triple
   `(a, b, c)` with distinct positions, try the rotation
   `a → pos(b), b → pos(c), c → pos(a)`.  Reaches 3-aircraft
   neighbourhoods that single-move and 2-opt swap can't.

## What changed

- `_solve_single(..., scoring="topology"|"balance")` plumbed through
  to `_construct`.
- `_construct(..., scoring)` adds a per-candidate balance penalty.
- `solve()` alternates `scoring` per multi-start (`k % 2`).
- `_local_search` gains Op 4: 3-cycle rotation in `O(R³)` per pass.

LOC delta: ~+90 lines.

## Eval result

| instance                          | obj_var | obj_milp |    gap |
| --------------------------------- | ------: | -------: | -----: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |
| scn_chain_tight_P5_R10_seed1      |  204.60 |   163.35 | +0.253 |
| scn_hub_tight_P5_R10_seed1        |  145.50 |   136.40 | +0.067 |

- **score**: **+0.1064** (worse than iter_0003's +0.0958).
- chain_R10 regressed from 199.4 to 204.6.

Diagnostic probes (chain_R10):

| config                       |  obj |
| ---------------------------- | ---: |
| topology, n_starts=6 (seeds 1-6) | 199.4 |
| topology, n_starts=3 (seeds 1-3) | 204.6 |
| balance,  n_starts=6 (seeds 1-6) | 204.15 |

The 199.4 basin lives in seeds 4-6.  iter_0008's mixed strategy uses
seeds 1, 3, 5 for topology and 2, 4, 6 for balance — so the topology
half misses the seed that finds 199.4, and the balance half can't
reach it either.  3-cycle didn't escape the worse basin either.

## Outcome

**rejected** — chain_R10 regression dominates the score.  Working copy
reverted to `iter_0003_lns_perturbation`.

## Lessons

- **Diversification via construction scoring is value-destroying when
  the harness fixes n_starts.**  Splitting 6 starts into 3 + 3 halves
  the effective coverage of each strategy.  If one strategy hits a
  rare-but-decisive basin only with certain seeds, halving its seed
  pool can silently break the run.  Any future strategy-mixing
  iteration must verify the per-strategy-with-full-n_starts result
  individually before deploying.
- **Balance penalty doesn't actually balance.** Even with the quadratic
  stacking penalty, the LS+LNS converges to the same (3, 1, 1, 2, 3)
  distribution.  The LS dominates the construction's bias.  Achieving
  the MILP's even distribution likely needs an LS operator that
  explicitly rebalances counts (e.g., "move one aircraft from a 3-stack
  to a 1-stack and adjust order").
- **3-cycle swap is correct but doesn't fire on this basin.**  Likely
  every 3-rotation reachable from the local optimum has a worse
  objective than the current state (any single rotation makes things
  worse before they get better — needs LNS-style basin escape).
- Next direction: **idle-gap insertion in the rebuild**.  Currently
  `_rebuild_job` lays jobs back-to-back and only delays via conflict
  resolution.  An LS operator that lets an aircraft start later than
  necessary (intentional idle) gives the rebuild a Mode-B-in-spirit
  degree of freedom: by holding F back, downstream blocked aircraft
  may save more delay than F loses.  This is what the MILP can do
  globally and we currently can't.
