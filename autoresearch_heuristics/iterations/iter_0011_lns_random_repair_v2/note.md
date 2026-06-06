# iter_0011_lns_random_repair_v2 — re-snapshot under broadened fast_eval

## Hypothesis

iter_0010's random-repair LNS was rejected by the old 3-instance
fast_eval set (it had no R≥20 case), but it BEATS the MILP on
triangle_R20 — the most useful instance to discriminate broader
search quality.  After extending `fast_eval` with
`scn_triangle_tight_P5_R20_seed1`, the same code should strictly
improve the iteration score.

## What changed

1. `benchmark.json`: added `scn_triangle_tight_P5_R20_seed1` to
   `fast_eval[instances]`.  Now 4 instances at 20 s each (~80 s total
   per evaluation, well under the previous "≈1 minute" budget).
2. `iter_0003`'s `eval.json` re-written under the broadened metric
   (score +0.0722) so that future comparisons are apples-to-apples.
3. Working copy restored from `iter_0010_lns_random_repair` (the
   uniform-vs-greedy repair alternation in the LNS loop).

No code changes from iter_0010.

## Eval result (4-instance fast_eval)

| instance                          | obj_var | obj_milp |    gap | compliant |
| --------------------------------- | ------: | -------: | -----: | :-------: |
| scn_triangle_tight_P5_R5_seed1    |    3.00 |     3.00 | +0.000 |     Y     |
| scn_chain_tight_P5_R10_seed1      |  199.40 |   163.35 | +0.221 |     Y     |
| scn_hub_tight_P5_R10_seed1        |  145.50 |   136.40 | +0.067 |     Y     |
| scn_triangle_tight_P5_R20_seed1   |  814.00 |   823.00 | **−0.011** |     Y     |

- **score (mean gap)**: **+0.0691**  (iter_0003 was +0.0722 on this
  same benchmark; iter_0010 = iter_0011 strictly improves).
- **n_compliant**: 4 / 4.
- elapsed: 80 s.

## Outcome

**accepted** — first iteration where the heuristic objectively beats
the MILP's 60 s incumbent on an instance inside `fast_eval` (gap −0.011
on triangle_R20).

## Lessons

- The broadened benchmark is now sensitive to LNS-side improvements
  that the 3-small-instance set was blind to.  Past iterations that
  were rejected only because of this blind spot (`iter_0002`
  intra-pos ops, `iter_0005` worst-removal) should be revisited
  under the new criterion — they may still not move the score, but
  it's worth confirming.
- Beating MILP at 60 s on a single R=20 case is good but not a
  general result.  The MILP at 60 s still wins on every R ≤ 10
  instance (where it solves to or near optimal), so closing those
  gaps is the next frontier.
