# iter_0001_ls_portfolio — add single-move + 2-opt swap + intra-position reorder

## Hypothesis

The construction phase is a forward greedy that only places each aircraft
once and never re-evaluates the assignment afterwards.  Item #1 of
`program.md`'s prioritised list predicts the biggest first jump comes from
adding the three operators the aircraft-level sibling has and this version
lacks: **single-move**, **2-opt swap**, and **intra-position adjacent swap**
in the scheduling sequence.  All three only touch the position assignment
$\pi$ (or the within-position order) and let `_rebuild_job` handle timing,
so the implementation stays small.

## What changed

`autoresearch_heuristics/topology_heuristic_job.py`:

- Extended `_rebuild_job(assignment, instance, params, order=None)` with
  an optional caller-supplied scheduling sequence.  When `order` is
  provided, aircraft are scheduled in that order instead of the default
  `earliest_start` sort.  Aircraft missing from `order` are appended.
- Added `_default_schedule_order(assignment, instance)` — the implicit
  sequence used by the original rebuild.
- Added `_local_search(assignment, order, instance, params, budget_s)`:
  first-improvement portfolio with **restart-on-improvement**, three
  operators applied in cheapest-first order: single-move, 2-opt swap,
  intra-position adjacent swap.  On any acceptance the dispatcher
  restarts from operator 1.
- Wired LS into `_solve_single`: construction runs first, then LS spends
  the remaining `budget_s`.  Each multi-start replicate now does
  construction + LS.
- Added a **compliance gate** in the LS acceptance criterion.  The
  module imports `check_solution_jobs_v2.check_solution` at load time
  (the eval harness puts its directory on `sys.path`).  Every candidate
  improvement is rebuilt **and** checked; a move is accepted only when
  the objective strictly improves *and* the rebuilt solution is
  compliant.  Without this gate the first eval found large objective
  improvements (e.g. obj 294.8 → 147.0 on chain_R10) but the resulting
  positions violated constraints the Mode-A rebuild can't fully resolve
  on its own.

LOC delta: roughly +130 lines (one new function, one helper, one optional
parameter on the rebuild).

## Eval result

Mode: `fast_eval`  (3 instances, 20 s budget each)

| instance                          | obj_var | obj_milp |    gap | compliant |  t (s) |
| --------------------------------- | ------: | -------: | -----: | :-------: | -----: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |     Y     |   0.03 |
| scn_chain_tight_P5_R10_seed1      |  199.40 |   163.35 | +0.221 |     Y     |   0.34 |
| scn_hub_tight_P5_R10_seed1        |  157.70 |   136.40 | +0.156 |     Y     |   0.28 |

- **score (mean gap)**: **+0.1256**  (baseline was +3.9146, **97% reduction**)
- **n_compliant**: 3 / 3
- **elapsed**: 0.66 s (well under the 60 s budget)

Per-instance evolution vs baseline:

| instance         | baseline obj | new obj | abs improvement | gap reduction |
| ---------------- | -----------: | ------: | --------------: | ------------: |
| triangle_R5      |        35.05 |    3.00 |          −91.4% |   +10.683 → 0 |
| chain_R10        |       294.80 |  199.40 |          −32.4% | +0.805 → +0.221 |
| hub_R10          |       171.30 |  157.70 |           −7.9% | +0.256 → +0.156 |

Triangle now matches the MILP optimum exactly.  Chain and hub remain above
the MILP incumbent but the gap is dramatically smaller.

## Outcome

**accepted** — score improved from +3.9146 to +0.1256 (Δ = −3.789).
`best.txt → iter_0001_ls_portfolio`.

## Lessons

- The compliance gate is **essential**: without it the 2-opt swap found
  large objective drops on chain_R10 (obj 294.8 → 147.0) and triangle_R5
  (obj 35.0 → 3.0) but both produced infeasible solutions.  The Mode-A
  rebuild's `_resolve_*` helpers do not enforce every checker constraint;
  any LS layer above it must verify with the canonical checker.
- Construction + LS still finishes in well under 1 s per instance — the
  20 s `fast_eval` budget is essentially unbounded for this configuration,
  so subsequent operators (Mode-C exploitation, smarter cost proxy) have
  plenty of runway.
- Restart-on-improvement is doing real work: chain and hub both spent
  most of their LS time after a successful 2-opt move re-triggered the
  single-move pass — see the 0.28–0.34 s solve times vs 0.03 s for
  triangle which converged immediately.
