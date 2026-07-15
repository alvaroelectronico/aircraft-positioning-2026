# iter_0007_mode_c_scan — Mode-C exploitation post-LS

## Hypothesis

`program.md` item #2: Mode-C exploitation could close chain_R10's
36-unit gap by absorbing rear-delay into front interruptible-job
extensions.  A single Mode-C event costs 2 × W^Mov + δ = 22 cost units,
so the operator should be productive whenever a single event saves
> 22 units of Mode-A delay — plausible on chain where per-aircraft
delays sit at 15-25 units.

## What changed

`autoresearch_heuristics/topology_heuristic_job.py`:

- `_rebuild_job` now accepts `extensions: {front_aid: {job_id: kappa}}`
  and `mode_c_skip: set[(rear_aid, front_aid)]`.  Extensions multiply
  job durations during layout (`+ kappa * delta`); mode_c_skip exempts
  the given rear-front pairs from Mode-A delay resolution.
  total_movements is derived as `2 * sum(kappa)`.
- `_resolve_rear_interactions` and `_resolve_front_interactions` now
  accept `mode_c_skip` and bypass conflict resolution for the listed
  pairs.
- Added `_mode_c_scan`: post-LS greedy scan that tries each
  `(rear, front, interruptible-job)` triple as a Mode-C event, rebuilds,
  and accepts the first improvement that passes the checker.  Called
  after the initial LS converges and after every LNS rebuild.

LOC delta: ~+90 lines (one new operator, two resolver signature changes,
rebuild extension support).

## Eval result

Mode: `fast_eval`  (3 instances, 20 s budget each)

| instance                          | obj_var | obj_milp |    gap | movements |
| --------------------------------- | ------: | -------: | -----: | --------: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |         0 |
| scn_chain_tight_P5_R10_seed1      |  199.40 |   163.35 | +0.221 |         0 |
| scn_hub_tight_P5_R10_seed1        |  145.50 |   136.40 | +0.067 |         0 |

- **score**: **+0.0958** (identical to iter_0003)
- **No Mode-C events accepted on any of the three instances.**

## Outcome

**rejected** — Mode-C scan didn't activate.  Working copy reverted to
`iter_0003_lns_perturbation`.

## Lessons

- A standalone probe (force a Mode-C event between an arbitrary
  blocking (R,F) pair with an interruptible front job) confirms the
  wiring works: the rebuild applies the extension (movs=2) and
  produces a longer schedule.  But the resulting solution is **infeasible**
  per `check_solution_jobs_v2`: the checker's RQ07 reclassifies every
  access (entry / exit) of every rear against every front and infers
  kappa from access-time-vs-job-interval geometry.  My greedy "1 event
  = 1 kappa" assumption doesn't survive that reclassification — a rear
  whose entry IS inside the extended interruptible job typically has
  its exit OUTSIDE the front's stay (Mode-A z+) **or** inside a
  *different* job of the front (could be non-interruptible →
  infeasible).  A correct Mode-C operator has to mirror the checker's
  per-access classification logic to know which jobs to extend and by
  how much — a substantial implementation.
- Even if the operator were correct, the economics don't favour Mode-C
  here: under the default weights (W^Mov=10, W^D=1, δ=2) each Mode-C
  event costs 22 units, plus the downstream cascade from extending a
  front's job by δ.  For these instances, where the MILP itself
  produces solutions with **0 movements**, the optimal policy is
  Mode-A.  So the heuristic's residual gap (e.g., chain_R10 199.4 vs
  MILP 163.35) is almost certainly a **Mode-A search-quality gap**,
  not a Mode-C-vs-Mode-A modelling gap.
- Practical implication: closing the remaining R=10 gaps on seed1
  needs either (a) a fundamentally different `_rebuild_job` that can
  introduce intentional idle time before a front to avoid a downstream
  conflict (essentially Mode-B in spirit, but as a Mode-A trick), or
  (b) much more aggressive search (3-opt, k-cycle position swaps, LNS
  with submilp repair).  Both are beyond the scope of a single
  autoresearch iteration.
- All Mode-C infrastructure (`extensions` + `mode_c_skip` in the
  rebuild, the two resolver signature changes) is **kept in this
  rejected snapshot** for posterity — if a future iteration wants to
  ship a checker-accurate Mode-C operator, the rebuild side is already
  done.
