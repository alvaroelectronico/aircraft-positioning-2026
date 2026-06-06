# iter_0004_lns_plus_extra_ops — re-add intra-pos ops 4-6 on top of LNS

## Hypothesis

In `iter_0002` the intra-position operators (insertion, non-adjacent
swap, EDD repair) didn't move `fast_eval` because LS+single-start
landed in a basin where they were no-ops.  With LNS perturbation (`iter_0003`)
the diversity of basins explored each restart should give those ops new
configurations where they can fire.  Hope: LNS picks new starting
points where the extended ops shave a few more delay units.

## What changed

Re-introduced ops 4, 5, 6 inside `_local_search` (identical code to
`iter_0002`), keeping the LNS perturbation loop from `iter_0003`.  The
LS now runs the full 6-operator portfolio inside every LNS iteration.

LOC delta: ~+90 lines (the operator code from iter_0002, now layered
with the LNS structure).

## Eval result

Mode: `fast_eval` (3 instances, 20 s budget each)

| instance                          | obj_var | obj_milp |    gap | compliant |   t (s) |
| --------------------------------- | ------: | -------: | -----: | :-------: | ------: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |     Y     |   20.00 |
| scn_chain_tight_P5_R10_seed1      |  199.40 |   163.35 | +0.221 |     Y     |   20.00 |
| scn_hub_tight_P5_R10_seed1        |  145.50 |   136.40 | +0.067 |     Y     |   20.00 |

- **score**: **+0.0958** (identical to iter_0003)

## Outcome

**rejected** — extended ops still don't fire on these basins.  Chain_R10
in particular is stuck at exactly 199.40 across iter_0001, iter_0002,
iter_0003, iter_0004 — five distinct LS configurations and the
objective never moves.

## Lessons

- The 6-operator LS portfolio + random-destroy LNS has now plateaued
  on `fast_eval` at the same incumbent the basic 3-op LS reached for
  chain_R10.  Further single-aircraft / pair / intra-position moves
  cannot break 199.40, no matter how many basins LNS visits.
- This is strong evidence that chain_R10's residual gap is structural
  — not a basin-escape problem.  The MILP gets 163.35 (still at 98 %
  MIP gap after 60 s, so even MILP doesn't know the real optimum), and
  the heuristic with Mode-A only sits at 199.40 = 89 makespan + 190.5
  delay × 1.0.  Closing the 34-delay-unit gap probably needs either
  (a) Mode-C exploitation (extend an interruptible front job to absorb
  a rear blocking event without delay), or (b) a smarter destroy
  operator that targets the chain's high-delay cluster instead of
  uniform random aircraft.
- Iter_0005 should try **worst-removal LNS**: destroy the K most-delayed
  aircraft plus their direct blocking-arc neighbours, rebuild, accept.
  This is the standard "shaw / worst-removal" heuristic from the LNS
  literature and is the obvious next thing before tackling Mode-C.
