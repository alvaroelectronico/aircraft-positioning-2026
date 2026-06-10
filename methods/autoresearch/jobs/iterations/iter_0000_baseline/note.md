# iter_0000_baseline — seeded copy of `solvers/topology_heuristic_job.py`

## Hypothesis

None.  This is the starting point of the autoresearch loop: a verbatim copy of
the canonical `TopologyHeuristicJob` from `solvers/topology_heuristic_job.py`
at the time the loop was bootstrapped.  Future iterations will be measured
against this score.

## What changed

Nothing.  The working copy was seeded with
`cp solvers/topology_heuristic_job.py autoresearch_heuristics/topology_heuristic_job.py`.

The variant is Mode-A-only construction with no local-search portfolio:

- Greedy job-by-job placement using the RCL/multi-start construction.
- `_resolve_rear_interactions` / `_resolve_front_interactions` convergence loop
  to keep solutions feasible.
- No single-move, no 2-opt swap, no intra-position reorder operators.
- $\hat n_{rp} = 0$ as the movement proxy during construction (so the $W^S = 10$
  movement weight is effectively inert in the cost-of-placement heuristic).

## Eval result

Mode: `fast_eval`  (3 instances, 20 s budget each)

| instance                          |   obj_var |  obj_milp |     gap | compliant |  t (s) |
| --------------------------------- | --------: | --------: | ------: | :-------: | -----: |
| scn_triangle_tight_P5_R5_seed1    |     35.05 |      3.00 | +10.683 |     Y     |   0.01 |
| scn_chain_tight_P5_R10_seed1      |    294.80 |    163.35 |  +0.805 |     Y     |   0.02 |
| scn_hub_tight_P5_R10_seed1        |    171.30 |    136.40 |  +0.256 |     Y     |   0.02 |

- **score (mean gap)**: **+3.9146**
- **n_compliant**: 3 / 3
- **elapsed**: 0.07 s

The triangle instance dominates the mean because its MILP optimum is essentially
zero-delay (obj=3.0, makespan-only) while the heuristic accepts 30 units of
delay — a huge relative gap on a tiny absolute denominator.  Future iterations
should pay attention to whether they improve this instance specifically, since
it has the most leverage on the score.

## Outcome

**accepted** — baseline, by definition.  `best.txt → iter_0000_baseline`.

## Lessons

- Construction-only heuristic leaves >390% mean gap to the MILP on `fast_eval`
  even with all three instances compliant — there is a lot of room for LS.
- The `fast_eval` score is dominated by the smallest instance because its
  MILP-incumbent denominator is tiny (3.0); a single LS pass that removes
  some delay on `triangle_R5` could move the score significantly.
- Heuristic wall-clock per instance is 0.01–0.02 s; the 20 s budget is
  effectively unbounded for this variant, so any LS portfolio has runway.
