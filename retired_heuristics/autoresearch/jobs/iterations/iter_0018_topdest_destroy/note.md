# iter_0018_topdest_destroy — destroy the 2 most-populated positions in LNS

## Hypothesis

Random destroy keeps stumbling into the same (3, 1, 1, 2, 3) basin on
chain.  Explicit "destroy every aircraft at the top-2 most-populated
positions" forces rebalancing in one LNS shot.

## What changed

LNS now cycles three modes (was two):
  0: random destroy + greedy repair
  1: random destroy + uniform repair  (iter_0011)
  2: topdest destroy + uniform repair  (new)

topdest picks the two positions with the most aircraft and destroys all
of them, then uniform-randomly reassigns.

## Eval result

| instance       | obj_var | obj_milp |    gap |
| -------------- | ------: | -------: | -----: |
| triangle_R5    |    3.00 |     3.00 | +0.000 |
| chain_R10      |  199.40 |   163.35 | +0.221 |
| hub_R10        |  145.50 |   136.40 | +0.067 |
| triangle_R20   |  **786.85** |   823.00 | **-0.044** |

Score +0.0609 (iter_0014 had +0.0630 — 3.3 % better).

## Outcome

**accepted** — triangle_R20 dropped another 7 units; now 4.4 % below the
MILP incumbent.

## Lessons

- Position-targeted destroy is more productive than random destroy on
  instances where the incumbent stacks aircraft at extreme positions.
  Forces an instant rebalance that random destroy would have to find
  by chance.
