# iter_0023_chained_multistart — share incumbent across multi-starts

## Hypothesis

Each multi-start currently does its own construction + LS + LNS from
scratch.  6 starts = 6 shallow LNS explorations.  Instead, run starts
1..5 with the GLOBAL BEST so far as their starting incumbent (skip
construction, run LS + LNS from there).  Effectively pools all six
starts' LNS budgets on the same basin neighbourhood, with fresh RNG
for diversification.

## What changed

- `_solve_single(..., seed_assignment=None)` accepts an external
  starting incumbent; skips `_construct` when provided.
- `_solve_single` returns `(sol, obj, assignment)` so caller can
  thread the incumbent forward.
- `solve()` runs n_starts iterations with shared_assignment that gets
  updated on every improvement.

LOC delta: ~+15 lines.

## Eval result

| instance       | obj_var | obj_milp |    gap |
| -------------- | ------: | -------: | -----: |
| triangle_R5    |    3.00 |     3.00 | +0.000 |
| chain_R10      |  198.80 |   163.35 | +0.217 |
| hub_R10        |  145.50 |   136.40 | +0.067 |
| triangle_R20   |  **780.35** |   823.00 | **-0.052** |

Score +0.0580 (iter_0022 had +0.0600 — 3.4 % better).

## Outcome

**accepted** — triangle_R20 gains another 6.5 obj units, now 5.2 % below
MILP.  No regression on the smaller instances.

## Lessons

- Chained multi-start is the right pattern here: the LNS finds
  improvements asymptotically, so 6 × (short LNS) loses to 1 × (long
  LNS) with multi-seed diversification.  The construction step is
  cheap; running it n_starts times was wasted budget.
- chain_R10 and hub_R10 still stuck — even with 6× the effective LNS
  budget on one basin, they can't go lower.  Rebuild quality, not
  search quality.
