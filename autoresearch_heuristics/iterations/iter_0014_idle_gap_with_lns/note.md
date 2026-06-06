# iter_0014_idle_gap_with_lns — idle-gap LS op layered on iter_0011's LNS

## Hypothesis

iter_0009 added idle-gap insertion as Op 4 but didn't fire — without
LNS diversity, the initial LS basin had no productive Δ-delay moves.
Re-adding it on top of iter_0011's random-repair LNS should give
each new basin a chance to discover delay-by-design moves that the
greedy rebuild can't anticipate.

## What changed

- `_rebuild_job(..., start_overrides=None)` — re-added the optional
  per-aircraft start floor (iter_0009).
- LS Op 4: for each aircraft, try `start_override = earliest_start + Δ`
  for `Δ ∈ {0, 2, 5, 10, 20, 50, 100}`.  100 added (vs iter_0009)
  because R=20 instances need bigger delays for the slot-2 staggering
  MILP uses.  Δ=0 clears any prior override.
- All four `_rebuild_job` call-sites inside `_local_search` now
  thread `start_overrides`.

LOC delta: ~+45 lines.

## Eval result

| instance                          | obj_var | obj_milp |      gap | compliant |
| --------------------------------- | ------: | -------: | -------: | :-------: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 |   +0.000 |     Y     |
| scn_chain_tight_P5_R10_seed1      |  199.40 |   163.35 |   +0.221 |     Y     |
| scn_hub_tight_P5_R10_seed1        |  145.50 |   136.40 |   +0.067 |     Y     |
| scn_triangle_tight_P5_R20_seed1   |  **793.85** |   823.00 | **−0.035** |     Y     |

- **score**: **+0.0630** (iter_0011 had +0.0691 — a 9 % reduction).
- triangle_R20 improvement is decisive: 814.0 → 793.85, now 3.5 % below
  the MILP's 60 s incumbent.

## Outcome

**accepted** — `best.txt → iter_0014_idle_gap_with_lns`.

## Lessons

- The idle-gap operator NEEDS LNS-induced basin diversity to fire.
  In iter_0009 (no LNS perturbation) every Δ tested was rejected
  because the construction's initial basin had no slack for
  productive delays.  After iter_0011's random-repair LNS produces
  varied basins, the same operator finds 20+ unit improvements on
  R=20.
- Extending the Δ set to 100 (in addition to 50) matters: triangle_R20
  uses a longer schedule where 100-unit delays for late aircraft are
  rational.
- chain_R10 and hub_R10 still don't move — the idle-gap is binding
  only when the schedule has room.  On tight R=10 instances any
  delay propagates immediately to tardiness; the operator correctly
  declines those moves.
- Next directions: (a) bigger Δ menu (200, 500) for R=30+ scale,
  (b) try idle-gap on the **last** aircraft of a position to push
  slot-2 staggering, (c) add a "pair-delay" op that simultaneously
  delays two aircraft at adjacent positions.
