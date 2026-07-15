# iter_0010_lns_random_repair — uniform-random repair in LNS rotation

## Hypothesis

Greedy GRASP repair (used by iter_0003) consistently sends the LNS
back to the same `(3, 1, 1, 2, 3)` distribution on chain_R10 — the
topology penalty is too strong a bias.  Alternating greedy with
**uniform-random repair** (each destroyed aircraft gets a uniformly
random position, no scoring) should let the search land on the
balanced 2-per-position basin from time to time, after which LS would
polish.

## What changed

In `_solve_single`'s LNS loop, alternate `repair` mode by `kick_idx`
parity:

- even iter → greedy repair (current GRASP scoring).
- odd  iter → uniform repair (`rng.choice(positions)` per destroyed
  aircraft, fully bypassing the topology bias).

LOC delta: ~+15 lines.

## Eval result

`fast_eval` (3 instances, 20 s budget each):

| instance                          | obj_var | obj_milp |    gap |
| --------------------------------- | ------: | -------: | -----: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |
| scn_chain_tight_P5_R10_seed1      |  199.40 |   163.35 | +0.221 |
| scn_hub_tight_P5_R10_seed1        |  145.50 |   136.40 | +0.067 |

- **score**: **+0.0958** (identical to iter_0003).

**Off-benchmark probe (60 s budget):**

| instance                          | iter_0003 | iter_0010 |    MILP |  Δ vs MILP |
| --------------------------------- | --------: | --------: | ------: | ---------: |
| scn_full_tight_P5_R20_seed1       |  1751.70  |  1743.95  | 2533.10 |   **−31%** |
| scn_triangle_tight_P5_R30_seed1   |  2592.80  |  2592.80  | 3208.85 |     −19%   |
| scn_triangle_tight_P5_R20_seed1   |   823.50  |   **760.45** |  823.00 |    **−7.6%** |
| scn_full_tight_P5_R10_seed1       |   341.55  |   324.70  |  180.35 |     +80%   |
| scn_triangle_loose_P5_R10_seed1   |    34.75  |    34.75  |   14.65 |    +137%   |

Random repair flips **triangle_R20** from +0.06 % above MILP to
**−7.6 % below MILP** — a meaningful win the iteration metric can't
see.

## Diagnostic about chain_R10's floor

A direct probe planting MILP's exact balanced assignment
(2 aircraft per position) into our rebuild gives obj=372.30 —
**worse than our heuristic's 199.4 from an unbalanced assignment**.
LS from this MILP-starting state walks AWAY from the balanced
distribution (toward `{P2: 4, P1: 2, P4: 4}` at obj=304).

So the 199.4 floor isn't an LS bug.  Our `_rebuild_job` itself
cannot reproduce MILP's timing on the balanced assignment because
MILP exploits interleaved staggering (R2 enters P2 at t=9 before R6
enters P1 at t=10) that our forward-greedy rebuild can't anticipate.
**Closing chain_R10 needs a smarter rebuild, not a smarter search.**

## Outcome

**rejected** — fast_eval score unchanged.  Working copy reverted to
`iter_0003_lns_perturbation`.

## Lessons

- Random repair IS an objective improvement on R ≥ 20, especially
  triangle_R20 where it crosses below the MILP incumbent.  The
  iteration metric (`fast_eval = {triangle_R5, chain_R10, hub_R10}`)
  is structurally blind to this regime.
- This is the third iteration (after 0002, 0005) where a change is
  rejected by fast_eval despite being valuable on the broader
  benchmark.  Strong case for the user to add at least one R ≥ 20
  instance (preferably `scn_triangle_tight_P5_R20_seed1` — the only
  instance currently sitting on the MILP boundary) to fast_eval.
- The chain_R10 199.4 plateau is no longer an LS-quality problem;
  it's a rebuild-quality problem.  Future work targeting chain
  should reformulate `_rebuild_job` (e.g., as a scheduling-pass
  that knows the full assignment up-front and can stagger starts
  based on global blocking-arc geometry) rather than adding more
  LS operators.
