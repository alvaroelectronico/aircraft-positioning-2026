# iter_0006_multi_strategy_construction — diversified construction order per multi-start

## Hypothesis

Every multi-start replicate currently uses the same greedy order
(heaviest-first); only the RCL pick differs.  Cycling through six
ordering strategies (heaviest, lightest, EDD, earliest, slack, random)
across the six multi-starts should produce genuinely diverse starting
points and crack chain_R10's 199.4 plateau.

## What changed

`autoresearch_heuristics/topology_heuristic_job.py`:

- Added module-level tuple `_CONSTR_STRATEGIES` with six labels.
- `solve()` now passes `_CONSTR_STRATEGIES[k % len(...)]` to
  `_solve_single` per multi-start replicate.
- `_solve_single` accepts a `strategy` arg and threads it into the
  initial `_construct` call AND into every LNS rebuild call (so each
  multi-start preserves its bias across LNS perturbations).
- `_construct` now accepts a `strategy` arg; six sort keys map to the
  six labels.
- Added a compliance gate on the **initial** `_local_search` state
  (previously only LS *improvements* were compliance-gated).  Without
  this, the lightest/earliest/EDD strategies' constructions can land on
  assignments whose Mode-A rebuild is infeasible; that state survives
  as `best_sol` and contaminates the multi-start best.  The gate sets
  `best_obj = +inf` when the initial is non-compliant, so any compliant
  LS move strictly dominates.

LOC delta: ~+50 lines.

## Eval result

Mode: `fast_eval`  (3 instances, 20 s budget each)

| instance                          | obj_var | obj_milp |    gap | compliant |   t (s) |
| --------------------------------- | ------: | -------: | -----: | :-------: | ------: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |     Y     |   20.00 |
| scn_chain_tight_P5_R10_seed1      |  203.00 |   163.35 | +0.243 |     Y     |   20.00 |
| scn_hub_tight_P5_R10_seed1        |  145.50 |   136.40 | +0.067 |     Y     |   20.00 |

- **score**: **+0.1031** (worse than iter_0003's +0.0958)
- **n_compliant**: 3 / 3

## Outcome

**rejected** — chain_R10 regressed from 199.4 to 203.0; the strategy
diversification produces objectively worse starting points on this
instance, and LNS can't recover the gap inside 20 s.  Working copy
reverted to `iter_0003_lns_perturbation`.

## Lessons

- Heaviest-first really is the right greedy order for these benchmarks;
  the diversification idea (more strategies → broader exploration) is
  wrong here.  The "diverse" strategies (lightest, EDD, earliest, slack,
  random) consume 5/6 of the multi-start budget on inferior basins that
  the single best heaviest start would have explored more deeply.
- A second-order discovery: the lightest/earliest/EDD orderings on
  chain_R10 produce a construction whose Mode-A rebuild is **infeasible**
  under the checker (the resolver loops converge but emit an assignment
  that violates some constraint we don't fully enforce).  The added
  initial-compliance gate now correctly discards them; without it,
  non-compliant solutions were leaking up through the multi-start best
  selection.  This is a real bug fix even though the iteration is
  rejected — keep the lesson when reverting.
- Next direction: **Mode-C exploitation**.  All five preceding
  iterations (0001-0005) hit obj 199.4 exactly on chain_R10, regardless
  of LS portfolio width or LNS destroy strategy.  This is almost
  certainly the Mode-A floor.  Closing the 36-unit gap to the MILP's
  163.35 requires either Mode-B (insert inter-job gaps in front aircraft)
  or Mode-C (extend interruptible front job to absorb a rear's access
  without delay).  Mode-C is the simpler of the two and has a cost of
  δ + 2·W^Mov = 22 per event, so it's worth it whenever a single Mode-C
  event saves > 22 units of delay — which is plausible on chain_R10
  with per-aircraft delays in the 15-25 range.
