# iter_0009_idle_gap_insertion — start-override operator

## Hypothesis

`_rebuild_job` lays jobs back-to-back and only delays aircraft when
forced by a Mode-A conflict.  An LS operator that lets an aircraft
start later than necessary (a Mode-B-in-spirit "intentional idle")
might let downstream rears avoid a conflict they currently inherit
from a too-early front.

## What changed

- `_rebuild_job(..., start_overrides=None)` — when provided, aircraft
  start at `max(earliest_start, pos_free, start_overrides[aid])`.
- LS Op 4: for each aircraft, try `start_override = earliest_start + Δ`
  for `Δ ∈ {0, 2, 5, 10, 20, 50}` (Δ=0 clears any previously set
  override).  `start_overrides` is persisted across LS iterations
  and across all four operators' rebuild calls.

LOC delta: ~+35 lines.

## Eval result

| instance                          | obj_var | obj_milp |    gap |
| --------------------------------- | ------: | -------: | -----: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |
| scn_chain_tight_P5_R10_seed1      |  199.40 |   163.35 | +0.221 |
| scn_hub_tight_P5_R10_seed1        |  145.50 |   136.40 | +0.067 |

- **score**: **+0.0958** (identical to iter_0003).

## Outcome

**rejected** — Op 4 found no improving idle-gap insertion.  Working
copy reverted to `iter_0003_lns_perturbation`.

## Lessons

- MILP's chain_R10 solution has no idle gaps: the two "slots" of
  5 aircraft each start back-to-back (slot 2 begins right after
  slot 1 finishes its longest member).  So idle-gap insertion is
  the wrong lever for this benchmark — the residual gap is **pure
  position-assignment quality**, not timing-discretion.
- This empirically confirms iter_0008's diagnosis: closing the chain
  basin requires a 4+-aircraft simultaneous position move (e.g.,
  rebalance "3 at P1 + 3 at P5" to "2 at P1 + 2 at P5 + 1 at P3
  + 1 at P2") that none of single-move / 2-opt swap / intra-pos /
  3-cycle / LNS-random-destroy can stumble into without further
  guidance.
- Next direction: **random-repair LNS** — in the LNS rotation, mix
  in iterations where the destroyed aircraft are reassigned to
  uniformly random positions (no greedy scoring).  This bypasses the
  topology-penalty bias entirely and could land on the MILP-style
  even distribution by chance, after which LS would polish.
