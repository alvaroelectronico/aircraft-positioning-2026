# iter_0026_fine_grained_deltas — expand idle-gap Δ menu

## Hypothesis

The iter_0014 Δ menu `{0, 2, 5, 10, 20, 50, 100}` misses any productive
delay value between those — e.g., a 3-unit or 7-unit delay that exactly
aligns slot-2 with slot-1's clear time.

## What changed

Expanded Δ menu to `{0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 70, 100, 150}`.
14 values instead of 7.

## Eval result

| instance       | obj_var | obj_milp |    gap |
| -------------- | ------: | -------: | -----: |
| triangle_R5    |    3.00 |     3.00 | +0.000 |
| chain_R10      |  **183.00** |   163.35 | **+0.120** |
| hub_R10        |  145.50 |   136.40 | +0.067 |
| triangle_R20   |  **743.50** |   823.00 | **-0.097** |

Score +0.0226 (iter_0023 had +0.0580 — **61 % better**).

chain_R10 cracked the 198.8 floor — now at 183.0.
triangle_R20 deepens to **9.7 % below MILP** (was 5.2 %).

## Outcome

**accepted** — single biggest jump since iter_0001 -> iter_0003 LNS.

## Lessons

- The Δ menu density matters more than its range.  Adding 1, 3, 7,
  15, 30, 70 between the existing values lets the idle-gap operator
  find exact alignment points the coarse grid misses.
- chain_R10 floor is NOT 198.8 — it's lower.  The previous "floor"
  was a Δ-grid artifact, not a structural rebuild limit.
