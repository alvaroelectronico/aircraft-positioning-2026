# iter_0005_lns_worst_removal — alternating random and worst-removal destroy

## Hypothesis

iter_0003's LNS uses pure random destroy.  Standard LNS literature
(Shaw, Ropke-Pisinger) finds that **worst-removal** — pick the K most
costly elements and their neighbours — intensifies the search around
the cluster that's actually hurting the objective.  Adding it as an
alternating destroy mode (random / worst-removal round-robin) should
focus LNS effort on chain_R10's high-delay aircraft and break the
199.4 plateau.

## What changed

`autoresearch_heuristics/topology_heuristic_job.py`:

- Added `_destroy_random(assignment, k, rng)` — extracted from the
  inline destroy code.
- Added `_destroy_worst(sol, assignment, k, instance, rng)` — picks
  the K most-delayed aircraft, then expands with their blocking-arc
  neighbours (positions reachable from / to the picked aircraft's
  position), capped at 2K total.  Falls back to random when delays are
  all zero.
- LNS loop now alternates: even iterations use random, odd use
  worst-removal.

LOC delta: ~+55 lines (two helpers).

## Eval result

Mode: `fast_eval`  (3 instances, 20 s budget each)

| instance                          | obj_var | obj_milp |    gap |
| --------------------------------- | ------: | -------: | -----: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |
| scn_chain_tight_P5_R10_seed1      |  199.40 |   163.35 | +0.221 |
| scn_hub_tight_P5_R10_seed1        |  145.50 |   136.40 | +0.067 |

- **score**: **+0.0958** (identical to iter_0003).

Off-benchmark probe at 60 s budget:

| instance                          | iter_0003 60s | iter_0005 60s |    MILP |
| --------------------------------- | ------------: | ------------: | ------: |
| scn_full_tight_P5_R20_seed1       |       ~2083  |       1691.50 | 2533.10 |
| scn_triangle_tight_P5_R30_seed1   |       ~2593  |       2570.00 | 3208.85 |
| scn_triangle_tight_P5_R20_seed1   |       ~911   |        824.05 |  823.00 |
| scn_full_tight_P5_R10_seed1       |       —      |        341.55 |  180.35 |
| scn_triangle_loose_P5_R10_seed1   |       —      |         34.75 |   14.65 |

Worst-removal cuts the full_R20 result by ~19 % vs random-only LNS at
60 s, and shaves triangle_R20 from +11 % to barely +0.1 % over the
MILP incumbent.  But on fast_eval's three small instances the bound is
the same.

## Outcome

**rejected** — fast_eval score did not strictly improve.  Working copy
reverted to `iter_0003_lns_perturbation`.

## Lessons

- Chain_R10 is now confirmed to be the binding constraint on `fast_eval`
  progress: five distinct LS/LNS configurations all hit obj 199.40
  exactly.  This is almost certainly the Mode-A local optimum that any
  position-search heuristic can reach without Mode-B / Mode-C.
- Worst-removal LNS is **objectively useful** on R ≥ 20 (≈19 % obj
  reduction on full_R20 at 60 s vs random-only LNS) but the iteration
  metric can't see it.  Same recurring pattern as iter_0002: when fast_eval
  saturates, real improvements on the harder benchmark get rejected.
- Pivoting next: try **multi-strategy construction** — each of the
  n_starts replicates uses a different aircraft-placement order (heaviest,
  lightest, EDD, random, blocking-load DESC, total-duration ASC).  The
  current code hard-codes "heaviest first" for every start; the seed
  only randomises the RCL pick, not the greedy order.  More starting-point
  diversity is the cheapest unexplored axis.
