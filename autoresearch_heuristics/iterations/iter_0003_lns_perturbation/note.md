# iter_0003_lns_perturbation — destroy-and-rebuild perturbation loop after LS

## Hypothesis

LS portfolio (iter_0001) finishes in ~0.3 s but leaves 91% of the 20 s
per-instance budget idle.  Each multi-start is a single basin descent;
once LS converges, the construction's initial commitments are locked in.
A diversification mechanism that perturbs the incumbent and re-runs LS
should escape basins the 1-2-aircraft LS moves can't reach.  LNS-style
**destroy-and-rebuild** is the standard pattern: pop K aircraft, rebuild
their positions via the same GRASP scoring, run LS, accept on strict
improvement.

## What changed

`autoresearch_heuristics/topology_heuristic_job.py`:

- Refactored the GRASP construction out of `_solve_single` into
  `_construct(instance, params, rng, weights, blocking_load,
  partial_assignment=None)`.  Aircraft present in `partial_assignment`
  are kept fixed; the rest are placed heaviest-first via the existing
  candidate-scoring + biased-random RCL.
- `_solve_single` now does: initial `_construct` → `_local_search` →
  **LNS loop until budget exhausted**.  Each LNS iteration:
  1. Pick K aircraft uniformly at random from the incumbent assignment
     (K cycles through `R//4, R//3, R//2` to mix small and large kicks).
  2. Rebuild them via `_construct` with the rest fixed.
  3. Run `_local_search` from the new assignment.
  4. Accept the new incumbent iff its objective is strictly lower.
- Compliance is already gated inside `_local_search`, so no extra check
  is needed at the LNS-accept point.

LOC delta: ~+40 lines net (construction factored out, LNS loop added).

## Eval result

Mode: `fast_eval`  (3 instances, 20 s budget each)

| instance                          | obj_var | obj_milp |    gap | compliant |   t (s) |
| --------------------------------- | ------: | -------: | -----: | :-------: | ------: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |     Y     |   20.00 |
| scn_chain_tight_P5_R10_seed1      |  199.40 |   163.35 | +0.221 |     Y     |   20.00 |
| scn_hub_tight_P5_R10_seed1        |  145.50 |   136.40 | +0.067 |     Y     |   20.00 |

- **score (mean gap)**: **+0.0958**  (was +0.1256, **24% reduction**)
- **n_compliant**: 3 / 3
- **elapsed**: 60 s (each instance now uses its full 20 s budget on LNS)

Per-instance:

| instance         | iter_0001 |   iter_0003 |  Δ obj | new gap |
| ---------------- | --------: | ----------: | -----: | ------: |
| triangle_R5      |      3.00 |        3.00 |    0.0 |  +0.000 |
| chain_R10        |    199.40 |      199.40 |    0.0 |  +0.221 |
| hub_R10          |    157.70 |      145.50 |  −12.2 |  +0.067 |

## Outcome

**accepted** — score improved from +0.1256 to +0.0958 (Δ = −0.030).
`best.txt → iter_0003_lns_perturbation`.

## Lessons

- LNS is a genuine basin-escape mechanism for `hub_R10`: it found a
  better incumbent after the initial LS converged (12.2 obj units, all
  from delay reduction).
- `chain_R10` remains stubborn — neither the LS portfolio nor 20 s of
  random destroy-and-rebuild can dent it from 199.4.  The MILP gets to
  163.35 (already a 97% MIP gap), so even the MILP doesn't have a
  certified optimum; the heuristic may be near the basin floor that the
  Mode-A schedule allows.  Future iterations should investigate whether
  Mode-C exploitation (item #2 in `program.md`) opens any room here,
  since chain conflicts are exactly where mid-job rear insertion is most
  productive in the paper.
- `triangle_R5` is now solved-to-optimality every run; the iteration
  metric is dominated by chain_R10 (which barely moves) and hub_R10
  (which is responsive).  Further gains on `fast_eval` are likely to
  come from chain_R10 specifically.
- Per-instance wall-clock is now 20 s exactly — LNS happily consumes
  whatever budget is left.  This is the intended trade.
