# iter_0002_ls_intra_pos_extra — add intra-position insertion + non-adj swap + EDD repair

## Hypothesis

The aircraft sibling's `_light_local_search` has four intra-position operators
the job version lacks: (4) intra-position insertion, (5) non-adjacent
intra-position swap, (6) EDD/slack/delay-ratio repair, (7) delay-block
insertion.  Adding the first three to the LS portfolio should shrink the
residual gap on the harder fast_eval instances (chain_R10 +0.221,
hub_R10 +0.156) by exploring within-position reorderings that ops 1–3
can't reach.

## What changed

`autoresearch_heuristics/topology_heuristic_job.py`:

- Added two helpers: `_position_blocks(order, assignment)` returns
  `{position: [aids in scheduling order]}`; `_splice_block(order, ids, new_block)`
  replaces a same-position subsequence in place.
- Extended `_local_search` from 3 to 6 operators, all compliance-gated:
  * Op 4: pop each same-position aircraft and reinsert at every other slot.
  * Op 5: swap any non-adjacent same-position pair (op 3 covers adjacent).
  * Op 6: replace each position block with EDD (target_finish ASC),
    slack ASC, or delay-ratio DESC.  Delay-ratio uses per-aircraft delay
    from the current best solution.
- Restart-on-improvement is preserved: any accepted move re-starts from op 1.

LOC delta: roughly +90 lines (3 operators, 2 helpers).

## Eval result

Mode: `fast_eval`  (3 instances, 20 s budget each)

| instance                          | obj_var | obj_milp |    gap | compliant |  t (s) |
| --------------------------------- | ------: | -------: | -----: | :-------: | -----: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |     Y     |   0.03 |
| scn_chain_tight_P5_R10_seed1      |  199.40 |   163.35 | +0.221 |     Y     |   0.39 |
| scn_hub_tight_P5_R10_seed1        |  157.70 |   136.40 | +0.156 |     Y     |   0.32 |

- **score (mean gap)**: **+0.1256** (unchanged from iter_0001_ls_portfolio).
- **n_compliant**: 3 / 3
- **elapsed**: 0.75 s

Off-benchmark probe on larger instances (not used for acceptance):

| instance                          |  iter_0001 |   iter_0002 |    MILP60s | new gap vs MILP |
| --------------------------------- | ---------: | ----------: | ---------: | --------------: |
| scn_full_tight_P5_R20_seed1       |    2083.55 |     1817.80 |    2533.10 |           −28%  |
| scn_triangle_tight_P5_R30_seed1   |    2592.80 |     2529.80 |    3208.85 |           −21%  |
| scn_triangle_tight_P5_R20_seed1   |     911.15 |      873.15 |     823.00 |            +6%  |

So the new operators ARE doing real work — they just have no leverage on
the three small instances that constitute `fast_eval`.

## Outcome

**rejected** — score did not strictly improve on `fast_eval`
(+0.1256 == +0.1256), so per the loop protocol the working copy is
reverted to `iter_0001_ls_portfolio`.

## Lessons

- The current `fast_eval` set is too small to reward intra-position
  reordering: on R≤10 with at most 2 aircraft per position, ops 4–6
  collapse to no-ops or are dominated by ops 1–3.  The operators are
  valuable but their value is invisible to the iteration metric.
- For future iterations, the intra-position operators should be
  resurrected as soon as `fast_eval` includes at least one R=20
  instance — they shrink the R=20 full gap from −18% to −28% vs MILP
  and the R=30 gap from −19% to −21%.
- Action item for the user: consider extending `benchmark.json[fast_eval]`
  with `scn_full_tight_P5_R20_seed1` or `scn_triangle_tight_P5_R20_seed1`
  to give the iteration metric visibility into the regime where the gap
  to MILP is largest.
